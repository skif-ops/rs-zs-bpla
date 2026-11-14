package ru.dioneya.commissioning.core.ble

/**
 * Framing of values longer than one ATT packet.
 *
 * Every frame:   [seq:1][flags:1] [total_len:2 BE, first frame only] [data...]
 *   seq   = frame counter 0..255, wraps; the receiver requires consecutive values
 *   flags = bit0 FIRST, bit1 LAST (a single-frame value has both)
 * The total length lets the receiver allocate once and reject truncated or
 * over-long values; a value may be at most [MAX_VALUE_BYTES].
 */
object LongValueFraming {
    const val HEADER_BYTES = 2
    const val FIRST_EXTRA_BYTES = 2
    const val FLAG_FIRST = 0x01
    const val FLAG_LAST = 0x02
    const val MAX_VALUE_BYTES = 4096

    /** Splits [value] into frames for an ATT payload of [attPayload] bytes (MTU - 3). */
    fun split(value: ByteArray, attPayload: Int): List<ByteArray> {
        require(attPayload >= HEADER_BYTES + FIRST_EXTRA_BYTES + 1) { "ATT payload too small" }
        require(value.size <= MAX_VALUE_BYTES) { "value too long" }
        val frames = ArrayList<ByteArray>()
        var pos = 0
        var seq = 0
        do {
            val first = pos == 0
            val room = attPayload - HEADER_BYTES - (if (first) FIRST_EXTRA_BYTES else 0)
            val n = minOf(room, value.size - pos)
            val last = pos + n >= value.size
            val frame = ByteArray(HEADER_BYTES + (if (first) FIRST_EXTRA_BYTES else 0) + n)
            frame[0] = seq.toByte()
            frame[1] = ((if (first) FLAG_FIRST else 0) or (if (last) FLAG_LAST else 0)).toByte()
            var o = HEADER_BYTES
            if (first) {
                frame[o++] = (value.size ushr 8).toByte()
                frame[o++] = value.size.toByte()
            }
            System.arraycopy(value, pos, frame, o, n)
            frames.add(frame)
            pos += n
            seq = (seq + 1) and 0xFF
        } while (pos < value.size)
        return frames
    }

    /** Incremental reassembler; feed frames in order, [complete] tells when the value is whole. */
    class Reassembler {
        private var buffer: ByteArray? = null
        private var filled = 0
        private var expectedSeq = 0
        var complete: Boolean = false
            private set
        val value: ByteArray
            get() {
                check(complete) { "value incomplete" }
                return buffer!!.copyOf(filled)
            }

        fun reset() { buffer = null; filled = 0; expectedSeq = 0; complete = false }

        /** Returns false (and resets) on any framing error so the caller can restart the read. */
        fun feed(frame: ByteArray): Boolean {
            if (complete || frame.size < HEADER_BYTES) { reset(); return false }
            val seq = frame[0].toInt() and 0xFF
            val flags = frame[1].toInt() and 0xFF
            val first = flags and FLAG_FIRST != 0
            val last = flags and FLAG_LAST != 0
            var o = HEADER_BYTES
            if (first) {
                if (buffer != null || seq != 0 || frame.size < HEADER_BYTES + FIRST_EXTRA_BYTES) { reset(); return false }
                val total = ((frame[2].toInt() and 0xFF) shl 8) or (frame[3].toInt() and 0xFF)
                if (total > MAX_VALUE_BYTES) { reset(); return false }
                buffer = ByteArray(total)
                o += FIRST_EXTRA_BYTES
            } else if (buffer == null || seq != expectedSeq) {
                reset(); return false
            }
            val n = frame.size - o
            val buf = buffer!!
            if (filled + n > buf.size) { reset(); return false }
            System.arraycopy(frame, o, buf, filled, n)
            filled += n
            expectedSeq = (seq + 1) and 0xFF
            if (last) {
                if (filled != buf.size) { reset(); return false }
                complete = true
            }
            return true
        }
    }
}

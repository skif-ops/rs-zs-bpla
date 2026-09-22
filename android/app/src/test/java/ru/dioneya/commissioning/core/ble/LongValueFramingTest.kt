package ru.dioneya.commissioning.core.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LongValueFramingTest {
    private fun roundTrip(size: Int, att: Int) {
        val value = ByteArray(size) { (it * 7 + 3).toByte() }
        val frames = LongValueFraming.split(value, att)
        val r = LongValueFraming.Reassembler()
        for (f in frames) { assertTrue(f.size <= att); assertTrue(r.feed(f)) }
        assertTrue(r.complete)
        assertArrayEquals(value, r.value)
    }

    @Test fun singleFrameAndMultiFrameValuesRoundTrip() {
        roundTrip(0, 244); roundTrip(1, 244); roundTrip(240, 244); roundTrip(241, 244); roundTrip(281, 244)
        roundTrip(1000, 244); roundTrip(4096, 244); roundTrip(4096, 20); roundTrip(300, 5)
    }

    @Test fun frameLayoutForMtu247() {
        val value = ByteArray(300) { it.toByte() }
        val frames = LongValueFraming.split(value, 244)
        assertEquals(2, frames.size)
        assertEquals(244, frames[0].size)                       // 2 header + 2 length + 240 data
        assertEquals(0, frames[0][0].toInt()); assertEquals(LongValueFraming.FLAG_FIRST, frames[0][1].toInt())
        assertEquals(300, ((frames[0][2].toInt() and 0xFF) shl 8) or (frames[0][3].toInt() and 0xFF))
        assertEquals(1, frames[1][0].toInt()); assertEquals(LongValueFraming.FLAG_LAST, frames[1][1].toInt())
        assertEquals(2 + 60, frames[1].size)
    }

    @Test fun reassemblerRejectsOutOfOrderTruncatedAndOversized() {
        val value = ByteArray(700) { it.toByte() }
        val frames = LongValueFraming.split(value, 244)
        val r = LongValueFraming.Reassembler()
        assertTrue(r.feed(frames[0]))
        assertFalse(r.feed(frames[2]))                          // sequence gap resets
        assertFalse(r.feed(frames[1]))                          // not FIRST after reset
        assertTrue(r.feed(frames[0])); assertTrue(r.feed(frames[1])); assertTrue(r.feed(frames[2])); assertTrue(r.complete)
        val truncated = frames[2].copyOf(frames[2].size - 1)
        val r2 = LongValueFraming.Reassembler()
        assertTrue(r2.feed(frames[0])); assertTrue(r2.feed(frames[1])); assertFalse(r2.feed(truncated))
        val huge = byteArrayOf(0, LongValueFraming.FLAG_FIRST.toByte(), 0x20, 0x00, 1)
        assertFalse(LongValueFraming.Reassembler().feed(huge))  // 8192 > MAX_VALUE_BYTES
        assertFalse(LongValueFraming.Reassembler().feed(byteArrayOf(0)))
    }

    @Test fun sequenceWrapsAfter256Frames() {
        val value = ByteArray(4096)
        val frames = LongValueFraming.split(value, 16)            // 12 data bytes per frame -> 342 frames
        assertTrue(frames.size > 256)
        assertEquals(0, frames[256][0].toInt())
        val r = LongValueFraming.Reassembler()
        for (f in frames) assertTrue(r.feed(f))
        assertTrue(r.complete)
    }
}

package ru.dioneya.commissioning.core.position

import ru.dioneya.commissioning.core.CoordinateSource
import ru.dioneya.commissioning.core.InstallationCommissioningOperation
import ru.dioneya.commissioning.core.InstallationCommissioningReadback
import ru.dioneya.commissioning.core.InstallationCommissioningRequest
import ru.dioneya.commissioning.core.InstallationPosition
import ru.dioneya.commissioning.core.PositionTrustPolicy
import java.io.ByteArrayOutputStream

/**
 * Wire format of the `installation_position` characteristic (ICD §3.1, addendum B.6):
 * canonical CBOR maps with integer keys, signed integers for coordinates.
 *
 * Write (phone -> station), keys 1..14:
 *   1 operation (0 initial, 1 recommission), 2 lat_e7, 3 lon_e7, 4 alt_dm, 5 accuracy_m,
 *   6 source (0 manual, 1 phone, 2 station gnss, 3 surveyed), 7 version, 8 locked,
 *   9 commissioned_time_us, 10..14 policy (warning m, suspect m, gross jump m, warning fixes, suspect fixes)
 * Read-back (station -> phone): keys 2..14 as above plus
 *   15 storage_generation, 16 commissioning_hash (32 bytes, SHA-256 of the canonical record), 17 audit_committed.
 * An empty map (0xa0) read back means "no installation position stored yet".
 */
object InstallationPositionCodec {
    const val KEY_OPERATION = 1L
    const val KEY_LAT = 2L
    const val KEY_LON = 3L
    const val KEY_ALT = 4L
    const val KEY_ACCURACY = 5L
    const val KEY_SOURCE = 6L
    const val KEY_VERSION = 7L
    const val KEY_LOCKED = 8L
    const val KEY_TIME = 9L
    const val KEY_WARN_M = 10L
    const val KEY_SUSPECT_M = 11L
    const val KEY_GROSS_M = 12L
    const val KEY_WARN_FIXES = 13L
    const val KEY_SUSPECT_FIXES = 14L
    const val KEY_GENERATION = 15L
    const val KEY_HASH = 16L
    const val KEY_AUDIT = 17L

    fun sourceId(source: CoordinateSource): Long = when (source) {
        CoordinateSource.MANUAL -> 0; CoordinateSource.PHONE_LOCATION -> 1; CoordinateSource.STATION_GNSS -> 2; CoordinateSource.SURVEYED -> 3
    }
    private fun sourceOf(id: Long): CoordinateSource? = CoordinateSource.entries.firstOrNull { sourceId(it) == id }

    fun encodeRequest(r: InstallationCommissioningRequest): ByteArray {
        val w = Writer()
        w.map(14)
        w.uint(KEY_OPERATION); w.uint(if (r.operation == InstallationCommissioningOperation.INITIAL) 0 else 1)
        w.uint(KEY_LAT); w.int(r.position.latE7.toLong())
        w.uint(KEY_LON); w.int(r.position.lonE7.toLong())
        w.uint(KEY_ALT); w.int(r.position.altDm.toLong())
        w.uint(KEY_ACCURACY); w.uint(r.position.accuracyM.toLong())
        w.uint(KEY_SOURCE); w.uint(sourceId(r.position.source))
        w.uint(KEY_VERSION); w.uint(r.position.version)
        w.uint(KEY_LOCKED); w.bool(r.position.locked)
        w.uint(KEY_TIME); w.uint(r.commissionedTimeUs)
        w.uint(KEY_WARN_M); w.uint(r.policy.warningDistanceM.toLong())
        w.uint(KEY_SUSPECT_M); w.uint(r.policy.suspectDistanceM.toLong())
        w.uint(KEY_GROSS_M); w.uint(r.policy.grossJumpDistanceM.toLong())
        w.uint(KEY_WARN_FIXES); w.uint(r.policy.warningConsecutiveFixes.toLong())
        w.uint(KEY_SUSPECT_FIXES); w.uint(r.policy.suspectConsecutiveFixes.toLong())
        return w.toByteArray()
    }

    /** Station-side helper (tests, emulator): the read-back record for a stored request. */
    fun encodeReadback(rb: InstallationCommissioningReadback): ByteArray {
        val w = Writer()
        w.map(16)
        w.uint(KEY_LAT); w.int(rb.position.latE7.toLong())
        w.uint(KEY_LON); w.int(rb.position.lonE7.toLong())
        w.uint(KEY_ALT); w.int(rb.position.altDm.toLong())
        w.uint(KEY_ACCURACY); w.uint(rb.position.accuracyM.toLong())
        w.uint(KEY_SOURCE); w.uint(sourceId(rb.position.source))
        w.uint(KEY_VERSION); w.uint(rb.position.version)
        w.uint(KEY_LOCKED); w.bool(rb.position.locked)
        w.uint(KEY_TIME); w.uint(rb.commissionedTimeUs)
        w.uint(KEY_WARN_M); w.uint(rb.policy.warningDistanceM.toLong())
        w.uint(KEY_SUSPECT_M); w.uint(rb.policy.suspectDistanceM.toLong())
        w.uint(KEY_GROSS_M); w.uint(rb.policy.grossJumpDistanceM.toLong())
        w.uint(KEY_WARN_FIXES); w.uint(rb.policy.warningConsecutiveFixes.toLong())
        w.uint(KEY_SUSPECT_FIXES); w.uint(rb.policy.suspectConsecutiveFixes.toLong())
        w.uint(KEY_GENERATION); w.uint(rb.storageGeneration)
        w.uint(KEY_HASH); w.bytes(hexToBytes(rb.commissioningHashHex))
        w.uint(KEY_AUDIT); w.bool(rb.auditCommitted)
        return w.toByteArray()
    }

    /** Result of decoding a read-back: a record, "empty" (nothing stored), or null on malformed input. */
    sealed class Readback {
        object Empty : Readback()
        data class Stored(val record: InstallationCommissioningReadback) : Readback()
    }

    fun decodeReadback(bytes: ByteArray): Readback? = try {
        val r = Reader(bytes)
        val n = r.mapHeader()
        if (n == 0) { r.requireEnd(); Readback.Empty } else {
            if (n != 16) throw IllegalArgumentException("key count")
            val v = HashMap<Long, Any>()
            var last = -1L
            repeat(n) {
                val k = r.uint()
                if (k <= last) throw IllegalArgumentException("order")
                last = k
                v[k] = when (k) {
                    KEY_LAT, KEY_LON, KEY_ALT -> r.int()
                    KEY_LOCKED, KEY_AUDIT -> r.bool()
                    KEY_HASH -> r.bytes()
                    KEY_ACCURACY, KEY_SOURCE, KEY_VERSION, KEY_TIME, KEY_WARN_M, KEY_SUSPECT_M, KEY_GROSS_M, KEY_WARN_FIXES, KEY_SUSPECT_FIXES, KEY_GENERATION -> r.uint()
                    else -> throw IllegalArgumentException("key $k")
                }
            }
            r.requireEnd()
            fun l(k: Long) = v[k] as Long
            val hash = v[KEY_HASH] as ByteArray
            if (hash.size != 32) throw IllegalArgumentException("hash")
            Readback.Stored(InstallationCommissioningReadback(
                position = InstallationPosition(
                    latE7 = l(KEY_LAT).toIntExact(), lonE7 = l(KEY_LON).toIntExact(), altDm = l(KEY_ALT).toIntExact(),
                    accuracyM = l(KEY_ACCURACY).toIntExact(), source = sourceOf(l(KEY_SOURCE)) ?: throw IllegalArgumentException("source"),
                    version = l(KEY_VERSION), locked = v[KEY_LOCKED] as Boolean,
                ),
                policy = PositionTrustPolicy(l(KEY_WARN_M).toIntExact(), l(KEY_SUSPECT_M).toIntExact(), l(KEY_GROSS_M).toIntExact(), l(KEY_WARN_FIXES).toIntExact(), l(KEY_SUSPECT_FIXES).toIntExact()),
                commissionedTimeUs = l(KEY_TIME),
                storageGeneration = l(KEY_GENERATION),
                commissioningHashHex = hash.joinToString("") { "%02x".format(it) },
                auditCommitted = v[KEY_AUDIT] as Boolean,
            ))
        }
    } catch (e: Exception) {
        null
    }

    private fun Long.toIntExact(): Int { require(this in Int.MIN_VALUE..Int.MAX_VALUE) { "int32" }; return toInt() }

    fun hexToBytes(hex: String): ByteArray {
        require(hex.length % 2 == 0)
        return ByteArray(hex.length / 2) { i -> hex.substring(2 * i, 2 * i + 2).toInt(16).toByte() }
    }

    /** Canonical CBOR (RFC 8949 §4.2.1) with the subset needed here: uint, negative int, bool, bytes, map. */
    class Writer {
        private val out = ByteArrayOutputStream()
        fun map(count: Int) = head(5, count.toLong())
        fun uint(v: Long) { require(v >= 0); head(0, v) }
        fun int(v: Long) = if (v >= 0) head(0, v) else head(1, -1 - v)
        fun bool(v: Boolean) = out.write(if (v) 0xf5 else 0xf4)
        fun bytes(b: ByteArray) { head(2, b.size.toLong()); out.write(b) }
        fun toByteArray(): ByteArray = out.toByteArray()
        private fun head(major: Int, v: Long) {
            val m = major shl 5
            when {
                v < 24 -> out.write(m or v.toInt())
                v < 0x100 -> { out.write(m or 24); out.write(v.toInt()) }
                v < 0x10000 -> { out.write(m or 25); out.write((v shr 8).toInt()); out.write(v.toInt()) }
                v < 0x100000000L -> { out.write(m or 26); for (s in intArrayOf(24, 16, 8, 0)) out.write((v shr s).toInt() and 0xff) }
                else -> { out.write(m or 27); for (s in intArrayOf(56, 48, 40, 32, 24, 16, 8, 0)) out.write((v shr s).toInt() and 0xff) }
            }
        }
    }

    class Reader(private val data: ByteArray) {
        private var pos = 0
        fun mapHeader(): Int = head(5).toInt()
        fun uint(): Long = head(0)
        fun int(): Long { val ib = peek(); return if (ib ushr 5 == 1) -1 - head(1) else head(0) }
        fun bool(): Boolean { val b = next(); return when (b) { 0xf5 -> true; 0xf4 -> false; else -> throw IllegalArgumentException("bool") } }
        fun bytes(): ByteArray { val n = head(2).toInt(); require(pos + n <= data.size); return data.copyOfRange(pos, pos + n).also { pos += n } }
        fun requireEnd() { if (pos != data.size) throw IllegalArgumentException("trailing bytes") }
        private fun peek(): Int { require(pos < data.size) { "truncated" }; return data[pos].toInt() and 0xff }
        private fun next(): Int { val b = peek(); pos++; return b }
        private fun head(expectMajor: Int): Long {
            val ib = next()
            require(ib ushr 5 == expectMajor) { "major type" }
            val ai = ib and 0x1f
            val v: Long = when {
                ai < 24 -> ai.toLong()
                ai == 24 -> next().toLong().also { require(it >= 24) { "not canonical" } }
                ai == 25 -> ((next() shl 8) or next()).toLong().also { require(it >= 0x100) { "not canonical" } }
                ai == 26 -> { var x = 0L; repeat(4) { x = (x shl 8) or next().toLong() }; require(x >= 0x10000) { "not canonical" }; x }
                ai == 27 -> { var x = 0L; repeat(8) { x = (x shl 8) or next().toLong() }; require(x < 0 || x >= 0x100000000L) { "not canonical" }; x }
                else -> throw IllegalArgumentException("indefinite length")
            }
            return v
        }
    }
}

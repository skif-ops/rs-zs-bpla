package ru.dioneya.commissioning.core.scan

import ru.dioneya.commissioning.core.CanonicalCbor
import ru.dioneya.commissioning.core.LoRaRegion
import ru.dioneya.commissioning.core.StationIdentity

/**
 * CBOR of the `identity` characteristic (addendum B.4): canonical map with
 * integer keys 1 serial(text), 2 station_id(uint), 3 hardware_revision(text),
 * 4 firmware_version(text), 5 bootloader_version(text), 6 region(uint, 1 = RU868, 2 = EU868).
 */
object IdentityCodec {
    const val KEY_SERIAL = 1L
    const val KEY_STATION_ID = 2L
    const val KEY_HARDWARE_REVISION = 3L
    const val KEY_FIRMWARE_VERSION = 4L
    const val KEY_BOOTLOADER_VERSION = 5L
    const val KEY_REGION = 6L

    fun encode(identity: StationIdentity): ByteArray {
        val w = CanonicalCbor.Writer()
        w.map(6)
        w.uint(KEY_SERIAL); w.text(identity.serial)
        w.uint(KEY_STATION_ID); w.uint(identity.stationId)
        w.uint(KEY_HARDWARE_REVISION); w.text(identity.hardwareRevision)
        w.uint(KEY_FIRMWARE_VERSION); w.text(identity.firmwareVersion)
        w.uint(KEY_BOOTLOADER_VERSION); w.text(identity.bootloaderVersion)
        w.uint(KEY_REGION); w.uint(if (identity.region == LoRaRegion.RU868) 1 else 2)
        return w.toByteArray()
    }

    /** Null on any malformed input (wrong keys, order, types, trailing bytes). */
    fun decode(bytes: ByteArray): StationIdentity? = try {
        val r = CanonicalCbor.Reader(bytes)
        val n = r.mapHeader()
        if (n != 6) throw IllegalArgumentException("key count")
        var serial: String? = null; var id: Long? = null; var hw: String? = null; var fw: String? = null; var bl: String? = null; var region: Long? = null
        var last = -1L
        repeat(n) {
            val k = r.uint()
            if (k <= last) throw IllegalArgumentException("order")
            last = k
            when (k) {
                KEY_SERIAL -> serial = r.text()
                KEY_STATION_ID -> id = r.uint()
                KEY_HARDWARE_REVISION -> hw = r.text()
                KEY_FIRMWARE_VERSION -> fw = r.text()
                KEY_BOOTLOADER_VERSION -> bl = r.text()
                KEY_REGION -> region = r.uint()
                else -> throw IllegalArgumentException("key $k")
            }
        }
        r.requireEnd()
        val reg = when (region) { 1L -> LoRaRegion.RU868; 2L -> LoRaRegion.EU868; else -> throw IllegalArgumentException("region") }
        StationIdentity(serial!!, id!!, hw!!, fw!!, bl!!, reg)
    } catch (e: Exception) {
        null
    }
}

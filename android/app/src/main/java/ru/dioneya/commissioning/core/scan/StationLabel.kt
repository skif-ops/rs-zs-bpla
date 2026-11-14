package ru.dioneya.commissioning.core.scan

/**
 * Enclosure label QR payload (protocols/STATION_LABEL_QR_v0_1.md), produced by
 * `muhoed-pki label-qr` and scanned in the station picker:
 *
 *     DIO1;S=<serial>;ID=<station_id>;T=<tenant>;K=<pairing secret base32>;C=<crc16 hex>
 *
 * CRC-16/CCITT-FALSE over everything before ";C=".  The pairing secret is kept
 * only for the current session (never persisted by the app).
 */
data class StationLabel(val serial: String, val stationId: Long, val tenant: String, val pairingSecretB32: String) {

    fun encode(): String {
        val body = "$VERSION_TAG;S=$serial;ID=$stationId;T=$tenant;K=$pairingSecretB32"
        return body + ";C=" + "%04X".format(crc16Ccitt(body.toByteArray(Charsets.US_ASCII)))
    }

    /** 16 secret bytes decoded from base32 (no padding). */
    fun pairingSecretBytes(): ByteArray = base32Decode(pairingSecretB32)

    /**
     * BLE pairing passkey (ICD addendum B.7): the station fixes its LESC passkey to
     * BE32(SHA-256("DIO-PAIR-V1" || secret)[0..3]) mod 1_000_000; the installer types this
     * six-digit number into the system pairing dialog.
     */
    fun pairingPasskey(): String {
        val md = java.security.MessageDigest.getInstance("SHA-256")
        md.update("DIO-PAIR-V1".toByteArray(Charsets.US_ASCII))
        val d = md.digest(pairingSecretBytes())
        val v = ((d[0].toLong() and 0xff) shl 24) or ((d[1].toLong() and 0xff) shl 16) or ((d[2].toLong() and 0xff) shl 8) or (d[3].toLong() and 0xff)
        return "%06d".format(v % 1_000_000L)
    }

    companion object {
        const val VERSION_TAG = "DIO1"
        private val SERIAL = Regex("DIO-EVT-(00[1-9]|0[1-3][0-9]|040|B01)")
        private val TENANT = Regex("[A-Za-z0-9._-]{1,16}")
        private val SECRET = Regex("[A-Z2-7]{26}")
        private const val B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

        fun crc16Ccitt(data: ByteArray): Int {
            var crc = 0xFFFF
            for (b in data) {
                crc = crc xor ((b.toInt() and 0xFF) shl 8)
                repeat(8) { crc = if (crc and 0x8000 != 0) ((crc shl 1) xor 0x1021) and 0xFFFF else (crc shl 1) and 0xFFFF }
            }
            return crc
        }

        fun stationIdForSerial(serial: String): Long = if (serial == "DIO-EVT-B01") 901 else serial.substring(8).toLong()

        /** Null when the text is not a valid, checksum-correct pilot label. */
        fun decode(text: String): StationLabel? {
            val t = text.trim()
            val i = t.lastIndexOf(";C=")
            if (i < 0) return null
            val body = t.substring(0, i)
            val crcHex = t.substring(i + 3)
            if (!crcHex.matches(Regex("[0-9A-Fa-f]{4}")) || !body.all { it.code in 32..126 }) return null
            if (crcHex.toInt(16) != crc16Ccitt(body.toByteArray(Charsets.US_ASCII))) return null
            val parts = body.split(';')
            if (parts.size != 5 || parts[0] != VERSION_TAG) return null
            val fields = HashMap<String, String>()
            for (p in parts.drop(1)) {
                val eq = p.indexOf('=')
                if (eq <= 0) return null
                fields[p.substring(0, eq)] = p.substring(eq + 1)
            }
            if (fields.keys != setOf("S", "ID", "T", "K")) return null
            val serial = fields.getValue("S")
            if (!SERIAL.matches(serial)) return null
            val id = fields.getValue("ID").toLongOrNull() ?: return null
            if (id != stationIdForSerial(serial)) return null
            val tenant = fields.getValue("T"); val secret = fields.getValue("K")
            if (!TENANT.matches(tenant) || !SECRET.matches(secret)) return null
            return StationLabel(serial, id, tenant, secret)
        }

        fun base32Decode(s: String): ByteArray {
            val out = java.io.ByteArrayOutputStream()
            var buffer = 0; var bits = 0
            for (ch in s) {
                val v = B32.indexOf(ch)
                require(v >= 0) { "base32" }
                buffer = (buffer shl 5) or v; bits += 5
                if (bits >= 8) { out.write((buffer shr (bits - 8)) and 0xFF); bits -= 8 }
            }
            return out.toByteArray()
        }
    }
}

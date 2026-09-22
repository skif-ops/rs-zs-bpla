package ru.dioneya.commissioning.core.profile

import ru.dioneya.commissioning.core.SimSlot
import ru.dioneya.commissioning.core.scan.StationLabel
import ru.dioneya.commissioning.core.server.ServerScreenController

/**
 * Server profile: what the "Сервер" screen needs identically for every station.
 * Public pinning data only (no secrets).
 *
 * QR payload (printed by `muhoed-pki server-qr`, protocols/STATION_LABEL_QR_v0_1.md §6):
 *
 *     DIOS1;H=<host[:port]>;P=<https_port>;CA=<ca_reference>;F=<sha256 hex64>;T=<topic_prefix>;C=<crc16>
 *
 * The app persists the profile as this same text plus local extras (APNs, preferred SIM)
 * so the stored form is validated by the same checksum on load.
 */
data class ServerProfile(
    val host: String,
    val mqttPort: Int,
    val httpsPort: Int,
    val caReference: String,
    val fingerprintHex: String,
    val topicPrefix: String = "zs/v1",
    val apn1: String = "",
    val apn2: String = "",
    val preferredSim: SimSlot = SimSlot.SIM1,
) {
    /** QR / stored core payload (without the local extras). */
    fun encode(): String {
        require(HOST.matches(host) && mqttPort in 1..65535 && httpsPort in 0..65535 && CA.matches(caReference) && FP.matches(fingerprintHex) && PREFIX.matches(topicPrefix)) { "invalid profile" }
        val body = "$VERSION_TAG;H=$host:$mqttPort;P=$httpsPort;CA=$caReference;F=$fingerprintHex;T=$topicPrefix"
        return body + ";C=" + "%04X".format(StationLabel.crc16Ccitt(body.toByteArray(Charsets.US_ASCII)))
    }

    fun toFields(base: ServerScreenController.Fields = ServerScreenController.Fields()): ServerScreenController.Fields = base.copy(
        hostPort = "$host:$mqttPort", httpsPort = httpsPort.toString(), caReference = caReference, fingerprintHex = fingerprintHex,
        topicPrefix = topicPrefix, apn1 = apn1, apn2 = apn2, preferredSim = preferredSim,
    )

    companion object {
        const val VERSION_TAG = "DIOS1"
        private val HOST = Regex("[A-Za-z0-9.\\-]{1,120}|\\[[0-9A-Fa-f:.]{2,45}]")
        private val CA = Regex("[A-Za-z0-9._\\-]{1,32}")
        private val FP = Regex("[0-9a-f]{64}")
        private val PREFIX = Regex("[A-Za-z0-9/_\\-]{1,24}")

        /** Null when the text is not a checksum-correct server profile. */
        fun decode(text: String): ServerProfile? {
            val t = text.trim()
            val i = t.lastIndexOf(";C=")
            if (i < 0) return null
            val body = t.substring(0, i); val crc = t.substring(i + 3)
            if (!crc.matches(Regex("[0-9A-Fa-f]{4}")) || !body.all { it.code in 32..126 }) return null
            if (crc.toInt(16) != StationLabel.crc16Ccitt(body.toByteArray(Charsets.US_ASCII))) return null
            val parts = body.split(';')
            if (parts.size != 6 || parts[0] != VERSION_TAG) return null
            val f = HashMap<String, String>()
            for (p in parts.drop(1)) { val e = p.indexOf('='); if (e <= 0) return null; f[p.substring(0, e)] = p.substring(e + 1) }
            if (f.keys != setOf("H", "P", "CA", "F", "T")) return null
            val hp = f.getValue("H"); val colon = hp.lastIndexOf(':')
            if (colon <= 0) return null
            val host = hp.substring(0, colon); val port = hp.substring(colon + 1).toIntOrNull() ?: return null
            val https = f.getValue("P").toIntOrNull() ?: return null
            val profile = ServerProfile(host, port, https, f.getValue("CA"), f.getValue("F").lowercase(), f.getValue("T"))
            return try { profile.encode(); profile } catch (_: IllegalArgumentException) { null }
        }

        /** Builds a profile from validated screen fields (host may carry the port, fingerprint may be empty = no pinning is not storable). */
        fun fromFields(f: ServerScreenController.Fields): ServerProfile? {
            val hp = ru.dioneya.commissioning.core.ServerEndpoint.parseHostPort(f.hostPort.trim()) ?: return null
            val fp = f.fingerprintHex.trim().replace(":", "").replace(" ", "").lowercase()
            val profile = ServerProfile(
                host = if (hp.first.contains(':')) "[${hp.first}]" else hp.first, mqttPort = hp.second, httpsPort = f.httpsPort.trim().toIntOrNull() ?: return null,
                caReference = f.caReference.trim(), fingerprintHex = fp, topicPrefix = f.topicPrefix.trim(),
                apn1 = f.apn1.trim(), apn2 = f.apn2.trim(), preferredSim = f.preferredSim,
            )
            return try { profile.encode(); profile } catch (_: IllegalArgumentException) { null }
        }
    }
}

/** Persistence of the single active profile; the Android implementation uses app-private SharedPreferences. */
interface ServerProfileStore {
    fun load(): ServerProfile?
    fun save(profile: ServerProfile)
    fun clear()

    /** Text form: line 1 = QR payload (checksummed), then local extras as key=value lines. */
    object Text {
        fun serialize(p: ServerProfile): String = buildString {
            append(p.encode()).append('\n')
            append("apn1=").append(p.apn1).append('\n')
            append("apn2=").append(p.apn2).append('\n')
            append("sim=").append(p.preferredSim.name).append('\n')
        }
        fun parse(text: String): ServerProfile? {
            val lines = text.lines().filter { it.isNotBlank() }
            val core = ServerProfile.decode(lines.firstOrNull() ?: return null) ?: return null
            var p = core
            for (l in lines.drop(1)) {
                val e = l.indexOf('='); if (e <= 0) continue
                when (l.substring(0, e)) {
                    "apn1" -> p = p.copy(apn1 = l.substring(e + 1))
                    "apn2" -> p = p.copy(apn2 = l.substring(e + 1))
                    "sim" -> p = p.copy(preferredSim = if (l.substring(e + 1) == SimSlot.SIM2.name) SimSlot.SIM2 else SimSlot.SIM1)
                }
            }
            return p
        }
    }
}

/** In-memory store for tests and for the validate-only mode. */
class MemoryServerProfileStore : ServerProfileStore {
    private var text: String? = null
    override fun load(): ServerProfile? = text?.let { ServerProfileStore.Text.parse(it) }
    override fun save(profile: ServerProfile) { text = ServerProfileStore.Text.serialize(profile) }
    override fun clear() { text = null }
}

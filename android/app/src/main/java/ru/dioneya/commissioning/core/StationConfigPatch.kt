package ru.dioneya.commissioning.core

import java.security.MessageDigest

/**
 * Server "Muhoed" endpoint and the other installer-settable station fields.
 *
 * Mirrors firmware `zs_station_config` schema v1 byte for byte:
 * - the same validation rules (error codes below are the Kotlin names of the
 *   firmware `ZS_STATION_CONFIG_ERR_*` bits);
 * - the same canonical CBOR `config_write` patch (definite lengths, integer
 *   keys in ascending order, no duplicates);
 * - the same canonical SHA-256 the station computes itself, so the app can
 *   verify the read-back without trusting a hash coming from the phone.
 *
 * `host` is an IPv4 literal, an IPv6 literal or an RFC 1123 hostname without
 * scheme; the transport is always MQTT over TLS on [mqttPort].
 */
data class ServerEndpoint(
    val host: String,
    val mqttPort: Int = DEFAULT_MQTT_PORT,
    val httpsPort: Int = 0,
    val caReference: String,
    /** SHA-256 of the server certificate for pinning; 32 zero bytes = not pinned. */
    val serverFingerprint: ByteArray = ByteArray(FINGERPRINT_BYTES),
    val tenant: String,
    val topicPrefix: String,
) {
    fun validate(): List<String> = buildList {
        if (!HostValidator.isValidHost(host)) add(ERR_HOST)
        if (mqttPort !in 1..MAX_PORT) add(ERR_MQTT_PORT)
        if (httpsPort !in 0..MAX_PORT || (httpsPort != 0 && httpsPort == mqttPort)) add(ERR_HTTPS_PORT)
        if (!TOKEN.matches(caReference) || caReference.length > CA_REF_MAX) add(ERR_CA_REFERENCE)
        if (serverFingerprint.size != FINGERPRINT_BYTES) add(ERR_FINGERPRINT)
        if (!TOKEN.matches(tenant) || tenant.length > TENANT_MAX) add(ERR_TENANT)
        if (!TOPIC.matches(topicPrefix) || topicPrefix.length > TOPIC_PREFIX_MAX ||
            topicPrefix.startsWith("/") || topicPrefix.endsWith("/")
        ) add(ERR_TOPIC_PREFIX)
    }

    override fun equals(other: Any?): Boolean =
        other is ServerEndpoint && host == other.host && mqttPort == other.mqttPort &&
            httpsPort == other.httpsPort && caReference == other.caReference &&
            serverFingerprint.contentEquals(other.serverFingerprint) &&
            tenant == other.tenant && topicPrefix == other.topicPrefix

    override fun hashCode(): Int = listOf(host, mqttPort, httpsPort, caReference,
        serverFingerprint.contentHashCode(), tenant, topicPrefix).hashCode()

    companion object {
        const val DEFAULT_MQTT_PORT = 8883
        const val MAX_PORT = 65535
        const val FINGERPRINT_BYTES = 32
        const val HOST_MAX = 64
        const val CA_REF_MAX = 32
        const val TENANT_MAX = 16
        const val TOPIC_PREFIX_MAX = 32
        private val TOKEN = Regex("[A-Za-z0-9._-]+")
        private val TOPIC = Regex("[A-Za-z0-9._/-]+")

        const val ERR_HOST = "invalid_server_host"
        const val ERR_MQTT_PORT = "invalid_mqtt_port"
        const val ERR_HTTPS_PORT = "invalid_https_port"
        const val ERR_CA_REFERENCE = "invalid_ca_reference"
        const val ERR_FINGERPRINT = "invalid_server_fingerprint"
        const val ERR_TENANT = "invalid_tenant"
        const val ERR_TOPIC_PREFIX = "invalid_topic_prefix"

        /** Parses "host", "host:port", "[v6]:port" or "v4:port" as typed by the installer. */
        fun parseHostPort(input: String, defaultPort: Int = DEFAULT_MQTT_PORT): Pair<String, Int>? {
            val text = input.trim()
            if (text.isEmpty() || text.contains("://")) return null
            if (text.startsWith("[")) {
                val end = text.indexOf(']')
                if (end < 0) return null
                val host = text.substring(1, end)
                val rest = text.substring(end + 1)
                val port = when {
                    rest.isEmpty() -> defaultPort
                    rest.startsWith(":") -> rest.substring(1).toIntOrNull() ?: return null
                    else -> return null
                }
                return host to port
            }
            val colon = text.lastIndexOf(':')
            if (colon > 0 && text.count { it == ':' } == 1) {
                val port = text.substring(colon + 1).toIntOrNull() ?: return null
                return text.substring(0, colon) to port
            }
            return text to defaultPort
        }
    }
}

/** Everything an installer may write through `config_write`; identity fields are read-only. */
data class StationConfigPatch(
    /** Monotonic configuration version; must exceed the version currently on the station. */
    val version: Long,
    val endpoint: ServerEndpoint,
    val preferredSim: SimSlot = SimSlot.SIM1,
    val apn1: String = "",
    val apn2: String = "",
    /** Not written; used only for hash verification of the read-back. */
    val stationId: Long = 0,
    val region: LoRaRegion = LoRaRegion.RU868,
) {
    fun validate(): List<String> = buildList {
        addAll(endpoint.validate())
        if (version !in 1..UINT32_MAX) add(ERR_VERSION)
        if (!APN.matches(apn1) && apn1.isNotEmpty() || apn1.length > APN_MAX) add(ERR_APN)
        if (!APN.matches(apn2) && apn2.isNotEmpty() || apn2.length > APN_MAX) add(ERR_APN)
        if (apn1.isEmpty() && apn2.isNotEmpty()) add(ERR_APN)
        if (region != LoRaRegion.RU868) add(ERR_REGION)
    }.distinct()

    /** Canonical CBOR patch for the station (firmware `zs_station_config_apply_patch`). */
    fun toCborPatch(): ByteArray {
        val w = CanonicalCbor.Writer()
        w.map(11)
        w.uint(KEY_VERSION); w.uint(version)
        w.uint(KEY_SERVER_HOST); w.text(endpoint.host)
        w.uint(KEY_MQTT_PORT); w.uint(endpoint.mqttPort.toLong())
        w.uint(KEY_HTTPS_PORT); w.uint(endpoint.httpsPort.toLong())
        w.uint(KEY_CA_REFERENCE); w.text(endpoint.caReference)
        w.uint(KEY_SERVER_FINGERPRINT); w.bytes(endpoint.serverFingerprint)
        w.uint(KEY_TENANT); w.text(endpoint.tenant)
        w.uint(KEY_TOPIC_PREFIX); w.text(endpoint.topicPrefix)
        w.uint(KEY_PREFERRED_SIM); w.uint(if (preferredSim == SimSlot.SIM1) 1 else 2)
        w.uint(KEY_APN1); w.text(apn1)
        w.uint(KEY_APN2); w.text(apn2)
        return w.toByteArray()
    }

    /** The exact canonical hash the station will store (`zs_station_config_compute_hash`). */
    fun stationHash(): ByteArray {
        val buf = ByteArray(HASH_INPUT_BYTES)
        var pos = 0
        fun put(b: Int) { buf[pos++] = b.toByte() }
        fun be16(v: Int) { put(v ushr 8); put(v) }
        fun be32(v: Long) { put((v ushr 24).toInt()); put((v ushr 16).toInt()); put((v ushr 8).toInt()); put(v.toInt()) }
        fun field(s: String, max: Int) {
            val bytes = s.toByteArray(Charsets.US_ASCII)
            require(bytes.size <= max) { "field too long" }
            put(bytes.size)
            bytes.copyInto(buf, pos)
            pos += max
        }
        HASH_DOMAIN.toByteArray(Charsets.US_ASCII).copyInto(buf, 0); pos = HASH_DOMAIN.length
        put(SCHEMA)
        be32(version)
        be32(stationId)
        put(regionCode(region))
        put(if (preferredSim == SimSlot.SIM1) 1 else 2)
        be16(endpoint.mqttPort)
        be16(endpoint.httpsPort)
        field(endpoint.host, ServerEndpoint.HOST_MAX)
        field(endpoint.caReference, ServerEndpoint.CA_REF_MAX)
        endpoint.serverFingerprint.copyInto(buf, pos); pos += ServerEndpoint.FINGERPRINT_BYTES
        field(endpoint.tenant, ServerEndpoint.TENANT_MAX)
        field(endpoint.topicPrefix, ServerEndpoint.TOPIC_PREFIX_MAX)
        field(apn1, APN_MAX)
        field(apn2, APN_MAX)
        check(pos == HASH_INPUT_BYTES)
        return MessageDigest.getInstance("SHA-256").digest(buf)
    }

    companion object {
        const val SCHEMA = 1
        const val UINT32_MAX = 0xFFFF_FFFFL
        const val APN_MAX = 32
        const val HASH_INPUT_BYTES = 281
        private const val HASH_DOMAIN = "ZS-STATION-CONFIG-V1"
        private val APN = Regex("[A-Za-z0-9.-]+")

        const val KEY_VERSION = 1L
        const val KEY_SERVER_HOST = 2L
        const val KEY_MQTT_PORT = 3L
        const val KEY_HTTPS_PORT = 4L
        const val KEY_CA_REFERENCE = 5L
        const val KEY_SERVER_FINGERPRINT = 6L
        const val KEY_TENANT = 7L
        const val KEY_TOPIC_PREFIX = 8L
        const val KEY_PREFERRED_SIM = 9L
        const val KEY_APN1 = 10L
        const val KEY_APN2 = 11L
        const val KEY_REGION = 12L
        const val KEY_STATION_ID = 13L
        const val KEY_CONFIG_HASH = 14L

        const val ERR_VERSION = "invalid_config_version"
        const val ERR_APN = "invalid_apn"
        const val ERR_REGION = "invalid_pilot_region"

        fun regionCode(region: LoRaRegion): Int = when (region) {
            LoRaRegion.RU868 -> 1
            LoRaRegion.EU868 -> 2
        }

        private fun regionFromCode(code: Long): LoRaRegion? = when (code) {
            1L -> LoRaRegion.RU868
            2L -> LoRaRegion.EU868
            else -> null
        }

        /**
         * Decodes the station `config_read` map and rebuilds the patch view plus the
         * station-reported hash.  Returns null on any malformed input.
         */
        fun parseReadback(bytes: ByteArray): ReadbackResult? = try {
            val r = CanonicalCbor.Reader(bytes)
            val count = r.mapHeader()
            var version: Long? = null; var host: String? = null; var mqtt: Long? = null; var https: Long? = null
            var ca: String? = null; var fp: ByteArray? = null; var tenant: String? = null; var prefix: String? = null
            var sim: Long? = null; var apn1: String? = null; var apn2: String? = null
            var region: Long? = null; var stationId: Long? = null; var hash: ByteArray? = null
            var lastKey = -1L
            repeat(count) {
                val key = r.uint()
                if (key <= lastKey) throw IllegalArgumentException("non-canonical key order")
                lastKey = key
                when (key) {
                    KEY_VERSION -> version = r.uint()
                    KEY_SERVER_HOST -> host = r.text()
                    KEY_MQTT_PORT -> mqtt = r.uint()
                    KEY_HTTPS_PORT -> https = r.uint()
                    KEY_CA_REFERENCE -> ca = r.text()
                    KEY_SERVER_FINGERPRINT -> fp = r.bytes()
                    KEY_TENANT -> tenant = r.text()
                    KEY_TOPIC_PREFIX -> prefix = r.text()
                    KEY_PREFERRED_SIM -> sim = r.uint()
                    KEY_APN1 -> apn1 = r.text()
                    KEY_APN2 -> apn2 = r.text()
                    KEY_REGION -> region = r.uint()
                    KEY_STATION_ID -> stationId = r.uint()
                    KEY_CONFIG_HASH -> hash = r.bytes()
                    else -> throw IllegalArgumentException("unknown key $key")
                }
            }
            r.requireEnd()
            val patch = StationConfigPatch(
                version = version!!,
                endpoint = ServerEndpoint(
                    host = host!!, mqttPort = mqtt!!.toInt(), httpsPort = https!!.toInt(),
                    caReference = ca!!, serverFingerprint = fp!!, tenant = tenant!!, topicPrefix = prefix!!,
                ),
                preferredSim = if (sim == 1L) SimSlot.SIM1 else if (sim == 2L) SimSlot.SIM2 else throw IllegalArgumentException("sim"),
                apn1 = apn1!!, apn2 = apn2!!, stationId = stationId!!, region = regionFromCode(region!!)!!,
            )
            ReadbackResult(patch, hash!!)
        } catch (e: Exception) {
            null
        }
    }

    data class ReadbackResult(val config: StationConfigPatch, val stationReportedHash: ByteArray) {
        /** True only when the station's stored record equals what the app intended to write. */
        fun matches(intended: StationConfigPatch): Boolean {
            val expected = intended.copy(stationId = config.stationId, region = config.region)
            return config == expected &&
                stationReportedHash.contentEquals(expected.stationHash()) &&
                stationReportedHash.contentEquals(config.stationHash())
        }
    }
}

/** RFC 1123 hostname / IPv4 / IPv6 literal checks, identical to firmware `zs_station_config_host_is_*`. */
object HostValidator {
    fun isValidHost(host: String): Boolean =
        host.isNotEmpty() && host.length <= ServerEndpoint.HOST_MAX &&
            (isIpv4(host) || isIpv6(host) || isHostname(host))

    fun isIpv4(host: String): Boolean {
        val parts = host.split('.')
        if (parts.size != 4) return false
        return parts.all { p ->
            p.isNotEmpty() && p.length <= 3 && p.all { it.isDigit() } &&
                !(p.length > 1 && p[0] == '0') && p.toInt() <= 255
        }
    }

    fun isIpv6(host: String): Boolean {
        if (host.isEmpty() || host.contains(":::")) return false
        if (host.startsWith(":") && !host.startsWith("::")) return false
        if (host.endsWith(":") && !host.endsWith("::")) return false
        val doubleColon = host.indexOf("::")
        if (doubleColon >= 0 && host.indexOf("::", doubleColon + 1) >= 0) return false
        val groups = host.split("::").flatMap { part -> if (part.isEmpty()) emptyList() else part.split(':') }
        if (groups.any { it.isEmpty() || it.length > 4 || !it.all { c -> c.isDigit() || c.lowercaseChar() in 'a'..'f' } }) return false
        return if (doubleColon >= 0) groups.size <= 7 else groups.size == 8
    }

    fun isHostname(host: String): Boolean {
        if (host.isEmpty() || host.length > ServerEndpoint.HOST_MAX) return false
        val labels = host.split('.')
        if (labels.any { it.isEmpty() || it.length > 63 || it.startsWith("-") || it.endsWith("-") }) return false
        if (labels.any { l -> !l.all { it.isLetterOrDigit() && it.code < 128 || it == '-' } }) return false
        return !labels.last().all { it.isDigit() }
    }
}

/** Minimal canonical CBOR (RFC 8949 §4.2.1) for unsigned ints, byte/text strings and definite maps. */
object CanonicalCbor {
    class Writer {
        private val out = java.io.ByteArrayOutputStream()
        fun map(count: Int) = head(5, count.toLong())
        fun uint(v: Long) = head(0, v)
        fun bytes(b: ByteArray) { head(2, b.size.toLong()); out.write(b) }
        fun text(s: String) { val b = s.toByteArray(Charsets.UTF_8); head(3, b.size.toLong()); out.write(b) }
        fun bool(v: Boolean) { out.write(if (v) 0xF5 else 0xF4) }
        fun toByteArray(): ByteArray = out.toByteArray()
        private fun head(major: Int, v: Long) {
            require(v >= 0)
            val m = major shl 5
            when {
                v < 24 -> out.write(m or v.toInt())
                v <= 0xFF -> { out.write(m or 24); out.write(v.toInt()) }
                v <= 0xFFFF -> { out.write(m or 25); out.write((v ushr 8).toInt()); out.write(v.toInt()) }
                v <= 0xFFFF_FFFFL -> { out.write(m or 26); for (s in intArrayOf(24, 16, 8, 0)) out.write((v ushr s).toInt()) }
                else -> throw IllegalArgumentException("value too large for schema")
            }
        }
    }

    class Reader(private val data: ByteArray) {
        private var pos = 0
        fun mapHeader(): Int = head(5).toInt()
        fun uint(): Long = head(0)
        fun bytes(): ByteArray = take(head(2))
        fun text(): String = String(take(head(3)), Charsets.UTF_8)
        fun bool(): Boolean {
            if (pos >= data.size) throw IllegalArgumentException("truncated")
            return when (data[pos++].toInt() and 0xFF) { 0xF4 -> false; 0xF5 -> true; else -> throw IllegalArgumentException("not a bool") }
        }
        fun requireEnd() { if (pos != data.size) throw IllegalArgumentException("trailing bytes") }
        private fun take(n: Long): ByteArray {
            if (n < 0 || pos + n > data.size) throw IllegalArgumentException("truncated")
            val r = data.copyOfRange(pos, pos + n.toInt()); pos += n.toInt(); return r
        }
        private fun head(expectMajor: Int): Long {
            if (pos >= data.size) throw IllegalArgumentException("truncated")
            val ib = data[pos++].toInt() and 0xFF
            if (ib ushr 5 != expectMajor) throw IllegalArgumentException("unexpected major type")
            val ai = ib and 0x1F
            val v: Long = when (ai) {
                in 0..23 -> ai.toLong()
                24 -> take(1)[0].toLong() and 0xFF
                25 -> take(2).fold(0L) { acc, b -> (acc shl 8) or (b.toLong() and 0xFF) }
                26 -> take(4).fold(0L) { acc, b -> (acc shl 8) or (b.toLong() and 0xFF) }
                else -> throw IllegalArgumentException("unsupported length form")
            }
            val minimal = when (ai) { 24 -> v >= 24; 25 -> v > 0xFF; 26 -> v > 0xFFFF; else -> true }
            if (!minimal) throw IllegalArgumentException("non-canonical length")
            return v
        }
    }
}

package ru.dioneya.commissioning.core.secrets

import ru.dioneya.commissioning.core.CanonicalCbor
import ru.dioneya.commissioning.core.ble.GattContractV01
import ru.dioneya.commissioning.core.role.EngineerKey

/**
 * Station secrets to provision over `station_secrets` (0x0206, ICD v0.3): the registry export
 * `<serial>.station-secrets.json` of `muhoed-pki station-secrets <serial>` -
 * `{"serial", "engineer_key_hex", "iccid1", "iccid2", "command_public_key_hex", "context": "DIO-SECRETS-V1"}`,
 * every field but serial/context optional.  The bundle is written once at commissioning (installer, blank station)
 * or by the engineer later; the phone keeps nothing of it after the write.  Pure Kotlin.
 */
class StationSecretsBundle(
    val serial: String,
    val engineerKey: ByteArray?,
    val iccid1: String?,
    val iccid2: String?,
    val commandPublicKey: ByteArray?,
) {
    init {
        require(serial.isNotBlank()) { "serial required" }
        require(engineerKey == null || engineerKey.size == EngineerKey.KEY_BYTES) { "engineer key must be 32 bytes" }
        require(commandPublicKey == null || commandPublicKey.size == COMMAND_KEY_BYTES) { "command key must be 32 bytes" }
        require(iccid1 == null || iccidValid(iccid1)) { "iccid1 must be 18..22 digits" }
        require(iccid2 == null || iccidValid(iccid2)) { "iccid2 must be 18..22 digits" }
    }

    val isEmpty: Boolean get() = engineerKey == null && iccid1 == null && iccid2 == null && commandPublicKey == null

    /** The CBOR patch the station merges into its record (only the present fields). */
    fun toCborPatch(): ByteArray {
        val w = CanonicalCbor.Writer()
        var n = 0
        if (engineerKey != null) n++; if (iccid1 != null) n++; if (iccid2 != null) n++; if (commandPublicKey != null) n++
        w.map(n)
        if (engineerKey != null) { w.uint(GattContractV01.SECRETS_KEY_ENGINEER); w.bytes(engineerKey) }
        if (iccid1 != null) { w.uint(GattContractV01.SECRETS_KEY_ICCID1); w.text(iccid1) }
        if (iccid2 != null) { w.uint(GattContractV01.SECRETS_KEY_ICCID2); w.text(iccid2) }
        if (commandPublicKey != null) { w.uint(GattContractV01.SECRETS_KEY_COMMAND); w.bytes(commandPublicKey) }
        return w.toByteArray()
    }

    /** What the bundle carries, for the confirmation dialog (never the values). */
    fun summary(): String = listOfNotNull(
        engineerKey?.let { "engineer key" }, iccid1?.let { "ICCID 1 …" + it.takeLast(4) }, iccid2?.let { "ICCID 2 …" + it.takeLast(4) },
        commandPublicKey?.let { "command key" }).joinToString(", ").ifEmpty { "nothing" }

    companion object {
        const val CONTEXT = "DIO-SECRETS-V1"
        const val COMMAND_KEY_BYTES = 32

        fun iccidValid(s: String): Boolean = s.length in 18..22 && s.all { it in '0'..'9' }

        /** The clear patch: `{5: true}` (engineer only). */
        fun clearPatch(): ByteArray { val w = CanonicalCbor.Writer(); w.map(1); w.uint(GattContractV01.SECRETS_KEY_CLEAR); w.bool(true); return w.toByteArray() }

        /** Parses the registry export; null when the context is foreign, a key is malformed or an ICCID is invalid. */
        fun fromExportJson(text: String): StationSecretsBundle? {
            val serial = jsonString(text, "serial") ?: return null
            val context = jsonString(text, "context") ?: return null
            if (context != CONTEXT) return null
            val key = jsonString(text, "engineer_key_hex")?.let { EngineerKey.hexToBytes(it) ?: return null }
            val cmd = jsonString(text, "command_public_key_hex")?.let { EngineerKey.hexToBytes(it) ?: return null }
            val iccid1 = jsonString(text, "iccid1")?.takeIf { it.isNotEmpty() }
            val iccid2 = jsonString(text, "iccid2")?.takeIf { it.isNotEmpty() }
            return try { StationSecretsBundle(serial, key, iccid1, iccid2, cmd) } catch (_: IllegalArgumentException) { null }
        }

        private fun jsonString(text: String, key: String): String? {
            val m = Regex("\"" + Regex.escape(key) + "\"\\s*:\\s*\"([^\"\\\\]*)\"").find(text) ?: return null
            return m.groupValues[1]
        }
    }
}

/** Presence map the station reads back (`{0: version, 1..4: bool}`) - never the values. */
data class StationSecretsPresence(val version: Long, val engineerKey: Boolean, val iccid1: Boolean, val iccid2: Boolean, val commandKey: Boolean) {
    val isBlank: Boolean get() = !engineerKey && !iccid1 && !iccid2 && !commandKey

    fun text(): String = if (isBlank) "not provisioned" else
        "v$version: " + listOfNotNull(engineerKey.takeIf { it }?.let { "engineer key" }, iccid1.takeIf { it }?.let { "ICCID 1" },
            iccid2.takeIf { it }?.let { "ICCID 2" }, commandKey.takeIf { it }?.let { "command key" }).joinToString(", ")

    companion object {
        fun decode(cbor: ByteArray): StationSecretsPresence? = try {
            val r = CanonicalCbor.Reader(cbor)
            var version = 0L; var ek = false; var i1 = false; var i2 = false; var ck = false
            repeat(r.mapHeader()) {
                when (r.uint()) {
                    GattContractV01.SECRETS_KEY_VERSION -> version = r.uint()
                    GattContractV01.SECRETS_KEY_ENGINEER -> ek = r.bool()
                    GattContractV01.SECRETS_KEY_ICCID1 -> i1 = r.bool()
                    GattContractV01.SECRETS_KEY_ICCID2 -> i2 = r.bool()
                    GattContractV01.SECRETS_KEY_COMMAND -> ck = r.bool()
                    else -> return null
                }
            }
            r.requireEnd()
            StationSecretsPresence(version, ek, i1, i2, ck)
        } catch (_: IllegalArgumentException) { null }
    }
}

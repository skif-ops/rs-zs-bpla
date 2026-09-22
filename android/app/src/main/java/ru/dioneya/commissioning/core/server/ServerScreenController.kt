package ru.dioneya.commissioning.core.server

import ru.dioneya.commissioning.core.LoRaRegion
import ru.dioneya.commissioning.core.ServerEndpoint
import ru.dioneya.commissioning.core.SimSlot
import ru.dioneya.commissioning.core.StationConfigPatch
import ru.dioneya.commissioning.core.ble.BleError
import ru.dioneya.commissioning.core.ble.BleException
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.GattContractV01

/**
 * Logic of the "Сервер" screen: edit the endpoint fields, validate, write the
 * CBOR patch over BLE, read back and verify the station hash, run the
 * self-test.  Pure Kotlin; the Activity only renders [State] and forwards taps.
 */
class ServerScreenController(private val session: BleSession, private val listener: (State) -> Unit) {

    enum class Phase { EDITING, INVALID, CONNECTING, WRITING, READING_BACK, VERIFIED, MISMATCH, REJECTED, ERROR, SELF_TEST, SELF_TEST_DONE }

    data class Fields(
        val hostPort: String = "",
        val httpsPort: String = "0",
        val caReference: String = "",
        val fingerprintHex: String = "",
        val tenant: String = "",
        val topicPrefix: String = "zs/v1",
        val version: String = "1",
        val preferredSim: SimSlot = SimSlot.SIM1,
        val apn1: String = "",
        val apn2: String = "",
    )

    data class State(
        val phase: Phase = Phase.EDITING,
        val fields: Fields = Fields(),
        val errors: List<String> = emptyList(),
        val message: String = "",
        val readback: StationConfigPatch? = null,
        val stationHashHex: String = "",
        val selfTest: List<SelfTestResult> = emptyList(),
    )

    data class SelfTestResult(val id: Int, val code: Int, val detail: Long) {
        val name: String get() = SELF_TEST_NAMES[id] ?: "test_$id"
        val codeName: String get() = SELF_TEST_CODES[code] ?: "code_$code"
    }

    @Volatile var state: State = State()
        private set

    private fun emit(next: State) { state = next; listener(next) }

    fun edit(fields: Fields) {
        emit(state.copy(fields = fields, phase = Phase.EDITING, errors = emptyList(), message = ""))
    }

    /** Builds the patch from the fields; null when validation fails (errors go to the state). */
    fun buildPatch(): StationConfigPatch? {
        val f = state.fields
        val errors = ArrayList<String>()
        val hostPort = ServerEndpoint.parseHostPort(f.hostPort.trim())
        if (hostPort == null) errors.add(ServerEndpoint.ERR_HOST)
        val https = f.httpsPort.trim().toIntOrNull()
        if (https == null || https !in 0..ServerEndpoint.MAX_PORT) errors.add(ServerEndpoint.ERR_HTTPS_PORT)
        val fp = parseFingerprint(f.fingerprintHex)
        if (fp == null) errors.add(ServerEndpoint.ERR_FINGERPRINT)
        val version = f.version.trim().toLongOrNull()
        if (version == null || version !in 1..StationConfigPatch.UINT32_MAX) errors.add(StationConfigPatch.ERR_VERSION)
        if (errors.isNotEmpty()) { emit(state.copy(phase = Phase.INVALID, errors = errors)); return null }
        val patch = StationConfigPatch(
            version = version!!,
            endpoint = ServerEndpoint(
                host = hostPort!!.first, mqttPort = hostPort.second, httpsPort = https!!,
                caReference = f.caReference.trim(), serverFingerprint = fp!!, tenant = f.tenant.trim(), topicPrefix = f.topicPrefix.trim(),
            ),
            preferredSim = f.preferredSim, apn1 = f.apn1.trim(), apn2 = f.apn2.trim(), region = LoRaRegion.RU868,
        )
        val v = patch.validate()
        if (v.isNotEmpty()) { emit(state.copy(phase = Phase.INVALID, errors = v)); return null }
        return patch
    }

    /** Writes the patch, reads back, verifies. Runs on the caller's thread (use a background thread in the Activity). */
    fun apply() {
        val patch = buildPatch() ?: return
        try {
            emit(state.copy(phase = Phase.CONNECTING, errors = emptyList(), message = ""))
            session.run({ session.connect() }, GattContractV01.TIMEOUT_CONNECT_MS + 1000)
            emit(state.copy(phase = Phase.WRITING))
            val status = session.run({
                session.request(GattContractV01.CHAR_CONFIG_WRITE, GattContractV01.CHAR_CONFIG_WRITE, patch.toCborPatch(), GattContractV01.TIMEOUT_CONFIG_WRITE_MS)
            }, GattContractV01.TIMEOUT_CONFIG_WRITE_MS + 2000)
            val code = if (status.isEmpty()) GattContractV01.WRITE_STATUS_STORAGE_ERROR else status[0].toInt() and 0xFF
            if (code != GattContractV01.WRITE_STATUS_OK) {
                emit(state.copy(phase = Phase.REJECTED, message = writeStatusText(code)))
                return
            }
            emit(state.copy(phase = Phase.READING_BACK))
            val raw = session.run({ session.readLong(GattContractV01.CHAR_CONFIG_READ) })
            val rb = StationConfigPatch.parseReadback(raw)
            if (rb == null) { emit(state.copy(phase = Phase.ERROR, message = "read-back: malformed record")); return }
            val hex = rb.stationReportedHash.joinToString("") { "%02x".format(it) }
            if (rb.matches(patch)) emit(state.copy(phase = Phase.VERIFIED, readback = rb.config, stationHashHex = hex, message = "station_id ${rb.config.stationId}"))
            else emit(state.copy(phase = Phase.MISMATCH, readback = rb.config, stationHashHex = hex, message = "read-back differs from the intended configuration"))
        } catch (e: BleException) {
            emit(state.copy(phase = Phase.ERROR, message = bleErrorText(e)))
        }
    }

    fun runSelfTest() {
        try {
            emit(state.copy(phase = Phase.SELF_TEST, message = ""))
            session.run({ if (!sessionConnected()) session.connect() }, GattContractV01.TIMEOUT_CONNECT_MS + 1000)
            val report = session.run({
                session.request(GattContractV01.CHAR_SELF_TEST, GattContractV01.CHAR_SELF_TEST, byteArrayOf(GattContractV01.SELF_TEST_RUN_ALL), GattContractV01.TIMEOUT_SELF_TEST_MS)
            }, GattContractV01.TIMEOUT_SELF_TEST_MS + 2000)
            val results = parseSelfTestReport(report)
            if (results == null) emit(state.copy(phase = Phase.ERROR, message = "self-test: malformed report"))
            else emit(state.copy(phase = Phase.SELF_TEST_DONE, selfTest = results, message = if (results.any { it.code == 2 || it.code == 4 }) "self-test: failures" else "self-test: OK"))
        } catch (e: BleException) {
            emit(state.copy(phase = Phase.ERROR, message = bleErrorText(e)))
        }
    }

    private fun sessionConnected(): Boolean = sessionConnectedProbe?.invoke() ?: false
    /** Test hook / Activity hook: reports whether the transport is connected (null = unknown, reconnect). */
    var sessionConnectedProbe: (() -> Boolean)? = null

    companion object {
        val SELF_TEST_NAMES = mapOf(
            1 to "power", 2 to "nor_flash", 3 to "sd_card", 4 to "mic_capture", 5 to "mic_alignment", 6 to "gnss_uart", 7 to "gnss_pps",
            8 to "lora_spi", 9 to "modem_at", 10 to "modem_tls", 11 to "ble_link", 12 to "rtc_lse", 13 to "station_config",
        )
        val SELF_TEST_CODES = mapOf(0 to "NOT_RUN", 1 to "PASS", 2 to "FAIL", 3 to "SKIPPED", 4 to "TIMEOUT")

        fun parseFingerprint(hex: String): ByteArray? {
            val h = hex.trim().replace(":", "").replace(" ", "")
            if (h.isEmpty()) return ByteArray(ServerEndpoint.FINGERPRINT_BYTES)
            if (h.length != 64 || !h.all { it in "0123456789abcdefABCDEF" }) return null
            return ByteArray(32) { i -> h.substring(2 * i, 2 * i + 2).toInt(16).toByte() }
        }

        fun writeStatusText(code: Int): String = when (code) {
            GattContractV01.WRITE_STATUS_REJECTED_VALIDATION -> "station rejected the patch: validation"
            GattContractV01.WRITE_STATUS_REJECTED_VERSION -> "station rejected the patch: version not newer"
            GattContractV01.WRITE_STATUS_NOT_IN_SERVICE_MODE -> "station is not in service mode"
            GattContractV01.WRITE_STATUS_NOT_AUTHORIZED -> "not authorized for this operation"
            GattContractV01.WRITE_STATUS_STORAGE_ERROR -> "station storage error"
            else -> "station returned status $code"
        }

        fun bleErrorText(e: BleException): String = when (e.code) {
            BleError.TIMEOUT -> "BLE timeout: ${e.message}"
            BleError.DISCONNECTED -> "BLE disconnected"
            BleError.FRAMING -> "BLE framing error: ${e.message}"
            BleError.NOT_FOUND -> "GATT characteristic not found: ${e.message}"
            else -> "BLE error: ${e.message}"
        }

        /** Decodes the firmware zs_selftest CBOR report {id: [code, detail]} (keys ascending). */
        fun parseSelfTestReport(bytes: ByteArray): List<SelfTestResult>? {
            var pos = 0
            fun head(major: Int): Long {
                if (pos >= bytes.size) throw IllegalArgumentException("truncated")
                val ib = bytes[pos++].toInt() and 0xFF
                if (ib ushr 5 != major) throw IllegalArgumentException("major")
                val ai = ib and 0x1F
                return when {
                    ai < 24 -> ai.toLong()
                    ai == 24 -> (bytes[pos++].toInt() and 0xFF).toLong()
                    ai == 25 -> { val v = ((bytes[pos].toInt() and 0xFF) shl 8) or (bytes[pos + 1].toInt() and 0xFF); pos += 2; v.toLong() }
                    ai == 26 -> { var v = 0L; repeat(4) { v = (v shl 8) or (bytes[pos++].toLong() and 0xFF) }; v }
                    else -> throw IllegalArgumentException("unsupported")
                }
            }
            return try {
                val n = head(5).toInt()
                val out = ArrayList<SelfTestResult>(n)
                var last = -1L
                repeat(n) {
                    val id = head(0)
                    if (id <= last) throw IllegalArgumentException("order")
                    last = id
                    if (head(4) != 2L) throw IllegalArgumentException("array")
                    val code = head(0)
                    val detail = head(0)
                    out.add(SelfTestResult(id.toInt(), code.toInt(), detail))
                }
                if (pos != bytes.size) throw IllegalArgumentException("trailing")
                out
            } catch (e: Exception) {
                null
            }
        }
    }
}

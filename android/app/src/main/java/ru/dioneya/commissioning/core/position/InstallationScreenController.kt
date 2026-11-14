package ru.dioneya.commissioning.core.position

import ru.dioneya.commissioning.core.CoordinateSource
import ru.dioneya.commissioning.core.InstallationCommissioningContract
import ru.dioneya.commissioning.core.InstallationCommissioningOperation
import ru.dioneya.commissioning.core.InstallationCommissioningReadback
import ru.dioneya.commissioning.core.InstallationCommissioningRequest
import ru.dioneya.commissioning.core.InstallationCommissioningRole
import ru.dioneya.commissioning.core.InstallationPosition
import ru.dioneya.commissioning.core.PositionTrustPolicy
import ru.dioneya.commissioning.core.ble.BleException
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.GattContractV01
import ru.dioneya.commissioning.core.server.ServerScreenController

/**
 * Logic of the "Координаты установки" screen (ICD §3.1): read what the station holds,
 * take the position from the phone or the keyboard, choose INITIAL / RECOMMISSION
 * from the stored version, write through `installation_position`, read back and
 * verify with [InstallationCommissioningContract].  Pure Kotlin.
 */
class InstallationScreenController(
    private val session: BleSession,
    private val clockUs: () -> Long,
    private val listener: (State) -> Unit,
) {
    enum class Phase { IDLE, READING, EDITING, INVALID, WRITING, READING_BACK, VERIFIED, MISMATCH, REJECTED, ERROR }

    data class Fields(
        val latitude: String = "", val longitude: String = "", val altitudeM: String = "0", val accuracyM: String = "5",
        val source: CoordinateSource = CoordinateSource.MANUAL,
        val policy: PositionTrustPolicy = PositionTrustPolicy(),
    )

    data class State(
        val phase: Phase = Phase.IDLE,
        val role: InstallationCommissioningRole = InstallationCommissioningRole.INSTALLER,
        val fields: Fields = Fields(),
        val stored: InstallationCommissioningReadback? = null,
        val operation: InstallationCommissioningOperation = InstallationCommissioningOperation.INITIAL,
        val errors: List<String> = emptyList(),
        val message: String = "",
        val readback: InstallationCommissioningReadback? = null,
    )

    @Volatile var state: State = State()
        private set

    private fun emit(next: State) { state = next; listener(next) }

    fun setRole(role: InstallationCommissioningRole) { emit(state.copy(role = role)) }

    fun edit(fields: Fields) { emit(state.copy(fields = fields, phase = Phase.EDITING, errors = emptyList(), message = "")) }

    /** Fills the fields from a phone fix (already converted by PhoneLocationProvider). */
    fun useLocation(position: InstallationPosition) {
        emit(state.copy(phase = Phase.EDITING, errors = emptyList(), message = "", fields = state.fields.copy(
            latitude = "%.7f".format(java.util.Locale.ROOT, position.latE7 / 1e7),
            longitude = "%.7f".format(java.util.Locale.ROOT, position.lonE7 / 1e7),
            altitudeM = "%.1f".format(java.util.Locale.ROOT, position.altDm / 10.0),
            accuracyM = position.accuracyM.toString(),
            source = CoordinateSource.PHONE_LOCATION,
        )))
    }

    /** Reads the stored record (or "empty") and derives the operation for the next write. Blocking. */
    fun readStored() {
        emit(state.copy(phase = Phase.READING, message = ""))
        try {
            session.run({ session.connect() }, GattContractV01.TIMEOUT_CONNECT_MS + 1000)
            val raw = session.run({ session.readLong(GattContractV01.CHAR_INSTALLATION_POSITION) })
            when (val rb = InstallationPositionCodec.decodeReadback(raw)) {
                null -> emit(state.copy(phase = Phase.ERROR, message = "installation_position: malformed record"))
                InstallationPositionCodec.Readback.Empty ->
                    emit(state.copy(phase = Phase.EDITING, stored = null, operation = InstallationCommissioningOperation.INITIAL, message = "station has no installation position yet"))
                is InstallationPositionCodec.Readback.Stored -> emit(state.copy(
                    phase = Phase.EDITING, stored = rb.record, operation = InstallationCommissioningOperation.RECOMMISSION,
                    message = "stored v${rb.record.position.version} (${rb.record.position.source.name.lowercase()}, generation ${rb.record.storageGeneration})",
                    fields = state.fields.copy(policy = rb.record.policy),
                ))
            }
        } catch (e: BleException) {
            emit(state.copy(phase = Phase.ERROR, message = ServerScreenController.bleErrorText(e)))
        }
    }

    /** Builds the request from the fields; null (with errors in the state) when invalid. */
    fun buildRequest(): InstallationCommissioningRequest? {
        val f = state.fields
        val errors = ArrayList<String>()
        val lat = f.latitude.trim().replace(',', '.').toDoubleOrNull()
        val lon = f.longitude.trim().replace(',', '.').toDoubleOrNull()
        val alt = f.altitudeM.trim().replace(',', '.').toDoubleOrNull()
        val acc = f.accuracyM.trim().toIntOrNull()
        if (lat == null || lat !in -90.0..90.0) errors.add("invalid_installation_latitude")
        if (lon == null || lon !in -180.0..180.0) errors.add("invalid_installation_longitude")
        if (alt == null) errors.add("invalid_installation_altitude")
        if (acc == null || acc !in 1..1000) errors.add("invalid_installation_accuracy")
        if (errors.isNotEmpty()) { emit(state.copy(phase = Phase.INVALID, errors = errors)); return null }
        val version = (state.stored?.position?.version ?: 0L) + 1
        val request = InstallationCommissioningRequest(
            operation = state.operation,
            position = InstallationPosition(
                latE7 = Math.round(lat!! * 1e7).toInt(), lonE7 = Math.round(lon!! * 1e7).toInt(), altDm = Math.round(alt!! * 10.0).toInt(),
                accuracyM = acc!!, source = f.source, version = version, locked = true,
            ),
            policy = f.policy,
            commissionedTimeUs = clockUs(),
        )
        val v = InstallationCommissioningContract.validateRequest(request, state.role, state.stored?.position?.version)
        if (v.isNotEmpty()) { emit(state.copy(phase = Phase.INVALID, errors = v)); return null }
        return request
    }

    /** Writes, reads back and verifies. Blocking: run on a background thread. */
    fun apply() {
        val request = buildRequest() ?: return
        try {
            emit(state.copy(phase = Phase.WRITING, errors = emptyList(), message = ""))
            session.run({ if (!(connectedProbe?.invoke() ?: false)) session.connect() }, GattContractV01.TIMEOUT_CONNECT_MS + 1000)
            val status = session.run({
                session.request(GattContractV01.CHAR_INSTALLATION_POSITION, GattContractV01.CHAR_INSTALLATION_POSITION,
                    InstallationPositionCodec.encodeRequest(request), GattContractV01.TIMEOUT_CONFIG_WRITE_MS)
            }, GattContractV01.TIMEOUT_CONFIG_WRITE_MS + 2000)
            val code = if (status.isEmpty()) GattContractV01.WRITE_STATUS_STORAGE_ERROR else status[0].toInt() and 0xFF
            if (code != GattContractV01.WRITE_STATUS_OK) { emit(state.copy(phase = Phase.REJECTED, message = statusText(code))); return }
            emit(state.copy(phase = Phase.READING_BACK))
            val raw = session.run({ session.readLong(GattContractV01.CHAR_INSTALLATION_POSITION) })
            val rb = InstallationPositionCodec.decodeReadback(raw)
            if (rb !is InstallationPositionCodec.Readback.Stored) { emit(state.copy(phase = Phase.ERROR, message = "read-back: no record after write")); return }
            val problems = InstallationCommissioningContract.verifyReadback(request, rb.record)
            if (problems.isEmpty()) emit(state.copy(phase = Phase.VERIFIED, readback = rb.record, stored = rb.record,
                operation = InstallationCommissioningOperation.RECOMMISSION, message = "v${rb.record.position.version} hash ${rb.record.commissioningHashHex.take(16)}…"))
            else emit(state.copy(phase = Phase.MISMATCH, readback = rb.record, stored = rb.record, operation = InstallationCommissioningOperation.RECOMMISSION,
                errors = problems, message = "read-back verification failed"))   /* the station did store a record: the next attempt is a re-commission */
        } catch (e: BleException) {
            emit(state.copy(phase = Phase.ERROR, message = ServerScreenController.bleErrorText(e)))
        }
    }

    var connectedProbe: (() -> Boolean)? = null

    companion object {
        /** Additional to the config_write codes (addendum B.3). */
        const val WRITE_STATUS_POSITION_LOCKED = 0x06

        fun statusText(code: Int): String = when (code) {
            WRITE_STATUS_POSITION_LOCKED -> "position is locked: a re-commission operation by the service engineer is required"
            else -> ServerScreenController.writeStatusText(code)
        }
    }
}

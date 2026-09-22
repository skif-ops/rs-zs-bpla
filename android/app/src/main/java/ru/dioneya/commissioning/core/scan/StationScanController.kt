package ru.dioneya.commissioning.core.scan

import ru.dioneya.commissioning.core.StationIdentity
import ru.dioneya.commissioning.core.ble.BleException
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.GattContractV01
import java.util.UUID

/**
 * Station picker logic: collects BLE advertisements, keeps the ones that carry
 * the Device Info service or the `DIO-EVT-` local name, orders them by signal,
 * optionally narrows to an expected serial (typed or scanned from the QR
 * label), and confirms the choice by reading the `identity` characteristic.
 * Pure Kotlin; the Activity feeds advertisements and renders [State].
 */
class StationScanController(private val listener: (State) -> Unit) {

    data class Advertisement(val address: String, val name: String?, val serviceUuids: List<UUID>, val rssi: Int)

    data class Candidate(val address: String, val name: String?, val rssi: Int, val lastSeenMs: Long) {
        /** Serial derived from the advertised local name when it is `DIO-EVT-xxx`. */
        val advertisedSerial: String? get() = name?.takeIf { SERIAL_IN_NAME.matches(it) }
    }

    enum class Phase { SCANNING, CONFIRMING, CONFIRMED, MISMATCH, ERROR }

    data class State(
        val phase: Phase = Phase.SCANNING,
        val candidates: List<Candidate> = emptyList(),
        val expectedSerial: String? = null,
        val selected: Candidate? = null,
        val identity: StationIdentity? = null,
        val message: String = "",
    )

    @Volatile var state: State = State()
        private set
    private val seen = LinkedHashMap<String, Candidate>()

    private fun emit(next: State) { state = next; listener(next) }

    /** Expected serial from QR/manual entry; empty clears the filter. Returns false when the text is not a valid pilot serial. */
    fun setExpectedSerial(text: String): Boolean {
        val s = text.trim().uppercase()
        if (s.isEmpty()) { emit(state.copy(expectedSerial = null, candidates = visible(null))); return true }
        if (!SERIAL_IN_NAME.matches(s)) return false
        emit(state.copy(expectedSerial = s, candidates = visible(s)))
        return true
    }

    /** Feeds one advertisement; returns true when it was accepted as a station. */
    fun onAdvertisement(adv: Advertisement, nowMs: Long): Boolean {
        val isStation = adv.serviceUuids.contains(GattContractV01.SERVICE_DEVICE_INFO) || (adv.name != null && SERIAL_IN_NAME.matches(adv.name))
        if (!isStation) return false
        seen[adv.address] = Candidate(adv.address, adv.name ?: seen[adv.address]?.name, adv.rssi, nowMs)
        if (state.phase == Phase.SCANNING) emit(state.copy(candidates = visible(state.expectedSerial, nowMs)))
        return true
    }

    /** Drops stations not seen for [STALE_MS]. */
    fun expire(nowMs: Long) {
        val before = seen.size
        seen.values.removeAll { nowMs - it.lastSeenMs > STALE_MS }
        if (seen.size != before && state.phase == Phase.SCANNING) emit(state.copy(candidates = visible(state.expectedSerial, nowMs)))
    }

    private fun visible(expected: String?, nowMs: Long = Long.MAX_VALUE): List<Candidate> =
        seen.values.filter { expected == null || it.advertisedSerial == null || it.advertisedSerial == expected }
            .sortedByDescending { it.rssi }

    /**
     * Connects to [candidate] through [session], reads and validates `identity`; with an
     * expected serial the station must match it.  Blocking: run on a background thread.
     */
    fun confirm(candidate: Candidate, session: BleSession) {
        emit(state.copy(phase = Phase.CONFIRMING, selected = candidate, identity = null, message = ""))
        try {
            session.run({ session.connect() }, GattContractV01.TIMEOUT_CONNECT_MS + 1000)
            val raw = session.run({ session.readLong(GattContractV01.CHAR_IDENTITY) })
            val identity = IdentityCodec.decode(raw)
            if (identity == null) { emit(state.copy(phase = Phase.ERROR, message = "identity: malformed record")); return }
            val problems = identity.validate()
            if (problems.isNotEmpty()) { emit(state.copy(phase = Phase.ERROR, identity = identity, message = "identity: " + problems.joinToString(", "))); return }
            val expected = state.expectedSerial
            if (expected != null && identity.serial != expected) {
                emit(state.copy(phase = Phase.MISMATCH, identity = identity, message = "station reports ${identity.serial}, expected $expected"))
                return
            }
            emit(state.copy(phase = Phase.CONFIRMED, identity = identity, message = "${identity.serial} station_id ${identity.stationId} fw ${identity.firmwareVersion}"))
        } catch (e: BleException) {
            emit(state.copy(phase = Phase.ERROR, message = e.message ?: "BLE error"))
        }
    }

    /** Back to scanning without losing the candidate list. */
    fun resume() { emit(state.copy(phase = Phase.SCANNING, selected = null, identity = null, message = "")) }

    companion object {
        const val STALE_MS = 15_000L
        val SERIAL_IN_NAME = Regex("DIO-EVT-(00[1-9]|0[1-3][0-9]|040|B01)")
    }
}

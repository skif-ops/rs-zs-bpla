package ru.dioneya.commissioning.core.secrets

import ru.dioneya.commissioning.core.ble.BleException
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.GattContractV01
import ru.dioneya.commissioning.core.server.ServerScreenController

/**
 * `station_secrets` (0x0206, ICD v0.3): read the presence map, write a bundle, clear the record.
 *
 * Policy on the station: service mode + secured link; a blank station takes the first bundle from the
 * installer, anything stored is changed only by the engineer (B.9) - the app shows the outcome and does
 * not try to guess.  Blocking calls; run on a background thread.
 */
class StationSecretsController(private val session: BleSession, private val timeoutMs: Long = GattContractV01.TIMEOUT_SECRETS_MS) {
    enum class Outcome { OK, NOT_IN_SERVICE_MODE, ENGINEER_REQUIRED, REJECTED, STORAGE_ERROR, PROTOCOL_ERROR, BLE_ERROR }

    data class Result(val outcome: Outcome, val presence: StationSecretsPresence?, val message: String)

    fun readPresence(): StationSecretsPresence? =
        StationSecretsPresence.decode(session.run({ session.readLong(GattContractV01.CHAR_STATION_SECRETS) }))

    fun write(bundle: StationSecretsBundle): Result {
        if (bundle.isEmpty) return Result(Outcome.REJECTED, null, "the bundle carries nothing to write")
        return exchange(bundle.toCborPatch(), "written: " + bundle.summary())
    }

    fun clear(): Result = exchange(StationSecretsBundle.clearPatch(), "station secrets cleared")

    private fun exchange(patch: ByteArray, okText: String): Result {
        val values = try {
            session.run({
                session.requestSequence(GattContractV01.CHAR_STATION_SECRETS, GattContractV01.CHAR_STATION_SECRETS, patch, timeoutMs) { it.size == 1 }
            }, timeoutMs + 2000)
        } catch (e: BleException) { return Result(Outcome.BLE_ERROR, null, ServerScreenController.bleErrorText(e)) }
        val status = values.last()[0].toInt() and 0xFF
        val presence = values.firstOrNull { it.size > 1 }?.let { StationSecretsPresence.decode(it) }
        return when (status) {
            GattContractV01.WRITE_STATUS_OK -> if (presence != null) Result(Outcome.OK, presence, okText)
                else Result(Outcome.PROTOCOL_ERROR, null, "station confirmed the write but sent no presence map")
            GattContractV01.WRITE_STATUS_NOT_IN_SERVICE_MODE -> Result(Outcome.NOT_IN_SERVICE_MODE, null, "station is not in service mode")
            GattContractV01.WRITE_STATUS_NOT_AUTHORIZED -> Result(Outcome.ENGINEER_REQUIRED, null,
                "station refused: link not secured, or secrets already provisioned - the engineer role is required to change them")
            GattContractV01.WRITE_STATUS_REJECTED_VALIDATION -> Result(Outcome.REJECTED, null, "station rejected the bundle (format)")
            GattContractV01.WRITE_STATUS_STORAGE_ERROR -> Result(Outcome.STORAGE_ERROR, null, "station could not store the record (NOR)")
            else -> Result(Outcome.PROTOCOL_ERROR, null, ServerScreenController.writeStatusText(status))
        }
    }
}

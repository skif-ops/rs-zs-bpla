package ru.dioneya.commissioning.core.role

import ru.dioneya.commissioning.core.ble.BleException
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.GattContractV01
import ru.dioneya.commissioning.core.server.ServerScreenController

/**
 * B.9 session role over `session_role` (0x0205): installer comes with the secured link,
 * engineer is proven by the HMAC challenge with the station's [EngineerKey].
 *
 *   write 01          → notify 01‖nonce16, then status 00
 *   write 02‖tag16    → notify 03‖role, then status 00  (else status 04 only)
 *
 * The role belongs to the BLE link: it is not stored and dies with the link; three wrong
 * tags lock elevation until the next link.  Blocking calls; run on a background thread.
 */
class SessionRoleController(private val session: BleSession, private val timeoutMs: Long = GattContractV01.TIMEOUT_ROLE_MS) {
    enum class Outcome { ENGINEER, WRONG_KEY, NOT_IN_SERVICE_MODE, LOCKED_OR_UNAVAILABLE, PROTOCOL_ERROR, BLE_ERROR }

    data class Result(val outcome: Outcome, val role: Int, val message: String)

    /** Reads the current role: 0 none, 1 installer, 2 engineer. */
    fun readRole(): Int {
        val v = session.run({ session.readLong(GattContractV01.CHAR_SESSION_ROLE) })   /* framed like every bridge read (B.2) */
        return if (v.isEmpty()) GattContractV01.ROLE_NONE else v[0].toInt() and 0xFF
    }

    /** Runs the challenge/response with [key]; the station serial must match the key's. */
    fun elevate(key: EngineerKey): Result {
        return try { elevateOrThrow(key) } catch (e: BleException) { Result(Outcome.BLE_ERROR, GattContractV01.ROLE_NONE, ServerScreenController.bleErrorText(e)) }
    }

    private fun elevateOrThrow(key: EngineerKey): Result {
        val challenge = exchange(byteArrayOf(GattContractV01.ROLE_OP_CHALLENGE))
        when (challenge.status) {
            GattContractV01.WRITE_STATUS_OK -> {}
            GattContractV01.WRITE_STATUS_NOT_IN_SERVICE_MODE -> return Result(Outcome.NOT_IN_SERVICE_MODE, GattContractV01.ROLE_NONE, "station is not in service mode")
            GattContractV01.WRITE_STATUS_NOT_AUTHORIZED -> return Result(Outcome.LOCKED_OR_UNAVAILABLE, GattContractV01.ROLE_NONE,
                "station refused the challenge: link not secured, key not provisioned or elevation locked for this link")
            else -> return Result(Outcome.PROTOCOL_ERROR, GattContractV01.ROLE_NONE, ServerScreenController.writeStatusText(challenge.status))
        }
        val nonce = challenge.values.firstOrNull { it.size == 1 + GattContractV01.ROLE_NONCE_BYTES && it[0] == GattContractV01.ROLE_OP_CHALLENGE }
            ?.copyOfRange(1, 1 + GattContractV01.ROLE_NONCE_BYTES)
            ?: return Result(Outcome.PROTOCOL_ERROR, GattContractV01.ROLE_NONE, "no nonce in the challenge answer")
        val response = exchange(byteArrayOf(GattContractV01.ROLE_OP_RESPONSE) + key.roleTag(nonce))
        when (response.status) {
            GattContractV01.WRITE_STATUS_OK -> {
                val result = response.values.firstOrNull { it.size == 2 && it[0] == GattContractV01.ROLE_OP_RESULT }
                    ?: return Result(Outcome.PROTOCOL_ERROR, GattContractV01.ROLE_NONE, "no role result after the response")
                val role = result[1].toInt() and 0xFF
                return if (role == GattContractV01.ROLE_ENGINEER) Result(Outcome.ENGINEER, role, "engineer role granted for this link")
                else Result(Outcome.PROTOCOL_ERROR, role, "station reported role $role")
            }
            GattContractV01.WRITE_STATUS_NOT_AUTHORIZED -> return Result(Outcome.WRONG_KEY, GattContractV01.ROLE_NONE, "station rejected the tag: wrong or rotated engineer key (3 failures lock the link)")
            GattContractV01.WRITE_STATUS_NOT_IN_SERVICE_MODE -> return Result(Outcome.NOT_IN_SERVICE_MODE, GattContractV01.ROLE_NONE, "station left service mode")
            else -> return Result(Outcome.PROTOCOL_ERROR, GattContractV01.ROLE_NONE, ServerScreenController.writeStatusText(response.status))
        }
    }

    private class Exchange(val values: List<ByteArray>, val status: Int)

    /** One write on session_role and every notified value up to and including the one-byte status. */
    private fun exchange(payload: ByteArray): Exchange {
        val values = session.run({
            session.requestSequence(GattContractV01.CHAR_SESSION_ROLE, GattContractV01.CHAR_SESSION_ROLE, payload, timeoutMs) { it.size == 1 }
        }, timeoutMs + 2000)
        return Exchange(values, values.last()[0].toInt() and 0xFF)
    }
}

package ru.dioneya.commissioning.core.role

import org.junit.Assert.assertEquals
import org.junit.Assert.assertArrayEquals
import org.junit.Test
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.FakeBleTransport
import ru.dioneya.commissioning.core.ble.GattContractV01
import java.util.UUID

/** Scripted station side of B.9 on the fake GATT: challenge → nonce + status, response → result + status. */
class SessionRoleControllerTest {
    private val roleChar: UUID = GattContractV01.CHAR_SESSION_ROLE
    private val key = EngineerKey("DIO-EVT-012", ByteArray(32) { (0xa0 + it).toByte() })

    /** Minimal station: one nonce per challenge, three failures lock the link, service-mode flag. */
    private class Station(val t: FakeBleTransport, val key: EngineerKey, var serviceMode: Boolean = true) {
        var role = GattContractV01.ROLE_INSTALLER
        var nonce: ByteArray? = null
        var failures = 0
        var counter = 0
        val writes = ArrayList<ByteArray>()
        fun status(code: Int) = t.notify(GattContractV01.CHAR_SESSION_ROLE, byteArrayOf(code.toByte()))
        fun onWrite(c: UUID, v: ByteArray) {
            if (c != GattContractV01.CHAR_SESSION_ROLE) return
            writes.add(v)
            val value = t.writtenValue(c) ?: return       // wait for the complete framed value
            t.writes.removeIf { it.first == c }
            if (!serviceMode) { status(GattContractV01.WRITE_STATUS_NOT_IN_SERVICE_MODE); return }
            when (value[0]) {
                GattContractV01.ROLE_OP_CHALLENGE -> {
                    if (failures >= 3) { status(GattContractV01.WRITE_STATUS_NOT_AUTHORIZED); return }
                    nonce = ByteArray(16) { (counter * 16 + it).toByte() }.also { counter++ }
                    t.notify(c, byteArrayOf(GattContractV01.ROLE_OP_CHALLENGE) + nonce!!)
                    status(GattContractV01.WRITE_STATUS_OK)
                }
                GattContractV01.ROLE_OP_RESPONSE -> {
                    val n = nonce
                    nonce = null                          // single use
                    if (n == null || failures >= 3 || !value.copyOfRange(1, value.size).contentEquals(key.roleTag(n))) {
                        failures++; status(GattContractV01.WRITE_STATUS_NOT_AUTHORIZED); return
                    }
                    role = GattContractV01.ROLE_ENGINEER
                    t.notify(c, byteArrayOf(GattContractV01.ROLE_OP_RESULT, GattContractV01.ROLE_ENGINEER.toByte()))
                    status(GattContractV01.WRITE_STATUS_OK)
                }
                else -> status(GattContractV01.WRITE_STATUS_REJECTED_VALIDATION)
            }
        }
    }

    private fun world(serviceMode: Boolean = true): Pair<Station, BleSession> {
        val t = FakeBleTransport(mtu = 247)
        val st = Station(t, key, serviceMode)
        t.onWrite = { c, v -> st.onWrite(c, v) }
        t.longValueProvider = { c -> if (c == roleChar) byteArrayOf(st.role.toByte()) else null }
        val s = BleSession(t, opTimeoutMs = 500)
        s.run({ s.connect() })
        return st to s
    }

    @Test fun elevatesWithTheRightKey() {
        val (st, s) = world()
        s.use {
            val c = SessionRoleController(s)
            assertEquals(GattContractV01.ROLE_INSTALLER, c.readRole())
            val r = c.elevate(key)
            assertEquals(SessionRoleController.Outcome.ENGINEER, r.outcome)
            assertEquals(GattContractV01.ROLE_ENGINEER, r.role)
            assertEquals(GattContractV01.ROLE_ENGINEER, c.readRole())
            assertEquals(2, st.writes.size)
            assertArrayEquals(byteArrayOf(GattContractV01.ROLE_OP_CHALLENGE), st.writes[0].copyOfRange(4, st.writes[0].size))   // first frame: [seq][flags][len16] 01
            assertEquals(1 + 16, st.writes[1].size - 4)                                                                          // 02‖tag16
            assertEquals(false, st.t.subscriptions[roleChar])                                                                      // unsubscribed after the exchange
        }
    }

    @Test fun wrongKeyIsRejectedAndThreeFailuresLockTheLink() {
        val (st, s) = world()
        s.use {
            val c = SessionRoleController(s)
            val wrong = EngineerKey("DIO-EVT-012", ByteArray(32) { 0x11 })
            repeat(3) { assertEquals(SessionRoleController.Outcome.WRONG_KEY, c.elevate(wrong).outcome) }
            assertEquals(3, st.failures)
            // locked: even the right key cannot get a challenge on this link
            assertEquals(SessionRoleController.Outcome.LOCKED_OR_UNAVAILABLE, c.elevate(key).outcome)
            assertEquals(GattContractV01.ROLE_INSTALLER, c.readRole())
        }
    }

    @Test fun keyOfAnotherStationFails() {
        val (_, s) = world()
        s.use {
            val other = EngineerKey("DIO-EVT-013", key.key)   // same bytes, other serial in the MAC input
            assertEquals(SessionRoleController.Outcome.WRONG_KEY, SessionRoleController(s).elevate(other).outcome)
        }
    }

    @Test fun outsideServiceModeAndSilentStation() {
        val (_, s) = world(serviceMode = false)
        s.use { assertEquals(SessionRoleController.Outcome.NOT_IN_SERVICE_MODE, SessionRoleController(s).elevate(key).outcome) }
        val silent = FakeBleTransport()
        BleSession(silent, opTimeoutMs = 200).use { s2 ->
            s2.run({ s2.connect() })
            val r = SessionRoleController(s2, timeoutMs = 300).elevate(key)   // no notification at all: BLE timeout surfaces as BLE_ERROR
            assertEquals(SessionRoleController.Outcome.BLE_ERROR, r.outcome)
        }
    }
}

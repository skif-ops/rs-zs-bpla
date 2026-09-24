package ru.dioneya.commissioning.core.secrets

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.dioneya.commissioning.core.CanonicalCbor
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.FakeBleTransport
import ru.dioneya.commissioning.core.ble.GattContractV01
import ru.dioneya.commissioning.core.role.EngineerKey
import java.util.UUID

/** Bundle parsing/encoding and the 0x0206 exchange against a scripted station (blank → installer OK, then engineer only). */
class StationSecretsTest {
    private val secretsChar: UUID = GattContractV01.CHAR_STATION_SECRETS
    private val export = """
        {"serial": "DIO-EVT-012", "engineer_key_hex": "a0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebf",
         "iccid1": "89701012345678901234", "iccid2": "", "context": "DIO-SECRETS-V1"}
    """.trimIndent()

    @Test fun parsesTheRegistryExport() {
        val b = StationSecretsBundle.fromExportJson(export)
        assertNotNull(b); b!!
        assertEquals("DIO-EVT-012", b.serial)
        assertArrayEquals(ByteArray(32) { (0xa0 + it).toByte() }, b.engineerKey)
        assertEquals("89701012345678901234", b.iccid1)
        assertNull(b.iccid2)
        assertNull(b.commandPublicKey)
        assertEquals("engineer key, ICCID 1 …1234", b.summary())
        /* patch: map(2) { 1: bstr32, 2: tstr } */
        val p = b.toCborPatch()
        assertEquals(0xa2, p[0].toInt() and 0xFF)
        assertEquals(0x01, p[1].toInt()); assertEquals(0x58, p[2].toInt() and 0xFF); assertEquals(32, p[3].toInt())
        assertEquals(0x02, p[36].toInt()); assertEquals(0x74, p[37].toInt() and 0xFF)
        assertEquals(2 + 34 + 22, p.size)
    }

    @Test fun rejectsForeignContextBadKeyAndBadIccid() {
        assertNull(StationSecretsBundle.fromExportJson(export.replace("DIO-SECRETS-V1", "DIO-ROLE-V1")))
        assertNull(StationSecretsBundle.fromExportJson(export.replace("a0a1", "zz")))
        assertNull(StationSecretsBundle.fromExportJson(export.replace("89701012345678901234", "1234")))
        assertNull(StationSecretsBundle.fromExportJson("{}"))
        val empty = StationSecretsBundle.fromExportJson("""{"serial": "X1", "context": "DIO-SECRETS-V1"}""")!!
        assertTrue(empty.isEmpty)
    }

    @Test fun presenceMapDecodes() {
        val w = CanonicalCbor.Writer(); w.map(5)
        w.uint(0); w.uint(3); w.uint(1); w.bool(true); w.uint(2); w.bool(true); w.uint(3); w.bool(false); w.uint(4); w.bool(false)
        val p = StationSecretsPresence.decode(w.toByteArray())!!
        assertEquals(3L, p.version); assertTrue(p.engineerKey); assertTrue(p.iccid1); assertFalse(p.iccid2); assertFalse(p.commandKey)
        assertEquals("v3: engineer key, ICCID 1", p.text())
        assertNull(StationSecretsPresence.decode(byteArrayOf(0x01)))
        assertTrue(StationSecretsPresence.decode(byteArrayOf(0xa0.toByte()))!!.isBlank)
    }

    /** Station: keeps a record, first write by anyone on a blank record, later writes only when [engineer]. */
    private class Station(val t: FakeBleTransport) {
        var version = 0L; var key: ByteArray? = null; var iccid1: String? = null; var iccid2: String? = null; var cmd: ByteArray? = null
        var engineer = false; var serviceMode = true
        fun blank() = key == null && iccid1 == null && iccid2 == null && cmd == null
        fun presence(): ByteArray { val w = CanonicalCbor.Writer(); w.map(5)
            w.uint(0); w.uint(version); w.uint(1); w.bool(key != null); w.uint(2); w.bool(iccid1 != null); w.uint(3); w.bool(iccid2 != null); w.uint(4); w.bool(cmd != null)
            return w.toByteArray() }
        fun status(code: Int) = t.notify(GattContractV01.CHAR_STATION_SECRETS, byteArrayOf(code.toByte()))
        fun onWrite(c: UUID, v: ByteArray) {
            if (c != GattContractV01.CHAR_STATION_SECRETS) return
            val value = t.writtenValue(c) ?: return
            t.writes.removeIf { it.first == c }
            if (!serviceMode) { status(GattContractV01.WRITE_STATUS_NOT_IN_SERVICE_MODE); return }
            if (!blank() && !engineer) { status(GattContractV01.WRITE_STATUS_NOT_AUTHORIZED); return }
            try {
                val r = CanonicalCbor.Reader(value); var clear = false
                var nk = key; var n1 = iccid1; var n2 = iccid2; var nc = cmd
                repeat(r.mapHeader()) {
                    when (r.uint()) {
                        1L -> nk = r.bytes().also { require(it.size == 32) }
                        2L -> n1 = r.text().ifEmpty { null }
                        3L -> n2 = r.text().ifEmpty { null }
                        4L -> nc = r.bytes().also { require(it.size == 32) }
                        5L -> clear = r.bool()
                        else -> throw IllegalArgumentException("key")
                    }
                }
                r.requireEnd()
                if (clear) { key = null; iccid1 = null; iccid2 = null; cmd = null; version = 0 } else { key = nk; iccid1 = n1; iccid2 = n2; cmd = nc; version++ }
            } catch (_: IllegalArgumentException) { status(GattContractV01.WRITE_STATUS_REJECTED_VALIDATION); return }
            t.notify(c, presence())
            status(GattContractV01.WRITE_STATUS_OK)
        }
    }

    private fun world(): Pair<Station, BleSession> {
        val t = FakeBleTransport(mtu = 247)
        val st = Station(t)
        t.onWrite = { c, v -> st.onWrite(c, v) }
        t.longValueProvider = { c -> if (c == secretsChar) st.presence() else null }
        val s = BleSession(t, opTimeoutMs = 500)
        s.run({ s.connect() })
        return st to s
    }

    @Test fun blankStationTakesTheFirstBundleThenNeedsTheEngineer() {
        val (st, s) = world()
        val ctl = StationSecretsController(s, timeoutMs = 500)
        assertTrue(ctl.readPresence()!!.isBlank)
        val bundle = StationSecretsBundle.fromExportJson(export)!!
        val r = ctl.write(bundle)
        assertEquals(StationSecretsController.Outcome.OK, r.outcome)
        assertEquals(1L, r.presence!!.version); assertTrue(r.presence.engineerKey); assertTrue(r.presence.iccid1); assertFalse(r.presence.iccid2)
        assertArrayEquals(bundle.engineerKey, st.key)
        /* installer again: refused */
        val again = ctl.write(StationSecretsBundle("DIO-EVT-012", null, null, "89702012345678901234", null))
        assertEquals(StationSecretsController.Outcome.ENGINEER_REQUIRED, again.outcome)
        assertNull(st.iccid2)
        /* engineer: merged, version 2 */
        st.engineer = true
        val merged = ctl.write(StationSecretsBundle("DIO-EVT-012", null, null, "89702012345678901234", null))
        assertEquals(StationSecretsController.Outcome.OK, merged.outcome)
        assertEquals(2L, merged.presence!!.version); assertTrue(merged.presence.engineerKey); assertTrue(merged.presence.iccid1); assertTrue(merged.presence.iccid2)
        assertEquals("89701012345678901234", st.iccid1)
        /* clear */
        val cleared = ctl.clear()
        assertEquals(StationSecretsController.Outcome.OK, cleared.outcome)
        assertTrue(cleared.presence!!.isBlank); assertNull(st.key)
        /* empty bundle never reaches the station */
        assertEquals(StationSecretsController.Outcome.REJECTED, ctl.write(StationSecretsBundle("DIO-EVT-012", null, null, null, null)).outcome)
        /* service mode gate */
        st.serviceMode = false
        assertEquals(StationSecretsController.Outcome.NOT_IN_SERVICE_MODE, ctl.write(bundle).outcome)
    }

    @Test fun keyHexRoundTrip() {
        val k = ByteArray(32) { (0x10 + it).toByte() }
        assertArrayEquals(k, EngineerKey.hexToBytes(EngineerKey.bytesToHex(k)))
    }
}

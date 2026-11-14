package ru.dioneya.commissioning.core.server

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.dioneya.commissioning.core.CanonicalCbor
import ru.dioneya.commissioning.core.ServerEndpoint
import ru.dioneya.commissioning.core.StationConfigPatch
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.FakeBleTransport
import ru.dioneya.commissioning.core.ble.GattContractV01
import ru.dioneya.commissioning.core.server.ServerScreenController.Fields
import ru.dioneya.commissioning.core.server.ServerScreenController.Phase

class ServerScreenControllerTest {
    private val fields = Fields(
        hostPort = "muhoed.example.ru:8883", httpsPort = "443", caReference = "muhoed-ca-2026",
        fingerprintHex = "ab".repeat(32), tenant = "pilot1", topicPrefix = "zs/v1", version = "7", apn1 = "internet",
    )

    /** Station side of the fake: accepts the patch, then serves a read-back built from what was written. */
    private fun stationThatStores(t: FakeBleTransport, stationId: Long = 12, tamper: ((StationConfigPatch) -> StationConfigPatch)? = null) {
        t.onWrite = { c, _ ->
            if (c == GattContractV01.CHAR_CONFIG_WRITE) {
                val written = t.writtenValue(GattContractV01.CHAR_CONFIG_WRITE)
                if (written != null) {
                    val intended = decodePatch(written)
                    val stored = tamper?.invoke(intended) ?: intended
                    val record = stored.copy(stationId = stationId)
                    t.serveLong(GattContractV01.CHAR_CONFIG_READ, encodeReadback(record))
                    Thread { Thread.sleep(10); t.notify(GattContractV01.CHAR_CONFIG_WRITE, byteArrayOf(GattContractV01.WRITE_STATUS_OK.toByte())) }.start()
                }
            }
        }
    }

    private fun states(): MutableList<Phase> = mutableListOf()

    @Test fun applyWritesPatchReadsBackAndVerifiesHash() {
        val t = FakeBleTransport()
        stationThatStores(t)
        val seen = states()
        BleSession(t, 500).use { s ->
            val c = ServerScreenController(s) { seen.add(it.phase) }
            c.edit(fields)
            c.apply()
            assertEquals(Phase.VERIFIED, c.state.phase)
            assertEquals(listOf(Phase.EDITING, Phase.CONNECTING, Phase.WRITING, Phase.READING_BACK, Phase.VERIFIED), seen)
            assertEquals(12L, c.state.readback!!.stationId)
            assertEquals("muhoed.example.ru", c.state.readback!!.endpoint.host)
            assertEquals(64, c.state.stationHashHex.length)
            assertTrue(c.state.message.contains("station_id 12"))
            val patch = c.buildPatch()!!
            assertArrayEquals(patch.toCborPatch(), t.writtenValue(GattContractV01.CHAR_CONFIG_WRITE))
        }
    }

    @Test fun tamperedReadbackIsAMismatch() {
        val t = FakeBleTransport()
        stationThatStores(t) { it.copy(endpoint = it.endpoint.copy(mqttPort = 8884)) }
        BleSession(t, 500).use { s ->
            val c = ServerScreenController(s) {}
            c.edit(fields); c.apply()
            assertEquals(Phase.MISMATCH, c.state.phase)
            assertEquals(8884, c.state.readback!!.endpoint.mqttPort)
        }
    }

    @Test fun stationRejectionAndBleErrorsAreReported() {
        val t = FakeBleTransport()
        t.onWrite = { c, _ -> if (c == GattContractV01.CHAR_CONFIG_WRITE && t.writtenValue(c) != null)
            Thread { t.notify(c, byteArrayOf(GattContractV01.WRITE_STATUS_NOT_IN_SERVICE_MODE.toByte())) }.start() }
        BleSession(t, 500).use { s ->
            val c = ServerScreenController(s) {}
            c.edit(fields); c.apply()
            assertEquals(Phase.REJECTED, c.state.phase)
            assertEquals("station is not in service mode", c.state.message)
        }
        val down = FakeBleTransport(); down.connectFails = true
        BleSession(down, 500).use { s ->
            val c = ServerScreenController(s) {}
            c.edit(fields); c.apply()
            assertEquals(Phase.ERROR, c.state.phase)
            assertEquals("BLE disconnected", c.state.message)
        }
    }

    @Test fun invalidFieldsNeverReachTheStation() {
        val t = FakeBleTransport()
        BleSession(t, 500).use { s ->
            val c = ServerScreenController(s) {}
            c.edit(fields.copy(hostPort = "https://bad host", fingerprintHex = "zz", httpsPort = "70000", version = "0"))
            assertNull(c.buildPatch())
            assertEquals(Phase.INVALID, c.state.phase)
            assertTrue(c.state.errors.containsAll(listOf(ServerEndpoint.ERR_HOST, ServerEndpoint.ERR_FINGERPRINT, ServerEndpoint.ERR_HTTPS_PORT, StationConfigPatch.ERR_VERSION)))
            c.apply()
            assertEquals(0, t.connectCount)
            c.edit(fields.copy(fingerprintHex = ""))                  // empty = not pinned
            val p = c.buildPatch()
            assertNotNull(p)
            assertArrayEquals(ByteArray(32), p!!.endpoint.serverFingerprint)
            c.edit(fields.copy(hostPort = "[2001:db8::1]:8883"))
            assertEquals("2001:db8::1", c.buildPatch()!!.endpoint.host)
        }
    }

    @Test fun selfTestReportIsDecoded() {
        // firmware zs_selftest_encode vector: map(3){1:[1,3900], 8:[2,7], 9:[3,0]}
        val report = byteArrayOf(0xa3.toByte(), 0x01, 0x82.toByte(), 0x01, 0x19, 0x0f, 0x3c, 0x08, 0x82.toByte(), 0x02, 0x07, 0x09, 0x82.toByte(), 0x03, 0x00)
        val parsed = ServerScreenController.parseSelfTestReport(report)!!
        assertEquals(3, parsed.size)
        assertEquals("power", parsed[0].name); assertEquals("PASS", parsed[0].codeName); assertEquals(3900L, parsed[0].detail)
        assertEquals("lora_spi", parsed[1].name); assertEquals("FAIL", parsed[1].codeName)
        assertEquals("modem_at", parsed[2].name); assertEquals("SKIPPED", parsed[2].codeName)
        assertNull(ServerScreenController.parseSelfTestReport(report.copyOf(report.size - 1)))
        assertNull(ServerScreenController.parseSelfTestReport(byteArrayOf(0xa1.toByte(), 0x05, 0x81.toByte(), 0x01)))
        val t = FakeBleTransport()
        t.onWrite = { c, v -> if (c == GattContractV01.CHAR_SELF_TEST && v.last() == GattContractV01.SELF_TEST_RUN_ALL) Thread { t.notify(c, report) }.start() }
        BleSession(t, 500).use { s ->
            val c = ServerScreenController(s) {}
            c.runSelfTest()
            assertEquals(Phase.SELF_TEST_DONE, c.state.phase)
            assertEquals("self-test: failures", c.state.message)
            assertEquals(3, c.state.selfTest.size)
        }
    }

    // ---- helpers: decode the 11-key patch and encode the 14-key read-back as the station would ----
    private fun decodePatch(bytes: ByteArray): StationConfigPatch {
        val r = CanonicalCbor.Reader(bytes)
        val n = r.mapHeader()
        val m = HashMap<Long, Any>()
        repeat(n) {
            val k = r.uint()
            m[k] = when (k) {
                1L, 3L, 4L, 9L, 12L -> r.uint()
                6L -> r.bytes()
                else -> r.text()
            }
        }
        return StationConfigPatch(
            version = m[1L] as Long,
            endpoint = ServerEndpoint(host = m[2L] as String, mqttPort = (m[3L] as Long).toInt(), httpsPort = (m[4L] as Long).toInt(),
                caReference = m[5L] as String, serverFingerprint = m[6L] as ByteArray, tenant = m[7L] as String, topicPrefix = m[8L] as String),
            preferredSim = if (m[9L] == 1L) ru.dioneya.commissioning.core.SimSlot.SIM1 else ru.dioneya.commissioning.core.SimSlot.SIM2,
            apn1 = m[10L] as String, apn2 = m[11L] as String,
        )
    }

    private fun encodeReadback(p: StationConfigPatch): ByteArray {
        val w = CanonicalCbor.Writer()
        w.map(14)
        w.uint(1); w.uint(p.version)
        w.uint(2); w.text(p.endpoint.host)
        w.uint(3); w.uint(p.endpoint.mqttPort.toLong())
        w.uint(4); w.uint(p.endpoint.httpsPort.toLong())
        w.uint(5); w.text(p.endpoint.caReference)
        w.uint(6); w.bytes(p.endpoint.serverFingerprint)
        w.uint(7); w.text(p.endpoint.tenant)
        w.uint(8); w.text(p.endpoint.topicPrefix)
        w.uint(9); w.uint(if (p.preferredSim == ru.dioneya.commissioning.core.SimSlot.SIM1) 1 else 2)
        w.uint(10); w.text(p.apn1)
        w.uint(11); w.text(p.apn2)
        w.uint(12); w.uint(1)
        w.uint(13); w.uint(p.stationId)
        w.uint(14); w.bytes(p.stationHash())
        return w.toByteArray()
    }
}

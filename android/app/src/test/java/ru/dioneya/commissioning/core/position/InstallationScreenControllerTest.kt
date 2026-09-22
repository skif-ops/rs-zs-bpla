package ru.dioneya.commissioning.core.position

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.dioneya.commissioning.core.CoordinateSource
import ru.dioneya.commissioning.core.InstallationCommissioningContract
import ru.dioneya.commissioning.core.InstallationCommissioningOperation
import ru.dioneya.commissioning.core.InstallationCommissioningReadback
import ru.dioneya.commissioning.core.InstallationCommissioningRequest
import ru.dioneya.commissioning.core.InstallationCommissioningRole
import ru.dioneya.commissioning.core.InstallationPosition
import ru.dioneya.commissioning.core.PositionTrustPolicy
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.FakeBleTransport
import ru.dioneya.commissioning.core.ble.GattContractV01
import ru.dioneya.commissioning.core.position.InstallationScreenController.Fields
import ru.dioneya.commissioning.core.position.InstallationScreenController.Phase

class InstallationScreenControllerTest {
    private val char = GattContractV01.CHAR_INSTALLATION_POSITION
    private val moscow = Fields(latitude = "55.7558000", longitude = "37.6173000", altitudeM = "156.4", accuracyM = "4", source = CoordinateSource.SURVEYED)
    private var clock = 1_800_000_000_000_000L

    /** Station emulator: stores the request, computes the contract hash, serves the read-back; optional tampering / lock. */
    private class Station(val t: FakeBleTransport) {
        var stored: InstallationCommissioningReadback? = null
        var generation = 0L
        var tamper: ((InstallationCommissioningReadback) -> InstallationCommissioningReadback)? = null
        var enforceLock = true
        init {
            t.longValueProvider = { c -> if (c == GattContractV01.CHAR_INSTALLATION_POSITION) current() else null }
            t.onWrite = { c, _ ->
                if (c == GattContractV01.CHAR_INSTALLATION_POSITION) t.writtenValue(c)?.let { bytes ->
                    val req = decodeRequest(bytes)
                    val status = when {
                        stored != null && req.operation == InstallationCommissioningOperation.INITIAL && enforceLock -> InstallationScreenController.WRITE_STATUS_POSITION_LOCKED
                        stored != null && req.position.version <= stored!!.position.version -> GattContractV01.WRITE_STATUS_REJECTED_VERSION
                        else -> GattContractV01.WRITE_STATUS_OK
                    }
                    if (status == GattContractV01.WRITE_STATUS_OK) {
                        generation++
                        stored = InstallationCommissioningReadback(req.position, req.policy, req.commissionedTimeUs, generation, InstallationCommissioningContract.canonicalHashHex(req), true)
                    }
                    t.writes.clear()
                    Thread { Thread.sleep(5); t.notify(c, byteArrayOf(status.toByte())) }.start()
                }
            }
        }
        fun current(): ByteArray {
            val rb = stored?.let { tamper?.invoke(it) ?: it }
            return if (rb == null) byteArrayOf(0xa0.toByte()) else InstallationPositionCodec.encodeReadback(rb)
        }
        private fun decodeRequest(b: ByteArray): InstallationCommissioningRequest {
            val r = InstallationPositionCodec.Reader(b)
            val n = r.mapHeader(); val m = HashMap<Long, Any>()
            repeat(n) { val k = r.uint(); m[k] = when (k) { 2L, 3L, 4L -> r.int(); 8L -> r.bool(); else -> r.uint() } }
            r.requireEnd()
            return InstallationCommissioningRequest(
                if (m[1L] == 0L) InstallationCommissioningOperation.INITIAL else InstallationCommissioningOperation.RECOMMISSION,
                InstallationPosition((m[2L] as Long).toInt(), (m[3L] as Long).toInt(), (m[4L] as Long).toInt(), (m[5L] as Long).toInt(),
                    CoordinateSource.entries.first { InstallationPositionCodec.sourceId(it) == m[6L] }, m[7L] as Long, m[8L] as Boolean),
                PositionTrustPolicy((m[10L] as Long).toInt(), (m[11L] as Long).toInt(), (m[12L] as Long).toInt(), (m[13L] as Long).toInt(), (m[14L] as Long).toInt()),
                m[9L] as Long,
            )
        }
    }

    @Test fun codecRoundTripsSignedCoordinatesAndDetectsMalformedInput() {
        val req = InstallationCommissioningRequest(InstallationCommissioningOperation.INITIAL,
            InstallationPosition(-338_688_000, 1_512_093_000, -50, 7, CoordinateSource.PHONE_LOCATION, 3, true), PositionTrustPolicy(), 1_800_000_000_123_456L)
        val rb = InstallationCommissioningReadback(req.position, req.policy, req.commissionedTimeUs, 5, InstallationCommissioningContract.canonicalHashHex(req), true)
        val bytes = InstallationPositionCodec.encodeReadback(rb)
        assertEquals(InstallationPositionCodec.Readback.Stored(rb), InstallationPositionCodec.decodeReadback(bytes))
        assertEquals(InstallationPositionCodec.Readback.Empty, InstallationPositionCodec.decodeReadback(byteArrayOf(0xa0.toByte())))
        assertNull(InstallationPositionCodec.decodeReadback(bytes.copyOf(bytes.size - 1)))
        assertNull(InstallationPositionCodec.decodeReadback(bytes + 0))
        val enc = InstallationPositionCodec.encodeRequest(req)
        assertArrayEquals(byteArrayOf(0xae.toByte(), 0x01, 0x00, 0x02, 0x3a, 0x14, 0x2f, 0xf7.toByte(), 0xff.toByte()), enc.copyOf(9))   // map(14), 1:0, 2: -338688000 = nint(338687999 = 0x142ff7ff)
        assertEquals(0xf5.toByte(), enc[enc.indexOf(0x08.toByte()) + 1])                     // 8: true
    }

    @Test fun initialCommissioningWritesReadsBackAndVerifies() {
        val t = FakeBleTransport(); val st = Station(t)
        val seen = mutableListOf<Phase>()
        BleSession(t, 500).use { s ->
            val c = InstallationScreenController(s, { clock }) { seen.add(it.phase) }
            c.readStored()
            assertEquals(Phase.EDITING, c.state.phase); assertNull(c.state.stored)
            assertEquals(InstallationCommissioningOperation.INITIAL, c.state.operation)
            c.edit(moscow)
            c.apply()
            assertEquals(Phase.VERIFIED, c.state.phase)
            val rb = c.state.readback!!
            assertEquals(557_558_000, rb.position.latE7); assertEquals(376_173_000, rb.position.lonE7); assertEquals(1564, rb.position.altDm)
            assertEquals(1L, rb.position.version); assertEquals(1L, rb.storageGeneration); assertTrue(rb.auditCommitted)
            assertEquals(listOf(Phase.READING, Phase.EDITING, Phase.EDITING, Phase.WRITING, Phase.READING_BACK, Phase.VERIFIED), seen)
            // the same installer cannot write again: the position is locked (INITIAL rejected by the station)
            c.edit(moscow.copy(latitude = "55.7559"))
            val before = st.generation
            // controller now knows the stored record and proposes RECOMMISSION; force INITIAL to exercise the lock
            c.apply()
            assertEquals(Phase.VERIFIED, c.state.phase)                 // recommission v2 by the controller's own choice
            assertEquals(2L, c.state.readback!!.position.version); assertEquals(before + 1, st.generation)
        }
    }

    @Test fun lockedStationRejectsInitialAndVersionMustGrow() {
        val t = FakeBleTransport(); val st = Station(t)
        BleSession(t, 500).use { s ->
            val c = InstallationScreenController(s, { clock }) {}
            c.readStored(); c.edit(moscow); c.apply()
            assertEquals(Phase.VERIFIED, c.state.phase)
            // a second app instance that never read the station sends INITIAL: rejected with the lock code
            val fresh = InstallationScreenController(s, { clock }) {}
            fresh.edit(moscow)
            fresh.apply()
            assertEquals(Phase.REJECTED, fresh.state.phase)
            assertTrue(fresh.state.message.contains("locked"))
            // after reading it recommissions with version 2 -> accepted
            fresh.readStored()
            assertEquals(InstallationCommissioningOperation.RECOMMISSION, fresh.state.operation)
            fresh.edit(moscow.copy(accuracyM = "3")); fresh.apply()
            assertEquals(Phase.VERIFIED, fresh.state.phase); assertEquals(2L, st.stored!!.position.version)
        }
    }

    @Test fun tamperedReadbackAndInvalidFieldsAreCaught() {
        val t = FakeBleTransport(); val st = Station(t)
        st.tamper = { it.copy(commissioningHashHex = "00".repeat(32)) }
        BleSession(t, 500).use { s ->
            val c = InstallationScreenController(s, { clock }) {}
            c.readStored(); c.edit(moscow); c.apply()
            assertEquals(Phase.MISMATCH, c.state.phase)
            assertTrue(c.state.errors.contains("commissioning_hash_mismatch"))
            st.tamper = { it.copy(auditCommitted = false) }
            c.edit(moscow); c.apply()
            assertEquals(Phase.MISMATCH, c.state.phase); assertTrue(c.state.errors.contains("commissioning_audit_not_committed"))
            c.edit(moscow.copy(latitude = "91", accuracyM = "0"))
            assertNull(c.buildRequest())
            assertEquals(Phase.INVALID, c.state.phase)
            assertTrue(c.state.errors.containsAll(listOf("invalid_installation_latitude", "invalid_installation_accuracy")))
            // installer cannot change the policy; the engineer can
            c.edit(moscow.copy(policy = PositionTrustPolicy(warningDistanceM = 30)))
            assertNull(c.buildRequest()); assertTrue(c.state.errors.contains("engineer_role_required_for_position_policy"))
            c.setRole(InstallationCommissioningRole.SERVICE_ENGINEER)
            assertNotNull(c.buildRequest())
        }
    }

    @Test fun phoneLocationFillsTheFields() {
        val c = InstallationScreenController(BleSession(FakeBleTransport(), 500), { clock }) {}
        c.useLocation(InstallationPosition(-338_688_123, 1_512_093_456, 421, 12, CoordinateSource.PHONE_LOCATION))
        assertEquals("-33.8688123", c.state.fields.latitude); assertEquals("151.2093456", c.state.fields.longitude)
        assertEquals("42.1", c.state.fields.altitudeM); assertEquals("12", c.state.fields.accuracyM)
        assertEquals(CoordinateSource.PHONE_LOCATION, c.state.fields.source)
        val r = c.buildRequest()!!
        assertEquals(-338_688_123, r.position.latE7); assertEquals(421, r.position.altDm)
    }
}

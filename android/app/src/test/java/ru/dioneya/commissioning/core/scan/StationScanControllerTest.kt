package ru.dioneya.commissioning.core.scan

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.dioneya.commissioning.core.LoRaRegion
import ru.dioneya.commissioning.core.StationIdentity
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.FakeBleTransport
import ru.dioneya.commissioning.core.ble.GattContractV01
import ru.dioneya.commissioning.core.scan.StationScanController.Advertisement
import ru.dioneya.commissioning.core.scan.StationScanController.Phase
import java.util.UUID

class StationScanControllerTest {
    private val svc = listOf(GattContractV01.SERVICE_DEVICE_INFO)
    private val other = listOf(UUID.fromString("0000180f-0000-1000-8000-00805f9b34fb"))
    private val identity = StationIdentity("DIO-EVT-012", 12, "Rev.A", "0.1.0-b1", "0.1.0", LoRaRegion.RU868)

    @Test fun identityCodecRoundTripsAndRejectsMalformed() {
        val bytes = IdentityCodec.encode(identity)
        assertEquals(identity, IdentityCodec.decode(bytes))
        assertNull(IdentityCodec.decode(bytes.copyOf(bytes.size - 1)))
        assertNull(IdentityCodec.decode(bytes + byteArrayOf(0)))
        val swapped = bytes.copyOf(); swapped[1] = 2; swapped[15] = 1     // key order violated
        assertNull(IdentityCodec.decode(swapped))
        assertEquals(LoRaRegion.EU868, IdentityCodec.decode(IdentityCodec.encode(identity.copy(region = LoRaRegion.EU868)))!!.region)
        assertArrayEquals(byteArrayOf(0xa6.toByte(), 0x01, 0x6b), bytes.copyOf(3))   // map(6), key 1, text(11)
    }

    @Test fun onlyStationsAreListedSortedBySignalAndExpired() {
        val seen = mutableListOf<Int>()
        val c = StationScanController { seen.add(it.candidates.size) }
        assertTrue(c.onAdvertisement(Advertisement("AA:00:00:00:00:01", "DIO-EVT-001", svc, -70), 1000))
        assertFalse(c.onAdvertisement(Advertisement("AA:00:00:00:00:09", "Headphones", other, -40), 1000))
        assertTrue(c.onAdvertisement(Advertisement("AA:00:00:00:00:02", null, svc, -50), 1100))          // no name, service only
        assertTrue(c.onAdvertisement(Advertisement("AA:00:00:00:00:03", "DIO-EVT-B01", emptyList(), -60), 1200)) // name only
        assertFalse(c.onAdvertisement(Advertisement("AA:00:00:00:00:04", "DIO-EVT-041", emptyList(), -30), 1200)) // outside the pilot
        assertEquals(listOf("AA:00:00:00:00:02", "AA:00:00:00:00:03", "AA:00:00:00:00:01"), c.state.candidates.map { it.address })
        c.onAdvertisement(Advertisement("AA:00:00:00:00:01", "DIO-EVT-001", svc, -45), 1300)               // rssi update
        assertEquals("AA:00:00:00:00:01", c.state.candidates.first().address)
        assertEquals("DIO-EVT-B01", c.state.candidates[2].advertisedSerial)
        assertNull(c.state.candidates[1].advertisedSerial)
        c.expire(1200 + StationScanController.STALE_MS + 1)                                          // 02 and 03 stale, 01 refreshed at 1300
        assertEquals(listOf("AA:00:00:00:00:01"), c.state.candidates.map { it.address })
        assertEquals(1, c.state.candidates.size)
        assertTrue(seen.isNotEmpty())
    }

    @Test fun expectedSerialNarrowsTheListButKeepsUnnamedStations() {
        val c = StationScanController {}
        c.onAdvertisement(Advertisement("A1", "DIO-EVT-001", svc, -70), 0)
        c.onAdvertisement(Advertisement("A2", "DIO-EVT-002", svc, -60), 0)
        c.onAdvertisement(Advertisement("A3", null, svc, -65), 0)
        assertFalse(c.setExpectedSerial("DIO-EVT-999"))
        assertTrue(c.setExpectedSerial("dio-evt-002"))
        assertEquals(listOf("A2", "A3"), c.state.candidates.map { it.address })
        assertTrue(c.setExpectedSerial(""))
        assertEquals(3, c.state.candidates.size)
    }

    @Test fun confirmReadsIdentityAndChecksTheExpectedSerial() {
        val t = FakeBleTransport()
        t.serveLong(GattContractV01.CHAR_IDENTITY, IdentityCodec.encode(identity))
        val c = StationScanController {}
        c.onAdvertisement(Advertisement("A1", "DIO-EVT-012", svc, -50), 0)
        c.onAdvertisement(Advertisement("A2", null, svc, -60), 0)                                    // unnamed: stays listed under any expected serial
        BleSession(t, 500).use { s ->
            c.confirm(c.state.candidates[0], s)
            assertEquals(Phase.CONFIRMED, c.state.phase)
            assertEquals(identity, c.state.identity)
            assertTrue(c.state.message.contains("station_id 12"))
            // expected serial differs from what the station reports
            t.serveLong(GattContractV01.CHAR_IDENTITY, IdentityCodec.encode(identity))
            c.resume(); c.setExpectedSerial("DIO-EVT-013")
            assertEquals(listOf("A2"), c.state.candidates.map { it.address })
            c.confirm(c.state.candidates[0], s)
            assertEquals(Phase.MISMATCH, c.state.phase)
            // invalid identity (bench serial with a lot station_id) is an error, not a confirmation
            t.serveLong(GattContractV01.CHAR_IDENTITY, IdentityCodec.encode(identity.copy(serial = "DIO-EVT-B01", stationId = 12, region = LoRaRegion.EU868)))
            c.resume(); c.setExpectedSerial("")
            c.confirm(c.state.candidates[0], s)
            assertEquals(Phase.ERROR, c.state.phase)
            assertTrue(c.state.message.contains("invalid_pilot_region"))
            // malformed record
            t.readFrames[GattContractV01.CHAR_IDENTITY] = ArrayDeque(listOf(byteArrayOf(0, 3, 0, 1, 0xff.toByte())))
            c.resume(); c.confirm(c.state.candidates[0], s)
            assertEquals(Phase.ERROR, c.state.phase)
        }
        val down = FakeBleTransport(); down.connectFails = true
        BleSession(down, 500).use { s -> c.resume(); c.confirm(c.state.candidates[0], s); assertEquals(Phase.ERROR, c.state.phase) }
    }
}

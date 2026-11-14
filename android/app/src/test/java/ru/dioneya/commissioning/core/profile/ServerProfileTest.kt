package ru.dioneya.commissioning.core.profile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import ru.dioneya.commissioning.core.SimSlot
import ru.dioneya.commissioning.core.server.ServerScreenController

class ServerProfileTest {
    /** Known answer shared with server/tests/test_pki_labels.py::test_server_profile_qr_payload_and_command. */
    private val vector = "DIOS1;H=muhoed.example.ru:8883;P=443;CA=dioneya-root;F=" + "ab".repeat(32) + ";T=zs/v1;C=F27A"
    private val profile = ServerProfile("muhoed.example.ru", 8883, 443, "dioneya-root", "ab".repeat(32))

    @Test fun decodesTheServerVectorAndReencodes() {
        assertEquals(profile, ServerProfile.decode(vector))
        assertEquals(vector, profile.encode())
        val v6 = ServerProfile("[2001:db8::10]", 8883, 0, "dioneya-root", "cd".repeat(32))
        assertEquals(v6, ServerProfile.decode(v6.encode()))
        assertNull(ServerProfile.decode(vector.dropLast(1) + "B"))
        assertNull(ServerProfile.decode(vector.replace("DIOS1", "DIOS2")))
        assertNull(ServerProfile.decode(vector.replace(";T=zs/v1", "")))
        assertNull(ServerProfile.decode("DIO1;S=DIO-EVT-012;ID=12;T=pilot1;K=JBSWY3DPEHPK3PXPJBSWY3DPEH;C=C5A3"))   // a station label is not a profile
    }

    @Test fun mapsToAndFromScreenFields() {
        val f = profile.copy(apn1 = "internet", preferredSim = SimSlot.SIM2).toFields(ServerScreenController.Fields(tenant = "pilot1", version = "3"))
        assertEquals("muhoed.example.ru:8883", f.hostPort); assertEquals("443", f.httpsPort); assertEquals("pilot1", f.tenant); assertEquals("3", f.version)
        assertEquals("internet", f.apn1); assertEquals(SimSlot.SIM2, f.preferredSim)
        val back = ServerProfile.fromFields(f)!!
        assertEquals(profile.copy(apn1 = "internet", preferredSim = SimSlot.SIM2), back)
        assertEquals("[2001:db8::10]", ServerProfile.fromFields(f.copy(hostPort = "[2001:db8::10]:8883"))!!.host)
        assertNull(ServerProfile.fromFields(f.copy(fingerprintHex = "")))          // unpinned endpoints are not saved as a profile
        assertNull(ServerProfile.fromFields(f.copy(hostPort = "https://x")))
    }

    @Test fun storeRoundTripsWithLocalExtras() {
        val store = MemoryServerProfileStore()
        assertNull(store.load())
        store.save(profile.copy(apn1 = "internet.mts.ru", apn2 = "internet.beeline.ru", preferredSim = SimSlot.SIM2))
        val loaded = store.load()
        assertNotNull(loaded)
        assertEquals("internet.beeline.ru", loaded!!.apn2); assertEquals(SimSlot.SIM2, loaded.preferredSim); assertEquals(profile.fingerprintHex, loaded.fingerprintHex)
        assertNull(ServerProfileStore.Text.parse("garbage\napn1=x"))
        store.clear(); assertNull(store.load())
    }
}

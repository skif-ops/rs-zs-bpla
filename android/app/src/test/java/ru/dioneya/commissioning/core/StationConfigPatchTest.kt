package ru.dioneya.commissioning.core

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Known-answer vectors are printed by firmware/tests/test_station_config.c
 * (REF_HASH, REF_PATCH, REF_READBACK) and must stay identical on both sides.
 */
class StationConfigPatchTest {
    private val fingerprint = ByteArray(32) { it.toByte() }

    private fun reference() = StationConfigPatch(
        version = 3,
        endpoint = ServerEndpoint(
            host = "10.20.30.40",
            mqttPort = 8883,
            httpsPort = 8443,
            caReference = "dioneya-root-2026",
            serverFingerprint = fingerprint,
            tenant = "pilot",
            topicPrefix = "zs/v1",
        ),
        preferredSim = SimSlot.SIM2,
        apn1 = "internet.mts.ru",
        apn2 = "internet",
        stationId = 7,
        region = LoRaRegion.RU868,
    )

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
    private fun unhex(s: String) = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

    @Test
    fun referenceIsValid() {
        assertTrue(reference().validate().isEmpty())
    }

    @Test
    fun patchMatchesFirmwareVector() {
        assertEquals(REF_PATCH, hex(reference().toCborPatch()))
    }

    @Test
    fun stationHashMatchesFirmwareVector() {
        assertEquals(REF_HASH, hex(reference().stationHash()))
    }

    @Test
    fun readbackFromFirmwareVectorMatchesIntendedWrite() {
        val readback = StationConfigPatch.parseReadback(unhex(REF_READBACK))
        assertNotNull(readback)
        assertEquals(7L, readback!!.config.stationId)
        assertEquals(LoRaRegion.RU868, readback.config.region)
        assertTrue(readback.matches(reference()))
        assertFalse(readback.matches(reference().copy(version = 4)))
        assertFalse(readback.matches(reference().copy(endpoint = reference().endpoint.copy(host = "10.20.30.41"))))
    }

    @Test
    fun readbackRejectsTamperedHashAndMalformedInput() {
        val tampered = unhex(REF_READBACK).also { it[it.size - 1] = (it[it.size - 1].toInt() xor 1).toByte() }
        val parsed = StationConfigPatch.parseReadback(tampered)
        assertNotNull(parsed)
        assertFalse(parsed!!.matches(reference()))
        assertNull(StationConfigPatch.parseReadback(unhex(REF_READBACK).copyOf(20)))
        assertNull(StationConfigPatch.parseReadback(byteArrayOf(0xbf.toByte(), 0x01, 0x03, 0xff.toByte())))
        assertNull(StationConfigPatch.parseReadback(unhex(REF_READBACK) + byteArrayOf(0)))
    }

    @Test
    fun hostValidationMatchesFirmwareRules() {
        assertTrue(HostValidator.isIpv4("10.20.30.40"))
        assertTrue(HostValidator.isIpv4("255.255.255.255"))
        assertFalse(HostValidator.isIpv4("256.1.1.1"))
        assertFalse(HostValidator.isIpv4("1.2.3"))
        assertFalse(HostValidator.isIpv4("01.2.3.4"))
        assertFalse(HostValidator.isIpv4("1.2.3.4."))
        assertTrue(HostValidator.isIpv6("2001:db8::1"))
        assertTrue(HostValidator.isIpv6("::1"))
        assertTrue(HostValidator.isIpv6("fe80:0:0:0:0:0:0:1"))
        assertFalse(HostValidator.isIpv6("2001:db8:::1"))
        assertFalse(HostValidator.isIpv6("2001:db8::1::2"))
        assertFalse(HostValidator.isIpv6("12345::1"))
        assertFalse(HostValidator.isIpv6("1:2:3:4:5:6:7:8:9"))
        assertTrue(HostValidator.isHostname("muhoed.example.ru"))
        assertTrue(HostValidator.isHostname("srv-1"))
        assertFalse(HostValidator.isHostname("-bad.ru"))
        assertFalse(HostValidator.isHostname("bad-.ru"))
        assertFalse(HostValidator.isHostname("bad..ru"))
        assertFalse(HostValidator.isHostname("bad_host.ru"))
        assertFalse(HostValidator.isHostname("123.456"))
        assertFalse(HostValidator.isValidHost("mqtts://x.ru"))
        assertFalse(HostValidator.isValidHost(""))
    }

    @Test
    fun endpointValidationReportsEachField() {
        val ok = reference().endpoint
        assertTrue(ok.validate().isEmpty())
        assertTrue(ServerEndpoint.ERR_MQTT_PORT in ok.copy(mqttPort = 0).validate())
        assertTrue(ServerEndpoint.ERR_MQTT_PORT in ok.copy(mqttPort = 70000).validate())
        assertTrue(ServerEndpoint.ERR_HTTPS_PORT in ok.copy(httpsPort = 8883).validate())
        assertTrue(ServerEndpoint.ERR_HOST in ok.copy(host = "mqtts://host").validate())
        assertTrue(ServerEndpoint.ERR_TOPIC_PREFIX in ok.copy(topicPrefix = "/zs").validate())
        assertTrue(ServerEndpoint.ERR_TENANT in ok.copy(tenant = "pi lot").validate())
        assertTrue(ServerEndpoint.ERR_FINGERPRINT in ok.copy(serverFingerprint = ByteArray(31)).validate())
        assertTrue(ServerEndpoint.ERR_CA_REFERENCE in ok.copy(caReference = "").validate())
        val patch = reference()
        assertTrue(StationConfigPatch.ERR_VERSION in patch.copy(version = 0).validate())
        assertTrue(StationConfigPatch.ERR_APN in patch.copy(apn1 = "").validate())
        assertTrue(StationConfigPatch.ERR_APN in patch.copy(apn1 = "bad apn").validate())
        assertTrue(StationConfigPatch.ERR_REGION in patch.copy(region = LoRaRegion.EU868).validate())
    }

    @Test
    fun parsesInstallerHostPortInput() {
        assertEquals("10.20.30.40" to 8883, ServerEndpoint.parseHostPort("10.20.30.40"))
        assertEquals("10.20.30.40" to 9001, ServerEndpoint.parseHostPort(" 10.20.30.40:9001 "))
        assertEquals("muhoed.example.ru" to 8883, ServerEndpoint.parseHostPort("muhoed.example.ru"))
        assertEquals("2001:db8::1" to 8883, ServerEndpoint.parseHostPort("[2001:db8::1]"))
        assertEquals("2001:db8::1" to 8884, ServerEndpoint.parseHostPort("[2001:db8::1]:8884"))
        assertNull(ServerEndpoint.parseHostPort("mqtts://host:8883"))
        assertNull(ServerEndpoint.parseHostPort("host:abc"))
        assertNull(ServerEndpoint.parseHostPort("[2001:db8::1"))
        assertNull(ServerEndpoint.parseHostPort(""))
    }

    companion object {
        const val REF_HASH = "eb5c2fb7ce7a8f804d67d74d99b2b68bb394531223e825505fdc4ed1f3d1a52a"
        const val REF_PATCH = "ab0103026b31302e32302e33302e3430031922b3041920fb057164696f6e6579612d726f6f742d32303236" +
            "065820000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f076570696c6f7408657a732f7631" +
            "09020a6f696e7465726e65742e6d74732e72750b68696e7465726e6574"
        const val REF_READBACK = "ae0103026b31302e32302e33302e3430031922b3041920fb057164696f6e6579612d726f6f742d32303236" +
            "065820000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f076570696c6f7408657a732f7631" +
            "09020a6f696e7465726e65742e6d74732e72750b68696e7465726e65740c010d070e5820" +
            "eb5c2fb7ce7a8f804d67d74d99b2b68bb394531223e825505fdc4ed1f3d1a52a"
    }
}

package ru.dioneya.commissioning.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class StationModelsTest {
    @Test
    fun acceptsLotSerialBoundaries() {
        for (serial in listOf("DIO-EVT-001", "DIO-EVT-020")) {
            val identity = StationIdentity(serial, 1, "A", "1", "1", LoRaRegion.RU868)
            assertTrue(identity.validate().isEmpty())
        }
    }

    @Test
    fun rejectsSerialOutsideLot() {
        val identity = StationIdentity("DIO-EVT-021", 1, "A", "1", "1", LoRaRegion.EU868)
        assertEquals(listOf("invalid_serial"), identity.validate())
    }

    @Test
    fun requiresTlsEndpoints() {
        val errors = ConfigurationValidator.validate(
            StationConfiguration("internet", "mqtt://example", "http://example", "pilot-ca"),
        )
        assertTrue("mqtt_tls_required" in errors)
        assertTrue("https_tls_required" in errors)
    }
}

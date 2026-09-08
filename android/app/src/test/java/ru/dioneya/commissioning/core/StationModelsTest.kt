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
        assertTrue("invalid_serial" in identity.validate())
    }

    @Test
    fun rejectsEu868ForPilotLot() {
        val identity = StationIdentity("DIO-EVT-001", 1, "A", "1", "1", LoRaRegion.EU868)
        assertEquals(listOf("invalid_pilot_region"), identity.validate())
    }

    @Test
    fun requiresTlsEndpoints() {
        val errors = ConfigurationValidator.validate(
            StationConfiguration("internet", "mqtt://example", "http://example", "pilot-ca"),
        )
        assertTrue("mqtt_tls_required" in errors)
        assertTrue("https_tls_required" in errors)
    }

    @Test
    fun acceptsProvisionedDualSimProfiles() {
        val dualSim = DualSimConfiguration(
            preferredSlot = SimSlot.SIM1,
            profiles = listOf(
                CellularProfile("mts-public", "MTS", SimSlot.SIM1, ApnMode.PUBLIC, "internet.mts.ru", true),
                CellularProfile("megafon-public", "MegaFon", SimSlot.SIM2, ApnMode.PUBLIC, "internet", true),
                CellularProfile("mts-private", "MTS", SimSlot.SIM1, ApnMode.PRIVATE, "dioneya.private", true, "apn-secret-01"),
            ),
        )
        val configuration = StationConfiguration(
            apn = "internet.mts.ru",
            mqttEndpoint = "mqtts://pilot.example",
            httpsFallbackEndpoint = "https://pilot.example",
            caReference = "pilot-ca",
            dualSim = dualSim,
        )
        assertTrue(ConfigurationValidator.validate(configuration).isEmpty())
    }

    @Test
    fun rejectsUnprovisionedPrivateProfile() {
        val dualSim = DualSimConfiguration(
            preferredSlot = SimSlot.SIM1,
            profiles = listOf(
                CellularProfile("mts-public", "MTS", SimSlot.SIM1, ApnMode.PUBLIC, "internet.mts.ru", true),
                CellularProfile("mts-private", "MTS", SimSlot.SIM1, ApnMode.PRIVATE, "dioneya.private", false),
            ),
        )
        val errors = ConfigurationValidator.validate(
            StationConfiguration("internet.mts.ru", "mqtts://pilot.example", null, "pilot-ca", dualSim),
        )
        assertTrue("unprovisioned_private_profile" in errors)
    }
}

package ru.dioneya.commissioning.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class StationModelsTest {
    private fun validPosition() = InstallationPosition(
        latE7 = 557_550_000,
        lonE7 = 376_150_000,
        altDm = 1800,
        accuracyM = 5,
        source = CoordinateSource.MANUAL,
    )

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
            StationConfiguration(
                "internet",
                "mqtt://example",
                "http://example",
                "pilot-ca",
                installationPosition = validPosition(),
            ),
        )
        assertTrue("mqtt_tls_required" in errors)
        assertTrue("https_tls_required" in errors)
    }

    @Test
    fun requiresInstallationPositionForFieldConfiguration() {
        val errors = ConfigurationValidator.validate(
            StationConfiguration("internet", "mqtts://example", null, "pilot-ca"),
        )
        assertTrue("missing_installation_position" in errors)
    }

    @Test
    fun rejectsInvalidInstallationCoordinates() {
        val bad = InstallationPosition(
            latE7 = 1_000_000_000,
            lonE7 = 0,
            altDm = 0,
            accuracyM = 5,
            source = CoordinateSource.PHONE_LOCATION,
        )
        assertTrue("invalid_installation_latitude" in bad.validate())
    }

    @Test
    fun acceptsDefaultPositionTrustPolicy() {
        assertTrue(PositionTrustPolicy().validate().isEmpty())
    }

    @Test
    fun acceptsProvisionedDualSimProfiles() {
        val dualSim = DualSimConfiguration(
            preferredSlot = SimSlot.SIM1,
            profiles = listOf(
                CellularProfile("mts-public", "MTS", SimSlot.SIM1, ApnMode.PUBLIC, "internet.mts.ru", true),
                CellularProfile("megafon-public", "MegaFon", SimSlot.SIM2, ApnMode.PUBLIC, "internet", true),
            ),
        )
        val configuration = StationConfiguration(
            apn = "internet.mts.ru",
            mqttEndpoint = "mqtts://pilot.example",
            httpsFallbackEndpoint = "https://pilot.example",
            caReference = "pilot-ca",
            dualSim = dualSim,
            installationPosition = validPosition(),
        )
        assertTrue(ConfigurationValidator.validate(configuration).isEmpty())
    }

    @Test
    fun rejectsPrivateProfileForPilot() {
        val dualSim = DualSimConfiguration(
            preferredSlot = SimSlot.SIM1,
            profiles = listOf(
                CellularProfile("mts-public", "MTS", SimSlot.SIM1, ApnMode.PUBLIC, "internet.mts.ru", true),
                CellularProfile("mts-private", "MTS", SimSlot.SIM1, ApnMode.PRIVATE, "dioneya.private", true),
            ),
        )
        val errors = ConfigurationValidator.validate(
            StationConfiguration(
                "internet.mts.ru",
                "mqtts://pilot.example",
                null,
                "pilot-ca",
                dualSim,
                validPosition(),
            ),
        )
        assertTrue("private_apn_not_allowed_in_pilot" in errors)
    }
}

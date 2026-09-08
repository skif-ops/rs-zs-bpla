package ru.dioneya.commissioning.core

enum class LoRaRegion {
    RU868,
    EU868,
}

enum class SimSlot {
    SIM1,
    SIM2,
}

enum class ApnMode {
    PUBLIC,
    PRIVATE,
}

data class StationIdentity(
    val serial: String,
    val stationId: Long,
    val hardwareRevision: String,
    val firmwareVersion: String,
    val bootloaderVersion: String,
    val region: LoRaRegion,
) {
    fun validate(): List<String> = buildList {
        if (!SERIAL_PATTERN.matches(serial)) add("invalid_serial")
        if (stationId <= 0) add("invalid_station_id")
        if (hardwareRevision.isBlank()) add("missing_hardware_revision")
        if (firmwareVersion.isBlank()) add("missing_firmware_version")
        if (bootloaderVersion.isBlank()) add("missing_bootloader_version")
        if (region != LoRaRegion.RU868) add("invalid_pilot_region")
    }

    companion object {
        private val SERIAL_PATTERN = Regex("DIO-EVT-(00[1-9]|01[0-9]|020)")
    }
}

data class StationConfiguration(
    val apn: String,
    val mqttEndpoint: String,
    val httpsFallbackEndpoint: String?,
    val caReference: String,
    val dualSim: DualSimConfiguration? = null,
)

data class CellularProfile(
    val profileId: String,
    val operatorId: String,
    val slot: SimSlot,
    val mode: ApnMode,
    val apn: String,
    val provisioned: Boolean,
    val credentialReference: String? = null,
)

data class DualSimConfiguration(
    val preferredSlot: SimSlot,
    val profiles: List<CellularProfile>,
)

object ConfigurationValidator {
    private val apnPattern = Regex("[A-Za-z0-9.-]{1,100}")
    private val caReferencePattern = Regex("[A-Za-z0-9._-]{1,80}")
    private val identifierPattern = Regex("[A-Za-z0-9._-]{1,80}")

    fun validate(configuration: StationConfiguration): List<String> = buildList {
        if (!apnPattern.matches(configuration.apn)) add("invalid_apn")
        if (!configuration.mqttEndpoint.startsWith("mqtts://")) add("mqtt_tls_required")
        val fallback = configuration.httpsFallbackEndpoint
        if (fallback != null && !fallback.startsWith("https://")) add("https_tls_required")
        if (!caReferencePattern.matches(configuration.caReference)) add("invalid_ca_reference")
        configuration.dualSim?.let { dualSim ->
            validateDualSim(dualSim).forEach { error -> add(error) }
        }
    }

    private fun validateDualSim(configuration: DualSimConfiguration): List<String> = buildList {
        if (configuration.profiles.isEmpty()) {
            add("missing_cellular_profiles")
            return@buildList
        }

        val ids = configuration.profiles.map { it.profileId }
        if (ids.size != ids.toSet().size) add("duplicate_cellular_profile_id")
        if (configuration.profiles.none { it.mode == ApnMode.PUBLIC && it.provisioned }) {
            add("missing_provisioned_public_profile")
        }
        if (configuration.profiles.none { it.slot == configuration.preferredSlot && it.provisioned }) {
            add("preferred_slot_has_no_provisioned_profile")
        }

        configuration.profiles.forEach { profile ->
            if (!identifierPattern.matches(profile.profileId)) add("invalid_cellular_profile_id")
            if (!identifierPattern.matches(profile.operatorId)) add("invalid_operator_id")
            if (!apnPattern.matches(profile.apn)) add("invalid_profile_apn")
            if (profile.mode == ApnMode.PRIVATE && !profile.provisioned) {
                add("unprovisioned_private_profile")
            }
            if (profile.credentialReference != null && !identifierPattern.matches(profile.credentialReference)) {
                add("invalid_credential_reference")
            }
        }
    }
}

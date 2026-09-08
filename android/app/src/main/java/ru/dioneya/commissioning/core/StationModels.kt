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

enum class CoordinateSource {
    MANUAL,
    PHONE_LOCATION,
    STATION_GNSS,
    SURVEYED,
}

enum class PositionTrustState {
    UNCONFIGURED,
    CONFIGURED_OK,
    CONFIGURED_WARN,
    CONFIGURED_SUSPECT,
    REVALIDATION_REQUIRED,
}

enum class TimeTrustState {
    UNKNOWN,
    GNSS_TIME_TRUSTED,
    HOLDOVER,
    GNSS_TIME_SUSPECT,
    UNSYNCED,
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

data class InstallationPosition(
    val latE7: Int,
    val lonE7: Int,
    val altDm: Int,
    val accuracyM: Int,
    val source: CoordinateSource,
    val version: Long = 1,
    val locked: Boolean = true,
) {
    fun validate(): List<String> = buildList {
        if (latE7 !in -900_000_000..900_000_000) add("invalid_installation_latitude")
        if (lonE7 !in -1_800_000_000..1_800_000_000) add("invalid_installation_longitude")
        if (altDm !in -50_000..100_000) add("invalid_installation_altitude")
        if (accuracyM !in 1..1000) add("invalid_installation_accuracy")
        if (version <= 0) add("invalid_installation_position_version")
        if (!locked) add("installation_position_not_locked")
    }
}

data class PositionTrustPolicy(
    val warningDistanceM: Int = 25,
    val suspectDistanceM: Int = 75,
    val grossJumpDistanceM: Int = 250,
    val warningConsecutiveFixes: Int = 3,
    val suspectConsecutiveFixes: Int = 10,
) {
    fun validate(): List<String> = buildList {
        if (warningDistanceM !in 5..500) add("invalid_position_warning_distance")
        if (suspectDistanceM <= warningDistanceM || suspectDistanceM > 2000) {
            add("invalid_position_suspect_distance")
        }
        if (grossJumpDistanceM <= suspectDistanceM || grossJumpDistanceM > 5000) {
            add("invalid_position_gross_jump_distance")
        }
        if (warningConsecutiveFixes !in 1..60) add("invalid_position_warning_persistence")
        if (suspectConsecutiveFixes < warningConsecutiveFixes || suspectConsecutiveFixes > 120) {
            add("invalid_position_suspect_persistence")
        }
    }
}

data class GnssIntegritySnapshot(
    val observedLatE7: Int?,
    val observedLonE7: Int?,
    val observedAltDm: Int?,
    val reportedAccuracyM: Int?,
    val distanceFromInstallationM: Int?,
    val fixType: Int,
    val satellites: Int,
    val hdopX100: Int,
    val jam: Boolean,
    val spoof: Boolean,
    val positionTrust: PositionTrustState,
    val timeTrust: TimeTrustState,
    val ppsOk: Boolean,
    val expectedTimeErrorUs: Long,
)

data class StationConfiguration(
    val apn: String,
    val mqttEndpoint: String,
    val httpsFallbackEndpoint: String?,
    val caReference: String,
    val dualSim: DualSimConfiguration? = null,
    val installationPosition: InstallationPosition? = null,
    val positionTrustPolicy: PositionTrustPolicy = PositionTrustPolicy(),
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

        val position = configuration.installationPosition
        if (position == null) {
            add("missing_installation_position")
        } else {
            position.validate().forEach { error -> add(error) }
        }
        configuration.positionTrustPolicy.validate().forEach { error -> add(error) }
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
            if (profile.mode == ApnMode.PRIVATE) {
                add("private_apn_not_allowed_in_pilot")
            }
            if (profile.credentialReference != null && !identifierPattern.matches(profile.credentialReference)) {
                add("invalid_credential_reference")
            }
        }
    }
}

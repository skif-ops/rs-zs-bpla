package ru.dioneya.commissioning.core

enum class LoRaRegion {
    RU868,
    EU868,
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
)

object ConfigurationValidator {
    private val apnPattern = Regex("[A-Za-z0-9.-]{1,100}")
    private val caReferencePattern = Regex("[A-Za-z0-9._-]{1,80}")

    fun validate(configuration: StationConfiguration): List<String> = buildList {
        if (!apnPattern.matches(configuration.apn)) add("invalid_apn")
        if (!configuration.mqttEndpoint.startsWith("mqtts://")) add("mqtt_tls_required")
        val fallback = configuration.httpsFallbackEndpoint
        if (fallback != null && !fallback.startsWith("https://")) add("https_tls_required")
        if (!caReferencePattern.matches(configuration.caReference)) add("invalid_ca_reference")
    }
}

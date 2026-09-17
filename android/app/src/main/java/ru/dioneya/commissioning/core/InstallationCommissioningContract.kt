package ru.dioneya.commissioning.core

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

enum class InstallationCommissioningOperation {
    INITIAL,
    RECOMMISSION,
}

enum class InstallationCommissioningRole {
    INSTALLER,
    SERVICE_ENGINEER,
}

data class InstallationCommissioningRequest(
    val operation: InstallationCommissioningOperation,
    val position: InstallationPosition,
    val policy: PositionTrustPolicy = PositionTrustPolicy(),
    val commissionedTimeUs: Long,
)

data class InstallationCommissioningReadback(
    val position: InstallationPosition,
    val policy: PositionTrustPolicy,
    val commissionedTimeUs: Long,
    val storageGeneration: Long,
    val commissioningHashHex: String,
    val auditCommitted: Boolean,
)

object InstallationCommissioningContract {
    private const val FORMAT_VERSION: Byte = 1
    private const val CONFIGURED_ALTITUDE_SOURCE: Byte = 1
    private const val CONFIGURED_POSITION_SOURCE: Byte = 1
    private const val CANONICAL_BYTES = 58
    private const val MAX_UINT32 = 0xffff_ffffL
    private val DOMAIN = "ZS-INSTALLATION-V1".toByteArray(StandardCharsets.US_ASCII)
    private val HASH_PATTERN = Regex("[0-9a-fA-F]{64}")

    fun validateRequest(
        request: InstallationCommissioningRequest,
        role: InstallationCommissioningRole,
        currentVersion: Long?,
    ): List<String> = buildList {
        addAll(validatePayload(request))
        if (role == InstallationCommissioningRole.INSTALLER && request.policy != PositionTrustPolicy()) {
            add("engineer_role_required_for_position_policy")
        }
        if (currentVersion == null && request.operation != InstallationCommissioningOperation.INITIAL) {
            add("recommission_without_existing_position")
        }
        if (currentVersion != null && request.operation == InstallationCommissioningOperation.INITIAL) {
            add("initial_write_rejected_for_locked_position")
        }
        if (currentVersion != null && request.operation == InstallationCommissioningOperation.RECOMMISSION &&
            request.position.version <= currentVersion
        ) {
            add("installation_position_version_not_monotonic")
        }
    }

    fun canonicalHashHex(request: InstallationCommissioningRequest): String {
        require(validatePayload(request).isEmpty()) { "invalid installation commissioning payload" }

        val position = request.position
        val policy = request.policy
        val buffer = ByteBuffer.allocate(CANONICAL_BYTES).order(ByteOrder.BIG_ENDIAN)
        buffer.put(DOMAIN)
        buffer.put(FORMAT_VERSION)
        buffer.put(1.toByte()) // configured
        buffer.put(1.toByte()) // locked
        buffer.put(coordinateSourceId(position.source))
        buffer.put(CONFIGURED_ALTITUDE_SOURCE)
        buffer.put(CONFIGURED_POSITION_SOURCE)
        buffer.putInt(position.version.toInt())
        buffer.putInt(position.latE7)
        buffer.putInt(position.lonE7)
        buffer.putInt(position.altDm)
        buffer.putShort(position.accuracyM.toShort())
        buffer.putShort(policy.warningDistanceM.toShort())
        buffer.putShort(policy.suspectDistanceM.toShort())
        buffer.putShort(policy.grossJumpDistanceM.toShort())
        buffer.put(policy.warningConsecutiveFixes.toByte())
        buffer.put(policy.suspectConsecutiveFixes.toByte())
        buffer.putLong(request.commissionedTimeUs)
        check(buffer.position() == CANONICAL_BYTES) { "canonical installation record size drift" }
        return MessageDigest.getInstance("SHA-256").digest(buffer.array()).toHex()
    }

    fun verifyReadback(
        request: InstallationCommissioningRequest,
        readback: InstallationCommissioningReadback,
    ): List<String> = buildList {
        val requestErrors = validatePayload(request)
        if (requestErrors.isNotEmpty()) {
            addAll(requestErrors)
            return@buildList
        }
        if (readback.position != request.position) add("installation_position_readback_mismatch")
        if (readback.policy != request.policy) add("position_policy_readback_mismatch")
        if (readback.commissionedTimeUs != request.commissionedTimeUs) {
            add("commissioned_time_readback_mismatch")
        }
        if (readback.storageGeneration !in 1..MAX_UINT32) add("invalid_storage_generation")
        if (!HASH_PATTERN.matches(readback.commissioningHashHex)) {
            add("invalid_commissioning_hash_format")
        } else if (!readback.commissioningHashHex.equals(canonicalHashHex(request), ignoreCase = true)) {
            add("commissioning_hash_mismatch")
        }
        if (!readback.auditCommitted) add("commissioning_audit_not_committed")
    }

    private fun validatePayload(request: InstallationCommissioningRequest): List<String> = buildList {
        request.position.validate().forEach { error -> add(error) }
        request.policy.validate().forEach { error -> add(error) }
        if (request.commissionedTimeUs <= 0) add("invalid_commissioned_time")
    }

    private fun coordinateSourceId(source: CoordinateSource): Byte = when (source) {
        CoordinateSource.MANUAL -> 0
        CoordinateSource.PHONE_LOCATION -> 1
        CoordinateSource.STATION_GNSS -> 2
        CoordinateSource.SURVEYED -> 3
    }

    private fun ByteArray.toHex(): String {
        val alphabet = "0123456789abcdef"
        return buildString(size * 2) {
            for (value in this@toHex) {
                val byte = value.toInt() and 0xff
                append(alphabet[byte ushr 4])
                append(alphabet[byte and 0x0f])
            }
        }
    }
}

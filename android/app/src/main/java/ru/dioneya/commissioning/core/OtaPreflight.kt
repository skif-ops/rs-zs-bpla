package ru.dioneya.commissioning.core

import java.security.MessageDigest

data class OtaManifest(
    val hardwareRevision: String,
    val versionCounter: Long,
    val imageSize: Long,
    val sha256Hex: String,
    val signatureAlgorithm: String,
    val signature: ByteArray,
)

sealed interface OtaPreflightResult {
    data object ReadyForCryptographicVerification : OtaPreflightResult
    data class Rejected(val reason: String) : OtaPreflightResult
}

object OtaPreflight {
    fun check(
        manifest: OtaManifest,
        image: ByteArray,
        expectedHardwareRevision: String,
        currentVersionCounter: Long,
    ): OtaPreflightResult {
        if (manifest.hardwareRevision != expectedHardwareRevision) {
            return OtaPreflightResult.Rejected("hardware_revision_mismatch")
        }
        if (manifest.versionCounter <= currentVersionCounter) {
            return OtaPreflightResult.Rejected("rollback_or_same_version")
        }
        if (manifest.imageSize != image.size.toLong()) {
            return OtaPreflightResult.Rejected("image_size_mismatch")
        }
        val actualHash = MessageDigest.getInstance("SHA-256")
            .digest(image)
            .joinToString("") { byte -> "%02x".format(byte) }
        if (!actualHash.equals(manifest.sha256Hex, ignoreCase = true)) {
            return OtaPreflightResult.Rejected("image_hash_mismatch")
        }
        if (manifest.signatureAlgorithm.isBlank() || manifest.signature.isEmpty()) {
            return OtaPreflightResult.Rejected("missing_signature")
        }
        return OtaPreflightResult.ReadyForCryptographicVerification
    }
}

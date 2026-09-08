package ru.dioneya.commissioning.core

import java.security.MessageDigest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OtaPreflightTest {
    private val image = "signed-image-placeholder".toByteArray()
    private val hash = MessageDigest.getInstance("SHA-256")
        .digest(image)
        .joinToString("") { byte -> "%02x".format(byte) }

    private fun manifest(counter: Long = 2, sha256: String = hash) = OtaManifest(
        hardwareRevision = "A",
        versionCounter = counter,
        imageSize = image.size.toLong(),
        sha256Hex = sha256,
        signatureAlgorithm = "UNFROZEN",
        signature = byteArrayOf(1),
    )

    @Test
    fun validStructureStillNeedsCryptographicVerifier() {
        assertEquals(
            OtaPreflightResult.ReadyForCryptographicVerification,
            OtaPreflight.check(manifest(), image, "A", 1),
        )
    }

    @Test
    fun rejectsDowngradeAndWrongHash() {
        val downgrade = OtaPreflight.check(manifest(counter = 1), image, "A", 1)
        assertEquals(OtaPreflightResult.Rejected("rollback_or_same_version"), downgrade)

        val wrongHash = OtaPreflight.check(manifest(sha256 = "00".repeat(32)), image, "A", 1)
        assertTrue(wrongHash is OtaPreflightResult.Rejected)
    }
}

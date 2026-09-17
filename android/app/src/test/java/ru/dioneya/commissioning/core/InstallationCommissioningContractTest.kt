package ru.dioneya.commissioning.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InstallationCommissioningContractTest {
    private fun request(
        version: Long = 1,
        operation: InstallationCommissioningOperation = InstallationCommissioningOperation.INITIAL,
        policy: PositionTrustPolicy = PositionTrustPolicy(),
    ) = InstallationCommissioningRequest(
        operation = operation,
        position = InstallationPosition(
            latE7 = 557_550_000,
            lonE7 = 376_150_000,
            altDm = 1800,
            accuracyM = 5,
            source = CoordinateSource.MANUAL,
            version = version,
            locked = true,
        ),
        policy = policy,
        commissionedTimeUs = 2_000_000_000_000_000L + version,
    )

    @Test
    fun canonicalHashMatchesFirmwareKnownAnswer() {
        // Cross-language vector: firmware/tests/test_installation_commissioning.c
        assertEquals(
            "9ad92b04c26e85a7f20c9259469774199348d98cfb47a563160bbab2154cea51",
            InstallationCommissioningContract.canonicalHashHex(request()),
        )
    }

    @Test
    fun acceptsExactCommittedReadback() {
        val request = request()
        val readback = InstallationCommissioningReadback(
            position = request.position,
            policy = request.policy,
            commissionedTimeUs = request.commissionedTimeUs,
            storageGeneration = 1,
            commissioningHashHex = InstallationCommissioningContract.canonicalHashHex(request),
            auditCommitted = true,
        )
        assertTrue(InstallationCommissioningContract.verifyReadback(request, readback).isEmpty())
    }

    @Test
    fun rejectsModifiedHashAndIncompleteAudit() {
        val request = request()
        val readback = InstallationCommissioningReadback(
            position = request.position.copy(latE7 = request.position.latE7 + 1),
            policy = request.policy,
            commissionedTimeUs = request.commissionedTimeUs,
            storageGeneration = 1,
            commissioningHashHex = "00".repeat(32),
            auditCommitted = false,
        )
        val errors = InstallationCommissioningContract.verifyReadback(request, readback)
        assertTrue("installation_position_readback_mismatch" in errors)
        assertTrue("commissioning_hash_mismatch" in errors)
        assertTrue("commissioning_audit_not_committed" in errors)
    }

    @Test
    fun invalidRequestFailsReadbackValidationWithoutHashing() {
        val request = request().copy(commissionedTimeUs = 0)
        val readback = InstallationCommissioningReadback(
            position = request.position,
            policy = request.policy,
            commissionedTimeUs = 0,
            storageGeneration = 1,
            commissioningHashHex = "00".repeat(32),
            auditCommitted = true,
        )
        assertEquals(
            listOf("invalid_commissioned_time"),
            InstallationCommissioningContract.verifyReadback(request, readback),
        )
    }

    @Test
    fun installerCannotChangePositionTrustPolicy() {
        val changed = request(policy = PositionTrustPolicy(warningDistanceM = 30))
        val errors = InstallationCommissioningContract.validateRequest(
            changed,
            InstallationCommissioningRole.INSTALLER,
            currentVersion = null,
        )
        assertTrue("engineer_role_required_for_position_policy" in errors)
    }

    @Test
    fun recommissionRequiresExistingRecordAndMonotonicVersion() {
        val noRecordErrors = InstallationCommissioningContract.validateRequest(
            request(operation = InstallationCommissioningOperation.RECOMMISSION),
            InstallationCommissioningRole.SERVICE_ENGINEER,
            currentVersion = null,
        )
        assertTrue("recommission_without_existing_position" in noRecordErrors)

        val rollbackErrors = InstallationCommissioningContract.validateRequest(
            request(version = 2, operation = InstallationCommissioningOperation.RECOMMISSION),
            InstallationCommissioningRole.SERVICE_ENGINEER,
            currentVersion = 2,
        )
        assertTrue("installation_position_version_not_monotonic" in rollbackErrors)
    }

    @Test
    fun engineerCanValidateMonotonicCustomPolicyRecommission() {
        val changed = request(
            version = 2,
            operation = InstallationCommissioningOperation.RECOMMISSION,
            policy = PositionTrustPolicy(warningDistanceM = 30),
        )
        assertTrue(
            InstallationCommissioningContract.validateRequest(
                changed,
                InstallationCommissioningRole.SERVICE_ENGINEER,
                currentVersion = 1,
            ).isEmpty(),
        )
    }
}

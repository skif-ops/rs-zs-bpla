package ru.dioneya.commissioning.core.ble

import java.util.UUID

/**
 * BLE GATT contract, proposal v0.1 (protocols/BLE_GATT_OTA_ICD_v0_1.md, addendum B).
 *
 * The ICD freezes UUIDs, MTU and framing only after the joint Android/firmware
 * prototype; this object is the Android side of that proposal.  All identifiers
 * live in one 128-bit base so the nRF52840 side can derive them the same way:
 *
 *     d10e XXXX -5a53-4c55-b0a1-0000 0000 0000    XXXX = 16-bit id below
 *
 * Long values (CBOR patches, read-backs, self-test reports) do not fit one ATT
 * packet and are carried as frames, see [LongValueFraming].
 */
object GattContractV01 {
    private const val BASE_PREFIX = "d10e"
    private const val BASE_SUFFIX = "-5a53-4c55-b0a1-000000000000"

    fun uuid(id16: Int): UUID {
        require(id16 in 0..0xFFFF)
        return UUID.fromString(BASE_PREFIX + "%04x".format(id16) + BASE_SUFFIX)
    }

    // Services
    val SERVICE_DEVICE_INFO: UUID = uuid(0x0100)
    val SERVICE_CONFIGURATION: UUID = uuid(0x0200)
    val SERVICE_DIAGNOSTICS: UUID = uuid(0x0300)
    val SERVICE_LOGS: UUID = uuid(0x0400)
    val SERVICE_OTA: UUID = uuid(0x0500)

    // Characteristics (ICD §3 table + self_test proposed for the diagnostics service)
    val CHAR_IDENTITY: UUID = uuid(0x0101)             // read: serial, HW rev, FW rev, region, station_id
    val CHAR_CONFIG_READ: UUID = uuid(0x0201)          // read/notify: station config read-back (CBOR, 14 keys)
    val CHAR_CONFIG_WRITE: UUID = uuid(0x0202)         // authenticated write: CBOR patch (11 keys), status by notify
    val CHAR_INSTALLATION_POSITION: UUID = uuid(0x0203)
    val CHAR_POSITION_TRUST_POLICY: UUID = uuid(0x0204)  // reserved in v0.2 (policy travels inside 0x0203)
    val CHAR_SESSION_ROLE: UUID = uuid(0x0205)           // B.9: read [role]; write 01 (challenge) / 02‖tag16; notify 01‖nonce16 / 03‖role + status
    val CHAR_STATUS: UUID = uuid(0x0301)               // read/notify
    val CHAR_GNSS_INTEGRITY: UUID = uuid(0x0302)       // read/notify
    val CHAR_SELF_TEST: UUID = uuid(0x0303)            // write 0x01 = run all; notify: CBOR {id: [code, detail]}
    val CHAR_LOG_CHUNK: UUID = uuid(0x0401)
    val CHAR_OTA_MANIFEST: UUID = uuid(0x0501)
    val CHAR_OTA_IMAGE_CHUNK: UUID = uuid(0x0502)
    val CHAR_OTA_CONTROL: UUID = uuid(0x0503)

    /** Client Characteristic Configuration descriptor (Bluetooth SIG). */
    val CCCD: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    /** Requested ATT MTU; the largest Android accepts. ATT payload is MTU - 3. */
    const val MTU_REQUEST = 247
    const val MTU_MIN = 23

    /** Status codes carried in the config_write notification (first byte). */
    const val WRITE_STATUS_OK = 0x00
    const val WRITE_STATUS_REJECTED_VALIDATION = 0x01
    const val WRITE_STATUS_REJECTED_VERSION = 0x02
    const val WRITE_STATUS_NOT_IN_SERVICE_MODE = 0x03
    const val WRITE_STATUS_NOT_AUTHORIZED = 0x04
    const val WRITE_STATUS_STORAGE_ERROR = 0x05

    const val SELF_TEST_RUN_ALL: Byte = 0x01

    /** session_role (B.9): roles and operations. */
    const val ROLE_NONE = 0
    const val ROLE_INSTALLER = 1
    const val ROLE_ENGINEER = 2
    const val ROLE_OP_CHALLENGE: Byte = 0x01
    const val ROLE_OP_RESPONSE: Byte = 0x02
    const val ROLE_OP_RESULT: Byte = 0x03
    const val ROLE_NONCE_BYTES = 16
    const val ROLE_TAG_BYTES = 16

    /** Operation timeouts (ms). */
    const val TIMEOUT_CONNECT_MS = 15_000L
    const val TIMEOUT_OPERATION_MS = 5_000L
    const val TIMEOUT_SELF_TEST_MS = 20_000L
    const val TIMEOUT_CONFIG_WRITE_MS = 10_000L
    const val TIMEOUT_ROLE_MS = 5_000L
}

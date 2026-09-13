#include "zs_installation_commissioning.h"
#include "zs_sha256.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  uint8_t slots[ZS_INSTALLATION_STORE_SLOT_COUNT][ZS_INSTALLATION_STORE_SLOT_BYTES];
} memory_store_t;

typedef struct {
  zs_commissioning_audit_event_t events[16];
  unsigned calls;
  unsigned count;
  unsigned fail_call;
} audit_log_t;

static bool memory_read(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size) {
  memory_store_t *store = ctx;
  if (slot >= ZS_INSTALLATION_STORE_SLOT_COUNT || offset + size > ZS_INSTALLATION_STORE_SLOT_BYTES) return false;
  memcpy(data, &store->slots[slot][offset], size);
  return true;
}

static bool memory_erase(void *ctx, uint8_t slot) {
  memory_store_t *store = ctx;
  if (slot >= ZS_INSTALLATION_STORE_SLOT_COUNT) return false;
  memset(store->slots[slot], 0xff, ZS_INSTALLATION_STORE_SLOT_BYTES);
  return true;
}

static bool memory_write(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size) {
  memory_store_t *store = ctx;
  if (slot >= ZS_INSTALLATION_STORE_SLOT_COUNT || offset + size > ZS_INSTALLATION_STORE_SLOT_BYTES) return false;
  for (size_t i = 0u; i < size; i++) {
    if ((store->slots[slot][offset + i] & data[i]) != data[i]) return false;
    store->slots[slot][offset + i] = data[i];
  }
  return true;
}

static bool append_audit(void *ctx, const zs_commissioning_audit_event_t *event) {
  audit_log_t *log = ctx;
  log->calls++;
  if (log->calls == log->fail_call) return false;
  assert(log->count < sizeof(log->events) / sizeof(log->events[0]));
  log->events[log->count++] = *event;
  return true;
}

static zs_installation_record_t request(uint32_t version) {
  zs_installation_record_t record;
  memset(&record, 0, sizeof(record));
  record.trust.installation.lat_e7 = 557550000;
  record.trust.installation.lon_e7 = 376150000;
  record.trust.installation.alt_dm = 1800;
  record.trust.installation.pos_accuracy_m = 5u;
  record.trust.installation.altitude_source = 1u;
  record.trust.warning_distance_m = 25u;
  record.trust.suspect_distance_m = 75u;
  record.trust.gross_jump_distance_m = 250u;
  record.trust.warning_consecutive_fixes = 3u;
  record.trust.suspect_consecutive_fixes = 10u;
  record.version = version;
  record.commissioned_time_us = UINT64_C(2000000000000000) + version;
  record.source = 0u;
  return record;
}

static zs_commissioning_context_t local_context(void) {
  const zs_commissioning_context_t context = {
      .origin = ZS_COMMISSIONING_ORIGIN_BLE_LOCAL,
      .role = ZS_COMMISSIONING_ROLE_INSTALLER,
      .ble_secure_connections = true,
      .peer_identity_verified = true,
      .physical_service_mode = true,
      .service_mode_started_ms = 1000u,
      .now_ms = 2000u};
  return context;
}

static void test_sha256(void) {
  static const uint8_t expected[ZS_SHA256_DIGEST_BYTES] = {
      0xbau, 0x78u, 0x16u, 0xbfu, 0x8fu, 0x01u, 0xcfu, 0xeau,
      0x41u, 0x41u, 0x40u, 0xdeu, 0x5du, 0xaeu, 0x22u, 0x23u,
      0xb0u, 0x03u, 0x61u, 0xa3u, 0x96u, 0x17u, 0x7au, 0x9cu,
      0xb4u, 0x10u, 0xffu, 0x61u, 0xf2u, 0x00u, 0x15u, 0xadu};
  static const char long_input[] =
      "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
  static const uint8_t expected_long[ZS_SHA256_DIGEST_BYTES] = {
      0x24u, 0x8du, 0x6au, 0x61u, 0xd2u, 0x06u, 0x38u, 0xb8u,
      0xe5u, 0xc0u, 0x26u, 0x93u, 0x0cu, 0x3eu, 0x60u, 0x39u,
      0xa3u, 0x3cu, 0xe4u, 0x59u, 0x64u, 0xffu, 0x21u, 0x67u,
      0xf6u, 0xecu, 0xedu, 0xd4u, 0x19u, 0xdbu, 0x06u, 0xc1u};
  uint8_t actual[ZS_SHA256_DIGEST_BYTES];
  zs_sha256_t ctx;
  zs_sha256_digest("abc", 3u, actual);
  assert(memcmp(actual, expected, sizeof(expected)) == 0);
  zs_sha256_init(&ctx);
  zs_sha256_update(&ctx, long_input, 17u);
  zs_sha256_update(&ctx, &long_input[17], sizeof(long_input) - 1u - 17u);
  zs_sha256_final(&ctx, actual);
  assert(memcmp(actual, expected_long, sizeof(expected_long)) == 0);
}

int main(void) {
  /* canonical record hash: 9ad92b04c26e85a7f20c9259469774199348d98cfb47a563160bbab2154cea51 */
  static const uint8_t expected_record_hash[ZS_INSTALLATION_HASH_BYTES] = {
      0x9au, 0xd9u, 0x2bu, 0x04u, 0xc2u, 0x6eu, 0x85u, 0xa7u,
      0xf2u, 0x0cu, 0x92u, 0x59u, 0x46u, 0x97u, 0x74u, 0x19u,
      0x93u, 0x48u, 0xd9u, 0x8cu, 0xfbu, 0x47u, 0xa5u, 0x63u,
      0x16u, 0x0bu, 0xbau, 0xb2u, 0x15u, 0x4cu, 0xeau, 0x51u};
  memory_store_t memory;
  audit_log_t audit_log = {0};
  zs_installation_store_io_t store = {&memory, memory_read, memory_erase, memory_write};
  zs_commissioning_audit_io_t audit = {&audit_log, append_audit};
  zs_commissioning_context_t context = local_context();
  zs_installation_record_t requested = request(1u);
  zs_installation_record_t readback;
  bool committed = true;
  memset(&memory, 0xff, sizeof(memory));
  test_sha256();

  context.origin = ZS_COMMISSIONING_ORIGIN_MQTT_REMOTE;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_INITIAL, &requested, &readback, &committed) ==
      ZS_COMMISSIONING_LOCAL_BLE_REQUIRED);
  assert(!committed && audit_log.count == 0u);

  context = local_context();
  context.ble_secure_connections = false;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_INITIAL, &requested, &readback, &committed) ==
      ZS_COMMISSIONING_PEER_AUTH_REQUIRED);
  context = local_context();
  context.peer_identity_verified = false;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_INITIAL, &requested, &readback, &committed) ==
      ZS_COMMISSIONING_PEER_AUTH_REQUIRED);
  context = local_context();
  context.physical_service_mode = false;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_INITIAL, &requested, &readback, &committed) ==
      ZS_COMMISSIONING_SERVICE_MODE_REQUIRED);
  context = local_context();
  context.now_ms = context.service_mode_started_ms + ZS_INSTALLATION_SERVICE_WINDOW_MS + 1u;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_INITIAL, &requested, &readback, &committed) ==
      ZS_COMMISSIONING_SERVICE_MODE_REQUIRED);

  context = local_context();
  requested.trust.warning_distance_m = 30u;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_INITIAL, &requested, &readback, &committed) ==
      ZS_COMMISSIONING_POLICY_ROLE_REQUIRED);

  requested = request(1u);
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_INITIAL, &requested, &readback, &committed) == ZS_COMMISSIONING_OK);
  assert(committed && readback.version == 1u && readback.storage_generation == 1u);
  assert(readback.trust.configured && readback.trust.locked);
  assert(readback.trust.installation.position_source == ZS_POSITION_SOURCE_CONFIGURED_INSTALL);
  assert(memcmp(readback.commissioning_hash, expected_record_hash, sizeof(expected_record_hash)) == 0);
  assert(zs_installation_record_hash_valid(&readback));
  assert(audit_log.count == 2u);
  assert(audit_log.events[0].phase == ZS_COMMISSIONING_AUDIT_INTENT);
  assert(audit_log.events[1].phase == ZS_COMMISSIONING_AUDIT_COMMITTED);

  context.origin = ZS_COMMISSIONING_ORIGIN_HTTPS_REMOTE;
  assert(zs_installation_commissioning_read(&store, &context, &readback) ==
         ZS_COMMISSIONING_LOCAL_BLE_REQUIRED);
  context = local_context();
  assert(zs_installation_commissioning_read(&store, &context, &readback) == ZS_COMMISSIONING_OK);

  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_INITIAL, &requested, &readback, &committed) ==
      ZS_COMMISSIONING_LOCKED);
  assert(!committed && audit_log.events[audit_log.count - 1u].phase == ZS_COMMISSIONING_AUDIT_REJECTED);
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_RECOMMISSION, &requested, &readback, &committed) ==
      ZS_COMMISSIONING_VERSION_REJECTED);
  assert(!committed);

  zs_installation_record_t changed = request(2u);
  changed.trust.warning_distance_m = 30u;
  context.role = ZS_COMMISSIONING_ROLE_INSTALLER;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_RECOMMISSION, &changed, &readback, &committed) ==
      ZS_COMMISSIONING_POLICY_ROLE_REQUIRED);
  context.role = ZS_COMMISSIONING_ROLE_ENGINEER;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_RECOMMISSION, &changed, &readback, &committed) == ZS_COMMISSIONING_OK);
  assert(committed && readback.version == 2u && readback.trust.warning_distance_m == 30u);

  audit_log.fail_call = audit_log.calls + 1u;
  changed = request(3u);
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_RECOMMISSION, &changed, &readback, &committed) ==
      ZS_COMMISSIONING_AUDIT_REQUIRED);
  assert(!committed);
  assert(zs_installation_commissioning_read(&store, &context, &readback) == ZS_COMMISSIONING_OK);
  assert(readback.version == 2u);

  audit_log.fail_call = audit_log.calls + 2u;
  assert(zs_installation_commissioning_apply(&store, &audit, &context,
      ZS_COMMISSIONING_OPERATION_RECOMMISSION, &changed, &readback, &committed) ==
      ZS_COMMISSIONING_AUDIT_FINALIZE_FAILED);
  assert(committed && readback.version == 3u);

  puts("zs_installation_commissioning_tests: OK");
  return 0;
}

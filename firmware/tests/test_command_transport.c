#include "zs_cbor.h"
#include "zs_command.h"
#include "zs_command_vector.h"
#include "zs_sha256.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  uint8_t signed_cbor[512];
  size_t signed_size;
  uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES];
  uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES];
  bool accept;
  unsigned calls;
} verifier_t;

typedef struct {
  zs_command_dedup_state_t state;
  uint8_t expected_id[ZS_COMMAND_UUID_BYTES];
  unsigned calls;
} dedup_t;

static bool verify_signature(void *ctx, const uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES],
                             const uint8_t *signed_cbor, size_t signed_size,
                             const uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES]) {
  verifier_t *verifier = ctx;
  verifier->calls++;
  return verifier->accept && signed_size == verifier->signed_size &&
         memcmp(key_id, verifier->key_id, ZS_COMMAND_KEY_ID_BYTES) == 0 &&
         memcmp(signed_cbor, verifier->signed_cbor, signed_size) == 0 &&
         memcmp(signature, verifier->signature, ZS_COMMAND_SIGNATURE_BYTES) == 0;
}

static zs_command_dedup_state_t dedup_lookup(
    void *ctx, const uint8_t command_id[ZS_COMMAND_UUID_BYTES]) {
  dedup_t *dedup = ctx;
  dedup->calls++;
  assert(memcmp(command_id, dedup->expected_id, ZS_COMMAND_UUID_BYTES) == 0);
  return dedup->state;
}

static void put_null(zs_cbor_t *cbor) {
  assert(cbor->len < cbor->cap);
  cbor->buf[cbor->len++] = 0xf6u;
}

static size_t encode_audio_payload(zs_cbor_t *cbor, uint64_t event_id,
                                   zs_audio_segment_t segment,
                                   int32_t start_ms, uint32_t duration_ms) {
  const size_t before = cbor->len;
  zs_cbor_map(cbor, 4u);
  zs_cbor_uint(cbor, 0u); zs_cbor_uint(cbor, event_id);
  zs_cbor_uint(cbor, 1u); zs_cbor_uint(cbor, segment);
  zs_cbor_uint(cbor, 2u);
  if (segment == ZS_AUDIO_SEGMENT_RANGE) zs_cbor_int(cbor, start_ms);
  else put_null(cbor);
  zs_cbor_uint(cbor, 3u);
  if (segment == ZS_AUDIO_SEGMENT_RANGE) zs_cbor_uint(cbor, duration_ms);
  else put_null(cbor);
  return cbor->len - before;
}

static size_t build_command(uint8_t *output, size_t capacity, verifier_t *verifier,
                            const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
                            uint32_t station_id, uint64_t created_us,
                            uint64_t expires_us, zs_audio_segment_t segment) {
  zs_cbor_t full, signed_map;
  uint8_t unsigned_bytes[512];
  for (size_t i = 0u; i < ZS_COMMAND_KEY_ID_BYTES; ++i)
    verifier->key_id[i] = (uint8_t)(0xa0u + i);
  for (size_t i = 0u; i < ZS_COMMAND_SIGNATURE_BYTES; ++i)
    verifier->signature[i] = (uint8_t)(0x40u + i);

  zs_cbor_init(&signed_map, unsigned_bytes, sizeof(unsigned_bytes));
  zs_cbor_map(&signed_map, 9u);
  zs_cbor_uint(&signed_map, 0u); zs_cbor_uint(&signed_map, ZS_COMMAND_SCHEMA_VERSION);
  zs_cbor_uint(&signed_map, 1u); zs_cbor_uint(&signed_map, ZS_COMMAND_MESSAGE_TYPE);
  zs_cbor_uint(&signed_map, 2u); zs_cbor_uint(&signed_map, station_id);
  zs_cbor_uint(&signed_map, 3u); zs_cbor_bytes(&signed_map, command_id, ZS_COMMAND_UUID_BYTES);
  zs_cbor_uint(&signed_map, 4u); zs_cbor_uint(&signed_map, created_us);
  zs_cbor_uint(&signed_map, 5u); zs_cbor_uint(&signed_map, expires_us);
  zs_cbor_uint(&signed_map, 6u); zs_cbor_uint(&signed_map, ZS_COMMAND_REQUEST_AUDIO);
  zs_cbor_uint(&signed_map, 7u);
  encode_audio_payload(&signed_map, UINT64_C(42), segment, -5000, 10000u);
  zs_cbor_uint(&signed_map, 8u);
  zs_cbor_bytes(&signed_map, verifier->key_id, ZS_COMMAND_KEY_ID_BYTES);
  assert(!signed_map.error);
  memcpy(verifier->signed_cbor, unsigned_bytes, signed_map.len);
  verifier->signed_size = signed_map.len;

  zs_cbor_init(&full, output, capacity);
  zs_cbor_map(&full, 10u);
  assert(signed_map.len > 1u && full.len == 1u);
  memcpy(&output[full.len], &unsigned_bytes[1], signed_map.len - 1u);
  full.len += signed_map.len - 1u;
  zs_cbor_uint(&full, 9u);
  zs_cbor_bytes(&full, verifier->signature, ZS_COMMAND_SIGNATURE_BYTES);
  assert(!full.error);
  return full.len;
}

static zs_command_status_t decode(const uint8_t *payload, size_t size,
                                  uint32_t station_id, uint64_t now_us,
                                  bool time_trusted, verifier_t *verifier,
                                  dedup_t *dedup, size_t workspace_size,
                                  zs_command_t *command) {
  uint8_t workspace[512];
  assert(workspace_size <= sizeof(workspace));
  memset(workspace, 0xa5, sizeof(workspace));
  return zs_command_decode_verify(payload, size, station_id, now_us, time_trusted,
                                  verify_signature, verifier, dedup_lookup, dedup,
                                  workspace, workspace_size, command);
}

static void test_server_generated_ed25519_vector(void) {
  static const uint8_t command_id[ZS_COMMAND_UUID_BYTES] = {
      0x12u, 0x34u, 0x56u, 0x78u, 0x12u, 0x34u, 0x56u, 0x78u,
      0x12u, 0x34u, 0x56u, 0x78u, 0x12u, 0x34u, 0x56u, 0x78u};
  uint8_t public_key_digest[ZS_SHA256_DIGEST_BYTES];
  verifier_t verifier = {.accept = true};
  dedup_t dedup = {.state = ZS_COMMAND_DEDUP_NOT_SEEN};
  zs_command_t command;

  assert(sizeof(zs_command_vector_signed_cbor) <= sizeof(verifier.signed_cbor));
  memcpy(verifier.signed_cbor, zs_command_vector_signed_cbor,
         sizeof(zs_command_vector_signed_cbor));
  verifier.signed_size = sizeof(zs_command_vector_signed_cbor);
  memcpy(verifier.key_id, zs_command_vector_key_id, sizeof(verifier.key_id));
  memcpy(verifier.signature, zs_command_vector_signature,
         sizeof(verifier.signature));
  memcpy(dedup.expected_id, command_id, sizeof(command_id));

  zs_sha256_digest(zs_command_vector_public_key,
                   sizeof(zs_command_vector_public_key), public_key_digest);
  assert(memcmp(public_key_digest, zs_command_vector_key_id,
                ZS_COMMAND_KEY_ID_BYTES) == 0);
  assert(decode(zs_command_vector_payload, sizeof(zs_command_vector_payload),
                ZS_COMMAND_VECTOR_STATION_ID, UINT64_C(1500000), true,
                &verifier, &dedup, sizeof(verifier.signed_cbor), &command) ==
         ZS_COMMAND_STATUS_OK);
  assert(verifier.calls == 1u && dedup.calls == 1u);
  assert(command.created_time_us == ZS_COMMAND_VECTOR_CREATED_US);
  assert(command.expires_time_us == ZS_COMMAND_VECTOR_EXPIRES_US);
  assert(command.audio.event_id == 42u);
  assert(command.audio.segment == ZS_AUDIO_SEGMENT_BOTH);
}

static void test_valid_audio_commands_and_ack(void) {
  static const uint8_t command_id[ZS_COMMAND_UUID_BYTES] = {
      0x12u, 0x34u, 0x56u, 0x78u, 0x12u, 0x34u, 0x56u, 0x78u,
      0x12u, 0x34u, 0x56u, 0x78u, 0x12u, 0x34u, 0x56u, 0x78u};
  uint8_t payload[512], ack[128];
  verifier_t verifier = {.accept = true};
  dedup_t dedup = {.state = ZS_COMMAND_DEDUP_NOT_SEEN};
  zs_command_t command;
  size_t size, ack_size;
  memcpy(dedup.expected_id, command_id, sizeof(command_id));

  size = build_command(payload, sizeof(payload), &verifier, command_id, 17u,
                       UINT64_C(1000000), UINT64_C(2000000),
                       ZS_AUDIO_SEGMENT_BOTH);
  assert(decode(payload, size, 17u, UINT64_C(1500000), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_OK);
  assert(verifier.calls == 1u && dedup.calls == 1u);
  assert(command.station_id == 17u && command.code == ZS_COMMAND_REQUEST_AUDIO);
  assert(command.audio.event_id == 42u && command.audio.segment == ZS_AUDIO_SEGMENT_BOTH);
  assert(!command.audio.has_range);

  verifier.calls = 0u;
  dedup.calls = 0u;
  size = build_command(payload, sizeof(payload), &verifier, command_id, 17u,
                       UINT64_C(1000000), UINT64_C(2000000),
                       ZS_AUDIO_SEGMENT_RANGE);
  assert(decode(payload, size, 17u, UINT64_C(1500000), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_OK);
  assert(command.audio.has_range && command.audio.start_offset_ms == -5000);
  assert(command.audio.duration_ms == 10000u);

  ack_size = zs_command_encode_ack(17u, command_id, ZS_COMMAND_ACK_OK,
                                   UINT64_C(1750000), 0u, ack, sizeof(ack));
  assert(ack_size == sizeof(zs_command_vector_ack));
  assert(memcmp(ack, zs_command_vector_ack, ack_size) == 0);
  assert(ack[0] == 0xa7u && ack[1] == 0x00u && ack[2] == 0x01u);
  assert(ack[3] == 0x01u && ack[4] == 0x05u);
  assert(memcmp(&ack[9], command_id, sizeof(command_id)) == 0);
}

static void test_fail_closed_guards(void) {
  static const uint8_t command_id[ZS_COMMAND_UUID_BYTES] = {1u};
  uint8_t payload[512], noncanonical[513], nil_uuid[512];
  verifier_t verifier = {.accept = true};
  dedup_t dedup = {.state = ZS_COMMAND_DEDUP_NOT_SEEN};
  zs_command_t command;
  size_t size;
  memcpy(dedup.expected_id, command_id, sizeof(command_id));
  size = build_command(payload, sizeof(payload), &verifier, command_id, 17u,
                       UINT64_C(1000000), UINT64_C(2000000),
                       ZS_AUDIO_SEGMENT_BOTH);

  assert(decode(payload, size, 18u, UINT64_C(1500000), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_STATION_MISMATCH);
  assert(decode(payload, size, 17u, UINT64_C(1500000), false, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_TIME_UNTRUSTED);
  assert(decode(payload, size, 17u, UINT64_C(999999), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_NOT_YET_VALID);
  assert(decode(payload, size, 17u, UINT64_C(2000000), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_EXPIRED);
  assert(decode(payload, size, 17u, UINT64_C(1500000), true, &verifier,
                &dedup, 1u, &command) == ZS_COMMAND_STATUS_WORKSPACE_TOO_SMALL);

  verifier.accept = false;
  assert(decode(payload, size, 17u, UINT64_C(1500000), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_SIGNATURE_REJECTED);
  verifier.accept = true;
  dedup.state = ZS_COMMAND_DEDUP_SEEN;
  assert(decode(payload, size, 17u, UINT64_C(1500000), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_DUPLICATE);
  assert(memcmp(command.command_id, command_id, sizeof(command_id)) == 0);
  dedup.state = ZS_COMMAND_DEDUP_ERROR;
  assert(decode(payload, size, 17u, UINT64_C(1500000), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_DEDUP_STORAGE_ERROR);

  memcpy(noncanonical, payload, 6u);
  noncanonical[6] = 0x18u;
  noncanonical[7] = payload[6];
  memcpy(&noncanonical[8], &payload[7], size - 7u);
  assert(decode(noncanonical, size + 1u, 17u, UINT64_C(1500000), true,
                &verifier, &dedup, sizeof(payload), &command) ==
         ZS_COMMAND_STATUS_INVALID_CBOR);

  memcpy(nil_uuid, payload, size);
  memset(&nil_uuid[9], 0, ZS_COMMAND_UUID_BYTES);
  assert(decode(nil_uuid, size, 17u, UINT64_C(1500000), true,
                &verifier, &dedup, sizeof(payload), &command) ==
         ZS_COMMAND_STATUS_INVALID_CBOR);

  assert(zs_command_decode_verify(payload, size, 17u, UINT64_C(1500000), true,
      verify_signature, &verifier, NULL, NULL, noncanonical, sizeof(noncanonical),
      &command) == ZS_COMMAND_STATUS_DEDUP_REQUIRED);
  assert(zs_command_encode_ack(0u, command_id, ZS_COMMAND_ACK_OK, 1u, 0u,
                               noncanonical, sizeof(noncanonical)) == 0u);
  assert(zs_command_encode_ack(17u, command_id, (zs_command_ack_result_t)-1,
                               1u, 0u, noncanonical,
                               sizeof(noncanonical)) == 0u);
  assert(strcmp(zs_command_status_name((zs_command_status_t)-1), "?") == 0);
}

static void test_ttl_limit(void) {
  static const uint8_t command_id[ZS_COMMAND_UUID_BYTES] = {2u};
  uint8_t payload[512];
  verifier_t verifier = {.accept = true};
  dedup_t dedup = {.state = ZS_COMMAND_DEDUP_NOT_SEEN};
  zs_command_t command;
  size_t size;
  memcpy(dedup.expected_id, command_id, sizeof(command_id));
  size = build_command(payload, sizeof(payload), &verifier, command_id, 17u,
                       UINT64_C(1000000),
                       UINT64_C(1000000) + ZS_COMMAND_MAX_TTL_US + 1u,
                       ZS_AUDIO_SEGMENT_BOTH);
  assert(decode(payload, size, 17u, UINT64_C(1500000), true, &verifier,
                &dedup, sizeof(payload), &command) == ZS_COMMAND_STATUS_INVALID_TTL);
}

int main(void) {
  test_server_generated_ed25519_vector();
  test_valid_audio_commands_and_ack();
  test_fail_closed_guards();
  test_ttl_limit();
  puts("zs_command_transport_tests: OK");
  return 0;
}

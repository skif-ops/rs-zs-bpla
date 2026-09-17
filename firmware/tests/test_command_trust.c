#include "zs_command_trust.h"
#include "zs_command_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  bool accept;
  unsigned calls;
} backend_t;

static bool verify_backend(
    void *ctx,
    const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES],
    const uint8_t *message,
    size_t message_size,
    const uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES]) {
  backend_t *backend = ctx;
  ++backend->calls;
  return backend->accept &&
         memcmp(public_key, zs_command_vector_public_key,
                ZS_COMMAND_PUBLIC_KEY_BYTES) == 0 &&
         message_size == sizeof(zs_command_vector_signed_cbor) &&
         memcmp(message, zs_command_vector_signed_cbor, message_size) == 0 &&
         memcmp(signature, zs_command_vector_signature,
                ZS_COMMAND_SIGNATURE_BYTES) == 0;
}

static zs_command_trust_key_t vector_key(bool enabled) {
  zs_command_trust_key_t key;
  memcpy(key.public_key, zs_command_vector_public_key,
         ZS_COMMAND_PUBLIC_KEY_BYTES);
  key.enabled = enabled;
  return key;
}

static zs_command_dedup_state_t not_seen(
    void *ctx, const uint8_t command_id[ZS_COMMAND_UUID_BYTES]) {
  (void)ctx;
  (void)command_id;
  return ZS_COMMAND_DEDUP_NOT_SEEN;
}

static void test_enabled_key_and_backend_binding(void) {
  backend_t backend = {.accept = true};
  zs_command_trust_key_t key = vector_key(true);
  zs_command_trust_t trust;
  uint8_t unknown_id[ZS_COMMAND_KEY_ID_BYTES] = {0};
  assert(zs_command_trust_init(&trust, &key, 1u, verify_backend, &backend));
  assert(memcmp(trust.key_ids[0], zs_command_vector_key_id,
                ZS_COMMAND_KEY_ID_BYTES) == 0);
  assert(zs_command_trust_verify(
      &trust, zs_command_vector_key_id, zs_command_vector_signed_cbor,
      sizeof(zs_command_vector_signed_cbor), zs_command_vector_signature));
  assert(backend.calls == 1u);

  assert(!zs_command_trust_verify(
      &trust, unknown_id, zs_command_vector_signed_cbor,
      sizeof(zs_command_vector_signed_cbor), zs_command_vector_signature));
  assert(backend.calls == 1u);
  trust.key_count = ZS_COMMAND_TRUST_MAX_KEYS + 1u;
  assert(!zs_command_trust_verify(
      &trust, zs_command_vector_key_id, zs_command_vector_signed_cbor,
      sizeof(zs_command_vector_signed_cbor), zs_command_vector_signature));
  assert(backend.calls == 1u);
  trust.key_count = 1u;
  backend.accept = false;
  assert(!zs_command_trust_verify(
      &trust, zs_command_vector_key_id, zs_command_vector_signed_cbor,
      sizeof(zs_command_vector_signed_cbor), zs_command_vector_signature));
  assert(backend.calls == 2u);
}

static void test_fail_closed_configuration(void) {
  backend_t backend = {.accept = true};
  zs_command_trust_key_t keys[2];
  zs_command_trust_t trust;
  keys[0] = vector_key(false);
  assert(!zs_command_trust_init(&trust, keys, 1u, verify_backend, &backend));
  assert(!trust.initialized);

  keys[0] = vector_key(true);
  keys[1] = vector_key(true);
  assert(!zs_command_trust_init(&trust, keys, 2u, verify_backend, &backend));
  memset(keys[0].public_key, 0, sizeof(keys[0].public_key));
  assert(!zs_command_trust_init(&trust, keys, 1u, verify_backend, &backend));
  assert(!zs_command_trust_init(&trust, keys, 1u, NULL, &backend));
  assert(!zs_command_trust_init(NULL, keys, 1u, verify_backend, &backend));
}

static void test_decoder_integration(void) {
  backend_t backend = {.accept = true};
  zs_command_trust_key_t key = vector_key(true);
  zs_command_trust_t trust;
  zs_command_t command;
  uint8_t workspace[256];
  assert(zs_command_trust_init(&trust, &key, 1u, verify_backend, &backend));
  assert(zs_command_decode_verify(
      zs_command_vector_payload, sizeof(zs_command_vector_payload),
      ZS_COMMAND_VECTOR_STATION_ID, UINT64_C(1500000), true,
      zs_command_trust_verify, &trust, not_seen, NULL,
      workspace, sizeof(workspace), &command) == ZS_COMMAND_STATUS_OK);
  assert(backend.calls == 1u);
  assert(command.audio.event_id == 42u);
}

int main(void) {
  test_enabled_key_and_backend_binding();
  test_fail_closed_configuration();
  test_decoder_integration();
  puts("zs_command_trust_tests: OK");
  return 0;
}

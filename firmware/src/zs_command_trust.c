#include "zs_command_trust.h"

#include "zs_sha256.h"

#include <string.h>

static bool all_zero(const uint8_t *data, size_t size) {
  uint8_t combined = 0u;
  for (size_t i = 0u; i < size; ++i) combined |= data[i];
  return combined == 0u;
}

static bool bytes_equal(const uint8_t *left, const uint8_t *right, size_t size) {
  uint8_t difference = 0u;
  for (size_t i = 0u; i < size; ++i) difference |= left[i] ^ right[i];
  return difference == 0u;
}

bool zs_command_trust_init(
    zs_command_trust_t *trust,
    const zs_command_trust_key_t *keys,
    size_t key_count,
    zs_ed25519_verify_backend_fn backend,
    void *backend_ctx) {
  uint8_t digest[ZS_SHA256_DIGEST_BYTES];
  size_t enabled_count = 0u;
  if (!trust) return false;
  memset(trust, 0, sizeof(*trust));
  if (!keys || key_count == 0u || key_count > ZS_COMMAND_TRUST_MAX_KEYS ||
      !backend) return false;
  for (size_t i = 0u; i < key_count; ++i) {
    if (all_zero(keys[i].public_key, ZS_COMMAND_PUBLIC_KEY_BYTES)) {
      memset(trust, 0, sizeof(*trust));
      return false;
    }
    trust->keys[i] = keys[i];
    zs_sha256_digest(keys[i].public_key, ZS_COMMAND_PUBLIC_KEY_BYTES, digest);
    memcpy(trust->key_ids[i], digest, ZS_COMMAND_KEY_ID_BYTES);
    for (size_t previous = 0u; previous < i; ++previous) {
      if (bytes_equal(trust->key_ids[i], trust->key_ids[previous],
                      ZS_COMMAND_KEY_ID_BYTES)) {
        memset(trust, 0, sizeof(*trust));
        memset(digest, 0, sizeof(digest));
        return false;
      }
    }
    if (keys[i].enabled) ++enabled_count;
  }
  memset(digest, 0, sizeof(digest));
  if (enabled_count == 0u) {
    memset(trust, 0, sizeof(*trust));
    return false;
  }
  trust->key_count = key_count;
  trust->backend = backend;
  trust->backend_ctx = backend_ctx;
  trust->initialized = true;
  return true;
}

bool zs_command_trust_verify(
    void *ctx,
    const uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES],
    const uint8_t *signed_cbor,
    size_t signed_cbor_size,
    const uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES]) {
  const zs_command_trust_t *trust = ctx;
  if (!trust || !trust->initialized || !trust->backend || !key_id ||
      trust->key_count == 0u || trust->key_count > ZS_COMMAND_TRUST_MAX_KEYS ||
      !signed_cbor || signed_cbor_size == 0u ||
      signed_cbor_size > ZS_COMMAND_MAX_BYTES || !signature) return false;
  for (size_t i = 0u; i < trust->key_count; ++i) {
    if (trust->keys[i].enabled &&
        bytes_equal(key_id, trust->key_ids[i], ZS_COMMAND_KEY_ID_BYTES)) {
      return trust->backend(trust->backend_ctx, trust->keys[i].public_key,
                            signed_cbor, signed_cbor_size, signature);
    }
  }
  return false;
}

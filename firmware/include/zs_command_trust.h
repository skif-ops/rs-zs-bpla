#ifndef ZS_COMMAND_TRUST_H
#define ZS_COMMAND_TRUST_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_command.h"

#define ZS_COMMAND_PUBLIC_KEY_BYTES 32u
#define ZS_COMMAND_TRUST_MAX_KEYS 4u

typedef bool (*zs_ed25519_verify_backend_fn)(
    void *ctx,
    const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES],
    const uint8_t *message,
    size_t message_size,
    const uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES]);

typedef struct {
  uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES];
  bool enabled;
} zs_command_trust_key_t;

typedef struct {
  zs_command_trust_key_t keys[ZS_COMMAND_TRUST_MAX_KEYS];
  uint8_t key_ids[ZS_COMMAND_TRUST_MAX_KEYS][ZS_COMMAND_KEY_ID_BYTES];
  size_t key_count;
  zs_ed25519_verify_backend_fn backend;
  void *backend_ctx;
  bool initialized;
} zs_command_trust_t;

/*
 * Copies and validates a bounded public-key set. No production key material is
 * compiled into this module; target provisioning supplies the entries and a
 * reviewed Ed25519 verification backend.
 */
bool zs_command_trust_init(
    zs_command_trust_t *trust,
    const zs_command_trust_key_t *keys,
    size_t key_count,
    zs_ed25519_verify_backend_fn backend,
    void *backend_ctx);

/* Signature callback compatible with zs_command_decode_verify(). */
bool zs_command_trust_verify(
    void *ctx,
    const uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES],
    const uint8_t *signed_cbor,
    size_t signed_cbor_size,
    const uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES]);

#endif

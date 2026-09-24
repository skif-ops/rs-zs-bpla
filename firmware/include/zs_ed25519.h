#ifndef ZS_ED25519_H
#define ZS_ED25519_H
/*
 * Ed25519 signature verification (RFC 8032, pure) and SHA-512 for the command trust backend
 * (zs_command_trust): the server signs command CBOR with its Ed25519 key (station/command_codec.py),
 * the station holds the raw public key in the secrets record (ICD BLE v0.3, key 4).
 * Portable C99 in the TweetNaCl style (16 x 16-bit limbs in int64): no tables, no heap, ~2 KB stack;
 * a verify costs a few ms on the host and tens of ms on the Cortex-M33. Verification only - the
 * station never signs. Host-tested against the `cryptography` library vectors (test_ed25519.c).
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_ED25519_PUBLIC_KEY_BYTES 32u
#define ZS_ED25519_SIGNATURE_BYTES 64u
#define ZS_SHA512_DIGEST_BYTES 64u

void zs_sha512(const uint8_t *data, size_t len, uint8_t out[ZS_SHA512_DIGEST_BYTES]);

/* True when `signature` is a valid Ed25519 signature of `message` under `public_key`.
   Rejects non-canonical S (>= L) and public keys / R that do not decode to curve points. */
bool zs_ed25519_verify(const uint8_t public_key[ZS_ED25519_PUBLIC_KEY_BYTES],
                       const uint8_t *message, size_t message_len,
                       const uint8_t signature[ZS_ED25519_SIGNATURE_BYTES]);

#endif

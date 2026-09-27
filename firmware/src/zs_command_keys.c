#include "zs_command_keys.h"

#include "zs_sha256.h"

#include <string.h>

void zs_command_key_id(const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES], uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES]) {
  uint8_t digest[ZS_SHA256_DIGEST_BYTES];
  zs_sha256_digest(public_key, ZS_COMMAND_PUBLIC_KEY_BYTES, digest);
  memcpy(key_id, digest, ZS_COMMAND_KEY_ID_BYTES);
}

uint64_t zs_command_key_id_u64(const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES]) {
  uint8_t id[ZS_COMMAND_KEY_ID_BYTES];
  uint64_t v = 0u;
  zs_command_key_id(public_key, id);
  for (unsigned i = 0u; i < ZS_COMMAND_KEY_ID_BYTES; i++) v = (v << 8) | id[i];
  return v;
}

size_t zs_command_keys_trust_set(const zs_station_secrets_t *rec, zs_command_trust_key_t out[2]) {
  size_t n = 0u;
  if (!rec || !out || !rec->command_key_set) return 0u;
  memset(out, 0, 2u * sizeof(out[0]));
  memcpy(out[n].public_key, rec->command_public_key, ZS_COMMAND_PUBLIC_KEY_BYTES); out[n++].enabled = true;
  if (rec->command_next_key_set) { memcpy(out[n].public_key, rec->command_next_key, ZS_COMMAND_PUBLIC_KEY_BYTES); out[n++].enabled = true; }
  return n;
}

static bool all_zero(const uint8_t *p, size_t n) {
  uint8_t acc = 0u;
  for (size_t i = 0u; i < n; i++) acc |= p[i];
  return acc == 0u;
}

void zs_command_keys_rotate(const zs_station_secrets_io_t *io, const uint8_t next[ZS_COMMAND_PUBLIC_KEY_BYTES],
                            zs_command_ack_result_t *result, uint16_t *detail) {
  zs_station_secrets_t rec;
  *result = ZS_COMMAND_ACK_OK;
  *detail = 0u;
  if (!io || zs_station_secrets_load(io, &rec, NULL) != ZS_STATION_SECRETS_OK || !rec.command_key_set) {
    *result = ZS_COMMAND_ACK_REJECTED; *detail = ZS_COMMAND_KEYS_REJECT_NO_RECORD; return;
  }
  if (all_zero(next, ZS_COMMAND_PUBLIC_KEY_BYTES) || memcmp(next, rec.command_public_key, ZS_COMMAND_PUBLIC_KEY_BYTES) == 0) {
    *result = ZS_COMMAND_ACK_REJECTED; *detail = ZS_COMMAND_KEYS_REJECT_INVALID_KEY;
  } else if (!(rec.command_next_key_set && memcmp(next, rec.command_next_key, ZS_COMMAND_PUBLIC_KEY_BYTES) == 0)) {
    rec.command_next_key_set = true;                 /* a pending next key is replaced: the server changed its mind */
    memcpy(rec.command_next_key, next, ZS_COMMAND_PUBLIC_KEY_BYTES);
    if (zs_station_secrets_commit(io, &rec) != ZS_STATION_SECRETS_OK) { *result = ZS_COMMAND_ACK_FAILED; *detail = ZS_COMMAND_KEYS_FAIL_STORAGE; }
  }
  memset(&rec, 0, sizeof(rec));
}

bool zs_command_keys_on_verified(const zs_station_secrets_io_t *io, const uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES]) {
  zs_station_secrets_t rec;
  uint8_t next_id[ZS_COMMAND_KEY_ID_BYTES];
  bool promoted = false;
  if (!io || !key_id || zs_station_secrets_load(io, &rec, NULL) != ZS_STATION_SECRETS_OK || !rec.command_next_key_set) return false;
  zs_command_key_id(rec.command_next_key, next_id);
  if (memcmp(next_id, key_id, ZS_COMMAND_KEY_ID_BYTES) == 0) {
    memcpy(rec.command_public_key, rec.command_next_key, ZS_COMMAND_PUBLIC_KEY_BYTES);
    rec.command_key_set = true;
    rec.command_next_key_set = false;
    memset(rec.command_next_key, 0, sizeof(rec.command_next_key));
    promoted = zs_station_secrets_commit(io, &rec) == ZS_STATION_SECRETS_OK;
  }
  memset(&rec, 0, sizeof(rec));
  return promoted;
}

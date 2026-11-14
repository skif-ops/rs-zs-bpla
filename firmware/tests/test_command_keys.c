/* MQTT ICD addendum E, command key rotation: the server-signed shared vector (tools/generate_command_rotate_vector.py)
   goes through the real trust adapter and Ed25519 backend on a RAM secrets store.
     current key k1 -> CMD_ROTATE_COMMAND_KEY(k2) signed by k1 -> both trusted -> CMD_SET_PARAMS signed by k2 promotes
     k2 -> a k1-signed command is refused afterwards.
   Also: idempotent rotation, refused keys, no record, a torn commit, the heartbeat key id. */
#include "zs_command_keys.h"
#include "zs_command_rotate_vector.h"
#include "zs_ed25519.h"
#include "zs_sha256.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t slots[2][ZS_STATION_SECRETS_SLOT_BYTES]; unsigned writes, fail_write, commits; } ram_t;
static bool r_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { ram_t *m = c; if (s >= 2u || o + n > ZS_STATION_SECRETS_SLOT_BYTES) return false; memcpy(d, &m->slots[s][o], n); return true; }
static bool r_erase(void *c, uint8_t s) { ram_t *m = c; if (s >= 2u) return false; memset(m->slots[s], 0xff, ZS_STATION_SECRETS_SLOT_BYTES); m->commits++; return true; }
static bool r_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) {
  ram_t *m = c;
  if (s >= 2u || o + n > ZS_STATION_SECRETS_SLOT_BYTES) return false;
  if (++m->writes == m->fail_write) return false;
  for (size_t i = 0u; i < n; i++) { if ((m->slots[s][o + i] & d[i]) != d[i]) return false; m->slots[s][o + i] = d[i]; }
  return true;
}

static bool ed25519(void *ctx, const uint8_t pk[ZS_COMMAND_PUBLIC_KEY_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx; return zs_ed25519_verify(pk, m, n, sig);
}
static zs_command_dedup_state_t never_seen(void *ctx, const uint8_t id[ZS_COMMAND_UUID_BYTES]) { (void)ctx; (void)id; return ZS_COMMAND_DEDUP_NOT_SEEN; }

/* decode with the trust set of the stored record, as app_comms builds it */
static zs_command_status_t decode(const zs_station_secrets_io_t *io, const uint8_t *p, size_t n, zs_command_t *c) {
  static uint8_t workspace[256];
  zs_station_secrets_t rec;
  zs_command_trust_key_t keys[2];
  zs_command_trust_t trust;
  size_t count;
  assert(zs_station_secrets_load(io, &rec, NULL) == ZS_STATION_SECRETS_OK);
  count = zs_command_keys_trust_set(&rec, keys);
  assert(count >= 1u && zs_command_trust_init(&trust, keys, count, ed25519, NULL));
  return zs_command_decode_verify(p, n, ZS_COMMAND_ROTATE_VECTOR_STATION_ID, ZS_COMMAND_ROTATE_VECTOR_CREATED_US + 1000u, true,
                                  zs_command_trust_verify, &trust, never_seen, NULL, workspace, sizeof(workspace), c);
}

int main(void) {
  static ram_t m;
  const zs_station_secrets_io_t io = {&m, r_read, r_erase, r_write};
  zs_station_secrets_t rec;
  zs_command_t rotate, params, reboot;
  zs_command_ack_result_t result;
  uint16_t detail;
  uint8_t id1[8], id2[8], zero[32] = {0};
  zs_command_trust_key_t keys[2];

  memset(&m, 0xff, sizeof(m)); m.writes = m.fail_write = m.commits = 0u;
  zs_command_key_id(zs_command_rotate_vector_current_public_key, id1);
  zs_command_key_id(zs_command_rotate_vector_next_public_key, id2);

  /* no record: nothing to rotate, nothing to promote */
  zs_command_keys_rotate(&io, zs_command_rotate_vector_next_public_key, &result, &detail);
  assert(result == ZS_COMMAND_ACK_REJECTED && detail == ZS_COMMAND_KEYS_REJECT_NO_RECORD && m.commits == 0u);
  assert(!zs_command_keys_on_verified(&io, id2));

  /* provisioned over BLE: k1 and the ICCID of slot 1 */
  memset(&rec, 0, sizeof(rec));
  rec.command_key_set = true; memcpy(rec.command_public_key, zs_command_rotate_vector_current_public_key, 32u);
  strcpy(rec.iccid[0], "89701012345678901234");
  assert(zs_station_secrets_commit(&io, &rec) == ZS_STATION_SECRETS_OK);
  assert(zs_command_keys_trust_set(&rec, keys) == 1u);
  assert(zs_command_keys_trust_set(NULL, keys) == 0u);

  /* the k1-signed rotation verifies; k1 is not a next key, so no promotion */
  assert(decode(&io, zs_command_rotate_vector_rotate, sizeof(zs_command_rotate_vector_rotate), &rotate) == ZS_COMMAND_STATUS_OK);
  assert(rotate.code == ZS_COMMAND_ROTATE_KEY && memcmp(rotate.key_id, id1, 8u) == 0);
  assert(memcmp(rotate.rotate.public_key, zs_command_rotate_vector_next_public_key, 32u) == 0);
  assert(!zs_command_keys_on_verified(&io, rotate.key_id));
  /* before the rotation a k2-signed command is refused */
  assert(decode(&io, zs_command_rotate_vector_params_by_next, sizeof(zs_command_rotate_vector_params_by_next), &params) == ZS_COMMAND_STATUS_SIGNATURE_REJECTED);

  /* a torn commit keeps the old trust set and reports FAILED 1 */
  m.fail_write = m.writes + 2u;
  zs_command_keys_rotate(&io, rotate.rotate.public_key, &result, &detail);
  assert(result == ZS_COMMAND_ACK_FAILED && detail == ZS_COMMAND_KEYS_FAIL_STORAGE);
  m.fail_write = 0u;
  assert(zs_station_secrets_load(&io, &rec, NULL) == ZS_STATION_SECRETS_OK && !rec.command_next_key_set);

  /* executed: k2 is the next key, both trusted, the other secrets untouched */
  zs_command_keys_rotate(&io, rotate.rotate.public_key, &result, &detail);
  assert(result == ZS_COMMAND_ACK_OK && detail == 0u);
  assert(zs_station_secrets_load(&io, &rec, NULL) == ZS_STATION_SECRETS_OK && rec.command_next_key_set && strcmp(rec.iccid[0], "89701012345678901234") == 0);
  assert(zs_command_keys_trust_set(&rec, keys) == 2u && memcmp(keys[1].public_key, zs_command_rotate_vector_next_public_key, 32u) == 0);
  { const unsigned c = m.commits;                     /* the same rotation again: OK, nothing written */
    zs_command_keys_rotate(&io, rotate.rotate.public_key, &result, &detail);
    assert(result == ZS_COMMAND_ACK_OK && m.commits == c); }
  zs_command_keys_rotate(&io, zs_command_rotate_vector_current_public_key, &result, &detail);   /* to the current key */
  assert(result == ZS_COMMAND_ACK_REJECTED && detail == ZS_COMMAND_KEYS_REJECT_INVALID_KEY);
  zs_command_keys_rotate(&io, zero, &result, &detail);
  assert(result == ZS_COMMAND_ACK_REJECTED && detail == ZS_COMMAND_KEYS_REJECT_INVALID_KEY);

  /* the old key still works during the overlap */
  assert(decode(&io, zs_command_rotate_vector_reboot_by_current, sizeof(zs_command_rotate_vector_reboot_by_current), &reboot) == ZS_COMMAND_STATUS_OK);
  assert(!zs_command_keys_on_verified(&io, reboot.key_id));

  /* the first k2-signed command promotes k2 and drops k1 */
  assert(decode(&io, zs_command_rotate_vector_params_by_next, sizeof(zs_command_rotate_vector_params_by_next), &params) == ZS_COMMAND_STATUS_OK);
  assert(params.code == ZS_COMMAND_SET_PARAMS && memcmp(params.key_id, id2, 8u) == 0);
  assert(zs_command_keys_on_verified(&io, params.key_id));
  assert(zs_station_secrets_load(&io, &rec, NULL) == ZS_STATION_SECRETS_OK && !rec.command_next_key_set);
  assert(memcmp(rec.command_public_key, zs_command_rotate_vector_next_public_key, 32u) == 0);
  assert(!zs_command_keys_on_verified(&io, params.key_id));                          /* once */
  assert(decode(&io, zs_command_rotate_vector_reboot_by_current, sizeof(zs_command_rotate_vector_reboot_by_current), &reboot) == ZS_COMMAND_STATUS_SIGNATURE_REJECTED);

  /* the heartbeat key id is the big-endian value of the §2.1 key id */
  { uint8_t digest[ZS_SHA256_DIGEST_BYTES]; uint64_t v = 0u;
    zs_sha256_digest(zs_command_rotate_vector_next_public_key, 32u, digest);
    for (unsigned i = 0u; i < 8u; i++) v = (v << 8) | digest[i];
    assert(zs_command_key_id_u64(zs_command_rotate_vector_next_public_key) == v && v != 0u); }

  puts("zs_command_keys_tests: OK");
  return 0;
}

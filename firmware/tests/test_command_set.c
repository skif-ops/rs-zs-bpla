/* ICD addendum D commands (CMD_REBOOT, CMD_SET_PARAMS): the server-signed shared vector decodes and verifies with the
   real Ed25519 backend, both commands pass the durable journal (distinct fingerprints, conflict on a reused UUID with
   different parameters), and malformed payloads are rejected before any side effect. */
#include "zs_command.h"
#include "zs_command_journal.h"
#include "zs_command_set_vector.h"
#include "zs_ed25519.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t slots[4][ZS_COMMAND_JOURNAL_SLOT_BYTES]; } ram_journal_t;
static bool j_read(void *ctx, uint16_t slot, uint32_t off, uint8_t *d, size_t n) { ram_journal_t *m = ctx; if (slot >= 4u || off + n > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false; memcpy(d, &m->slots[slot][off], n); return true; }
static bool j_erase(void *ctx, uint16_t slot) { ram_journal_t *m = ctx; if (slot >= 4u) return false; memset(m->slots[slot], 0xff, ZS_COMMAND_JOURNAL_SLOT_BYTES); return true; }
static bool j_write(void *ctx, uint16_t slot, uint32_t off, const uint8_t *d, size_t n) {
  ram_journal_t *m = ctx;
  if (slot >= 4u || off + n > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false;
  for (size_t i = 0u; i < n; i++) { if ((m->slots[slot][off + i] & d[i]) != d[i]) return false; m->slots[slot][off + i] = d[i]; }
  return true;
}

static bool verify(void *ctx, const uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx; (void)key_id;
  return zs_ed25519_verify(zs_command_set_vector_public_key, m, n, sig);
}
static zs_command_dedup_state_t never_seen(void *ctx, const uint8_t id[ZS_COMMAND_UUID_BYTES]) { (void)ctx; (void)id; return ZS_COMMAND_DEDUP_NOT_SEEN; }

static zs_command_status_t decode(const uint8_t *p, size_t n, zs_command_t *c) {
  static uint8_t workspace[256];
  return zs_command_decode_verify(p, n, ZS_COMMAND_SET_VECTOR_STATION_ID, ZS_COMMAND_SET_VECTOR_CREATED_US + 1000u, true,
                                  verify, NULL, never_seen, NULL, workspace, sizeof(workspace), c);
}

int main(void) {
  zs_command_t reboot, params, tampered;
  uint8_t copy[512];
  ram_journal_t ram;
  zs_command_journal_io_t io = {&ram, 4u, j_read, j_erase, j_write};
  const uint64_t now = ZS_COMMAND_SET_VECTOR_CREATED_US + 1000u;

  /* the server-signed envelopes */
  assert(decode(zs_command_set_vector_reboot, sizeof(zs_command_set_vector_reboot), &reboot) == ZS_COMMAND_STATUS_OK);
  assert(reboot.code == ZS_COMMAND_REBOOT && reboot.reboot.delay_s == 30u && reboot.station_id == 17u);
  assert(decode(zs_command_set_vector_params, sizeof(zs_command_set_vector_params), &params) == ZS_COMMAND_STATUS_OK);
  assert(params.code == ZS_COMMAND_SET_PARAMS && !params.params.reset_to_defaults && params.params.count == 3u);
  assert(params.params.id[0] == 1u && params.params.value[0] == 3600);     /* heartbeat_period_s */
  assert(params.params.id[1] == 2u && params.params.value[1] == 2);        /* mic_channel */
  assert(params.params.id[2] == 6u && params.params.value[2] == 5);        /* listen_dwell_s */

  /* one flipped payload byte: the signature no longer matches (or the structure breaks) - never OK */
  memcpy(copy, zs_command_set_vector_params, sizeof(zs_command_set_vector_params));
  for (size_t i = 60u; i < sizeof(zs_command_set_vector_params) - 70u; i++) {
    copy[i] ^= 0x01u;
    assert(decode(copy, sizeof(zs_command_set_vector_params), &tampered) != ZS_COMMAND_STATUS_OK);
    copy[i] ^= 0x01u;
  }

  /* durable journal: both commands accepted and completed; a reused UUID with other parameters is a conflict */
  for (unsigned s = 0u; s < 4u; s++) j_erase(&ram, (uint16_t)s);
  assert(zs_command_journal_accept(&io, &reboot, now) == ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_complete(&io, reboot.command_id, ZS_COMMAND_ACK_OK, 0u, now + 1u) == ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_accept(&io, &reboot, now + 2u) == ZS_COMMAND_JOURNAL_ALREADY_COMPLETED);   /* no second reboot */
  assert(zs_command_journal_accept(&io, &params, now) == ZS_COMMAND_JOURNAL_OK);
  tampered = params;
  tampered.params.value[1] = 3;
  assert(zs_command_journal_accept(&io, &tampered, now + 3u) == ZS_COMMAND_JOURNAL_CONFLICT);
  tampered = reboot;
  tampered.reboot.delay_s = 31u;
  assert(zs_command_journal_accept(&io, &tampered, now + 3u) == ZS_COMMAND_JOURNAL_CONFLICT);
  /* invalid semantics never reach the journal */
  tampered = params;
  tampered.params.count = 0u;
  assert(zs_command_journal_accept(&io, &tampered, now) != ZS_COMMAND_JOURNAL_OK);
  tampered.params.reset_to_defaults = true;
  tampered.command_id[15] ^= 0x55u;
  assert(zs_command_journal_accept(&io, &tampered, now) == ZS_COMMAND_JOURNAL_OK);         /* reset with no params is valid */
  printf("command set (addendum D) tests passed\n");
  return 0;
}

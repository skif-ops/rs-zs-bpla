/* MQTT ICD addendum F, firmware update: the server-signed shared vector (tools/generate_fw_update_vector.py) through
   the real command decoder, the release check (Ed25519 over "DIO-FW-V1" || manifest) and the download engine on a
   RAM flash bank with flash semantics (erase to 0xFF, program only erased quad-words).
     envelope -> CMD_UPDATE_FIRMWARE payload -> every refusal of zs_fw_update_check -> fwreq bytes equal the server's
     -> chunks out of order / foreign / repeated are skipped -> image programmed (tail padded) -> SHA-256 read back and
     .fw_info -> OK; flash, SHA-256, .fw_info and stall failures. */
#include "zs_command.h"
#include "zs_command_journal.h"
#include "zs_command_rotate_vector.h"
#include "zs_command_trust.h"
#include "zs_ed25519.h"
#include "zs_fw_update.h"
#include "zs_fw_update_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define BANK_BYTES 8192u
#define PAGE 1024u
typedef struct {
  uint8_t mem[BANK_BYTES];
  unsigned erases, programs, fail_program_at, fail_erase_at;
} bank_t;
static bool b_erase(void *c, uint32_t o, uint32_t n) {
  bank_t *b = c;
  if (o % PAGE || n % PAGE || o + n > BANK_BYTES) return false;
  if (++b->erases == b->fail_erase_at) return false;
  memset(&b->mem[o], 0xff, n);
  return true;
}
static bool b_program(void *c, uint32_t o, const uint8_t *d, size_t n) {
  bank_t *b = c;
  if (o % 16u || n % 16u || o + n > BANK_BYTES) return false;
  if (++b->programs == b->fail_program_at) return false;
  for (size_t i = 0u; i < n; i++) if (b->mem[o + i] != 0xffu) return false;    /* a quad-word is programmed once */
  memcpy(&b->mem[o], d, n);
  return true;
}
static bool b_read(void *c, uint32_t o, uint8_t *d, size_t n) { bank_t *b = c; if (o + n > BANK_BYTES) return false; memcpy(d, &b->mem[o], n); return true; }

static uint8_t journal[4][ZS_COMMAND_JOURNAL_SLOT_BYTES];
static bool j_read(void *c, uint16_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s >= 4u || o + n > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false; memcpy(d, &journal[s][o], n); return true; }
static bool j_erase(void *c, uint16_t s) { (void)c; if (s >= 4u) return false; memset(journal[s], 0xff, ZS_COMMAND_JOURNAL_SLOT_BYTES); return true; }
static bool j_write(void *c, uint16_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s >= 4u || o + n > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((journal[s][o + i] & d[i]) != d[i]) return false; journal[s][o + i] = d[i]; } return true; }

static bool ed25519(void *ctx, const uint8_t pk[ZS_COMMAND_PUBLIC_KEY_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx; return zs_ed25519_verify(pk, m, n, sig);
}
static zs_command_dedup_state_t never_seen(void *ctx, const uint8_t id[ZS_COMMAND_UUID_BYTES]) { (void)ctx; (void)id; return ZS_COMMAND_DEDUP_NOT_SEEN; }

static const zs_fw_chunk_t *chunk(unsigned i) {
  static zs_fw_chunk_t c[3];
  const uint8_t *msg[3] = {zs_fw_update_vector_chunk0, zs_fw_update_vector_chunk1, zs_fw_update_vector_chunk2};
  const size_t len[3] = {sizeof(zs_fw_update_vector_chunk0), sizeof(zs_fw_update_vector_chunk1), sizeof(zs_fw_update_vector_chunk2)};
  assert(zs_fw_chunk_decode(msg[i], len[i], &c[i]));
  return &c[i];
}

/* runs the engine to the end with the three chunks in order; returns the final step */
static zs_fw_step_t run_all(zs_fw_download_t *dl) {
  zs_fw_step_t st;
  unsigned guard = 0u;
  while ((st = zs_fw_download_step(dl, 512u)) != ZS_FW_STEP_FINISHED && guard++ < 1000u) {
    if (st == ZS_FW_STEP_NEED_CHUNK) {
      const zs_fw_chunk_result_t r = zs_fw_download_on_chunk(dl, chunk(dl->chunks));
      if (r == ZS_FW_CHUNK_FAILED) return zs_fw_download_step(dl, 512u);
      assert(r == ZS_FW_CHUNK_ACCEPTED);
    }
  }
  return st;
}

int main(void) {
  static uint8_t workspace[256];
  zs_command_t cmd;
  zs_command_trust_key_t key;
  zs_command_trust_t trust;
  zs_fw_release_key_t release;
  zs_fw_station_t station;
  zs_fw_manifest_t manifest;
  uint8_t digest[32], buf[64];
  zs_fw_info_t info;

  /* ---- the envelope: code 5 with the manifest, the release key id and the signature ---- */
  memset(&key, 0, sizeof(key));
  memcpy(key.public_key, zs_command_rotate_vector_current_public_key, 32u);
  key.enabled = true;
  assert(zs_command_trust_init(&trust, &key, 1u, ed25519, NULL));
  assert(zs_command_decode_verify(zs_fw_update_vector_command, sizeof(zs_fw_update_vector_command), ZS_FW_UPDATE_VECTOR_STATION_ID,
                                  ZS_FW_UPDATE_VECTOR_CREATED_US + 1000u, true, zs_command_trust_verify, &trust, never_seen, NULL,
                                  workspace, sizeof(workspace), &cmd) == ZS_COMMAND_STATUS_OK);
  assert(cmd.code == ZS_COMMAND_UPDATE_FIRMWARE);
  assert(cmd.firmware.manifest_size == sizeof(zs_fw_update_vector_manifest) &&
         memcmp(cmd.firmware.manifest, zs_fw_update_vector_manifest, sizeof(zs_fw_update_vector_manifest)) == 0);
  assert(memcmp(cmd.firmware.signature, zs_fw_update_vector_signature, 64u) == 0);
  memcpy(release.public_key, zs_fw_update_vector_release_public_key, 32u);
  { uint8_t id[8]; zs_fw_release_key_id(release.public_key, id); assert(memcmp(id, cmd.firmware.key_id, 8u) == 0); }
  { /* a truncated payload map is refused by the codec */
    uint8_t bad[sizeof(zs_fw_update_vector_command)];
    memcpy(bad, zs_fw_update_vector_command, sizeof(bad));
    for (size_t i = 0u; i + 1u < sizeof(bad); i++) if (bad[i] == 0x07u && bad[i + 1u] == 0xa3u) { bad[i + 1u] = 0xa2u; break; }
    assert(zs_command_decode_verify(bad, sizeof(bad), ZS_FW_UPDATE_VECTOR_STATION_ID, ZS_FW_UPDATE_VECTOR_CREATED_US + 1000u, true,
                                    zs_command_trust_verify, &trust, never_seen, NULL, workspace, sizeof(workspace), &cmd) == ZS_COMMAND_STATUS_INVALID_CBOR);
    assert(zs_command_decode_verify(zs_fw_update_vector_command, sizeof(zs_fw_update_vector_command), ZS_FW_UPDATE_VECTOR_STATION_ID,
                                    ZS_FW_UPDATE_VECTOR_CREATED_US + 1000u, true, zs_command_trust_verify, &trust, never_seen, NULL,
                                    workspace, sizeof(workspace), &cmd) == ZS_COMMAND_STATUS_OK);
  }

  /* ---- the release check ---- */
  station = (zs_fw_station_t){&release, 1u, ZS_FW_TARGET_STM32_APP, 6u, BANK_BYTES - PAGE, false};
  assert(zs_fw_update_check(&cmd.firmware, &station, &manifest) == 0u);
  assert(manifest.target == 1u && manifest.version == ZS_FW_UPDATE_VECTOR_VERSION && manifest.size == sizeof(zs_fw_update_vector_image));
  zs_sha256_digest(zs_fw_update_vector_image, sizeof(zs_fw_update_vector_image), digest);
  assert(memcmp(manifest.sha256, digest, 32u) == 0);
  {
    zs_fw_station_t s = station;
    zs_update_firmware_command_t f = cmd.firmware;
    s.key_count = 0u; assert(zs_fw_update_check(&f, &s, &manifest) == ZS_FW_REJECT_UNSUPPORTED);
    s = station; s.capacity = 0u; assert(zs_fw_update_check(&f, &s, &manifest) == ZS_FW_REJECT_UNSUPPORTED);
    s = station; s.target = ZS_FW_TARGET_NRF52; assert(zs_fw_update_check(&f, &s, &manifest) == ZS_FW_REJECT_TARGET);
    s = station; s.running_version = 7u; assert(zs_fw_update_check(&f, &s, &manifest) == ZS_FW_REJECT_VERSION);
    s = station; s.running_version = 9u; assert(zs_fw_update_check(&f, &s, &manifest) == ZS_FW_REJECT_VERSION);
    s = station; s.capacity = 2048u; assert(zs_fw_update_check(&f, &s, &manifest) == ZS_FW_REJECT_SIZE);
    s = station; s.trial = true; assert(zs_fw_update_check(&f, &s, &manifest) == ZS_FW_REJECT_TRIAL);
    f.signature[10] ^= 1u; assert(zs_fw_update_check(&f, &station, &manifest) == ZS_FW_REJECT_MANIFEST);
    f = cmd.firmware; f.manifest[f.manifest_size - 1u] ^= 1u; assert(zs_fw_update_check(&f, &station, &manifest) == ZS_FW_REJECT_MANIFEST);
    f = cmd.firmware; f.key_id[0] ^= 1u; assert(zs_fw_update_check(&f, &station, &manifest) == ZS_FW_REJECT_MANIFEST);
    f = cmd.firmware; f.manifest_size = 3u; assert(zs_fw_update_check(&f, &station, &manifest) == ZS_FW_REJECT_MANIFEST);
    { /* a second, unrelated release key does not help a foreign signature; the right key in slot 2 works */
      zs_fw_release_key_t two[2];
      memset(two[0].public_key, 0x42, 32u); two[1] = release;
      s = station; s.keys = two; s.key_count = 2u;
      assert(zs_fw_update_check(&cmd.firmware, &s, &manifest) == 0u);
    }
    assert(zs_fw_update_check(&cmd.firmware, &station, &manifest) == 0u);
  }

  /* ---- .fw_info and the messages ---- */
  assert(zs_fw_info_parse(&zs_fw_update_vector_image[ZS_FW_INFO_OFFSET], &info) && info.target == 1u && info.version == 7u);
  { uint8_t b[32]; zs_fw_info_encode(1u, 7u, b); assert(memcmp(b, &zs_fw_update_vector_image[ZS_FW_INFO_OFFSET], 32u) == 0); b[0] ^= 1u; assert(!zs_fw_info_parse(b, &info)); }
  assert(zs_fw_request_encode(ZS_FW_UPDATE_VECTOR_STATION_ID, cmd.command_id, 0u, 1024u, buf, sizeof(buf)) == sizeof(zs_fw_update_vector_request0) &&
         memcmp(buf, zs_fw_update_vector_request0, sizeof(zs_fw_update_vector_request0)) == 0);
  {
    uint32_t sid, off, len; uint8_t id[16];
    assert(zs_fw_request_decode(zs_fw_update_vector_request0, sizeof(zs_fw_update_vector_request0), &sid, id, &off, &len));
    assert(sid == 17u && off == 0u && len == 1024u && memcmp(id, cmd.command_id, 16u) == 0);
    assert(zs_fw_request_encode(17u, cmd.command_id, 0u, 1025u, buf, sizeof(buf)) == 0u);
    assert(!zs_fw_chunk_decode(zs_fw_update_vector_request0, sizeof(zs_fw_update_vector_request0), &(zs_fw_chunk_t){0}));  /* type 8 is no chunk */
    assert(!zs_fw_chunk_decode(zs_fw_update_vector_chunk0, sizeof(zs_fw_update_vector_chunk0) - 1u, &(zs_fw_chunk_t){0}));
  }
  assert(chunk(0)->offset == 0u && chunk(1)->offset == 1024u && chunk(2)->offset == 2048u && chunk(2)->data_len == 552u);

  /* ---- the download engine ---- */
  {
    static bank_t bank;
    const zs_fw_image_io_t io = {&bank, BANK_BYTES - PAGE, PAGE, BANK_BYTES - PAGE, b_erase, b_program, b_read, NULL};
    zs_fw_download_t dl;
    zs_fw_chunk_t foreign;
    uint8_t foreign_msg[sizeof(zs_fw_update_vector_chunk0)];
    size_t n;
    memset(bank.mem, 0x00, sizeof(bank.mem));               /* old content everywhere, the record page included */
    assert(!zs_fw_download_start(&dl, &io, 17u, cmd.command_id, &(zs_fw_manifest_t){1u, 7u, BANK_BYTES, {0}}));   /* larger than the image area */
    assert(zs_fw_download_start(&dl, &io, 17u, cmd.command_id, &manifest));
    assert(zs_fw_download_active(&dl) && zs_fw_download_want(&dl) == 0u);
    assert(zs_fw_download_step(&dl, 0u) == ZS_FW_STEP_BUSY);        /* one page per call on a small budget */
    assert(zs_fw_download_step(&dl, 0u) == ZS_FW_STEP_BUSY);
    assert(zs_fw_download_step(&dl, 0u) == ZS_FW_STEP_NEED_CHUNK);  /* 3 image pages, then the record page */
    assert(bank.erases == 4u && bank.mem[BANK_BYTES - PAGE] == 0xffu && bank.mem[3u * PAGE] == 0x00u);   /* page 4..6 untouched */
    n = zs_fw_download_request(&dl, buf, sizeof(buf));
    assert(n == sizeof(zs_fw_update_vector_request0) && memcmp(buf, zs_fw_update_vector_request0, n) == 0);
    assert(zs_fw_download_on_chunk(&dl, chunk(1)) == ZS_FW_CHUNK_IGNORED);          /* out of order */
    memcpy(foreign_msg, zs_fw_update_vector_chunk0, sizeof(foreign_msg));
    for (size_t i = 0u; i + 16u < sizeof(foreign_msg); i++) if (memcmp(&foreign_msg[i], cmd.command_id, 16u) == 0) { foreign_msg[i + 15u] ^= 1u; break; }
    assert(zs_fw_chunk_decode(foreign_msg, sizeof(foreign_msg), &foreign));
    assert(zs_fw_download_on_chunk(&dl, &foreign) == ZS_FW_CHUNK_IGNORED);          /* another command */
    assert(zs_fw_download_on_chunk(&dl, chunk(0)) == ZS_FW_CHUNK_ACCEPTED && dl.offset == 1024u);
    assert(zs_fw_download_on_chunk(&dl, chunk(0)) == ZS_FW_CHUNK_IGNORED);          /* a late repeat */
    assert(zs_fw_download_want(&dl) == 1024u);
    assert(zs_fw_download_on_chunk(&dl, chunk(1)) == ZS_FW_CHUNK_ACCEPTED);
    assert(zs_fw_download_want(&dl) == 552u);
    assert(zs_fw_download_on_chunk(&dl, chunk(2)) == ZS_FW_CHUNK_ACCEPTED && dl.state == ZS_FW_DOWNLOAD_VERIFYING);
    assert(zs_fw_download_want(&dl) == 0u && zs_fw_download_request(&dl, buf, sizeof(buf)) == 0u);
    assert(zs_fw_download_step(&dl, 1024u) == ZS_FW_STEP_BUSY);                     /* 2600 bytes at 1 KiB per call */
    assert(zs_fw_download_step(&dl, 1024u) == ZS_FW_STEP_BUSY);
    assert(zs_fw_download_step(&dl, 1024u) == ZS_FW_STEP_FINISHED);
    assert(dl.result == ZS_COMMAND_ACK_OK && dl.detail == 3u && !zs_fw_download_active(&dl));
    assert(memcmp(bank.mem, zs_fw_update_vector_image, sizeof(zs_fw_update_vector_image)) == 0);
    for (size_t i = sizeof(zs_fw_update_vector_image); i < 3u * PAGE; i++) assert(bank.mem[i] == 0xffu);   /* padded tail, erased rest */
    assert(zs_fw_download_step(&dl, 1024u) == ZS_FW_STEP_FINISHED);

    /* the whole run on the helper, as the comms task drives it */
    memset(bank.mem, 0x00, sizeof(bank.mem)); bank.erases = bank.programs = 0u;
    assert(zs_fw_download_start(&dl, &io, 17u, cmd.command_id, &manifest) && run_all(&dl) == ZS_FW_STEP_FINISHED && dl.result == ZS_COMMAND_ACK_OK);

    /* flash failures */
    memset(bank.mem, 0x00, sizeof(bank.mem)); bank.erases = bank.programs = 0u; bank.fail_erase_at = 2u;
    assert(zs_fw_download_start(&dl, &io, 17u, cmd.command_id, &manifest) && run_all(&dl) == ZS_FW_STEP_FINISHED);
    assert(dl.result == ZS_COMMAND_ACK_FAILED && dl.detail == ZS_FW_FAIL_FLASH);
    bank.erases = bank.programs = 0u; bank.fail_erase_at = 0u; bank.fail_program_at = 2u;
    assert(zs_fw_download_start(&dl, &io, 17u, cmd.command_id, &manifest) && run_all(&dl) == ZS_FW_STEP_FINISHED);
    assert(dl.result == ZS_COMMAND_ACK_FAILED && dl.detail == ZS_FW_FAIL_FLASH);
    bank.programs = 0u; bank.fail_program_at = 0u;

    /* a bit flipped in flash after programming: the read-back SHA-256 catches it */
    assert(zs_fw_download_start(&dl, &io, 17u, cmd.command_id, &manifest));
    while (zs_fw_download_step(&dl, 0u) != ZS_FW_STEP_NEED_CHUNK) {}
    for (unsigned i = 0u; i < 3u; i++) assert(zs_fw_download_on_chunk(&dl, chunk(i)) == ZS_FW_CHUNK_ACCEPTED);
    bank.mem[2000] ^= 0x10u;
    while (zs_fw_download_step(&dl, 4096u) != ZS_FW_STEP_FINISHED) {}
    assert(dl.result == ZS_COMMAND_ACK_FAILED && dl.detail == ZS_FW_FAIL_SHA256);

    /* a signed manifest whose version disagrees with the image's own .fw_info */
    {
      zs_fw_manifest_t other = manifest;
      other.version = 8u;
      assert(zs_fw_download_start(&dl, &io, 17u, cmd.command_id, &other) && run_all(&dl) == ZS_FW_STEP_FINISHED);
      assert(dl.result == ZS_COMMAND_ACK_FAILED && dl.detail == ZS_FW_FAIL_INFO);
    }

    /* the comms task gives up (no chunk in three sessions): FAILED 4, the flash untouched afterwards */
    assert(zs_fw_download_start(&dl, &io, 17u, cmd.command_id, &manifest));
    while (zs_fw_download_step(&dl, 0u) != ZS_FW_STEP_NEED_CHUNK) {}
    zs_fw_download_fail(&dl, ZS_FW_FAIL_STALLED);
    assert(zs_fw_download_step(&dl, 0u) == ZS_FW_STEP_FINISHED && dl.result == ZS_COMMAND_ACK_FAILED && dl.detail == ZS_FW_FAIL_STALLED);
    assert(zs_fw_download_on_chunk(&dl, chunk(0)) == ZS_FW_CHUNK_IGNORED);
    zs_fw_download_abort(&dl);
    assert(dl.state == ZS_FW_DOWNLOAD_IDLE && zs_fw_download_step(&dl, 0u) == ZS_FW_STEP_IDLE);
  }

  /* ---- the journal keeps CMD_UPDATE_FIRMWARE like any other command: the same UUID with another release conflicts ---- */
  {
    zs_command_t other = cmd;
    const zs_command_journal_io_t jio = {NULL, 4u, j_read, j_erase, j_write};
    memset(journal, 0xff, sizeof(journal));
    assert(zs_command_journal_accept(&jio, &cmd, ZS_FW_UPDATE_VECTOR_CREATED_US + 1000u) == ZS_COMMAND_JOURNAL_OK);
    assert(zs_command_journal_accept(&jio, &cmd, ZS_FW_UPDATE_VECTOR_CREATED_US + 2000u) == ZS_COMMAND_JOURNAL_ALREADY_ACCEPTED);
    other.firmware.signature[0] ^= 1u;
    assert(zs_command_journal_accept(&jio, &other, ZS_FW_UPDATE_VECTOR_CREATED_US + 2000u) == ZS_COMMAND_JOURNAL_CONFLICT);
    other = cmd; other.firmware.manifest_size = 0u;
    assert(zs_command_journal_accept(&jio, &other, ZS_FW_UPDATE_VECTOR_CREATED_US + 2000u) == ZS_COMMAND_JOURNAL_INVALID_COMMAND);
    assert(zs_command_journal_complete(&jio, cmd.command_id, ZS_COMMAND_ACK_OK, 3u, ZS_FW_UPDATE_VECTOR_CREATED_US + 3000u) == ZS_COMMAND_JOURNAL_OK);
    assert(zs_command_journal_encode_ack(&jio, cmd.command_id, buf, sizeof(buf)) > 0u);
  }

  puts("zs_fw_update_tests: OK");
  return 0;
}

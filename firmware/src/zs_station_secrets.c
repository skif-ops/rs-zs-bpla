#include "zs_station_secrets.h"

#include <string.h>

static const uint8_t MAGIC[8] = {'Z', 'S', 'S', 'E', 'C', 'R', '0', '1'};
#define OFF_VERSION 8u
#define OFF_FLAGS 12u
#define OFF_ENGINEER 16u
#define OFF_ICCID1 48u
#define OFF_ICCID2 71u
#define OFF_COMMAND 94u
#define OFF_CRC 128u
#define FLAG_ENGINEER 1u
#define FLAG_ICCID1 2u
#define FLAG_ICCID2 4u
#define FLAG_COMMAND 8u

static uint32_t crc32(const uint8_t *d, size_t n) {
  uint32_t c = 0xffffffffu;
  for (size_t i = 0u; i < n; i++) { c ^= d[i]; for (unsigned b = 0u; b < 8u; b++) c = (c >> 1) ^ (0xedb88320u & (uint32_t)-(int32_t)(c & 1u)); }
  return ~c;
}
static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static void put_le32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static bool io_valid(const zs_station_secrets_io_t *io) { return io && io->read && io->erase && io->write; }

bool zs_station_secrets_iccid_valid(const char *iccid) {
  size_t n;
  if (!iccid) return false;
  n = strlen(iccid);
  if (n < 18u || n > 22u) return false;
  for (size_t i = 0u; i < n; i++) if (iccid[i] < '0' || iccid[i] > '9') return false;
  return true;
}

static bool newer(uint32_t a, uint32_t b) { return a != b && (uint32_t)(a - b) < 0x80000000u; }

/* Field-wise equality of the provisioned content (unset secrets are not compared). */
static bool same(const zs_station_secrets_t *a, const zs_station_secrets_t *b) {
  if (a->version != b->version || a->engineer_key_set != b->engineer_key_set || a->command_key_set != b->command_key_set) return false;
  if (a->engineer_key_set && memcmp(a->engineer_key, b->engineer_key, ZS_STATION_SECRETS_KEY_BYTES) != 0) return false;
  if (a->command_key_set && memcmp(a->command_public_key, b->command_public_key, ZS_STATION_SECRETS_KEY_BYTES) != 0) return false;
  return strcmp(a->iccid[0], b->iccid[0]) == 0 && strcmp(a->iccid[1], b->iccid[1]) == 0;
}

/* Decodes one slot; false when blank, torn or corrupt. */
static bool read_slot(const zs_station_secrets_io_t *io, uint8_t slot, zs_station_secrets_t *out, bool *io_error) {
  uint8_t raw[ZS_STATION_SECRETS_RECORD_BYTES];
  uint32_t flags;
  if (!io->read(io->ctx, slot, 0u, raw, sizeof(raw))) { *io_error = true; return false; }
  if (memcmp(raw, MAGIC, sizeof(MAGIC)) != 0 || crc32(raw, OFF_CRC) != le32(raw + OFF_CRC)) return false;
  memset(out, 0, sizeof(*out));
  out->version = le32(raw + OFF_VERSION);
  flags = le32(raw + OFF_FLAGS);
  out->engineer_key_set = (flags & FLAG_ENGINEER) != 0u;
  out->command_key_set = (flags & FLAG_COMMAND) != 0u;
  memcpy(out->engineer_key, raw + OFF_ENGINEER, ZS_STATION_SECRETS_KEY_BYTES);
  memcpy(out->command_public_key, raw + OFF_COMMAND, ZS_STATION_SECRETS_KEY_BYTES);
  if (flags & FLAG_ICCID1) { memcpy(out->iccid[0], raw + OFF_ICCID1, ZS_STATION_SECRETS_ICCID_CAPACITY - 1u); out->iccid[0][ZS_STATION_SECRETS_ICCID_CAPACITY - 1u] = 0; }
  if (flags & FLAG_ICCID2) { memcpy(out->iccid[1], raw + OFF_ICCID2, ZS_STATION_SECRETS_ICCID_CAPACITY - 1u); out->iccid[1][ZS_STATION_SECRETS_ICCID_CAPACITY - 1u] = 0; }
  if ((flags & FLAG_ICCID1) && !zs_station_secrets_iccid_valid(out->iccid[0])) return false;
  if ((flags & FLAG_ICCID2) && !zs_station_secrets_iccid_valid(out->iccid[1])) return false;
  return true;
}

zs_station_secrets_result_t zs_station_secrets_load(const zs_station_secrets_io_t *io, zs_station_secrets_t *out, uint8_t *active_slot) {
  zs_station_secrets_t cand;
  bool found = false, io_error = false;
  if (!io_valid(io) || !out) return ZS_STATION_SECRETS_INVALID_ARGUMENT;
  memset(out, 0, sizeof(*out));
  if (active_slot) *active_slot = 0u;
  for (uint8_t s = 0u; s < ZS_STATION_SECRETS_SLOT_COUNT; s++) {
    if (!read_slot(io, s, &cand, &io_error)) continue;
    if (!found || newer(cand.version, out->version)) { *out = cand; found = true; if (active_slot) *active_slot = s; }
  }
  memset(&cand, 0, sizeof(cand));
  if (found) return ZS_STATION_SECRETS_OK;
  return io_error ? ZS_STATION_SECRETS_IO_ERROR : ZS_STATION_SECRETS_NOT_FOUND;
}

zs_station_secrets_result_t zs_station_secrets_commit(const zs_station_secrets_io_t *io, zs_station_secrets_t *in) {
  zs_station_secrets_t stored, back;
  uint8_t raw[ZS_STATION_SECRETS_RECORD_BYTES], active = 0u, target;
  uint32_t flags = 0u;
  zs_station_secrets_result_t r;
  if (!io_valid(io) || !in) return ZS_STATION_SECRETS_INVALID_ARGUMENT;
  if ((in->iccid[0][0] && !zs_station_secrets_iccid_valid(in->iccid[0])) || (in->iccid[1][0] && !zs_station_secrets_iccid_valid(in->iccid[1])))
    return ZS_STATION_SECRETS_INVALID_ARGUMENT;
  r = zs_station_secrets_load(io, &stored, &active);
  if (r == ZS_STATION_SECRETS_IO_ERROR) return r;
  in->version = r == ZS_STATION_SECRETS_OK ? stored.version + 1u : 1u;
  if (in->version == 0u) in->version = 1u;
  target = r == ZS_STATION_SECRETS_OK ? (uint8_t)((active + 1u) % ZS_STATION_SECRETS_SLOT_COUNT) : 0u;
  memset(&stored, 0, sizeof(stored));

  memset(raw, 0xff, sizeof(raw));
  memcpy(raw, MAGIC, sizeof(MAGIC));
  put_le32(raw + OFF_VERSION, in->version);
  if (in->engineer_key_set) { flags |= FLAG_ENGINEER; memcpy(raw + OFF_ENGINEER, in->engineer_key, ZS_STATION_SECRETS_KEY_BYTES); }
  if (in->iccid[0][0]) { flags |= FLAG_ICCID1; memset(raw + OFF_ICCID1, 0, ZS_STATION_SECRETS_ICCID_CAPACITY); memcpy(raw + OFF_ICCID1, in->iccid[0], strlen(in->iccid[0])); }
  if (in->iccid[1][0]) { flags |= FLAG_ICCID2; memset(raw + OFF_ICCID2, 0, ZS_STATION_SECRETS_ICCID_CAPACITY); memcpy(raw + OFF_ICCID2, in->iccid[1], strlen(in->iccid[1])); }
  if (in->command_key_set) { flags |= FLAG_COMMAND; memcpy(raw + OFF_COMMAND, in->command_public_key, ZS_STATION_SECRETS_KEY_BYTES); }
  put_le32(raw + OFF_FLAGS, flags);
  put_le32(raw + OFF_CRC, crc32(raw, OFF_CRC));

  if (!io->erase(io->ctx, target)) { memset(raw, 0, sizeof(raw)); return ZS_STATION_SECRETS_IO_ERROR; }
  /* body first, the CRC (the commit marker of this record) last */
  if (!io->write(io->ctx, target, 0u, raw, OFF_CRC) || !io->write(io->ctx, target, OFF_CRC, raw + OFF_CRC, 4u)) { memset(raw, 0, sizeof(raw)); return ZS_STATION_SECRETS_IO_ERROR; }
  memset(raw, 0, sizeof(raw));
  r = zs_station_secrets_load(io, &back, &active);
  if (r != ZS_STATION_SECRETS_OK) return r == ZS_STATION_SECRETS_IO_ERROR ? r : ZS_STATION_SECRETS_VERIFY_FAILED;
  r = (active == target && same(&back, in)) ? ZS_STATION_SECRETS_OK : ZS_STATION_SECRETS_VERIFY_FAILED;
  memset(&back, 0, sizeof(back));
  return r;
}

zs_station_secrets_result_t zs_station_secrets_clear(const zs_station_secrets_io_t *io) {
  if (!io_valid(io)) return ZS_STATION_SECRETS_INVALID_ARGUMENT;
  for (uint8_t s = 0u; s < ZS_STATION_SECRETS_SLOT_COUNT; s++) if (!io->erase(io->ctx, s)) return ZS_STATION_SECRETS_IO_ERROR;
  return ZS_STATION_SECRETS_OK;
}

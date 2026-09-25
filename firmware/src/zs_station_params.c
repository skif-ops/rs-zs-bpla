#include "zs_station_params.h"
#include <string.h>

#define PARAMS_MAGIC UINT32_C(0x4d50535a)   /* "ZSPM" */
#define PARAMS_FORMAT 1u

static const struct { int32_t min, max, def; } table[ZS_PARAM_COUNT] = {
  {900, 86400, 21600},   /* heartbeat_period_s */
  {0, 3, 0},             /* mic_channel */
  {4, 40, 10},           /* event_update_windows */
  {1, 10, 3},            /* comms_degraded_after */
  {300, 14400, 1800},    /* gsm_probe_s */
  {1, 10, 3},            /* listen_dwell_s */
};

void zs_station_params_defaults(zs_station_params_t *p) {
  if (!p) return;
  p->version = 0u;
  for (unsigned i = 0u; i < ZS_PARAM_COUNT; i++) p->value[i] = table[i].def;
}
int32_t zs_station_params_get(const zs_station_params_t *p, zs_param_id_t id) {
  const unsigned i = (unsigned)id - 1u;
  return (p && i < ZS_PARAM_COUNT) ? p->value[i] : 0;
}
bool zs_station_params_range(zs_param_id_t id, int32_t *min, int32_t *max, int32_t *def) {
  const unsigned i = (unsigned)id - 1u;
  if (i >= ZS_PARAM_COUNT) return false;
  if (min) *min = table[i].min;
  if (max) *max = table[i].max;
  if (def) *def = table[i].def;
  return true;
}

uint16_t zs_station_params_apply_command(const zs_station_params_t *current, const zs_set_params_command_t *cmd,
                                         zs_station_params_t *out) {
  zs_station_params_t next;
  if (!current || !cmd || !out || cmd->count > ZS_COMMAND_PARAMS_MAX) return ZS_STATION_PARAMS_REJECT_BASE;
  for (uint8_t k = 0u; k < cmd->count; k++) {
    const unsigned i = (unsigned)cmd->id[k] - 1u;
    if (i >= ZS_PARAM_COUNT || cmd->value[k] < table[i].min || cmd->value[k] > table[i].max)
      return (uint16_t)(ZS_STATION_PARAMS_REJECT_BASE | (cmd->id[k] & 0xffu));
  }
  next = *current;
  if (cmd->reset_to_defaults) { const uint32_t v = next.version; zs_station_params_defaults(&next); next.version = v; }
  for (uint8_t k = 0u; k < cmd->count; k++) next.value[cmd->id[k] - 1u] = cmd->value[k];
  *out = next;
  return 0u;
}

static uint32_t crc32(const uint8_t *d, size_t n) {
  uint32_t c = UINT32_MAX;
  for (size_t i = 0u; i < n; i++) { c ^= d[i]; for (unsigned b = 0u; b < 8u; b++) c = (c >> 1) ^ (UINT32_C(0xedb88320) & (uint32_t)-(int32_t)(c & 1u)); }
  return ~c;
}
static void put32(uint8_t *p, uint32_t v) { for (unsigned i = 0u; i < 4u; i++) p[i] = (uint8_t)(v >> (8u * i)); }
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

/* magic u32 | format u16 | count u16 | version u32 | value i32 x 6 | crc32 (all little endian) = 40 bytes */
static void encode(const zs_station_params_t *p, uint8_t b[ZS_STATION_PARAMS_RECORD_BYTES]) {
  memset(b, 0xff, ZS_STATION_PARAMS_RECORD_BYTES);
  put32(&b[0], PARAMS_MAGIC);
  b[4] = PARAMS_FORMAT; b[5] = 0u; b[6] = ZS_PARAM_COUNT; b[7] = 0u;
  put32(&b[8], p->version);
  for (unsigned i = 0u; i < ZS_PARAM_COUNT; i++) put32(&b[12u + 4u * i], (uint32_t)p->value[i]);
  put32(&b[36], crc32(b, 36u));
}
static bool decode(const uint8_t b[ZS_STATION_PARAMS_RECORD_BYTES], zs_station_params_t *p) {
  if (get32(&b[0]) != PARAMS_MAGIC || b[4] != PARAMS_FORMAT || b[6] != ZS_PARAM_COUNT || get32(&b[36]) != crc32(b, 36u)) return false;
  p->version = get32(&b[8]);
  for (unsigned i = 0u; i < ZS_PARAM_COUNT; i++) {
    p->value[i] = (int32_t)get32(&b[12u + 4u * i]);
    if (p->value[i] < table[i].min || p->value[i] > table[i].max) return false;   /* never trust a stored value blindly */
  }
  return p->version != 0u;
}

static int newest_slot(const zs_station_params_io_t *io, zs_station_params_t *out, bool *io_error) {
  uint8_t b[ZS_STATION_PARAMS_RECORD_BYTES];
  zs_station_params_t r;
  int best = -1;
  *io_error = false;
  for (uint8_t s = 0u; s < 2u; s++) {
    if (!io->read(io->ctx, s, 0u, b, sizeof(b))) { *io_error = true; continue; }
    if (decode(b, &r) && (best < 0 || (int32_t)(r.version - out->version) > 0)) { *out = r; best = s; }
  }
  return best;
}

zs_station_params_result_t zs_station_params_load(const zs_station_params_io_t *io, zs_station_params_t *out) {
  bool io_error;
  if (!out) return ZS_STATION_PARAMS_IO_ERROR;
  zs_station_params_defaults(out);
  if (!io || !io->read) return ZS_STATION_PARAMS_IO_ERROR;
  if (newest_slot(io, out, &io_error) < 0) { zs_station_params_defaults(out); return io_error ? ZS_STATION_PARAMS_IO_ERROR : ZS_STATION_PARAMS_NOT_FOUND; }
  return ZS_STATION_PARAMS_OK;
}

zs_station_params_result_t zs_station_params_commit(const zs_station_params_io_t *io, zs_station_params_t *p) {
  uint8_t b[ZS_STATION_PARAMS_RECORD_BYTES], back[ZS_STATION_PARAMS_RECORD_BYTES];
  zs_station_params_t current, stored;
  bool io_error;
  int active;
  uint8_t target;
  if (!io || !io->read || !io->erase || !io->write || !p) return ZS_STATION_PARAMS_IO_ERROR;
  zs_station_params_defaults(&current);
  active = newest_slot(io, &current, &io_error);
  target = active == 0 ? 1u : 0u;
  stored = *p;
  stored.version = (active < 0 ? 0u : current.version) + 1u;
  if (stored.version == 0u) stored.version = 1u;
  encode(&stored, b);
  if (!io->erase(io->ctx, target) || !io->write(io->ctx, target, 0u, b, sizeof(b))) return ZS_STATION_PARAMS_IO_ERROR;
  if (!io->read(io->ctx, target, 0u, back, sizeof(back)) || memcmp(b, back, sizeof(b)) != 0) return ZS_STATION_PARAMS_VERIFY_FAILED;
  p->version = stored.version;
  return ZS_STATION_PARAMS_OK;
}

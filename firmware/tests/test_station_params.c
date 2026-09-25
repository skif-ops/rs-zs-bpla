/* Runtime parameters (addendum D): whole-command validation, reset semantics, double-slot NOR record (newest valid
   slot wins, torn/corrupt slot ignored, stored out-of-range values refused). */
#include "zs_station_params.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t slot[2][64]; bool fail_write; } ram_t;
static bool r_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { ram_t *m = c; if (s > 1u || o + n > 64u) return false; memcpy(d, &m->slot[s][o], n); return true; }
static bool r_erase(void *c, uint8_t s) { ram_t *m = c; if (s > 1u) return false; memset(m->slot[s], 0xff, 64u); return true; }
static bool r_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) {
  ram_t *m = c; if (s > 1u || o + n > 64u || m->fail_write) return false;
  for (size_t i = 0u; i < n; i++) { if ((m->slot[s][o + i] & d[i]) != d[i]) return false; m->slot[s][o + i] = d[i]; }
  return true;
}

static zs_set_params_command_t cmd(bool reset, unsigned n, const uint16_t *id, const int32_t *v) {
  zs_set_params_command_t c;
  memset(&c, 0, sizeof(c));
  c.reset_to_defaults = reset; c.count = (uint8_t)n;
  for (unsigned i = 0u; i < n; i++) { c.id[i] = id[i]; c.value[i] = v[i]; }
  return c;
}

int main(void) {
  ram_t ram;
  zs_station_params_io_t io = {&ram, r_read, r_erase, r_write};
  zs_station_params_t p, q, loaded;
  memset(&ram, 0xff, sizeof(ram)); ram.fail_write = false;

  /* nothing stored: defaults (the table of the ICD) */
  assert(zs_station_params_load(&io, &p) == ZS_STATION_PARAMS_NOT_FOUND && p.version == 0u);
  assert(zs_station_params_get(&p, ZS_PARAM_HEARTBEAT_PERIOD_S) == 21600 && zs_station_params_get(&p, ZS_PARAM_MIC_CHANNEL) == 0);
  assert(zs_station_params_get(&p, ZS_PARAM_LISTEN_DWELL_S) == 3 && zs_station_params_get(&p, ZS_PARAM_GSM_PROBE_S) == 1800);

  /* the shared-vector command: heartbeat 3600, mic 2, dwell 5 */
  {
    const uint16_t id[] = {1u, 2u, 6u}; const int32_t v[] = {3600, 2, 5};
    zs_set_params_command_t c = cmd(false, 3u, id, v);
    assert(zs_station_params_apply_command(&p, &c, &q) == 0u);
    assert(zs_station_params_get(&q, ZS_PARAM_HEARTBEAT_PERIOD_S) == 3600 && zs_station_params_get(&q, ZS_PARAM_MIC_CHANNEL) == 2);
    assert(zs_station_params_get(&q, ZS_PARAM_LISTEN_DWELL_S) == 5 && zs_station_params_get(&q, ZS_PARAM_GSM_PROBE_S) == 1800);
  }
  /* one bad entry rejects everything; the detail names it */
  {
    const uint16_t id[] = {1u, 2u}; const int32_t v[] = {3600, 4};
    zs_set_params_command_t c = cmd(false, 2u, id, v);
    zs_station_params_t untouched = q;
    assert(zs_station_params_apply_command(&p, &c, &untouched) == (0x0100u | 2u) && memcmp(&untouched, &q, sizeof(q)) == 0);
    const uint16_t id2[] = {9u}; const int32_t v2[] = {1};
    c = cmd(false, 1u, id2, v2);
    assert(zs_station_params_apply_command(&p, &c, &untouched) == (0x0100u | 9u));
    const uint16_t id3[] = {1u}; const int32_t v3[] = {899};
    c = cmd(false, 1u, id3, v3);
    assert(zs_station_params_apply_command(&p, &c, &untouched) == (0x0100u | 1u));
  }

  /* commit, reload, second commit goes to the other slot, newest wins */
  assert(zs_station_params_commit(&io, &q) == ZS_STATION_PARAMS_OK && q.version == 1u);
  assert(zs_station_params_load(&io, &loaded) == ZS_STATION_PARAMS_OK && memcmp(&loaded, &q, sizeof(q)) == 0);
  {
    const uint16_t id[] = {5u}; const int32_t v[] = {600};
    zs_set_params_command_t c = cmd(true, 1u, id, v);     /* reset, then gsm probe 600 */
    assert(zs_station_params_apply_command(&loaded, &c, &p) == 0u);
    assert(zs_station_params_get(&p, ZS_PARAM_HEARTBEAT_PERIOD_S) == 21600 && zs_station_params_get(&p, ZS_PARAM_GSM_PROBE_S) == 600);
  }
  assert(zs_station_params_commit(&io, &p) == ZS_STATION_PARAMS_OK && p.version == 2u);
  assert(zs_station_params_load(&io, &loaded) == ZS_STATION_PARAMS_OK && loaded.version == 2u && zs_station_params_get(&loaded, ZS_PARAM_GSM_PROBE_S) == 600);

  /* a torn write of the next commit leaves the previous record in force */
  ram.slot[0][20] ^= 0xffu;                              /* slot 0 holds version 1 (older); corrupt it */
  assert(zs_station_params_load(&io, &loaded) == ZS_STATION_PARAMS_OK && loaded.version == 2u);
  ram.fail_write = true;
  q = loaded; q.value[ZS_PARAM_MIC_CHANNEL - 1u] = 3;
  assert(zs_station_params_commit(&io, &q) == ZS_STATION_PARAMS_IO_ERROR);
  ram.fail_write = false;
  assert(zs_station_params_load(&io, &loaded) == ZS_STATION_PARAMS_OK && loaded.version == 2u && zs_station_params_get(&loaded, ZS_PARAM_MIC_CHANNEL) == 0);

  /* a stored value outside the table (bit rot with a matching CRC is unlikely, a format bug is not) is refused */
  {
    zs_station_params_t bad = loaded;
    bad.value[ZS_PARAM_MIC_CHANNEL - 1u] = 7;            /* bypass the command validation */
    assert(zs_station_params_commit(&io, &bad) == ZS_STATION_PARAMS_OK);
    assert(zs_station_params_load(&io, &loaded) == ZS_STATION_PARAMS_OK && loaded.version == 2u);   /* falls back to the valid slot */
  }
  printf("station params tests passed\n");
  return 0;
}

#include "zs_position_trust.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static zs_position_trust_config_t default_config(void) {
  zs_position_trust_config_t cfg;
  memset(&cfg, 0, sizeof(cfg));
  cfg.configured = true;
  cfg.locked = true;
  cfg.installation.lat_e7 = 557550000;
  cfg.installation.lon_e7 = 376150000;
  cfg.installation.alt_dm = 1800;
  cfg.installation.pos_accuracy_m = 5;
  cfg.installation.position_source = ZS_POSITION_SOURCE_CONFIGURED_INSTALL;
  cfg.warning_distance_m = 25;
  cfg.suspect_distance_m = 75;
  cfg.gross_jump_distance_m = 250;
  cfg.warning_consecutive_fixes = 3;
  cfg.suspect_consecutive_fixes = 10;
  return cfg;
}

static zs_position_t gnss_offset_lat(int32_t delta_e7) {
  zs_position_t p;
  memset(&p, 0, sizeof(p));
  p.lat_e7 = 557550000 + delta_e7;
  p.lon_e7 = 376150000;
  p.alt_dm = 1800;
  p.pos_accuracy_m = 5;
  p.position_source = ZS_POSITION_SOURCE_GNSS_LIVE;
  return p;
}

int main(void) {
  zs_position_trust_state_t state;
  zs_position_trust_init(&state);
  zs_position_trust_config_t cfg = default_config();

  zs_position_t near = gnss_offset_lat(500); /* about 5.6 m */
  zs_position_trust_result_t r = zs_position_trust_update(&cfg, &state, &near, 5, false, false);
  assert(r.trust == ZS_POSITION_TRUST_CONFIGURED_OK);
  assert(r.effective_position.lat_e7 == cfg.installation.lat_e7);
  assert(r.effective_position.position_source == ZS_POSITION_SOURCE_CONFIGURED_INSTALL);

  zs_position_t warn = gnss_offset_lat(3500); /* about 39 m */
  for (int i = 0; i < 3; ++i) r = zs_position_trust_update(&cfg, &state, &warn, 5, false, false);
  assert(r.trust == ZS_POSITION_TRUST_CONFIGURED_WARN);
  assert(r.effective_position.lat_e7 == cfg.installation.lat_e7);

  zs_position_trust_init(&state);
  zs_position_t suspect = gnss_offset_lat(8000); /* about 89 m */
  for (int i = 0; i < 10; ++i) r = zs_position_trust_update(&cfg, &state, &suspect, 5, false, false);
  assert(r.trust == ZS_POSITION_TRUST_CONFIGURED_SUSPECT);
  assert(r.effective_position.lat_e7 == cfg.installation.lat_e7);

  zs_position_trust_init(&state);
  r = zs_position_trust_update(&cfg, &state, &near, 5, true, false);
  assert(r.trust == ZS_POSITION_TRUST_CONFIGURED_SUSPECT);

  zs_position_trust_init(&state);
  r = zs_position_trust_update(&cfg, &state, &near, 5, false, true);
  assert(r.trust == ZS_POSITION_TRUST_REVALIDATION_REQUIRED);
  assert(r.effective_position.lat_e7 == cfg.installation.lat_e7);

  cfg.configured = false;
  zs_position_trust_init(&state);
  r = zs_position_trust_update(&cfg, &state, &near, 5, false, false);
  assert(r.trust == ZS_POSITION_TRUST_UNCONFIGURED);
  assert(r.effective_position.lat_e7 == near.lat_e7);
  assert(r.effective_position.position_source == ZS_POSITION_SOURCE_GNSS_LIVE);

  printf("zs_position_trust_tests: PASS\n");
  return 0;
}

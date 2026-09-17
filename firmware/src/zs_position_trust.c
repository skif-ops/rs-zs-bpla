#include "zs_position_trust.h"

#include <math.h>
#include <stddef.h>

#define ZS_EARTH_RADIUS_M 6371000.0
#define ZS_DEG_TO_RAD 0.01745329251994329577

static uint16_t clamp_u16(uint32_t value) {
  return value > 65535u ? 65535u : (uint16_t)value;
}

static uint16_t max_u16(uint16_t a, uint16_t b) { return a > b ? a : b; }

void zs_position_trust_init(zs_position_trust_state_t *state) {
  if (!state) return;
  state->warning_count = 0u;
  state->suspect_count = 0u;
  state->trust = ZS_POSITION_TRUST_UNCONFIGURED;
  state->revalidation_required = false;
}

uint32_t zs_position_distance_m(const zs_position_t *a, const zs_position_t *b) {
  if (!a || !b) return 0u;

  const double lat1 = ((double)a->lat_e7 / 10000000.0) * ZS_DEG_TO_RAD;
  const double lat2 = ((double)b->lat_e7 / 10000000.0) * ZS_DEG_TO_RAD;
  const double dlat = lat2 - lat1;
  const double dlon = ((double)((int64_t)b->lon_e7 - (int64_t)a->lon_e7) / 10000000.0) * ZS_DEG_TO_RAD;
  const double x = dlon * cos((lat1 + lat2) * 0.5);
  const double y = dlat;
  const double distance = ZS_EARTH_RADIUS_M * sqrt(x * x + y * y);
  if (!isfinite(distance) || distance <= 0.0) return 0u;
  if (distance >= 4294967295.0) return UINT32_MAX;
  return (uint32_t)(distance + 0.5);
}

zs_position_trust_result_t zs_position_trust_update(
    const zs_position_trust_config_t *config,
    zs_position_trust_state_t *state,
    const zs_position_t *gnss_position,
    uint16_t gnss_horizontal_accuracy_m,
    bool receiver_spoof,
    bool movement_detected) {
  zs_position_trust_result_t result = {0};
  if (!config || !state || !gnss_position) return result;

  if (!config->configured || !config->locked) {
    result.effective_position = *gnss_position;
    result.effective_position.position_source = ZS_POSITION_SOURCE_GNSS_LIVE;
    result.trust = ZS_POSITION_TRUST_UNCONFIGURED;
    state->trust = result.trust;
    return result;
  }

  result.effective_position = config->installation;
  result.effective_position.position_source = ZS_POSITION_SOURCE_CONFIGURED_INSTALL;

  const uint32_t distance_u32 = zs_position_distance_m(&config->installation, gnss_position);
  result.distance_m = clamp_u16(distance_u32);

  const uint16_t warning_floor = config->warning_distance_m ? config->warning_distance_m : 25u;
  const uint16_t suspect_floor = config->suspect_distance_m ? config->suspect_distance_m : 75u;
  const uint16_t gross_floor = config->gross_jump_distance_m ? config->gross_jump_distance_m : 250u;
  const uint8_t warning_count_required = config->warning_consecutive_fixes ? config->warning_consecutive_fixes : 3u;
  const uint8_t suspect_count_required = config->suspect_consecutive_fixes ? config->suspect_consecutive_fixes : 10u;

  const uint16_t warning_dynamic = clamp_u16((uint32_t)gnss_horizontal_accuracy_m * 3u);
  const uint16_t suspect_dynamic = clamp_u16((uint32_t)gnss_horizontal_accuracy_m * 5u);
  const uint16_t warning_threshold = max_u16(warning_floor, warning_dynamic);
  const uint16_t suspect_threshold = max_u16(suspect_floor, suspect_dynamic);

  if (movement_detected) {
    state->revalidation_required = true;
    state->trust = ZS_POSITION_TRUST_REVALIDATION_REQUIRED;
    result.trust = state->trust;
    result.warning = true;
    result.suspect = true;
    return result;
  }

  if (receiver_spoof || distance_u32 >= gross_floor) {
    state->suspect_count = suspect_count_required;
    state->warning_count = warning_count_required;
    state->trust = ZS_POSITION_TRUST_CONFIGURED_SUSPECT;
    result.trust = state->trust;
    result.warning = true;
    result.suspect = true;
    return result;
  }

  if (distance_u32 >= suspect_threshold) {
    if (state->suspect_count < 255u) state->suspect_count++;
    if (state->warning_count < 255u) state->warning_count++;
  } else if (distance_u32 >= warning_threshold) {
    state->suspect_count = 0u;
    if (state->warning_count < 255u) state->warning_count++;
  } else {
    state->warning_count = 0u;
    state->suspect_count = 0u;
  }

  if (state->suspect_count >= suspect_count_required) {
    state->trust = ZS_POSITION_TRUST_CONFIGURED_SUSPECT;
  } else if (state->warning_count >= warning_count_required) {
    state->trust = ZS_POSITION_TRUST_CONFIGURED_WARN;
  } else {
    state->trust = ZS_POSITION_TRUST_CONFIGURED_OK;
  }

  result.trust = state->trust;
  result.warning = state->trust == ZS_POSITION_TRUST_CONFIGURED_WARN ||
                   state->trust == ZS_POSITION_TRUST_CONFIGURED_SUSPECT;
  result.suspect = state->trust == ZS_POSITION_TRUST_CONFIGURED_SUSPECT;
  return result;
}

#ifndef ZS_POSITION_TRUST_H
#define ZS_POSITION_TRUST_H

#include "zs_types.h"

#include <stdbool.h>
#include <stdint.h>

typedef struct {
  bool configured;
  bool locked;
  zs_position_t installation;
  uint16_t warning_distance_m;
  uint16_t suspect_distance_m;
  uint16_t gross_jump_distance_m;
  uint8_t warning_consecutive_fixes;
  uint8_t suspect_consecutive_fixes;
} zs_position_trust_config_t;

typedef struct {
  uint8_t warning_count;
  uint8_t suspect_count;
  zs_position_trust_t trust;
  bool revalidation_required;
} zs_position_trust_state_t;

typedef struct {
  zs_position_t effective_position;
  uint16_t distance_m;
  zs_position_trust_t trust;
  bool warning;
  bool suspect;
} zs_position_trust_result_t;

void zs_position_trust_init(zs_position_trust_state_t *state);

uint32_t zs_position_distance_m(const zs_position_t *a, const zs_position_t *b);

zs_position_trust_result_t zs_position_trust_update(
    const zs_position_trust_config_t *config,
    zs_position_trust_state_t *state,
    const zs_position_t *gnss_position,
    uint16_t gnss_horizontal_accuracy_m,
    bool receiver_spoof,
    bool movement_detected);

#endif

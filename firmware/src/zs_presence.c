#include "zs_presence.h"
#include <string.h>

static bool uav_class(uint8_t c) { return c == ZS_CLASS_PISTON_UAV || c == ZS_CLASS_REACTIVE_UAV || c == ZS_CLASS_ELECTRIC_UAV; }
static bool ground_engine_class(uint8_t c) { return c == ZS_CLASS_ROAD_TRAFFIC || c == ZS_CLASS_AGRICULTURAL || c == ZS_CLASS_GENERATOR; }
static uint8_t majority_of(uint8_t windows) { return (uint8_t)(((uint16_t)windows * 5u + 7u) / 8u); } /* 5/8 as in the consensus */

zs_presence_t zs_presence_evaluate(const zs_classifier_consensus_t *votes, const zs_air_gate_result_t *gate) {
  zs_presence_t p;
  memset(&p, 0, sizeof(p));
  uint16_t uav_conf = 0u;
  if (votes) {
    p.windows = votes->count;
    for (uint8_t i = 0u; i < votes->count; i++) {
      if (votes->confidence_u8[i] < ZS_CLASSIFICATION_MIN_CONFIDENCE_U8) continue;
      if (uav_class(votes->class_id[i])) { p.uav_votes++; uav_conf = (uint16_t)(uav_conf + votes->confidence_u8[i]); }
      else if (ground_engine_class(votes->class_id[i])) p.ground_votes++;
    }
  }
  const bool comb = gate && gate->present;
  const uint8_t gate_conf = comb ? gate->confidence_u8 : 0u;
  const uint8_t mean_uav = p.uav_votes ? (uint8_t)(uav_conf / p.uav_votes) : 0u;
  const bool enough = p.windows >= ZS_CLASSIFICATION_MIN_WINDOWS;
  const bool uav_majority = enough && p.uav_votes >= majority_of(p.windows);
  const bool ground_majority = enough && p.ground_votes >= majority_of(p.windows);
  p.comb = comb;
  if (uav_majority) {
    p.level = ZS_PRESENCE_CONFIRMED;
    p.confidence_u8 = comb && gate_conf > mean_uav ? gate_conf : mean_uav;
  } else if (comb && ground_majority) {
    p.level = ZS_PRESENCE_ENGINE_UNCONFIRMED;
    p.confidence_u8 = gate_conf;
  } else if (comb && p.uav_votes >= 2u) {
    p.level = ZS_PRESENCE_CONFIRMED;
    p.confidence_u8 = (uint8_t)(((uint16_t)gate_conf + mean_uav) / 2u);
  } else if (comb) {
    p.level = ZS_PRESENCE_SUSPECT;
    p.confidence_u8 = (uint8_t)(gate_conf / 2u);
  } else if (p.uav_votes >= 2u) {
    p.level = ZS_PRESENCE_SUSPECT;
    p.confidence_u8 = (uint8_t)(mean_uav / 2u);
  } else {
    p.level = ZS_PRESENCE_NONE;
    p.confidence_u8 = 0u;
  }
  return p;
}

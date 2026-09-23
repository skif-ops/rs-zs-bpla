#ifndef ZS_PRESENCE_H
#define ZS_PRESENCE_H
/*
 * Station level-1 decision ("is there a UAV") from the two independent pieces of evidence the
 * station has per window: the centroid classifier votes kept by zs_classifier_consensus and the
 * AIR gate (zs_air_gate: a steady, airborne-plausible propulsion comb over the last seconds).
 *
 *   gate present + UAV majority            -> CONFIRMED  (both agree)
 *   UAV majority alone                     -> CONFIRMED  (distant target, no comb: Lyuty file 3, Mavic far away)
 *   gate present + >= 2 UAV votes          -> CONFIRMED  (comb plus partial classifier support)
 *   gate present + weak UAV majority       -> CONFIRMED  (right class but far from its centroid: a maneuvering or
 *                                                        distant target; the comb supplies the missing confidence)
 *   gate present + ground-engine majority  -> ENGINE     (APC/tractor/generator line in 30..300 Hz: not airborne)
 *   gate present, no classifier support    -> SUSPECT
 *   >= 2 UAV votes, no gate                -> SUSPECT
 *   weak UAV majority, no gate             -> SUSPECT
 *   otherwise                              -> NONE
 * Family/type stay with zs_classifier_consensus and the server hierarchy; this module only decides level 1.
 */
#include "zs_air_gate.h"
#include "zs_classifier_consensus.h"

#define ZS_PRESENCE_WEAK_CONFIDENCE_U8 48u   /* confidence = 1 - d / (1.5 r): 48/255 is d <= 1.2 r, just outside the 95 % member radius */

typedef enum {
  ZS_PRESENCE_NONE = 0,
  ZS_PRESENCE_SUSPECT = 1,
  ZS_PRESENCE_ENGINE_UNCONFIRMED = 2,   /* a steady engine comb that the classifier attributes to ground machinery */
  ZS_PRESENCE_CONFIRMED = 3
} zs_presence_level_t;

typedef struct {
  uint8_t level;          /* zs_presence_level_t */
  uint8_t confidence_u8;
  uint8_t windows;        /* classifier windows in the vote */
  uint8_t uav_votes;      /* windows with a UAV class at >= ZS_CLASSIFICATION_MIN_CONFIDENCE_U8 (distance <= 0.75 radius) */
  uint8_t uav_weak_votes; /* windows with a UAV class at >= ZS_PRESENCE_WEAK_CONFIDENCE_U8 (distance <= 1.2 radius) */
  uint8_t ground_votes;   /* windows with a ground-engine class (road traffic, agricultural, generator) */
  bool comb;              /* gate present */
} zs_presence_t;

zs_presence_t zs_presence_evaluate(const zs_classifier_consensus_t *votes, const zs_air_gate_result_t *gate);

#endif

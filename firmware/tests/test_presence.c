/* Level-1 fusion of the centroid votes and the AIR gate. */
#include "zs_presence.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static zs_classifier_consensus_t votes_of(const uint8_t *classes, unsigned n, uint8_t conf) {
  zs_classifier_consensus_t v; zs_classification_t c; zs_hier_classification_t h;
  zs_classifier_consensus_init(&v);
  for (unsigned i = 0u; i < n; i++) { zs_classifier_result_t r = {classes[i], conf, 0.0f}; (void)zs_classifier_consensus_push(&v, r, &c, &h); }
  return v;
}
static zs_air_gate_result_t gate_of(bool present, uint8_t conf) { zs_air_gate_result_t g; memset(&g, 0, sizeof(g)); g.present = present; g.confidence_u8 = conf; return g; }

int main(void) {
  const uint8_t uav8[8] = {1, 1, 1, 3, 1, 1, 1, 1}, ground8[8] = {14, 14, 10, 14, 14, 13, 14, 14}, birds8[8] = {15, 15, 15, 15, 15, 15, 15, 15};
  const uint8_t mixed8[8] = {15, 1, 15, 15, 1, 15, 15, 15}, three[3] = {1, 1, 1};
  zs_classifier_consensus_t v; zs_air_gate_result_t g; zs_presence_t p;

  v = votes_of(uav8, 8u, 220u); g = gate_of(true, 240u); p = zs_presence_evaluate(&v, &g);          /* both agree */
  assert(p.level == ZS_PRESENCE_CONFIRMED && p.confidence_u8 == 240u && p.uav_votes == 8u && p.comb);
  v = votes_of(uav8, 8u, 200u); g = gate_of(false, 0u); p = zs_presence_evaluate(&v, &g);            /* distant: classifier alone */
  assert(p.level == ZS_PRESENCE_CONFIRMED && p.confidence_u8 == 200u && !p.comb);
  v = votes_of(ground8, 8u, 220u); g = gate_of(true, 230u); p = zs_presence_evaluate(&v, &g);       /* APC / tractor engine line */
  assert(p.level == ZS_PRESENCE_ENGINE_UNCONFIRMED && p.ground_votes == 8u && p.confidence_u8 == 230u);
  v = votes_of(ground8, 8u, 220u); g = gate_of(false, 0u); p = zs_presence_evaluate(&v, &g);
  assert(p.level == ZS_PRESENCE_NONE);
  v = votes_of(birds8, 8u, 220u); g = gate_of(true, 180u); p = zs_presence_evaluate(&v, &g);        /* comb under a bird recording */
  assert(p.level == ZS_PRESENCE_SUSPECT && p.confidence_u8 == 90u);
  v = votes_of(mixed8, 8u, 200u); g = gate_of(true, 200u); p = zs_presence_evaluate(&v, &g);        /* 2 UAV votes + comb */
  assert(p.level == ZS_PRESENCE_CONFIRMED && p.uav_votes == 2u && p.confidence_u8 == 200u);
  v = votes_of(mixed8, 8u, 200u); g = gate_of(false, 0u); p = zs_presence_evaluate(&v, &g);        /* 2 UAV votes alone */
  assert(p.level == ZS_PRESENCE_SUSPECT && p.confidence_u8 == 100u);
  v = votes_of(birds8, 8u, 220u); g = gate_of(false, 0u); p = zs_presence_evaluate(&v, &g);
  assert(p.level == ZS_PRESENCE_NONE && p.uav_votes == 0u);
  v = votes_of(three, 3u, 220u); g = gate_of(false, 0u); p = zs_presence_evaluate(&v, &g);         /* fewer than 4 windows: no majority yet */
  assert(p.level == ZS_PRESENCE_SUSPECT && p.windows == 3u);
  v = votes_of(uav8, 8u, 100u); g = gate_of(true, 240u); p = zs_presence_evaluate(&v, &g);          /* right class, far from the centroid: the comb confirms */
  assert(p.level == ZS_PRESENCE_CONFIRMED && p.uav_votes == 0u && p.uav_weak_votes == 8u && p.confidence_u8 == 184u);
  v = votes_of(uav8, 8u, 100u); g = gate_of(false, 0u); p = zs_presence_evaluate(&v, &g);           /* ... and alone it is only a suspect */
  assert(p.level == ZS_PRESENCE_SUSPECT && p.confidence_u8 == 24u);
  v = votes_of(uav8, 8u, 40u); g = gate_of(true, 240u); p = zs_presence_evaluate(&v, &g);           /* below the weak threshold: no classifier support */
  assert(p.level == ZS_PRESENCE_SUSPECT && p.uav_weak_votes == 0u);
  p = zs_presence_evaluate(NULL, NULL);
  assert(p.level == ZS_PRESENCE_NONE);
  printf("presence tests passed\n");
  return 0;
}

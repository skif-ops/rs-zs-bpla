#include "zs_classifier_consensus.h"

#include <assert.h>
#include <stdio.h>

static zs_classifier_result_t result(uint8_t class_id, uint8_t confidence_u8) {
  zs_classifier_result_t value = {class_id, confidence_u8, 0.0f};
  return value;
}

static void push_n(
    zs_classifier_consensus_t *ctx,
    uint8_t class_id,
    unsigned count,
    zs_classification_t *classification,
    zs_hier_classification_t *hierarchy) {
  for (unsigned i = 0u; i < count; i++) {
    (void)zs_classifier_consensus_push(ctx, result(class_id, 220u), classification, hierarchy);
  }
}

int main(void) {
  zs_classifier_consensus_t ctx;
  zs_classification_t classification;
  zs_hier_classification_t hierarchy;

  zs_classifier_consensus_init(&ctx);
  assert(!zs_classifier_consensus_push(&ctx, result(ZS_CLASS_PISTON_UAV, 220u), &classification, &hierarchy));
  assert(!zs_classifier_consensus_push(&ctx, result(ZS_CLASS_PISTON_UAV, 220u), &classification, &hierarchy));
  assert(!zs_classifier_consensus_push(&ctx, result(ZS_CLASS_PISTON_UAV, 220u), &classification, &hierarchy));
  assert(zs_classifier_consensus_push(&ctx, result(ZS_CLASS_PISTON_UAV, 220u), &classification, &hierarchy));
  assert(!classification.unknown);
  assert(classification.class_id == ZS_CLASS_PISTON_UAV);
  assert(hierarchy.family_id == ZS_FAMILY_PROP_PISTON);
  assert(hierarchy.type_id == ZS_TYPE_UNKNOWN);
  assert(hierarchy.family_status == ZS_DECISION_PROVISIONAL);
  assert(hierarchy.type_status == ZS_DECISION_UNKNOWN);

  zs_classifier_consensus_init(&ctx);
  push_n(&ctx, ZS_CLASS_PISTON_UAV, 2u, &classification, &hierarchy);
  push_n(&ctx, ZS_CLASS_REACTIVE_UAV, 2u, &classification, &hierarchy);
  assert(classification.unknown);

  zs_classifier_consensus_init(&ctx);
  push_n(&ctx, ZS_CLASS_REACTIVE_UAV, 4u, &classification, &hierarchy);
  assert(hierarchy.family_id == ZS_FAMILY_TURBINE_JET);
  assert(hierarchy.type_id == ZS_TYPE_UNKNOWN);

  zs_classifier_consensus_init(&ctx);
  push_n(&ctx, ZS_CLASS_ELECTRIC_UAV, 4u, &classification, &hierarchy);
  assert(hierarchy.family_id == ZS_FAMILY_ROTOR_ELECTRIC);
  assert(hierarchy.type_id == ZS_TYPE_UNKNOWN);

  zs_classifier_consensus_init(&ctx);
  push_n(&ctx, ZS_CLASS_REACTIVE_UAV, 2u, &classification, &hierarchy);
  push_n(&ctx, ZS_CLASS_PISTON_UAV, 8u, &classification, &hierarchy);
  assert(ctx.count == ZS_CLASSIFICATION_MAX_WINDOWS);
  assert(classification.class_id == ZS_CLASS_PISTON_UAV);
  assert(hierarchy.family_id == ZS_FAMILY_PROP_PISTON);

  puts("zs_classifier_consensus_tests: OK");
  return 0;
}

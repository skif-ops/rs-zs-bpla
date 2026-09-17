#include "zs_classifier_consensus.h"

#include <string.h>

static uint8_t required_votes(uint8_t windows) {
  /* ceil(windows * 5 / 8): 3/4, 4/5, 4/6, 5/7, 5/8. */
  return (uint8_t)(((uint16_t)windows * 5u + 7u) / 8u);
}

static uint8_t family_for_class(uint8_t class_id) {
  switch (class_id) {
    case ZS_CLASS_PISTON_UAV:
      return ZS_FAMILY_PROP_PISTON;
    case ZS_CLASS_REACTIVE_UAV:
      return ZS_FAMILY_TURBINE_JET;
    case ZS_CLASS_ELECTRIC_UAV:
      return ZS_FAMILY_ROTOR_ELECTRIC;
    default:
      return ZS_FAMILY_UNKNOWN;
  }
}

void zs_classifier_consensus_init(zs_classifier_consensus_t *ctx) {
  if (ctx != NULL) {
    memset(ctx, 0, sizeof(*ctx));
  }
}

bool zs_classifier_consensus_push(
    zs_classifier_consensus_t *ctx,
    zs_classifier_result_t window,
    zs_classification_t *classification,
    zs_hier_classification_t *hierarchy) {
  uint8_t best_class = ZS_CLASS_UNKNOWN;
  uint8_t best_votes = 0u;
  uint16_t best_confidence_sum = 0u;

  if (ctx == NULL || classification == NULL || hierarchy == NULL) {
    return false;
  }
  memset(classification, 0, sizeof(*classification));
  memset(hierarchy, 0, sizeof(*hierarchy));
  classification->unknown = true;

  ctx->class_id[ctx->next] = window.class_id;
  ctx->confidence_u8[ctx->next] = window.confidence_u8;
  ctx->next = (uint8_t)((ctx->next + 1u) % ZS_CLASSIFICATION_MAX_WINDOWS);
  if (ctx->count < ZS_CLASSIFICATION_MAX_WINDOWS) {
    ctx->count++;
  }
  if (ctx->count < ZS_CLASSIFICATION_MIN_WINDOWS) {
    return false;
  }

  for (uint8_t i = 0u; i < ctx->count; i++) {
    uint8_t votes = 0u;
    uint16_t confidence_sum = 0u;
    const uint8_t candidate = ctx->class_id[i];
    if (candidate == ZS_CLASS_UNKNOWN ||
        ctx->confidence_u8[i] < ZS_CLASSIFICATION_MIN_CONFIDENCE_U8) {
      continue;
    }
    for (uint8_t j = 0u; j < ctx->count; j++) {
      if (ctx->class_id[j] == candidate &&
          ctx->confidence_u8[j] >= ZS_CLASSIFICATION_MIN_CONFIDENCE_U8) {
        votes++;
        confidence_sum = (uint16_t)(confidence_sum + ctx->confidence_u8[j]);
      }
    }
    if (votes > best_votes || (votes == best_votes && confidence_sum > best_confidence_sum)) {
      best_class = candidate;
      best_votes = votes;
      best_confidence_sum = confidence_sum;
    }
  }

  if (best_votes < required_votes(ctx->count)) {
    return true;
  }

  classification->class_id = best_class;
  classification->confidence_u8 = (uint8_t)(best_confidence_sum / ctx->count);
  classification->unknown = false;
  hierarchy->family_id = family_for_class(best_class);
  if (hierarchy->family_id != ZS_FAMILY_UNKNOWN) {
    hierarchy->family_confidence_u8 = classification->confidence_u8;
    hierarchy->family_status = ZS_DECISION_PROVISIONAL;
  }
  hierarchy->type_id = ZS_TYPE_UNKNOWN;
  hierarchy->type_confidence_u8 = 0u;
  hierarchy->type_status = ZS_DECISION_UNKNOWN;
  return true;
}

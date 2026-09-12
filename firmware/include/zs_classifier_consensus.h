#ifndef ZS_CLASSIFIER_CONSENSUS_H
#define ZS_CLASSIFIER_CONSENSUS_H

#include <stdbool.h>
#include <stdint.h>

#include "zs_classifier.h"

#define ZS_CLASSIFICATION_MIN_WINDOWS 4u
#define ZS_CLASSIFICATION_MAX_WINDOWS 8u
#define ZS_CLASSIFICATION_MIN_CONFIDENCE_U8 128u

typedef struct {
  uint8_t class_id[ZS_CLASSIFICATION_MAX_WINDOWS];
  uint8_t confidence_u8[ZS_CLASSIFICATION_MAX_WINDOWS];
  uint8_t count;
  uint8_t next;
} zs_classifier_consensus_t;

void zs_classifier_consensus_init(zs_classifier_consensus_t *ctx);

/* Returns true once at least four unique analysis windows are available.
 * A true return with classification.unknown set still means that the bounded
 * series was evaluated but did not reach the 5/8 agreement threshold. */
bool zs_classifier_consensus_push(
    zs_classifier_consensus_t *ctx,
    zs_classifier_result_t window,
    zs_classification_t *classification,
    zs_hier_classification_t *hierarchy);

#endif

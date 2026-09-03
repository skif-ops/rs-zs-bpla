#ifndef ZS_CLASSIFIER_H
#define ZS_CLASSIFIER_H
#include "zs_types.h"
typedef struct { uint8_t class_id; uint8_t confidence_u8; float distance; } zs_classifier_result_t;
zs_classifier_result_t zs_classifier_predict_centroid(const float features[ZS_FEATURE_COUNT]);
#endif

#include "zs_classifier.h"
#include "zs_model.h"

/* The pipeline's classifier: the active model (built-in table or a model package, zs_model.h). */
zs_classifier_result_t zs_classifier_predict_centroid(const float f[ZS_FEATURE_COUNT]) { return zs_model_predict_active(f); }

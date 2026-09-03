#include "zs_classifier.h"
#include "zs_model_centroids.h"
#include <math.h>
zs_classifier_result_t zs_classifier_predict_centroid(const float f[ZS_FEATURE_COUNT]){float best=1e30f;unsigned bi=0;for(unsigned c=0;c<ZS_MODEL_CLASS_COUNT;c++){float d=0;for(unsigned i=0;i<ZS_FEATURE_COUNT;i++){float z=(f[i]-zs_model_mean[i])/(zs_model_std[i]+1e-6f);float q=z-zs_model_centroid[c][i];d+=q*q;}d=sqrtf(d);if(d<best){best=d;bi=c;}}float conf=1.0f-best/(zs_model_radius[bi]*1.5f+1e-6f);if(conf<0)conf=0;if(conf>1)conf=1;zs_classifier_result_t r={(uint8_t)zs_model_class_id[bi],(uint8_t)(conf*255.0f+0.5f),best};return r;}

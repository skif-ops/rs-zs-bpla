#ifndef ZS_DSP_H
#define ZS_DSP_H
#include "zs_types.h"
#include <stddef.h>
#include <stdbool.h>
typedef struct { uint32_t windows_processed; float last_peak; float last_dc; } zs_dsp_ctx_t;
void zs_dsp_init(zs_dsp_ctx_t *ctx);
bool zs_dsp_extract_1s(zs_dsp_ctx_t *ctx, const int16_t *pcm, size_t n, float out43[ZS_FEATURE_COUNT]);
bool zs_dsp_debug_global_magnitude(const int16_t *pcm, size_t n, float *out, size_t out_n);
#endif

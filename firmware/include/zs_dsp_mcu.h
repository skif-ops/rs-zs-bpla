#ifndef ZS_DSP_MCU_H
#define ZS_DSP_MCU_H

/*
 * MCU implementation of the zs_dsp 43-feature extractor (same definitions and
 * ordering, see zs_dsp.h / server golden feature_order.txt): float32 only,
 * zs_fft_mixed, ~260 KB static scratch with overlays.  Not re-entrant: one
 * window at a time (the S2 DSP task).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_dsp.h"

void zs_dsp_mcu_init(zs_dsp_ctx_t *ctx);
bool zs_dsp_mcu_extract_1s(zs_dsp_ctx_t *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]);
size_t zs_dsp_mcu_scratch_bytes(void);

#endif

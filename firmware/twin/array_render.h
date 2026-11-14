#ifndef TWIN_ARRAY_RENDER_H
#define TWIN_ARRAY_RENDER_H
/* Plane-wave rendering of a mono source onto the 3+1 microphone array for the twin and the host tests: every
   channel is the source delayed by a fixed latency plus its own arrival offset (windowed-sinc fractional delay,
   17 taps; the source is band-limited far below Nyquist, so the interpolation error is negligible for GCC-PHAT). */
#include "zs_spatial.h"

#include <stdbool.h>
#include <stdint.h>

#define ARRAY_RENDER_HISTORY 48u
#define ARRAY_RENDER_LATENCY 24.0f     /* samples; keeps every channel's delay positive */
#define ARRAY_RENDER_HALF 8

typedef struct {
  zs_spatial_geometry_t geometry;
  float sample_rate_hz;
  float hist[ARRAY_RENDER_HISTORY];
  unsigned pos;
  uint32_t quiet;                       /* consecutive zero input samples (skip the FIR when the source is silent) */
  float taps[ZS_SPATIAL_MIC_COUNT][ARRAY_RENDER_HISTORY];
  float azimuth_deg, elevation_deg;
} array_render_t;

void array_render_init(array_render_t *r, const zs_spatial_geometry_t *geometry, float sample_rate_hz);
/* Direction of arrival (from where the sound comes): azimuth clockwise from north, elevation above horizon. */
void array_render_set_direction(array_render_t *r, float azimuth_deg, float elevation_deg, float temperature_c);
void array_render_push(array_render_t *r, float x, float out[ZS_SPATIAL_MIC_COUNT]);
#endif

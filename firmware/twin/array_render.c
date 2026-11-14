#include "array_render.h"

#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

void array_render_init(array_render_t *r, const zs_spatial_geometry_t *geometry, float sample_rate_hz) {
  memset(r, 0, sizeof(*r));
  if (geometry) r->geometry = *geometry; else zs_spatial_geometry_3p1_default(&r->geometry);
  r->sample_rate_hz = sample_rate_hz;
  r->quiet = ARRAY_RENDER_HISTORY;
  array_render_set_direction(r, 0.0f, 0.0f, 15.0f);
}

void array_render_set_direction(array_render_t *r, float azimuth_deg, float elevation_deg, float temperature_c) {
  float tdoa_us[ZS_SPATIAL_REF_TDOA_COUNT];
  float delay[ZS_SPATIAL_MIC_COUNT];
  r->azimuth_deg = azimuth_deg;
  r->elevation_deg = elevation_deg;
  /* arrival of mic j relative to mic 1 (t_j - t_1); mic 1 itself at the fixed latency */
  (void)zs_spatial_reference_tdoas_from_angles(&r->geometry, azimuth_deg, elevation_deg, temperature_c, tdoa_us);
  delay[0] = ARRAY_RENDER_LATENCY;
  for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) delay[j + 1u] = ARRAY_RENDER_LATENCY + tdoa_us[j] * 1.0e-6f * r->sample_rate_hz;
  for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) {
    for (unsigned k = 0u; k < ARRAY_RENDER_HISTORY; k++) {
      const float x = (float)k - delay[c];
      float h = 0.0f;
      if (fabsf(x) <= (float)ARRAY_RENDER_HALF) {
        const float sinc = fabsf(x) < 1.0e-6f ? 1.0f : sinf((float)M_PI * x) / ((float)M_PI * x);
        const float w = 0.5f + 0.5f * cosf((float)M_PI * x / ((float)ARRAY_RENDER_HALF + 1.0f));
        h = sinc * w;
      }
      r->taps[c][k] = h;
    }
  }
}

void array_render_push(array_render_t *r, float x, float out[ZS_SPATIAL_MIC_COUNT]) {
  r->pos = (r->pos + 1u) % ARRAY_RENDER_HISTORY;
  r->hist[r->pos] = x;
  r->quiet = x == 0.0f ? (r->quiet < ARRAY_RENDER_HISTORY ? r->quiet + 1u : r->quiet) : 0u;
  if (r->quiet >= ARRAY_RENDER_HISTORY) { for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) out[c] = 0.0f; return; }
  for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) {
    float acc = 0.0f;
    for (unsigned k = 0u; k < ARRAY_RENDER_HISTORY; k++) {
      const float h = r->taps[c][k];
      if (h != 0.0f) acc += h * r->hist[(r->pos + ARRAY_RENDER_HISTORY - k) % ARRAY_RENDER_HISTORY];
    }
    out[c] = acc;
  }
}

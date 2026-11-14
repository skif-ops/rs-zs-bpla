#include "zs_bearing.h"

#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

void zs_bearing_init(zs_bearing_ctx_t *ctx, const zs_spatial_geometry_t *geometry) {
  if (!ctx) return;
  memset(ctx, 0, sizeof(*ctx));
  if (geometry) ctx->geometry = *geometry;
  else zs_spatial_geometry_3p1_default(&ctx->geometry);
  ctx->fmin_hz = ZS_BEARING_DEFAULT_FMIN_HZ;
  ctx->fmax_hz = ZS_BEARING_DEFAULT_FMAX_HZ;
  ctx->min_quality = ZS_BEARING_DEFAULT_MIN_QUALITY;
}

static float median_of(float *v, unsigned n) {
  for (unsigned i = 1u; i < n; i++) {           /* insertion sort, n <= ZS_BEARING_FRAMES */
    const float x = v[i];
    unsigned j = i;
    while (j > 0u && v[j - 1u] > x) { v[j] = v[j - 1u]; j--; }
    v[j] = x;
  }
  return (n & 1u) ? v[n / 2u] : 0.5f * (v[n / 2u - 1u] + v[n / 2u]);
}

/* Frame provider: fills channel pointers for frame k of ZS_BEARING_FRAMES. */
typedef bool (*frame_fn)(void *ctx, unsigned k, const int16_t *ch[ZS_SPATIAL_MIC_COUNT]);

static bool bearing_core(zs_bearing_ctx_t *ctx, frame_fn get, void *fctx, uint32_t sample_rate_hz, float temperature_c,
                         zs_spatial_gcc_workspace_t *ws, zs_bearing_t *out) {
  float d[ZS_SPATIAL_REF_TDOA_COUNT][ZS_BEARING_FRAMES];
  float med[ZS_SPATIAL_REF_TDOA_COUNT], spread_us = 0.0f;
  unsigned used = 0u;
  const float c = zs_spatial_speed_of_sound(temperature_c);
  const float max_delay_us = zs_spatial_max_baseline_m(&ctx->geometry) / c * 1.0e6f + 5.0f;
  zs_spatial_solution_t s;

  for (unsigned k = 0u; k < ZS_BEARING_FRAMES; k++) {
    const int16_t *ch[ZS_SPATIAL_MIC_COUNT];
    float delay[ZS_SPATIAL_REF_TDOA_COUNT], q[ZS_SPATIAL_REF_TDOA_COUNT];
    if (!get(fctx, k, ch)) { ctx->no_audio++; return false; }
    if (!zs_spatial_gcc_phat_reference_delays(ch, ZS_SPATIAL_GCC_N, sample_rate_hz, max_delay_us, ctx->fmin_hz, ctx->fmax_hz,
                                              ws, delay, q)) continue;
    if (q[0] < ctx->min_quality || q[1] < ctx->min_quality || q[2] < ctx->min_quality) continue;
    for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) d[j][used] = delay[j];
    used++;
  }
  out->frames_used = (uint8_t)used;
  if (used < ZS_BEARING_MIN_FRAMES) { ctx->weak++; return false; }

  for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) {
    float dev[ZS_BEARING_FRAMES];
    med[j] = median_of(d[j], used);
    for (unsigned k = 0u; k < used; k++) dev[k] = fabsf(d[j][k] - med[j]);
    const float mad_us = 1.4826f * median_of(dev, used) / sqrtf((float)used);   /* sigma of the median, robust */
    if (mad_us > spread_us) spread_us = mad_us;
    out->tdoa_us[j] = med[j];
  }
  if (!zs_spatial_direction_from_reference_tdoas(&ctx->geometry, med, temperature_c, &s)) { ctx->unsolved++; return false; }

  out->azimuth_deg = s.azimuth_deg;
  out->elevation_deg = s.elevation_deg;
  out->residual_us = s.residual_us;
  out->confidence = s.confidence;
  {
    /* delay scatter and solver residual over the effective horizontal aperture (triangle side for the locked
       geometry), as an angle; floor 0.5 deg for geometry tolerance */
    const float aperture_m = zs_spatial_max_baseline_m(&ctx->geometry) * 0.73f;
    const float t_us = sqrtf(spread_us * spread_us + s.residual_us * s.residual_us);
    float sigma = (float)(180.0 / M_PI) * c * t_us * 1.0e-6f / aperture_m + 0.5f;
    out->sigma_deg = sigma > 45.0f ? 45.0f : sigma;
  }
  out->valid = true;
  ctx->computed++;
  return true;
}

typedef struct {
  const zs_audio_ring_t *ring;
  uint64_t start;
  uint32_t step;
  int16_t *frames;
} ring_src_t;

static bool ring_frame(void *p, unsigned k, const int16_t *ch[ZS_SPATIAL_MIC_COUNT]) {
  ring_src_t *r = p;
  const uint64_t end = r->start + (uint64_t)k * r->step + ZS_SPATIAL_GCC_N;
  if (!zs_audio_ring_range_ok(r->ring, end, ZS_SPATIAL_GCC_N)) return false;
  for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) {
    int16_t *dst = r->frames + (size_t)c * ZS_SPATIAL_GCC_N;
    for (uint32_t i = 0u; i < ZS_SPATIAL_GCC_N; i++) dst[i] = zs_audio_ring_at(r->ring, end, ZS_SPATIAL_GCC_N, i, c);
    ch[c] = dst;
  }
  return true;
}

bool zs_bearing_from_ring(zs_bearing_ctx_t *ctx, const zs_audio_ring_t *ring, uint64_t end_sample, uint32_t span_samples,
                          float temperature_c, int16_t *frames, zs_spatial_gcc_workspace_t *workspace, zs_bearing_t *out) {
  ring_src_t src;
  if (!out) return false;
  memset(out, 0, sizeof(*out));
  if (!ctx || !ring || !frames || !workspace || span_samples < ZS_SPATIAL_GCC_N || end_sample < span_samples) return false;
  ctx->attempts++;
  if (!zs_audio_ring_range_ok(ring, end_sample, span_samples)) { ctx->no_audio++; return false; }
  src.ring = ring;
  src.start = end_sample - span_samples;
  src.step = (span_samples - ZS_SPATIAL_GCC_N) / (ZS_BEARING_FRAMES - 1u);
  src.frames = frames;
  return bearing_core(ctx, ring_frame, &src, ring->sample_rate, temperature_c, workspace, out);
}

typedef struct {
  const int16_t *const *channels;
  uint32_t step;
} chan_src_t;

static bool chan_frame(void *p, unsigned k, const int16_t *ch[ZS_SPATIAL_MIC_COUNT]) {
  chan_src_t *s = p;
  for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) ch[c] = s->channels[c] + (size_t)k * s->step;
  return true;
}

bool zs_bearing_from_channels(zs_bearing_ctx_t *ctx, const int16_t *const channels[ZS_SPATIAL_MIC_COUNT], uint32_t count,
                              uint32_t sample_rate_hz, float temperature_c, zs_spatial_gcc_workspace_t *workspace,
                              zs_bearing_t *out) {
  chan_src_t src;
  if (!out) return false;
  memset(out, 0, sizeof(*out));
  if (!ctx || !channels || !workspace || count < ZS_SPATIAL_GCC_N || sample_rate_hz == 0u) return false;
  for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) if (!channels[c]) return false;
  ctx->attempts++;
  src.channels = channels;
  src.step = (count - ZS_SPATIAL_GCC_N) / (ZS_BEARING_FRAMES - 1u);
  return bearing_core(ctx, chan_frame, &src, sample_rate_hz, temperature_c, workspace, out);
}

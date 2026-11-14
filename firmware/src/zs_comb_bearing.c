#include "zs_comb_bearing.h"

#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define FS_IN 32000.0f
#define FS_DEC (FS_IN / (float)ZS_COMB_BEARING_DECIM)
#define BIN_HZ (FS_DEC / (float)ZS_COMB_BEARING_N)
#define REL_TOL 0.012f                 /* harmonic tolerance: Doppler drift over the span plus the f0 estimate */
#define COARSE_US 5.0f
#define FINE_US 0.5f
#define FRAME_SEARCH_US 30.0f

/* low-pass for the 32 -> 8 kHz decimation: Hamming-windowed sinc, cut-off 3.6 kHz (passband to 3.1 kHz, the alias of
   everything above 4.9 kHz lands above 3.1 kHz) */
static float taps[ZS_COMB_BEARING_TAPS];
static bool taps_ready;

static void taps_init(void) {
  const float fc = 3600.0f / FS_IN, mid = 0.5f * (float)(ZS_COMB_BEARING_TAPS - 1u);
  float sum = 0.0f;
  for (unsigned i = 0u; i < ZS_COMB_BEARING_TAPS; i++) {
    const float x = (float)i - mid;
    const float sinc = fabsf(x) < 1e-6f ? 2.0f * fc : sinf(2.0f * (float)M_PI * fc * x) / ((float)M_PI * x);
    const float w = 0.54f - 0.46f * cosf(2.0f * (float)M_PI * (float)i / (float)(ZS_COMB_BEARING_TAPS - 1u));
    taps[i] = sinc * w;
    sum += taps[i];
  }
  for (unsigned i = 0u; i < ZS_COMB_BEARING_TAPS; i++) taps[i] /= sum;
  taps_ready = true;
}

typedef int16_t (*sample_fn)(const void *src, unsigned ch, uint32_t i);   /* i = 0 .. SPAN + TAPS - 2 */

static void decimate(sample_fn get, const void *src, float *memory) {
  if (!taps_ready) taps_init();
  for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) {
    float *y = memory + (size_t)c * ZS_COMB_BEARING_SPAN_DECIMATED;
    for (uint32_t m = 0u; m < ZS_COMB_BEARING_SPAN_DECIMATED; m++) {
      float acc = 0.0f;
      const uint32_t base = m * ZS_COMB_BEARING_DECIM;
      for (unsigned i = 0u; i < ZS_COMB_BEARING_TAPS; i++) acc += taps[i] * (float)get(src, c, base + i);
      y[m] = acc * (1.0f / 32768.0f);
    }
  }
}

/* Hann frame f of every channel -> spectrum */
bool zs_comb_bearing_frame_spectra(const float *memory, unsigned f, zs_complex_t spectrum[ZS_SPATIAL_MIC_COUNT][ZS_COMB_BEARING_N]) {
  if (!memory || !spectrum || f >= ZS_COMB_BEARING_FRAMES) return false;
  const float a = 2.0f * (float)M_PI / (float)(ZS_COMB_BEARING_N - 1u);
  const float cr = cosf(a), si = sinf(a);
  for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) {
    const float *x = memory + (size_t)c * ZS_COMB_BEARING_SPAN_DECIMATED + (size_t)f * ZS_COMB_BEARING_HOP;
    zs_complex_t *X = spectrum[c];
    float wr = 1.0f, wi = 0.0f;                        /* e^{i a n}, the window's cosine by rotation */
    for (unsigned n = 0u; n < ZS_COMB_BEARING_N; n++) {
      X[n].re = x[n] * (0.5f - 0.5f * wr);
      X[n].im = 0.0f;
      const float nr = wr * cr - wi * si;
      wi = wr * si + wi * cr;
      wr = nr;
    }
    if (!zs_fft_radix2(X, ZS_COMB_BEARING_N)) return false;
  }
  return true;
}

/* within `scale` tolerances of a harmonic of f0 */
static bool near_harmonic(float f, float f0, float scale) {
  if (f0 <= 0.0f) return false;
  const float h = roundf(f / f0);
  if (h < 1.0f) return false;
  const float target = h * f0;
  const float tol = fmaxf(BIN_HZ, REL_TOL * target);
  return fabsf(f - target) <= scale * tol;
}

/* bins of source s: own harmonics minus everybody else's (with a guard) */
static unsigned build_mask(const float *f0, unsigned count, unsigned s, uint8_t *mask, unsigned *kmax) {
  unsigned n = 0u;
  *kmax = 0u;
  for (unsigned k = 0u; k < ZS_COMB_BEARING_BINS; k++) {
    const float f = (float)k * BIN_HZ;
    uint8_t on = f >= ZS_COMB_BEARING_FMIN_HZ && f <= ZS_COMB_BEARING_FMAX_HZ && near_harmonic(f, f0[s], 1.0f);
    /* a guard of twice the tolerance around the others' harmonics: the skirt of their lines stays out too */
    for (unsigned o = 0u; on && o < count; o++) if (o != s && near_harmonic(f, f0[o], 2.0f)) on = 0u;
    mask[k] = on;
    if (on) { n++; *kmax = k; }
  }
  return n;
}

/* correlation of masked cross spectra at lag tau (us): sum over bins of Re(C_k e^{i w_k tau}), rotation over k */
static float correlation(const zs_complex_t *C, const uint8_t *mask, unsigned kmax, float tau_us) {
  const float dw = 2.0f * (float)M_PI * BIN_HZ * tau_us * 1e-6f;
  const float zr = cosf(dw), zi = sinf(dw);
  float er = 1.0f, ei = 0.0f, r = 0.0f;
  for (unsigned k = 0u; k <= kmax; k++) {
    if (mask[k]) r += C[k].re * er - C[k].im * ei;
    const float nr = er * zr - ei * zi;
    ei = er * zi + ei * zr;
    er = nr;
  }
  return r;
}

static float peak_search(const zs_complex_t *C, const uint8_t *mask, unsigned kmax, float lo_us, float hi_us, float step_us,
                         float *best_r) {
  float best_t = lo_us, best = -1e30f;
  for (float t = lo_us; t <= hi_us + 1e-3f; t += step_us) {
    const float r = correlation(C, mask, kmax, t);
    if (r > best) { best = r; best_t = t; }
  }
  /* parabola through the neighbours */
  {
    const float r0 = correlation(C, mask, kmax, best_t - step_us), r2 = correlation(C, mask, kmax, best_t + step_us);
    const float den = r0 - 2.0f * best + r2;
    if (fabsf(den) > 1e-12f) {
      float frac = 0.5f * (r0 - r2) / den;
      frac = frac > 0.5f ? 0.5f : (frac < -0.5f ? -0.5f : frac);
      best_t += frac * step_us;
    }
  }
  *best_r = best;
  return best_t;
}

static float median_of(float *v, unsigned n) {
  for (unsigned i = 1u; i < n; i++) {
    const float x = v[i];
    unsigned j = i;
    while (j > 0u && v[j - 1u] > x) { v[j] = v[j - 1u]; j--; }
    v[j] = x;
  }
  return (n & 1u) ? v[n / 2u] : 0.5f * (v[n / 2u - 1u] + v[n / 2u]);
}

static unsigned comb_core(const zs_bearing_ctx_t *ctx, zs_comb_bearing_stats_t *stats, const float *f0_hz, unsigned count,
                          float temperature_c, const float *memory, zs_comb_bearing_workspace_t *ws, zs_bearing_t *out) {
  const float c = zs_spatial_speed_of_sound(temperature_c);
  const float max_delay_us = zs_spatial_max_baseline_m(&ctx->geometry) / c * 1.0e6f + 5.0f;
  unsigned bins[ZS_COMB_BEARING_MAX_SOURCES], kmax[ZS_COMB_BEARING_MAX_SOURCES], valid = 0u;
  float tau[ZS_COMB_BEARING_MAX_SOURCES][ZS_SPATIAL_REF_TDOA_COUNT];
  float frame_tau[ZS_COMB_BEARING_MAX_SOURCES][ZS_SPATIAL_REF_TDOA_COUNT][ZS_COMB_BEARING_FRAMES];
  bool live[ZS_COMB_BEARING_MAX_SOURCES];
  float coh_min[ZS_COMB_BEARING_MAX_SOURCES];

  for (unsigned s = 0u; s < count; s++) {
    bins[s] = build_mask(f0_hz, count, s, ws->mask[s], &kmax[s]);
    live[s] = bins[s] >= ZS_COMB_BEARING_MIN_BINS;
    coh_min[s] = 1.0f;
    if (!live[s] && stats) stats->few_bins++;
  }
  memset(ws->acc, 0, sizeof(ws->acc));

  /* pass 1: PHAT cross spectra of each source's bins summed over the frames */
  for (unsigned f = 0u; f < ZS_COMB_BEARING_FRAMES; f++) {
    if (!zs_comb_bearing_frame_spectra(memory, f, ws->spectrum)) return 0u;
    for (unsigned s = 0u; s < count; s++) {
      if (!live[s]) continue;
      for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) {
        const zs_complex_t *X = ws->spectrum[j + 1u], *R = ws->spectrum[0];
        zs_complex_t *A = ws->acc[s][j];
        for (unsigned k = 0u; k <= kmax[s]; k++) {
          if (!ws->mask[s][k]) continue;
          const float cr = X[k].re * R[k].re + X[k].im * R[k].im, ci = X[k].im * R[k].re - X[k].re * R[k].im;
          const float m = sqrtf(cr * cr + ci * ci);
          if (m > 1e-20f) { A[k].re += cr / m; A[k].im += ci / m; }
        }
      }
    }
  }
  for (unsigned s = 0u; s < count; s++) {
    if (!live[s]) continue;
    for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT && live[s]; j++) {
      float r, r_fine;
      const float coarse = peak_search(ws->acc[s][j], ws->mask[s], kmax[s], -max_delay_us, max_delay_us, COARSE_US, &r);
      tau[s][j] = peak_search(ws->acc[s][j], ws->mask[s], kmax[s], coarse - COARSE_US, coarse + COARSE_US, FINE_US, &r_fine);
      const float coherence = r_fine / ((float)bins[s] * (float)ZS_COMB_BEARING_FRAMES);
      if (coherence < ctx->min_quality) { live[s] = false; if (stats) stats->weak++; }
      if (coherence < coh_min[s]) coh_min[s] = coherence;
    }
  }

  /* pass 2: each frame's delay near the summed maximum (their spread is the sigma) */
  for (unsigned f = 0u; f < ZS_COMB_BEARING_FRAMES; f++) {
    bool any = false;
    for (unsigned s = 0u; s < count; s++) any = any || live[s];
    if (!any) break;
    if (!zs_comb_bearing_frame_spectra(memory, f, ws->spectrum)) return 0u;
    for (unsigned s = 0u; s < count; s++) {
      if (!live[s]) continue;
      for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) {
        const zs_complex_t *X = ws->spectrum[j + 1u], *R = ws->spectrum[0];
        zs_complex_t *frame_c = ws->acc[s][j];             /* the sum is no longer needed: the frame's spectrum goes there */
        float r;
        for (unsigned k = 0u; k <= kmax[s]; k++) {
          if (!ws->mask[s][k]) continue;
          const float cr = X[k].re * R[k].re + X[k].im * R[k].im, ci = X[k].im * R[k].re - X[k].re * R[k].im;
          const float m = sqrtf(cr * cr + ci * ci);
          frame_c[k].re = m > 1e-20f ? cr / m : 0.0f;
          frame_c[k].im = m > 1e-20f ? ci / m : 0.0f;
        }
        frame_tau[s][j][f] = peak_search(frame_c, ws->mask[s], kmax[s], tau[s][j] - FRAME_SEARCH_US, tau[s][j] + FRAME_SEARCH_US,
                                         COARSE_US, &r);
      }
    }
  }

  for (unsigned s = 0u; s < count; s++) {
    zs_spatial_solution_t sol;
    float spread_us = 0.0f;
    if (!live[s]) continue;
    for (unsigned j = 0u; j < ZS_SPATIAL_REF_TDOA_COUNT; j++) {
      float dev[ZS_COMB_BEARING_FRAMES];
      for (unsigned f = 0u; f < ZS_COMB_BEARING_FRAMES; f++) dev[f] = fabsf(frame_tau[s][j][f] - tau[s][j]);
      const float mad_us = 1.4826f * median_of(dev, ZS_COMB_BEARING_FRAMES) / sqrtf((float)ZS_COMB_BEARING_FRAMES);
      if (mad_us > spread_us) spread_us = mad_us;
      out[s].tdoa_us[j] = tau[s][j];
    }
    if (!zs_spatial_direction_from_reference_tdoas(&ctx->geometry, tau[s], temperature_c, &sol)) {
      if (stats) stats->unsolved++;
      continue;
    }
    out[s].azimuth_deg = sol.azimuth_deg;
    out[s].elevation_deg = sol.elevation_deg;
    out[s].residual_us = sol.residual_us;
    out[s].confidence = fminf(coh_min[s], sol.confidence);   /* the weakest pair's coherence or the solver's */
    {
      const float aperture_m = zs_spatial_max_baseline_m(&ctx->geometry) * 0.73f;
      const float t_us = sqrtf(spread_us * spread_us + sol.residual_us * sol.residual_us);
      const float sigma = (float)(180.0 / M_PI) * c * t_us * 1.0e-6f / aperture_m + 0.5f;
      out[s].sigma_deg = sigma > 45.0f ? 45.0f : sigma;
    }
    out[s].frames_used = (uint8_t)ZS_COMB_BEARING_FRAMES;
    out[s].valid = true;
    valid++;
    if (stats) stats->computed++;
  }
  return valid;
}

static bool args_ok(const zs_bearing_ctx_t *ctx, const float *f0_hz, unsigned count, const float *memory,
                    const zs_comb_bearing_workspace_t *ws, const zs_bearing_t *out) {
  if (!ctx || !f0_hz || !memory || !ws || !out || count == 0u || count > ZS_COMB_BEARING_MAX_SOURCES) return false;
  for (unsigned s = 0u; s < count; s++) if (!(f0_hz[s] >= 30.0f && f0_hz[s] <= 1000.0f)) return false;
  return true;
}

static void reset_out(const float *f0_hz, unsigned count, zs_bearing_t *out) {
  for (unsigned s = 0u; s < count; s++) { memset(&out[s], 0, sizeof(out[s])); out[s].f0_hz = f0_hz[s]; }
}

typedef struct {
  const zs_audio_ring_t *ring;
  uint64_t end;
  uint32_t count;
} ring_src_t;

static int16_t ring_sample(const void *p, unsigned ch, uint32_t i) {
  const ring_src_t *r = p;
  return zs_audio_ring_at(r->ring, r->end, r->count, i, ch);
}

bool zs_comb_bearing_decimate_ring(const zs_audio_ring_t *ring, uint64_t end_sample, float *memory) {
  ring_src_t src;
  if (!ring || !memory) return false;
  src.ring = ring;
  src.end = end_sample;
  src.count = ZS_COMB_BEARING_SPAN + ZS_COMB_BEARING_TAPS - 1u;
  if (end_sample < src.count || !zs_audio_ring_range_ok(ring, end_sample, src.count)) return false;
  decimate(ring_sample, &src, memory);
  return true;
}

typedef struct {
  const int16_t *const *channels;
  uint32_t offset;
} chan_src_t;

static int16_t chan_sample(const void *p, unsigned ch, uint32_t i) {
  const chan_src_t *s = p;
  return s->channels[ch][s->offset + i];
}

bool zs_comb_bearing_decimate_channels(const int16_t *const channels[ZS_SPATIAL_MIC_COUNT], uint32_t count_samples, float *memory) {
  chan_src_t src;
  const uint32_t need = ZS_COMB_BEARING_SPAN + ZS_COMB_BEARING_TAPS - 1u;
  if (!channels || !memory || count_samples < need) return false;
  for (unsigned c = 0u; c < ZS_SPATIAL_MIC_COUNT; c++) if (!channels[c]) return false;
  src.channels = channels;
  src.offset = count_samples - need;
  decimate(chan_sample, &src, memory);
  return true;
}

unsigned zs_comb_bearings_from_memory(const zs_bearing_ctx_t *ctx, zs_comb_bearing_stats_t *stats, const float *memory,
                                      const float *f0_hz, unsigned count, float temperature_c, zs_comb_bearing_workspace_t *ws,
                                      zs_bearing_t *out) {
  if (!args_ok(ctx, f0_hz, count, memory, ws, out)) return 0u;
  reset_out(f0_hz, count, out);
  if (stats) stats->attempts += count;
  return comb_core(ctx, stats, f0_hz, count, temperature_c, memory, ws, out);
}

unsigned zs_comb_bearings_from_ring(const zs_bearing_ctx_t *ctx, zs_comb_bearing_stats_t *stats, const zs_audio_ring_t *ring,
                                    uint64_t end_sample, const float *f0_hz, unsigned count, float temperature_c, float *memory,
                                    zs_comb_bearing_workspace_t *ws, zs_bearing_t *out) {
  if (!args_ok(ctx, f0_hz, count, memory, ws, out) || !ring) return 0u;
  reset_out(f0_hz, count, out);
  if (stats) stats->attempts += count;
  if (!zs_comb_bearing_decimate_ring(ring, end_sample, memory)) { if (stats) stats->no_audio += count; return 0u; }
  return comb_core(ctx, stats, f0_hz, count, temperature_c, memory, ws, out);
}

unsigned zs_comb_bearings_from_channels(const zs_bearing_ctx_t *ctx, zs_comb_bearing_stats_t *stats,
                                        const int16_t *const channels[ZS_SPATIAL_MIC_COUNT], uint32_t count_samples,
                                        const float *f0_hz, unsigned count, float temperature_c, float *memory,
                                        zs_comb_bearing_workspace_t *ws, zs_bearing_t *out) {
  if (!args_ok(ctx, f0_hz, count, memory, ws, out)) return 0u;
  if (!zs_comb_bearing_decimate_channels(channels, count_samples, memory)) return 0u;
  reset_out(f0_hz, count, out);
  if (stats) stats->attempts += count;
  return comb_core(ctx, stats, f0_hz, count, temperature_c, memory, ws, out);
}

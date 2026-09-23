#include "zs_air_gate.h"
#include <math.h>
#include <string.h>

/* server/config.py */
#define BAND_LOW_HZ 18.0f
#define BAND_HIGH_HZ 2400.0f
#define F0_MIN_HZ 12.0f
#define F0_MAX_HZ 180.0f
#define MAX_HARMONICS 16u
#define PRESENT_SNR_DB 6.0f      /* server, on the median-floor SNR (kept for the report) */
#define PRESENT_CONTRAST_DB 3.0f /* station gate runs on the unbiased contrast: white noise gives 0..1 dB */
#define STRONG_CONTRAST_DB 8.0f  /* server "strong evidence" 12 dB on the biased SNR ~ 8 dB of contrast */
#define RELAX_CONTRAST_DB 12.0f  /* server relaxes the steadiness limit at 20 dB biased SNR */
#define PERSISTENCE_MIN 0.35f
#define MIN_HARMONICS 4u
#define STEADINESS_CV_MAX 0.12f
#define MAINS_NOTCH_HZ 1.2f
#define MAINS_NOTCH_MAX_HZ 200.0f

#define DEC_SAMPLES (ZS_AIR_WINDOW_SAMPLES / ZS_AIR_DECIMATION) /* 6400 */
#define BIN_HZ ((float)ZS_AIR_SAMPLE_RATE / (float)ZS_AIR_DECIMATION / (float)ZS_AIR_FFT) /* 0.78125 */
#define BINS ZS_AIR_BINS
#define B_LO ((unsigned)(BAND_LOW_HZ / BIN_HZ) + 1u)
#define B_HI ((unsigned)(BAND_HIGH_HZ / BIN_HZ))

static float peak_near(const float *p, float target, float tol, unsigned *at) {
  int lo = (int)floorf((target - tol) / BIN_HZ), hi = (int)ceilf((target + tol) / BIN_HZ);
  float best = -1.0f;
  if (lo < 0) lo = 0;
  if (hi >= (int)BINS) hi = (int)BINS - 1;
  for (int i = lo; i <= hi; i++) if (p[i] > best) { best = p[i]; if (at) *at = (unsigned)i; }
  return best;
}

static float comb_power_at(const float *p, float f0) {
  float tol = fmaxf(1.5f * BIN_HZ, f0 * 0.05f), total = 0.0f;
  for (unsigned k = 1u; k <= MAX_HARMONICS; k++) { float t = f0 * (float)k; if (t > BAND_HIGH_HZ) break; float pk = peak_near(p, t, tol, NULL); if (pk > 0.0f) total += pk; }
  return total;
}

static float median_of(float *v, unsigned n) {
  if (n == 0u) return 0.0f;
  for (unsigned i = 1u; i < n; i++) { float x = v[i]; unsigned j = i; while (j > 0u && v[j - 1u] > x) { v[j] = v[j - 1u]; j--; } v[j] = x; }
  return (n & 1u) ? v[n / 2u] : 0.5f * (v[n / 2u - 1u] + v[n / 2u]);
}

/* median of log power over [from, to] via a 256-bin histogram */
static float band_median_log(const float *lp, unsigned from, unsigned to) {
  float lo = 1e30f, hi = -1e30f;
  for (unsigned i = from; i <= to; i++) { if (lp[i] < lo) lo = lp[i]; if (lp[i] > hi) hi = lp[i]; }
  if (hi - lo < 1e-6f) return lo;
  unsigned hist[256] = {0}, n = to - from + 1u;
  for (unsigned i = from; i <= to; i++) { unsigned b = (unsigned)((lp[i] - lo) / (hi - lo) * 255.0f); if (b > 255u) b = 255u; hist[b]++; }
  unsigned acc = 0u, target = (n + 1u) / 2u, b = 0u;
  for (; b < 256u; b++) { acc += hist[b]; if (acc >= target) break; }
  return lo + ((float)b + 0.5f) / 255.0f * (hi - lo);
}

/* Power spectrum of the band for one window: DC removal, decimate x5 (9-tap triangle), Hann, FFT, mains notches. */
static bool window_spectrum(const int16_t *pcm, zs_complex_t *x, float *p) {
  double sum = 0.0;
  for (unsigned i = 0u; i < ZS_AIR_WINDOW_SAMPLES; i++) sum += pcm[i];
  const float dc = (float)(sum / ZS_AIR_WINDOW_SAMPLES);
  static const float tri[9] = {1, 2, 3, 4, 5, 4, 3, 2, 1};
  for (unsigned m = 0u; m < DEC_SAMPLES; m++) {
    int c = (int)(m * ZS_AIR_DECIMATION);
    float acc = 0.0f;
    for (int t = -4; t <= 4; t++) { int i = c + t; if (i >= 0 && i < (int)ZS_AIR_WINDOW_SAMPLES) acc += tri[t + 4] * ((float)pcm[i] - dc); }
    float w = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * (float)m / (float)DEC_SAMPLES);
    x[m].re = acc * (1.0f / 25.0f) * (1.0f / 32768.0f) * w;
    x[m].im = 0.0f;
  }
  for (unsigned m = DEC_SAMPLES; m < ZS_AIR_FFT; m++) { x[m].re = 0.0f; x[m].im = 0.0f; }
  if (!zs_fft_radix2(x, ZS_AIR_FFT)) return false;
  for (unsigned i = 0u; i < BINS; i++) { float re = x[i].re, im = x[i].im; p[i] = re * re + im * im + 1e-20f; }
  for (unsigned base = 50u; base <= 60u; base += 10u)
    for (float f = (float)base; f <= MAINS_NOTCH_MAX_HZ; f += (float)base) {
      unsigned lo = (unsigned)floorf((f - MAINS_NOTCH_HZ * 0.5f) / BIN_HZ), hi = (unsigned)ceilf((f + MAINS_NOTCH_HZ * 0.5f) / BIN_HZ);
      float fill = 0.5f * (p[lo > 0u ? lo - 1u : 0u] + p[hi + 1u < BINS ? hi + 1u : BINS - 1u]);
      for (unsigned i = lo; i <= hi && i < BINS; i++) p[i] = fill;
    }
  return true;
}

/* Comb fit on the averaged log spectrum (server DroneSeparator._fit_comb_fundamental on the median spectrum). */
static void fit_comb(const float *lp, float *f0_out, float *anchor_out) {
  static float p[BINS];
  for (unsigned i = 0u; i < BINS; i++) p[i] = expf(lp[i]);
  const float floor_log = band_median_log(lp, B_LO, B_HI);
  /* anchor: the most prominent bin (power over the mean of ±32 Hz around it, ±2.5 Hz guarded) */
  unsigned dom = B_LO; float best_prom = -1.0f;
  const unsigned half = (unsigned)(32.0f / BIN_HZ), guard = (unsigned)(2.5f / BIN_HZ);
  for (unsigned i = B_LO; i <= B_HI; i++) {
    unsigned lo = i > half ? i - half : 0u, hi = i + half < BINS ? i + half : BINS - 1u;
    double local = 0.0; unsigned n_local = 0u;
    for (unsigned j = lo; j <= hi; j++) { if (j + guard >= i && j <= i + guard) continue; local += p[j]; n_local++; }
    const float lf = n_local ? (float)(local / n_local) : 1e-30f;
    const float prom = p[i] / (lf > 1e-30f ? lf : 1e-30f);
    if (lp[i] >= floor_log && prom > best_prom) { best_prom = prom; dom = i; }
  }
  *f0_out = 0.0f; *anchor_out = 0.0f;
  if (best_prom < 2.0f) return;                              /* nothing line-like: < 3 dB over its surroundings */
  const float dominant = (float)dom * BIN_HZ;
  float best_f0 = dominant, best_pw = comb_power_at(p, dominant);
  const float floor8 = expf(floor_log) * 6.3096f;
  for (unsigned k = 2u; k <= 6u; k++) {
    float cand = dominant / (float)k;
    if (cand < F0_MIN_HZ) break;
    unsigned hits = 0u, low = 0u; float tol = fmaxf(1.5f * BIN_HZ, cand * 0.04f);
    for (unsigned h = 1u; h <= 4u; h++) { float t = cand * (float)h; if (t > BAND_HIGH_HZ) break; if (peak_near(p, t, tol, NULL) >= floor8) { hits++; if (h <= 2u) low++; } }
    if (hits >= 3u && low >= 1u) {   /* a real lower fundamental shows its 1st or 2nd tooth, not only the dominant's neighbours */ float pw = comb_power_at(p, cand); if (pw > best_pw) { best_pw = pw; best_f0 = cand; } }
  }
  { float gbest = best_f0, gpw = -1.0f;
    for (float g = best_f0 * 0.95f; g < best_f0 * 1.05f; g += BIN_HZ * 0.25f) { if (g < F0_MIN_HZ) continue; float pw = comb_power_at(p, g); if (pw > gpw) { gpw = pw; gbest = g; } }
    best_f0 = gbest; }
  if (best_f0 > F0_MAX_HZ * 4.0f) return;                    /* no plausible propulsion comb */
  /* strongest tooth of the fitted comb on the average = the line to track per window */
  float tol = fmaxf(1.5f * BIN_HZ, best_f0 * 0.06f), apw = -1.0f; unsigned abin = dom;
  for (unsigned k = 1u; k <= MAX_HARMONICS; k++) { float t = best_f0 * (float)k; if (t > BAND_HIGH_HZ) break; unsigned at = 0u; float pk = peak_near(p, t, tol, &at); if (pk > apw) { apw = pk; abin = at; } }
  *f0_out = best_f0; *anchor_out = (float)abin * BIN_HZ;
}

/* Per-window measurement at the fixed f0 (server _window_harmonic_snr / _count_harmonics with the
   half-order comparison, see the header). */
static void measure_window(const float *p, float f0_avg, float anchor_hz, zs_air_window_t *w) {
  memset(w, 0, sizeof(*w));
  if (f0_avg <= 0.0f) return;
  /* refine the fundamental on this window (±10 %, BIN/2 steps): a real propulsion line drifts with RPM and
     Doppler by several percent per second, which would misalign the high teeth of a fixed comb */
  float f0 = f0_avg, best_pw = -1.0f;
  for (float g = f0_avg * 0.9f; g <= f0_avg * 1.1f; g += BIN_HZ * 0.5f) { if (g < F0_MIN_HZ) continue; float pw = comb_power_at(p, g); if (pw > best_pw) { best_pw = pw; f0 = g; } }
  static float lp[BINS];
  static uint8_t mask[BINS];
  for (unsigned i = 0u; i < BINS; i++) { lp[i] = logf(p[i]); mask[i] = 0u; }
  const float floor6 = expf(band_median_log(lp, B_LO, B_HI)) * 3.981f;
  const float tol = fmaxf(1.5f * BIN_HZ, f0 * 0.06f);
  float peaks = 0.0f, half = 0.0f; unsigned np = 0u, nh = 0u;
  for (unsigned k = 1u; k <= MAX_HARMONICS; k++) {
    float t = f0 * (float)k;
    if (t > BAND_HIGH_HZ) break;
    int lo = (int)floorf((t - tol) / BIN_HZ), hi = (int)ceilf((t + tol) / BIN_HZ);
    for (int i = lo < 0 ? 0 : lo; i <= hi && i < (int)BINS; i++) mask[i] = 1u;
    float pk = peak_near(p, t, tol, NULL);
    if (pk > 0.0f) { peaks += pk; np++; if (pk >= floor6) w->harmonic_count++; }
  }
  for (unsigned k = 0u; k < MAX_HARMONICS; k++) { float t = f0 * ((float)k + 0.5f); if (t > BAND_HIGH_HZ) break; float pk = peak_near(p, t, tol, NULL); if (pk > 0.0f) { half += pk; nh++; } }
  w->integer_order_ratio = (peaks + half) > 0.0f ? peaks / (peaks + half) : 0.0f;
  const float level = np ? peaks / (float)np : 0.0f, between = nh ? half / (float)nh : 0.0f;
  w->contrast_db = (between > 1e-30f && level > 0.0f) ? 10.0f * log10f(level / between) : 0.0f;
  /* server _window_harmonic_snr: median of the band from 0.5 f0 with the harmonic bins excluded */
  {
    unsigned n_lo = (unsigned)fmaxf((float)B_LO, f0 * 0.5f / BIN_HZ), m = 0u;
    static float noise_lp[BINS];
    for (unsigned i = n_lo; i <= B_HI; i++) if (!mask[i]) noise_lp[m++] = lp[i];
    const float noise = m ? expf(band_median_log(noise_lp, 0u, m - 1u)) : 0.0f;
    w->snr_db = (noise > 1e-30f && level > 0.0f) ? 10.0f * log10f(level / noise) : 0.0f;
  }
  w->comb = w->snr_db >= PRESENT_SNR_DB && w->contrast_db >= PRESENT_CONTRAST_DB && w->harmonic_count >= 2u;
  w->f0_hz = f0;
  if (anchor_hz > 0.0f) { float k = floorf(anchor_hz / f0_avg + 0.5f); if (k < 1.0f) k = 1.0f; w->dominant_hz = f0 * k; }
}

void zs_air_gate_init(zs_air_gate_t *g) { memset(g, 0, sizeof(*g)); }

const zs_air_window_t *zs_air_gate_last(const zs_air_gate_t *g) {
  return g->count ? &g->hist[(g->next + ZS_AIR_HISTORY - 1u) % ZS_AIR_HISTORY] : NULL;
}

zs_air_gate_result_t zs_air_gate_evaluate(const zs_air_gate_t *g) {
  zs_air_gate_result_t r;
  float snr[ZS_AIR_HISTORY], ctr[ZS_AIR_HISTORY], f0s[ZS_AIR_HISTORY], sorted[ZS_AIR_HISTORY], ratios[ZS_AIR_HISTORY];
  unsigned n = g->count, present = 0u, ncomb = 0u, hmax = 0u;
  memset(&r, 0, sizeof(r));
  if (n == 0u) return r;
  for (unsigned i = 0u; i < n; i++) {
    const zs_air_window_t *w = &g->hist[i];
    snr[i] = w->snr_db; ctr[i] = w->contrast_db;
    if (w->comb) { present++; ratios[ncomb] = w->integer_order_ratio; f0s[ncomb] = w->f0_hz; ncomb++; if (w->harmonic_count > hmax) hmax = w->harmonic_count; }
  }
  r.persistence = (float)present / (float)n;
  r.median_snr_db = median_of(snr, n);
  r.median_contrast_db = median_of(ctr, n);
  r.harmonic_count = (uint8_t)hmax;
  r.f0_hz = g->f0_hz;
  r.steadiness_cv = 1.0f;
  if (ncomb >= 2u) {
    /* fold a window's f0 up by 2 or 3 when that lands within 6 % of the highest estimate: the comb fit
       slips to exact sub-harmonics on real recordings and such a slip is not motion of the source,
       whereas a glide never folds exactly */
    float ref = 0.0f;
    for (unsigned i = 0u; i < ncomb; i++) if (f0s[i] > ref) ref = f0s[i];
    float mean = 0.0f;
    for (unsigned i = 0u; i < ncomb; i++) {
      for (unsigned k = 2u; k <= 3u; k++) { float up = f0s[i] * (float)k; if (fabsf(up - ref) <= 0.06f * ref) { f0s[i] = up; break; } }
      mean += f0s[i];
    }
    (void)sorted;
    mean /= (float)ncomb;
    float var = 0.0f; for (unsigned i = 0u; i < ncomb; i++) { float d = f0s[i] - mean; var += d * d; } var /= (float)ncomb;
    r.steadiness_cv = mean > 0.0f ? sqrtf(var) / mean : 1.0f;
  }
  const float order_ratio = ncomb ? median_of(ratios, ncomb) : 0.0f;
  float cv_max = STEADINESS_CV_MAX;
  if (r.median_contrast_db >= RELAX_CONTRAST_DB) cv_max = fminf(cv_max * 2.0f, 0.25f);
  for (unsigned m = 50u; m <= 60u; m += 10u)
    if (r.f0_hz > 0.0f && fabsf(r.f0_hz - (float)m) <= 2.0f && (r.steadiness_cv <= 0.02f || order_ratio >= 0.95f)) r.mains = true;
  const bool strong = r.persistence >= 0.6f && r.median_contrast_db >= STRONG_CONTRAST_DB;
  const unsigned min_h = strong ? 2u : MIN_HARMONICS;
  r.present = n >= 2u && r.persistence >= PERSISTENCE_MIN && r.median_contrast_db >= PRESENT_CONTRAST_DB && r.steadiness_cv <= cv_max && hmax >= min_h && !r.mains;
  float score = 0.40f * fminf(r.persistence / 0.6f, 1.0f) + 0.30f * fminf(fmaxf(r.median_contrast_db, 0.0f) / 10.0f, 1.0f) +
                0.20f * (1.0f - fminf(r.steadiness_cv / 0.1f, 1.0f)) + 0.10f * fminf((float)hmax / 8.0f, 1.0f);
  if (!r.present) score *= 0.5f;
  r.confidence_u8 = (uint8_t)(fminf(fmaxf(score, 0.0f), 1.0f) * 255.0f + 0.5f);
  return r;
}

bool zs_air_gate_push(zs_air_gate_t *g, const int16_t *pcm, size_t n, zs_complex_t *scratch, zs_air_gate_result_t *out) {
  if (!g || !pcm || !scratch || n < ZS_AIR_WINDOW_SAMPLES || !out) { if (out) memset(out, 0, sizeof(*out)); return false; }
  if (!window_spectrum(pcm, scratch, g->spectrum)) { memset(out, 0, sizeof(*out)); return false; }
  /* running geometric mean over the history depth */
  const float alpha = 1.0f / (float)(g->count < ZS_AIR_HISTORY ? g->count + 1u : ZS_AIR_HISTORY);
  for (unsigned i = 0u; i < BINS; i++) { float l = logf(g->spectrum[i]); g->avg_log[i] += (l - g->avg_log[i]) * alpha; }
  fit_comb(g->avg_log, &g->f0_hz, &g->anchor_hz);
  zs_air_window_t w;
  measure_window(g->spectrum, g->f0_hz, g->anchor_hz, &w);
  g->hist[g->next] = w;
  g->next = (uint8_t)((g->next + 1u) % ZS_AIR_HISTORY);
  if (g->count < ZS_AIR_HISTORY) g->count++;
  *out = zs_air_gate_evaluate(g);
  return true;
}

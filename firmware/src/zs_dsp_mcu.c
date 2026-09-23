/*
 * zs_dsp_mcu: the zs_dsp feature extractor (43 features, 1 s window at 32 kHz)
 * re-implemented for the STM32U585:
 *   - zs_fft_mixed instead of the recursive cosf/sinf FFT;
 *   - no double precision (float with chunked accumulation, int64 for the DC sum);
 *   - one 128 KB complex work buffer and one 128 KB float buffer with overlays
 *     instead of ~430 KB of separate static arrays;
 *   - MFCC DCT and STFT window from tables built once.
 * Feature definitions, band limits, thresholds and ordering are those of zs_dsp.c.
 * The host A/B test (test_dsp_mcu) keeps both implementations within the golden
 * acceptance (median normalized error <= 3 %, p95 <= 5 %).
 */
#include "zs_dsp_mcu.h"

#include "zs_fft_mixed.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define SR 32000u
#define NSAMP 32000u
#define N_GLOBAL 32000u
#define GLOBAL_BINS (N_GLOBAL / 2u + 1u)
#define STFT_N 2048u
#define STFT_HOP 512u
#define STFT_BINS (STFT_N / 2u + 1u)
#define STFT_FRAMES 63u
#define N_MELS 128u
#define N_MFCC 13u
#define YIN_FRAMES 32u
#define YIN_FFT 8192u
#define YIN_MINP 64u
#define YIN_MAXP 800u
#define MAX_HARMONICS 64u
#define WORK_COMPLEX 16384u   /* >= 2 * YIN_FFT and >= N_GLOBAL/2 */
#define MAX_PEAKS 8192u

/* ---- scratch memory (260 KB) -------------------------------------------------- */
static zs_complex_t g_work[WORK_COMPLEX];      /* 128 KB: FFT scratch, YIN, STFT, median tmp */
static float g_magbuf[N_GLOBAL];               /* 128 KB: packed FFT input, then |X| in [0, GLOBAL_BINS) */
#define g_mag g_magbuf
static float *const g_tail = g_magbuf + GLOBAL_BINS;             /* 15999 floats after the magnitudes */
#define g_peaks ((uint16_t *)(void *)g_tail)                     /* MAX_PEAKS entries = 4096 floats */
#define g_peak_state ((uint8_t *)(void *)(g_tail + 4096u))       /* GLOBAL_BINS bytes ~ 4001 floats */
#define g_mel ((float (*)[N_MELS])(void *)g_tail)                /* STFT_FRAMES x N_MELS = 8064 floats, after harmonics */
static float g_yin[YIN_MAXP + 1u];
static float g_f0[YIN_FRAMES];
static float g_harmonics[MAX_HARMONICS];
static float g_stft_window[STFT_N];
static float g_dct[N_MFCC][N_MELS];
static float g_mel_edges[N_MELS + 2u];
static bool g_tables_ready;

/* ---- helpers ---------------------------------------------------------------- */
static float clamp01(float x) { return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x); }

static float hz_to_mel(float hz) {
  const float f_sp = 200.0f / 3.0f;
  float m = hz / f_sp;
  if (hz >= 1000.0f) {
    const float min_log_mel = 1000.0f / f_sp, logstep = logf(6.4f) / 27.0f;
    m = min_log_mel + logf(hz / 1000.0f) / logstep;
  }
  return m;
}
static float mel_to_hz(float mel) {
  const float f_sp = 200.0f / 3.0f, min_log_mel = 1000.0f / f_sp, logstep = logf(6.4f) / 27.0f;
  if (mel >= min_log_mel) return 1000.0f * expf(logstep * (mel - min_log_mel));
  return f_sp * mel;
}

static void build_tables(void) {
  float mel0 = hz_to_mel(0.0f), mel1 = hz_to_mel((float)SR * 0.5f);
  if (g_tables_ready) return;
  for (unsigned i = 0u; i < STFT_N; i++) g_stft_window[i] = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * (float)i / (float)STFT_N);
  for (unsigned k = 0u; k < N_MFCC; k++) {
    float norm = (k == 0u) ? sqrtf(1.0f / (float)N_MELS) : sqrtf(2.0f / (float)N_MELS);
    for (unsigned m = 0u; m < N_MELS; m++) g_dct[k][m] = norm * cosf((float)M_PI * (float)k * ((float)m + 0.5f) / (float)N_MELS);
  }
  for (unsigned i = 0u; i < N_MELS + 2u; i++) g_mel_edges[i] = mel_to_hz(mel0 + (mel1 - mel0) * (float)i / (float)(N_MELS + 1u));
  g_tables_ready = true;
}

static void sort_small(float *a, unsigned n) {
  for (unsigned i = 1u; i < n; i++) {
    float v = a[i]; int j = (int)i - 1;
    while (j >= 0 && a[j] > v) { a[j + 1] = a[j]; j--; }
    a[j + 1] = v;
  }
}
static float median_small(float *a, unsigned n) {
  if (!n) return 0.0f;
  sort_small(a, n);
  return (n & 1u) ? a[n / 2u] : 0.5f * (a[n / 2u - 1u] + a[n / 2u]);
}
static void fswap(float *a, float *b) { float t = *a; *a = *b; *b = t; }
static float quickselect(float *a, unsigned n, unsigned k) {
  unsigned l = 0u, r = n - 1u;
  for (;;) {
    if (l == r) return a[l];
    float pivot = a[l + (r - l) / 2u];
    unsigned i = l, j = r;
    while (i <= j) {
      while (a[i] < pivot) i++;
      while (a[j] > pivot) { if (j == 0u) break; j--; }
      if (i <= j) { fswap(&a[i], &a[j]); i++; if (j == 0u) break; j--; }
    }
    if (k <= j) r = j; else if (k >= i) l = i; else return a[k];
  }
}
/* Median of a[i0..i1)/maxv using g_work as scratch (must be free at call time). */
static float exact_median_normalized(const float *a, unsigned i0, unsigned i1, float maxv) {
  float *tmp = (float *)(void *)g_work;
  unsigned n;
  if (maxv <= 0.0f || i1 <= i0) return 0.0f;
  n = i1 - i0;
  for (unsigned j = 0u; j < n; j++) tmp[j] = a[i0 + j] / maxv;
  if (n & 1u) return quickselect(tmp, n, n / 2u);
  {
    float hi = quickselect(tmp, n, n / 2u), lo = tmp[0];
    for (unsigned i = 1u; i < n / 2u; i++) if (tmp[i] > lo) lo = tmp[i];
    return 0.5f * (lo + hi);
  }
}
static int cmp_peak_height_desc(const void *aa, const void *bb) {
  const uint16_t a = *(const uint16_t *)aa, b = *(const uint16_t *)bb;
  const float da = g_mag[a], db = g_mag[b];
  if (da < db) return 1;
  if (da > db) return -1;
  return (int)b - (int)a;
}

/* Chunked float accumulation: partial sums of 256 terms keep the rounding error ~1e-6 relative. */
typedef struct { float total, part; unsigned n; } acc_t;
static void acc_add(acc_t *a, float v) { a->part += v; if (++a->n == 256u) { a->total += a->part; a->part = 0.0f; a->n = 0u; } }
static float acc_get(const acc_t *a) { return a->total + a->part; }

/* ---- preprocessing ------------------------------------------------------------ */
typedef struct { const int16_t *pcm; float dc, scale; } sig_t;

static float sample_norm(const sig_t *s, int idx) {
  if (idx < 0 || idx >= (int)NSAMP) return 0.0f;
  return ((float)s->pcm[idx] - s->dc) * s->scale;
}
static float sample_edge(const sig_t *s, int idx) {
  if (idx < 0) idx = 0; else if (idx >= (int)NSAMP) idx = (int)NSAMP - 1;
  return ((float)s->pcm[idx] - s->dc) * s->scale;
}

static void preprocess_stats(sig_t *s, float *energy, float *rms, float *zcr) {
  int64_t sum = 0;
  float mean, peak = 0.0f, sc, prev;
  acc_t e = {0.0f, 0.0f, 0u};
  unsigned crossings = 0u;
  for (unsigned i = 0u; i < NSAMP; i++) sum += s->pcm[i];
  mean = (float)((double)sum / (double)NSAMP); /* one exact int64 -> float conversion; the M33 does this in software once */
  for (unsigned i = 0u; i < NSAMP; i++) { float v = fabsf((float)s->pcm[i] - mean); if (v > peak) peak = v; }
  sc = peak > 1e-9f ? 1.0f / peak : 1.0f;
  prev = ((float)s->pcm[0] - mean) * sc;
  for (unsigned i = 0u; i < NSAMP; i++) {
    float y = ((float)s->pcm[i] - mean) * sc;
    acc_add(&e, y * y);
    if (i && ((y >= 0.0f) != (prev >= 0.0f))) crossings++;
    prev = y;
  }
  s->dc = mean;
  s->scale = sc;
  *energy = acc_get(&e) / (float)NSAMP;
  *rms = sqrtf(*energy);
  *zcr = (float)crossings / (float)(NSAMP - 1u);
}

/* ---- global spectrum (Hann-windowed 32000-point real FFT) ------------------- */
static float global_sample(const void *ctx, unsigned i) {
  const sig_t *s = ctx;
  float w = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * (float)i / (float)NSAMP);
  return sample_norm(s, (int)i) * w;
}
static bool global_spectrum(const sig_t *s, float *max_mag) {
  return zs_fft_mixed_real_magnitude(global_sample, s, N_GLOBAL, g_work, g_magbuf, max_mag);
}

/* ---- YIN f0 track ------------------------------------------------------------- */
static float f0_one_frame(const sig_t *s, int start) {
  zs_complex_t *x = g_work, *scratch = g_work + YIN_FFT;
  float cumulative_energy[YIN_MAXP + 1u];
  acc_t run = {0.0f, 0.0f, 0u};
  float acf0, d[YIN_MAXP + 1u], cum = 0.0f, bestv, shift = 0.0f, period;
  unsigned best;
  bool found = false;
  for (unsigned i = 0u; i < 4096u; i++) {
    float y = sample_norm(s, start + (int)i);
    x[i].re = y; x[i].im = 0.0f;
    acc_add(&run, y * y);
    if (i <= YIN_MAXP) cumulative_energy[i] = acc_get(&run);
  }
  for (unsigned i = 4096u; i < YIN_FFT; i++) { x[i].re = 0.0f; x[i].im = 0.0f; }
  if (!zs_fft_mixed_complex(x, scratch, YIN_FFT)) return 0.0f;
  /* power spectrum, then inverse via conj(FFT(conj(P)))/N; P is real so conj is a no-op */
  for (unsigned i = 0u; i < YIN_FFT; i++) { float p = x[i].re * x[i].re + x[i].im * x[i].im; x[i].re = p; x[i].im = 0.0f; }
  if (!zs_fft_mixed_complex(x, scratch, YIN_FFT)) return 0.0f;
  acf0 = x[0].re / (float)YIN_FFT;
  d[0] = 0.0f;
  for (unsigned k = 1u; k <= YIN_MAXP; k++) d[k] = 2.0f * (acf0 - x[k].re / (float)YIN_FFT) - cumulative_energy[k - 1u];
  for (unsigned k = 1u; k <= YIN_MAXP; k++) { cum += d[k]; g_yin[k] = (cum > 1e-30f) ? d[k] * (float)k / cum : 1.0f; }
  best = YIN_MINP; bestv = g_yin[YIN_MINP];
  if (g_yin[YIN_MINP] < g_yin[YIN_MINP + 1u] && g_yin[YIN_MINP] < 0.1f) { best = YIN_MINP; found = true; }
  for (unsigned k = YIN_MINP + 1u; !found && k < YIN_MAXP; k++) {
    bool trough = (g_yin[k] < g_yin[k - 1u] && g_yin[k] <= g_yin[k + 1u]);
    if (g_yin[k] < bestv) { bestv = g_yin[k]; best = k; }
    if (trough && g_yin[k] < 0.1f) { best = k; found = true; }
  }
  if (!found && g_yin[YIN_MAXP] < bestv) best = YIN_MAXP;
  if (best > YIN_MINP && best < YIN_MAXP) {
    float a = g_yin[best - 1u], b = g_yin[best], c = g_yin[best + 1u], den = a - 2.0f * b + c;
    if (fabsf(den) > 1e-20f) { float q = 0.5f * (a - c) / den; if (fabsf(q) <= 1.0f) shift = q; }
  }
  period = (float)best + shift;
  return period > 0.0f ? (float)SR / period : 0.0f;
}

static unsigned estimate_f0_track(const sig_t *s, float *median, float *variation) {
  unsigned n = 0u;
  float tmp[YIN_FRAMES];
  acc_t sa = {0.0f, 0.0f, 0u}, ssa = {0.0f, 0.0f, 0u};
  float mean, var;
  for (unsigned fr = 0u; fr < YIN_FRAMES; fr++) {
    float f = f0_one_frame(s, (int)(fr * 1024u) - 2048);
    if (f > 0.0f) g_f0[n++] = f;
  }
  if (!n) { *median = 0.0f; *variation = 0.0f; return 0u; }
  memcpy(tmp, g_f0, n * sizeof(float));
  *median = median_small(tmp, n);
  if (n < 2u) { *variation = 0.0f; return n; }
  for (unsigned i = 0u; i < n; i++) { acc_add(&sa, g_f0[i]); acc_add(&ssa, g_f0[i] * g_f0[i]); }
  mean = acc_get(&sa) / (float)n; var = acc_get(&ssa) / (float)n - mean * mean;
  if (var < 0.0f) var = 0.0f;
  *variation = (fabsf(mean) > 1e-12f) ? clamp01(sqrtf(var) / fabsf(mean)) : 0.0f;
  return n;
}

static float spectral_f0_fallback(float max_mag) {
  unsigned lo, hi, bi;
  float bm = 0.0f;
  if (max_mag <= 0.0f) return 0.0f;
  lo = (unsigned)ceilf(40.0f * (float)N_GLOBAL / (float)SR); hi = (unsigned)floorf(500.0f * (float)N_GLOBAL / (float)SR); bi = lo;
  for (unsigned i = lo; i <= hi; i++) if (g_mag[i] > bm) { bm = g_mag[i]; bi = i; }
  return (float)bi * (float)SR / (float)N_GLOBAL;
}

/* ---- harmonics ---------------------------------------------------------------- */
static unsigned detect_harmonics(float f0, float max_mag, float *step, float *variation) {
  const float df = (float)SR / (float)N_GLOBAL;
  unsigned band0, band1, np = 0u, nw = 0u, distance, n = 0u, max_idx;
  float med, prominence_req;
  bool no_peaks;
  if (f0 <= 0.0f || max_mag <= 0.0f) { *step = 0.0f; *variation = 1.0f; return 0u; }
  band0 = (unsigned)ceilf((f0 * 0.7f) / df); band1 = (unsigned)floorf(12000.0f / df);
  if (band1 >= GLOBAL_BINS) band1 = GLOBAL_BINS - 1u;
  med = exact_median_normalized(g_mag, band0, band1 + 1u, max_mag);
  prominence_req = fmaxf(0.015f, med * 4.0f);
  for (unsigned i = band0 + 1u; i < band1;) {
    if (g_mag[i - 1u] < g_mag[i]) {
      unsigned j = i + 1u;
      while (j <= band1 && g_mag[j] == g_mag[i]) j++;
      if (j <= band1 && g_mag[j] < g_mag[i] && np < MAX_PEAKS) g_peaks[np++] = (uint16_t)((i + j - 1u) / 2u);
      i = j;
    } else i++;
  }
  memset(g_peak_state, 0, GLOBAL_BINS);
  qsort(g_peaks, np, sizeof(uint16_t), cmp_peak_height_desc);
  distance = (unsigned)fmaxf(1.0f, floorf((f0 / df) * 0.45f));
  for (unsigned j = 0u; j < np; j++) {
    int p = g_peaks[j], lo, hi;
    if (g_peak_state[p]) continue;
    g_peak_state[p] = 2u;
    lo = p - (int)distance + 1; hi = p + (int)distance - 1;
    if (lo < (int)band0) lo = (int)band0;
    if (hi > (int)band1) hi = (int)band1;
    for (int q = lo; q <= hi; q++) if (q != p && g_peak_state[q] == 0u) g_peak_state[q] = 1u;
  }
  np = 0u;
  for (unsigned p = band0 + 1u; p < band1; p++) if (g_peak_state[p] == 2u) g_peaks[np++] = (uint16_t)p;
  for (unsigned j = 0u; j < np; j++) {
    int p = g_peaks[j], q = p;
    float peak = g_mag[p] / max_mag, left_min = peak, right_min = peak, prom;
    while (q > (int)band0) { float v; q--; v = g_mag[q] / max_mag; if (v > peak) break; if (v < left_min) left_min = v; }
    q = p;
    while (q < (int)band1) { float v; q++; v = g_mag[q] / max_mag; if (v > peak) break; if (v < right_min) right_min = v; }
    prom = peak - fmaxf(left_min, right_min);
    if (prom >= prominence_req) g_peaks[nw++] = (uint16_t)p;
  }
  np = nw;
  no_peaks = (np == 0u);
  max_idx = (unsigned)floorf(12000.0f / f0);
  for (unsigned hi = 1u; hi <= max_idx && n < MAX_HARMONICS; hi++) {
    float target = (float)hi * f0, tol = fmaxf(5.0f, f0 * 0.08f), bm = -1.0f;
    int best = -1;
    for (unsigned j = 0u; j < np; j++) {
      float pf = (float)g_peaks[j] * df;
      if (fabsf(pf - target) <= tol && g_mag[g_peaks[j]] > bm) { bm = g_mag[g_peaks[j]]; best = g_peaks[j]; }
    }
    if (best >= 0) g_harmonics[n++] = (float)best * df;
  }
  if (no_peaks && n == 0u) { g_harmonics[0] = f0; n = 1u; }
  if (n >= 2u) {
    float dif[MAX_HARMONICS], tmp[MAX_HARMONICS];
    for (unsigned i = 1u; i < n; i++) dif[i - 1u] = g_harmonics[i] - g_harmonics[i - 1u];
    memcpy(tmp, dif, (n - 1u) * sizeof(float));
    *step = median_small(tmp, n - 1u);
    if (n >= 3u) {
      float ss = 0.0f, sx = 0.0f, mean, v;
      for (unsigned i = 0u; i < n - 1u; i++) { sx += dif[i]; ss += dif[i] * dif[i]; }
      mean = sx / (float)(n - 1u); v = ss / (float)(n - 1u) - mean * mean;
      if (v < 0.0f) v = 0.0f;
      *variation = clamp01(sqrtf(v) / f0);
    } else *variation = 0.0f;
  } else { *step = f0; *variation = 0.0f; }
  return n;
}

static void global_features(float max_mag, float *noise_floor, float *high_band, float *roughness) {
  float df = (float)SR / (float)N_GLOBAL, local_max = 0.0f;
  unsigned n0, r0, r1, c = 0u;
  acc_t total = {0.0f, 0.0f, 0u}, band = {0.0f, 0.0f, 0u}, acc = {0.0f, 0.0f, 0u};
  if (max_mag <= 0.0f) { *noise_floor = *high_band = *roughness = 0.0f; return; }
  n0 = (unsigned)ceilf(3000.0f / df);
  *noise_floor = exact_median_normalized(g_mag, n0, GLOBAL_BINS, max_mag);
  for (unsigned i = 1u; i < GLOBAL_BINS; i++) {
    float f = (float)i * df, p = g_mag[i] * g_mag[i];
    if (f > 20.0f) acc_add(&total, p);
    if (f >= 6000.0f && f <= 10000.0f) acc_add(&band, p);
  }
  *high_band = acc_get(&total) > 1e-20f ? clamp01(acc_get(&band) / acc_get(&total)) : 0.0f;
  r0 = (unsigned)ceilf(50.0f / df); r1 = (unsigned)floorf(10000.0f / df);
  for (unsigned i = r0; i <= r1; i++) if (g_mag[i] > local_max) local_max = g_mag[i];
  if (local_max > 0.0f) {
    for (unsigned i = r0 + 1u; i <= r1; i++) { acc_add(&acc, fabsf(g_mag[i] / local_max - g_mag[i - 1u] / local_max)); c++; }
  }
  *roughness = c ? clamp01((acc_get(&acc) / (float)c) * 35.0f) : 0.0f;
}

/* ---- STFT + MFCC ---------------------------------------------------------------- */
static void stft_and_mfcc(const sig_t *s, float *zcr_frame_mean, float *centroid_mean, float *flatness_mean,
                          float *bandwidth_mean, float mfcc_mean[N_MFCC], float mfcc_std[N_MFCC]) {
  zs_complex_t *frame = g_work, *scratch = g_work + STFT_N;
  float zsum = 0.0f, csum = 0.0f, fsum = 0.0f, bsum = 0.0f, max_mel = 0.0f, floor_db;
  float sum[N_MFCC] = {0}, sumsq[N_MFCC] = {0};
  for (unsigned fr = 0u; fr < STFT_FRAMES; fr++) {
    int start = (int)(fr * STFT_HOP) - (int)(STFT_N / 2u);
    unsigned zc = 0u;
    float prev = sample_edge(s, start), centroid;
    acc_t sum_mag = {0.0f, 0.0f, 0u}, sum_fm = {0.0f, 0.0f, 0u}, logp = {0.0f, 0.0f, 0u}, sump = {0.0f, 0.0f, 0u}, bwv = {0.0f, 0.0f, 0u};
    float geo, arith;
    for (unsigned i = 1u; i < STFT_N; i++) { float cur = sample_edge(s, start + (int)i); if ((cur >= 0.0f) != (prev >= 0.0f)) zc++; prev = cur; }
    zsum += (float)zc / (float)STFT_N;
    for (unsigned i = 0u; i < STFT_N; i++) { frame[i].re = sample_norm(s, start + (int)i) * g_stft_window[i]; frame[i].im = 0.0f; }
    if (!zs_fft_mixed_complex(frame, scratch, STFT_N)) continue;
    /* magnitudes reused below: keep them in the scratch half as floats */
    {
      float *m = (float *)(void *)scratch;
      for (unsigned k = 0u; k < STFT_BINS; k++) {
        float mag = sqrtf(frame[k].re * frame[k].re + frame[k].im * frame[k].im), f = (float)k * (float)SR / (float)STFT_N, p = mag * mag + 1e-10f;
        m[k] = mag;
        acc_add(&sum_mag, mag); acc_add(&sum_fm, f * mag); acc_add(&logp, logf(p)); acc_add(&sump, p);
      }
      centroid = acc_get(&sum_mag) > 1e-20f ? acc_get(&sum_fm) / acc_get(&sum_mag) : 0.0f;
      csum += centroid;
      if (acc_get(&sum_mag) > 1e-20f) {
        float inv = 1.0f / acc_get(&sum_mag);
        for (unsigned k = 0u; k < STFT_BINS; k++) { float d = (float)k * (float)SR / (float)STFT_N - centroid; acc_add(&bwv, m[k] * inv * d * d); }
      }
      bsum += sqrtf(fmaxf(0.0f, acc_get(&bwv)));
      geo = expf(acc_get(&logp) / (float)STFT_BINS); arith = acc_get(&sump) / (float)STFT_BINS;
      fsum += (arith > 0.0f) ? geo / arith : 0.0f;
      for (unsigned mel = 0u; mel < N_MELS; mel++) {
        float left = g_mel_edges[mel], center = g_mel_edges[mel + 1u], right = g_mel_edges[mel + 2u];
        float norm = 2.0f / fmaxf(right - left, 1e-12f);
        acc_t e = {0.0f, 0.0f, 0u};
        unsigned k0 = (unsigned)fmaxf(0.0f, floorf(left * (float)STFT_N / (float)SR));
        unsigned k2 = (unsigned)fminf((float)(STFT_BINS - 1u), ceilf(right * (float)STFT_N / (float)SR));
        for (unsigned k = k0; k <= k2; k++) {
          float f = (float)k * (float)SR / (float)STFT_N, w = 0.0f;
          if (f >= left && f < center) w = (f - left) / fmaxf(center - left, 1e-12f);
          else if (f >= center && f <= right) w = (right - f) / fmaxf(right - center, 1e-12f);
          acc_add(&e, m[k] * m[k] * w * norm);
        }
        g_mel[fr][mel] = acc_get(&e);
        if (g_mel[fr][mel] > max_mel) max_mel = g_mel[fr][mel];
      }
    }
  }
  *zcr_frame_mean = zsum / (float)STFT_FRAMES;
  *centroid_mean = csum / (float)STFT_FRAMES;
  *flatness_mean = fsum / (float)STFT_FRAMES;
  *bandwidth_mean = bsum / (float)STFT_FRAMES;
  floor_db = 10.0f * log10f(fmaxf(max_mel, 1e-10f)) - 80.0f;
  for (unsigned fr = 0u; fr < STFT_FRAMES; fr++) {
    float db[N_MELS];
    for (unsigned mel = 0u; mel < N_MELS; mel++) { float v = 10.0f * log10f(fmaxf(g_mel[fr][mel], 1e-10f)); if (v < floor_db) v = floor_db; db[mel] = v; }
    for (unsigned k = 0u; k < N_MFCC; k++) {
      float coef = 0.0f;
      for (unsigned mel = 0u; mel < N_MELS; mel++) coef += db[mel] * g_dct[k][mel];
      sum[k] += coef; sumsq[k] += coef * coef;
    }
  }
  for (unsigned k = 0u; k < N_MFCC; k++) {
    float mean = sum[k] / (float)STFT_FRAMES, v = sumsq[k] / (float)STFT_FRAMES - mean * mean;
    if (v < 0.0f) v = 0.0f;
    mfcc_mean[k] = mean; mfcc_std[k] = sqrtf(v);
  }
}

/* ---- public ---------------------------------------------------------------------- */
void zs_dsp_mcu_init(zs_dsp_ctx_t *ctx) {
  if (ctx) memset(ctx, 0, sizeof(*ctx));
  build_tables();
}

zs_complex_t *zs_dsp_mcu_borrow_work(size_t *complex_count) {
  if (complex_count) *complex_count = WORK_COMPLEX;
  return g_work;
}

size_t zs_dsp_mcu_scratch_bytes(void) {
  return sizeof(g_work) + sizeof(g_magbuf) + sizeof(g_yin) + sizeof(g_f0) + sizeof(g_harmonics) + sizeof(g_stft_window) + sizeof(g_dct) + sizeof(g_mel_edges);
}

bool zs_dsp_mcu_extract_1s(zs_dsp_ctx_t *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) {
  sig_t s;
  float energy, rms, zcr_global, max_mag, f0, f0var, hstep, hvar, noise, high, rough;
  float zcr_frames, centroid, flatness, bandwidth, mmean[N_MFCC], mstd[N_MFCC];
  float f0_stability, spacing_stability, hpresence, hstab;
  unsigned hcount;
  if (!ctx || !pcm || !out || n != NSAMP) return false;
  build_tables();
  memset(out, 0, ZS_FEATURE_COUNT * sizeof(float));
  s.pcm = pcm; s.dc = 0.0f; s.scale = 1.0f;
  preprocess_stats(&s, &energy, &rms, &zcr_global);
  ctx->last_dc = s.dc;
  ctx->last_peak = s.scale > 0.0f ? 1.0f / s.scale : 0.0f;
  if (!global_spectrum(&s, &max_mag)) return false;      /* g_mag valid from here; g_work free */
  estimate_f0_track(&s, &f0, &f0var);                    /* uses g_work */
  if (f0 <= 0.0f) f0 = spectral_f0_fallback(max_mag);
  hcount = detect_harmonics(f0, max_mag, &hstep, &hvar); /* peaks/state in g_tail, median tmp in g_work */
  global_features(max_mag, &noise, &high, &rough);
  stft_and_mfcc(&s, &zcr_frames, &centroid, &flatness, &bandwidth, mmean, mstd); /* mel in g_tail, frames in g_work */
  f0_stability = 1.0f - f0var; spacing_stability = 1.0f - hvar;
  hpresence = clamp01((float)hcount / 24.0f);
  if (hpresence < 0.15f) hpresence = 0.15f;
  hstab = f0 > 0.0f ? clamp01(0.45f * f0_stability + 0.35f * spacing_stability + 0.20f * hpresence) : 0.0f;
  out[0] = f0; out[1] = (float)hcount; out[2] = hstep; out[3] = hstab; out[4] = energy; out[5] = rms;
  out[6] = zcr_frames; out[7] = centroid; out[8] = flatness; out[9] = bandwidth; out[10] = noise; out[11] = high;
  out[12] = f0var; out[13] = hvar; out[14] = clamp01(f0var * 4.0f); out[15] = rough; out[16] = clamp01(1.0f - f0var * 5.0f);
  for (unsigned k = 0u; k < N_MFCC; k++) { out[17u + k] = mmean[k]; out[30u + k] = mstd[k]; }
  ctx->windows_processed++;
  (void)zcr_global;
  return true;
}

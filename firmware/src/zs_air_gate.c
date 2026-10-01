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
#define ZS_AIR_TWO_PI 6.28318530717958647692f /* strict C11 on the target has no M_PI */
/* station-only plausibility of an *airborne* propulsion comb (server has none): a ground engine idles below
   30 Hz (APC at 15 Hz on the Muhoed recording), cicadas chorus at 500+ Hz; UAV props/engines sit in between */
#define AIR_F0_MIN_HZ 30.0f
#define AIR_F0_MAX_HZ 300.0f
/* several sources (header): two combs are one source when their fundamentals are in a ratio m/n (m, n <= 6) within
   0.5 % (the comb fit over many teeth refines to about 0.1 Hz, 0.1 % at 120 Hz; two engines drift through such a
   ratio with the Doppler shift only for moments); a further comb counts when it carries a twentieth of the main
   comb's power */
#define RATIO_TOL 0.005f
#define SECONDARY_MIN_POWER 0.05f
#define SECONDARY_F0_MIN_HZ 30.0f
#define SECONDARY_F0_MAX_HZ 600.0f
#define SMEAR 0.04f              /* relative smear of a line on the average (notch half-width) */
#define MAIN_SWITCH 1.25f        /* another source becomes the main one when its comb is 1 dB stronger */
#define SAME_SOURCE 0.06f        /* combs this close are one smeared source */
#define SOURCES_STABLE 3u        /* a comb is a source from this score on... */
#define SOURCES_SCORE_MAX 6u     /* ...(score capped: a source gone stops counting within 4 fits) */
#define SOURCES_DRIFT 0.04f      /* a comb is found again within 4 % of the fit before */
#define SUPPRESS_RHO 0.9f        /* comb notch: -3 dB width (1 - rho) / pi * f0, i.e. 3.8 Hz at 120 Hz, gain ~1 between */
#define SUPPRESS_MAX_DELAY 1100u /* 32000 / SECONDARY_F0_MIN_HZ + 2 */

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

/* Line prominence: peak power over the mean of ±32 Hz around it (±2.5 Hz guarded); a tooth is "real" at >= 2 (3 dB). */
static float prominence_at(const float *p, unsigned bin) {
  const unsigned half = (unsigned)(32.0f / BIN_HZ), guard = (unsigned)(2.5f / BIN_HZ);
  unsigned lo = bin > half ? bin - half : 0u, hi = bin + half < BINS ? bin + half : BINS - 1u;
  double local = 0.0; unsigned n_local = 0u;
  for (unsigned j = lo; j <= hi; j++) { if (j + guard >= bin && j <= bin + guard) continue; local += p[j]; n_local++; }
  const float lf = n_local ? (float)(local / n_local) : 1e-30f;
  return p[bin] / (lf > 1e-30f ? lf : 1e-30f);
}
static bool tooth_prominent(const float *p, float target, float tol) {
  unsigned at = 0u;
  return peak_near(p, target, tol, &at) > 0.0f && prominence_at(p, at) >= 2.0f;
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
    float w = 0.5f - 0.5f * cosf(ZS_AIR_TWO_PI * (float)m / (float)DEC_SAMPLES);
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

/* best comb power within +-span of f0, BIN/4 steps */
static float refine_f0(const float *p, float f0, float span) {
  float best = f0, bpw = -1.0f;
  for (float g = f0 * (1.0f - span); g < f0 * (1.0f + span); g += BIN_HZ * 0.25f) { if (g < F0_MIN_HZ) continue; float pw = comb_power_at(p, g); if (pw > bpw) { bpw = pw; best = g; } }
  return best;
}

/* real teeth among the first six harmonics of f0 */
static unsigned teeth_of(const float *p, float floor8, float f0) {
  const float tol = fmaxf(1.5f * BIN_HZ, f0 * 0.04f);
  unsigned teeth = 0u;
  for (unsigned h = 1u; h <= 6u; h++) {
    const float t = f0 * (float)h;
    if (t > BAND_HIGH_HZ) break;
    if (peak_near(p, t, tol, NULL) >= floor8 && tooth_prominent(p, t, tol)) teeth++;
  }
  return teeth;
}

/* the strongest line's own source: the lowest fundamental dominant / k (k <= 6) whose first six harmonics are
   nearly all real lines (five of six: the fundamental itself may be weak).  The common sub-harmonic of two sources
   misses most of its teeth; the strongest line itself when nothing lower is complete. */
static float own_comb(const float *p, float floor_log, float dominant) {
  const float floor8 = expf(floor_log) * 6.3096f;
  float best = dominant;
  for (unsigned k = 2u; k <= 6u; k++) {
    const float cand = dominant / (float)k;
    if (cand < F0_MIN_HZ) break;
    if (teeth_of(p, floor8, refine_f0(p, cand, 0.02f)) >= 5u) best = cand;
  }
  return refine_f0(p, best, 0.05f);
}

/* a / b near m / n with m, n <= 6: one harmonic family */
static bool small_ratio(float a, float b) {
  if (a <= 0.0f || b <= 0.0f) return true;
  const float r = a / b;
  for (unsigned n = 1u; n <= 6u; n++)
    for (unsigned m = 1u; m <= 6u; m++) { const float q = (float)m / (float)n; if (fabsf(r - q) <= RATIO_TOL * q) return true; }
  return false;
}

/* a / b near k or 1 / k with k <= 6 within a relative `tol`: one comb is a harmonic of the other.  With the wide
   SAME_SOURCE tolerance this also catches what the notch left of a known comb whose lines were smeared wider (a
   leftover at 2.07 times a comb is that comb's second harmonic).  Once the strongest line's own comb is known
   (own_comb: the common sub-harmonic misses its teeth), a comb in a ratio like 3 / 2 to it is another source. */
static bool harmonic_ratio(float a, float b, float tol) {
  if (a <= 0.0f || b <= 0.0f) return true;
  const float r = a > b ? a / b : b / a;
  for (unsigned k = 1u; k <= 6u; k++) if (fabsf(r - (float)k) <= tol * (float)k) return true;
  return false;
}

/* removes the teeth of a comb (every harmonic, wider than the fit tolerance and in proportion to the harmonic: on
   the 4 s average a Doppler-shifted line is smeared by a few percent of its frequency) */
static void notch_comb(float *p, float f0, float fill) {
  for (unsigned k = 1u; k <= 64u; k++) {
    const float t = f0 * (float)k, tol = fmaxf(fmaxf(2.0f * BIN_HZ, 0.05f * f0), SMEAR * t);
    if (t - tol > BAND_HIGH_HZ) break;
    int lo = (int)floorf((t - tol) / BIN_HZ), hi = (int)ceilf((t + tol) / BIN_HZ);
    for (int i = lo < 0 ? 0 : lo; i <= hi && i < (int)BINS; i++) p[i] = fill;
  }
}

/* a tooth position lies wholly in a removed band: unknown, neither present nor missing */
static bool removed_at(const float *p, float t, float tol, float fill) {
  int lo = (int)floorf((t - tol) / BIN_HZ), hi = (int)ceilf((t + tol) / BIN_HZ);
  if (lo < 0) lo = 0;
  if (hi >= (int)BINS) hi = (int)BINS - 1;
  for (int i = lo; i <= hi; i++) if (p[i] != fill) return false;
  return true;
}

/* real teeth among the first six harmonics of a comb in a spectrum with removed bands; *known: positions not removed */
static unsigned residual_teeth(const float *p, float floor8, float fill, float f0, unsigned *known, unsigned *low) {
  const float tol = fmaxf(1.5f * BIN_HZ, f0 * 0.04f);
  unsigned teeth = 0u;
  *known = 0u; if (low) *low = 0u;
  for (unsigned h = 1u; h <= 6u; h++) {
    const float t = f0 * (float)h;
    if (t > BAND_HIGH_HZ) break;
    if (removed_at(p, t, tol, fill)) continue;
    (*known)++;
    if (peak_near(p, t, tol, NULL) >= floor8 && tooth_prominent(p, t, tol)) { teeth++; if (low && h <= 2u) (*low)++; }
  }
  return teeth;
}

/* the strongest comb left in a spectrum whose known combs were removed (0: none): its most prominent line, that
   line's own comb or a lower fundamental whose teeth are real lines, refined.  Tooth positions inside removed bands
   (where another source's teeth were) count neither way; of the rest at least three must be real and at most one
   missing. */
static float residual_comb(const float *p, float floor_log, unsigned *line_bin) {
  const float fill = expf(floor_log), floor8 = fill * 6.3096f;
  unsigned dom = B_LO; float best_prom = -1.0f;
  for (unsigned i = B_LO; i <= B_HI; i++) {
    if (p[i] < fill || p[i] == fill) continue;
    const float prom = prominence_at(p, i);
    if (prom > best_prom) { best_prom = prom; dom = i; }
  }
  *line_bin = 0u;
  if (best_prom < 2.0f) return 0.0f;
  *line_bin = dom;
  const float dominant = (float)dom * BIN_HZ;
  float best = 0.0f, best_pw = -1.0f;
  for (unsigned k = 1u; k <= 6u; k++) {
    const float cand = dominant / (float)k;
    if (cand < SECONDARY_F0_MIN_HZ) break;
    if (cand > SECONDARY_F0_MAX_HZ) continue;
    unsigned known = 0u, low = 0u;
    const unsigned teeth = residual_teeth(p, floor8, fill, cand, &known, &low);
    if (teeth < 3u || teeth + 1u < known || (k > 1u && low < 1u)) continue;
    const float pw = comb_power_at(p, cand);
    if (pw > best_pw) { best_pw = pw; best = cand; }
  }
  if (best <= 0.0f) return 0.0f;
  best = refine_f0(p, best, 0.05f);
  unsigned known = 0u;
  const unsigned teeth = residual_teeth(p, floor8, fill, best, &known, NULL);
  return teeth >= 3u && teeth + 1u >= known ? best : 0.0f;
}

/* the comb near f0 is in this window too: three real teeth among its first five (refined +-5 % on the window).  Two
   sources sound in every window; a single source gliding in pitch smears the average into what looks like two
   combs, but any one window holds one of them only. */
static bool comb_in_window(const float *win, float win_floor_log, float f0) {
  const float floor8 = expf(win_floor_log) * 6.3096f, f = refine_f0(win, f0, 0.05f), tol = fmaxf(1.5f * BIN_HZ, f * 0.04f);
  unsigned teeth = 0u;
  for (unsigned h = 1u; h <= 5u; h++) {
    const float t = f * (float)h;
    if (t > BAND_HIGH_HZ) break;
    if (peak_near(win, t, tol, NULL) >= floor8 && tooth_prominent(win, t, tol)) teeth++;
  }
  return teeth >= 3u;
}

static float strongest_tooth(const float *p, float f0, unsigned fallback_bin) {
  const float tol = fmaxf(1.5f * BIN_HZ, f0 * 0.06f);
  float apw = -1.0f; unsigned abin = fallback_bin;
  for (unsigned k = 1u; k <= MAX_HARMONICS; k++) { float t = f0 * (float)k; if (t > BAND_HIGH_HZ) break; unsigned at = 0u; float pk = peak_near(p, t, tol, &at); if (pk > apw) { apw = pk; abin = at; } }
  return (float)abin * BIN_HZ;
}

/* Combs left in `work` (the known ones, `combs[0..*n)`, removed already), line by line from the most prominent: every
   comb found is removed in turn - a leftover of a known comb (its line drifted wider than the notch), one of its
   harmonic family, a weak one or one missing from the current window - and only a strong comb of another source that
   sounds in this window is added; a line that leads to no comb (or to one too cut up by the removed bands to tell)
   is removed alone and the next line tried.  `own`: combs[0] is the strongest line's own comb, so only integer
   ratios to it are its family. */
static void collect_sources(const float *p, float *work, float fill, float floor_log, const float *win, float win_floor_log,
                            float *combs, unsigned *n, unsigned max, bool own) {
  for (unsigned iter = 0u; iter < 8u && *n < max; iter++) {
    unsigned line = 0u;
    const float c = residual_comb(work, floor_log, &line);
    if (line == 0u) break;                                   /* nothing line-like left */
    if (c <= 0.0f) {                                         /* a line of no comb (or of one too cut up to tell): */
      const int lo = (int)line - 2, hi = (int)line + 2;      /* removed alone, the next line may lead to one */
      for (int i = lo < 0 ? 0 : lo; i <= hi && i < (int)BINS; i++) work[i] = fill;
      continue;
    }
    notch_comb(work, c, fill);
    bool related = false;
    float strongest = 0.0f;
    for (unsigned i = 0u; i < *n; i++) {
      related = related || harmonic_ratio(combs[i], c, SAME_SOURCE) || (!own && small_ratio(combs[i], c));
      strongest = fmaxf(strongest, comb_power_at(p, combs[i]));
    }
    if (related || comb_power_at(p, c) < SECONDARY_MIN_POWER * strongest || !comb_in_window(win, win_floor_log, c)) continue;
    combs[(*n)++] = c;
  }
}

/* -1 for every tracked comb this fit did not find (seen == NULL: none was found); a track at 0 is forgotten */
static void decay_sources(zs_air_gate_t *g, const bool *seen) {
  unsigned count = g->source_count < ZS_AIR_SOURCE_TRACKS ? g->source_count : ZS_AIR_SOURCE_TRACKS;
  for (unsigned j = 0u; j < count; j++) if ((!seen || !seen[j]) && g->source_score[j]) g->source_score[j]--;
  for (unsigned j = 0u; j < count;) {
    if (g->source_score[j]) { j++; continue; }
    count--;
    g->source_hz[j] = g->source_hz[count]; g->source_score[j] = g->source_score[count];
  }
  g->source_count = (uint8_t)count;
}

/* Several sources (header): the main comb and up to ZS_AIR_MAX_SECONDARY other combs.  `best_f0` is the single-comb
   fit; when it is a sub-harmonic of the strongest line it may be the common sub-harmonic of two sources: then the
   strongest line's own comb is removed and the rest searched; another source found there means a mixture, and the
   strongest comb becomes the gate's line. */
static void separate_sources(const float *p, float *work, float floor_log, float dominant, const float *win, float win_floor_log,
                             float *best_f0, zs_air_gate_t *g) {
  const float fill = expf(floor_log);
  float combs[2u + ZS_AIR_MAX_SECONDARY];
  unsigned n = 0u;
  bool mixture = false;                                      /* this fit shows a mixture: new sources may start */
  /* the fit took a sub-harmonic of the strongest line, and not that line's own fundamental (a complete comb, five of
     six teeth real): maybe the common sub-harmonic of two sources */
  const float own = *best_f0 < dominant * 0.9f ? own_comb(p, floor_log, dominant) : 0.0f;
  const bool sub = own > *best_f0 * (1.0f + SAME_SOURCE);
  if (sub) {
    combs[n++] = own;
    memcpy(work, p, BINS * sizeof(float));
    notch_comb(work, combs[0], fill);
    collect_sources(p, work, fill, floor_log, win, win_floor_log, combs, &n, 1u + ZS_AIR_MAX_SECONDARY, true);
    if (n < 2u || !comb_in_window(win, win_floor_log, combs[0])) n = 0u;   /* one source after all: its fit stands */
    mixture = n >= 2u;
  }
  if (n == 0u) {
    combs[n++] = *best_f0;
    memcpy(work, p, BINS * sizeof(float));
    notch_comb(work, combs[0], fill);
    collect_sources(p, work, fill, floor_log, win, win_floor_log, combs, &n, 1u + ZS_AIR_MAX_SECONDARY + (sub ? 1u : 0u), false);
    if (sub && n >= 3u) {                                    /* two unrelated sources under the sub-harmonic: a mixture */
      for (unsigned i = 1u; i < n; i++) combs[i - 1u] = combs[i];
      n--;
      mixture = true;
    } else if (n > 1u + ZS_AIR_MAX_SECONDARY) n = 1u + ZS_AIR_MAX_SECONDARY;
  }
  unsigned main = 0u;                                        /* the strongest comb is the gate's line */
  for (unsigned i = 1u; i < n; i++) if (comb_power_at(p, combs[i]) > comb_power_at(p, combs[main])) main = i;
  if (main != 0u) { const float t = combs[0]; combs[0] = combs[main]; combs[main] = t; main = 0u; }
  /* every comb found scores (header); the sources are the combs that score, unrelated to a stronger one.  A comb
     beside the main one starts a track only in a fit that shows a mixture (the common sub-harmonic of two sources):
     an engine's own further combs (firing order, gearing) never do, while a source once started is kept up by any fit
     that finds it */
  bool seen[ZS_AIR_SOURCE_TRACKS] = {false};
  for (unsigned i = 0u; i < n; i++) {
    unsigned j = 0u;
    while (j < g->source_count && fabsf(combs[i] - g->source_hz[j]) > SOURCES_DRIFT * combs[i]) j++;
    if (j == g->source_count && i > 0u && !mixture) continue;   /* another comb starts a source only in a mixture */
    if (j == g->source_count) {                              /* a new comb: a free track or the weakest one */
      if (g->source_count < ZS_AIR_SOURCE_TRACKS) j = g->source_count++;
      else { j = 0u; for (unsigned k = 1u; k < ZS_AIR_SOURCE_TRACKS; k++) if (g->source_score[k] < g->source_score[j]) j = k; }
      g->source_score[j] = 0u;
    }
    if (!seen[j]) { g->source_hz[j] = combs[i]; g->source_score[j] = (uint8_t)(g->source_score[j] < SOURCES_SCORE_MAX ? g->source_score[j] + 1u : SOURCES_SCORE_MAX); seen[j] = true; }
  }
  decay_sources(g, seen);
  /* a scoring comb below two scoring, mutually unrelated combs of its own family is their common sub-harmonic (the
     single-comb fit of the windows the mixture was not separated in), not a source */
  bool common[ZS_AIR_SOURCE_TRACKS] = {false};
  for (unsigned j = 0u; j < g->source_count; j++) {
    if (g->source_score[j] < SOURCES_STABLE) continue;
    for (unsigned a = 0u; a < g->source_count && !common[j]; a++)
      for (unsigned b = a + 1u; b < g->source_count && !common[j]; b++) {
        if (a == j || b == j || g->source_score[a] < SOURCES_STABLE || g->source_score[b] < SOURCES_STABLE) continue;
        const float hj = g->source_hz[j], ha = g->source_hz[a], hb = g->source_hz[b];
        common[j] = hj < 0.9f * ha && hj < 0.9f * hb && small_ratio(ha, hj) && small_ratio(hb, hj) && !harmonic_ratio(ha, hb, SAME_SOURCE);
      }
  }
  n = 0u;
  for (unsigned pick = 0u; pick < 1u + ZS_AIR_MAX_SECONDARY; pick++) {   /* the scoring combs, strongest first */
    int best = -1; float best_pw = -1.0f;
    for (unsigned j = 0u; j < g->source_count; j++) {
      if (g->source_score[j] < SOURCES_STABLE || common[j]) continue;
      bool related = false;
      for (unsigned i = 0u; i < n; i++) related = related || harmonic_ratio(combs[i], g->source_hz[j], SAME_SOURCE);
      const float pw = comb_power_at(p, g->source_hz[j]);
      if (!related && pw > best_pw) { best_pw = pw; best = (int)j; }
    }
    if (best < 0) break;
    combs[n++] = refine_f0(p, g->source_hz[best], SOURCES_DRIFT);
  }
  /* the main comb stays the one of the fit before while the other is not clearly (MAIN_SWITCH) stronger: two sources
     of about the same level would otherwise swap from fit to fit, and the window measurement and its median
     fundamental with them */
  for (unsigned i = 1u; i < n && g->main_hz > 0.0f; i++)
    if (fabsf(combs[i] - g->main_hz) <= SOURCES_DRIFT * g->main_hz && comb_power_at(p, combs[0]) < MAIN_SWITCH * comb_power_at(p, combs[i])) {
      const float t = combs[0]; combs[0] = combs[i]; combs[i] = t;
      break;
    }
  if (n > 1u) *best_f0 = combs[0];                           /* otherwise the single-comb fit stands */
  else n = 0u;
  g->main_hz = n > 1u ? combs[0] : 0.0f;
  g->secondary_count = 0u;
  for (unsigned i = 0u; i < n; i++) if (i != main && g->secondary_count < ZS_AIR_MAX_SECONDARY) g->secondary_f0_hz[g->secondary_count++] = combs[i];
  for (unsigned i = g->secondary_count; i < ZS_AIR_MAX_SECONDARY; i++) g->secondary_f0_hz[i] = 0.0f;
}

/* Comb fit on the averaged log spectrum (server DroneSeparator._fit_comb_fundamental on the median spectrum). */
static void fit_comb(const float *lp, float *p, float *work, const float *win, float win_floor_log, zs_air_gate_t *g) {
  float *f0_out = &g->f0_hz, *anchor_out = &g->anchor_hz;
  g->secondary_count = 0u;
  for (unsigned i = 0u; i < BINS; i++) p[i] = expf(lp[i]);
  const float floor_log = band_median_log(lp, B_LO, B_HI);
  /* anchor: the most prominent bin (power over the mean of ±32 Hz around it, ±2.5 Hz guarded) */
  unsigned dom = B_LO; float best_prom = -1.0f;
  for (unsigned i = B_LO; i <= B_HI; i++) {
    if (lp[i] < floor_log) continue;
    const float prom = prominence_at(p, i);
    if (prom > best_prom) { best_prom = prom; dom = i; }
  }
  *f0_out = 0.0f; *anchor_out = 0.0f;
  if (best_prom < 2.0f) { decay_sources(g, NULL); return; }   /* nothing line-like: < 3 dB over its surroundings */
  const float dominant = (float)dom * BIN_HZ;
  float best_f0 = dominant, best_pw = comb_power_at(p, dominant);
  const float floor8 = expf(floor_log) * 6.3096f;
  for (unsigned k = 2u; k <= 6u; k++) {
    float cand = dominant / (float)k;
    if (cand < F0_MIN_HZ) break;
    unsigned hits = 0u, low = 0u; float tol = fmaxf(1.5f * BIN_HZ, cand * 0.04f);
    for (unsigned h = 1u; h <= 4u; h++) {
      float t = cand * (float)h;
      if (t > BAND_HIGH_HZ) break;
      /* a tooth of the lower comb must be a real line: above the floor AND prominent against its surroundings
         (wind rumble is above the global floor everywhere below 40 Hz, which used to pull the fit to 12 Hz) */
      if (peak_near(p, t, tol, NULL) >= floor8 && tooth_prominent(p, t, tol)) { hits++; if (h <= 2u) low++; }
    }
    if (hits >= 3u && low >= 1u) {   /* a real lower fundamental shows its 1st or 2nd tooth, not only the dominant's neighbours */ float pw = comb_power_at(p, cand); if (pw > best_pw) { best_pw = pw; best_f0 = cand; } }
  }
  { float gbest = best_f0, gpw = -1.0f;
    for (float g = best_f0 * 0.95f; g < best_f0 * 1.05f; g += BIN_HZ * 0.25f) { if (g < F0_MIN_HZ) continue; float pw = comb_power_at(p, g); if (pw > gpw) { gpw = pw; gbest = g; } }
    best_f0 = gbest; }
  if (best_f0 > F0_MAX_HZ * 4.0f) { decay_sources(g, NULL); return; }   /* no plausible propulsion comb */
  separate_sources(p, work, floor_log, dominant, win, win_floor_log, &best_f0, g);
  /* strongest tooth of the fitted comb on the average = the line to track per window */
  *f0_out = best_f0; *anchor_out = strongest_tooth(p, best_f0, dom);
}

/* Per-window measurement at the fixed f0 (server _window_harmonic_snr / _count_harmonics with the
   half-order comparison, see the header). */
static void measure_window(const float *p, float f0_avg, float anchor_hz, float *lp, uint8_t *mask, float *noise_lp, zs_air_window_t *w) {
  memset(w, 0, sizeof(*w));
  if (f0_avg <= 0.0f) return;
  /* refine the fundamental on this window (±10 %, BIN/2 steps): a real propulsion line drifts with RPM and
     Doppler by several percent per second, which would misalign the high teeth of a fixed comb */
  float f0 = f0_avg, best_pw = -1.0f;
  for (float g = f0_avg * 0.9f; g <= f0_avg * 1.1f; g += BIN_HZ * 0.5f) { if (g < F0_MIN_HZ) continue; float pw = comb_power_at(p, g); if (pw > best_pw) { best_pw = pw; f0 = g; } }
  for (unsigned i = 0u; i < BINS; i++) { lp[i] = logf(p[i]); mask[i] = 0u; }
  const float floor6 = expf(band_median_log(lp, B_LO, B_HI)) * 3.981f;
  const float tol = fmaxf(1.5f * BIN_HZ, f0 * 0.06f);
  float peaks = 0.0f, half = 0.0f; unsigned np = 0u, nh = 0u;
  unsigned low_teeth = 0u;
  for (unsigned k = 1u; k <= MAX_HARMONICS; k++) {
    float t = f0 * (float)k;
    if (t > BAND_HIGH_HZ) break;
    int lo = (int)floorf((t - tol) / BIN_HZ), hi = (int)ceilf((t + tol) / BIN_HZ);
    for (int i = lo < 0 ? 0 : lo; i <= hi && i < (int)BINS; i++) mask[i] = 1u;
    float pk = peak_near(p, t, tol, NULL);
    if (pk > 0.0f) { peaks += pk; np++; if (pk >= floor6) w->harmonic_count++; if (k <= 4u && pk >= floor6 && tooth_prominent(p, t, tol)) low_teeth++; }
  }
  w->low_teeth = (uint8_t)low_teeth;
  for (unsigned k = 0u; k < MAX_HARMONICS; k++) { float t = f0 * ((float)k + 0.5f); if (t > BAND_HIGH_HZ) break; float pk = peak_near(p, t, tol, NULL); if (pk > 0.0f) { half += pk; nh++; } }
  w->integer_order_ratio = (peaks + half) > 0.0f ? peaks / (peaks + half) : 0.0f;
  const float level = np ? peaks / (float)np : 0.0f, between = nh ? half / (float)nh : 0.0f;
  w->contrast_db = (between > 1e-30f && level > 0.0f) ? 10.0f * log10f(level / between) : 0.0f;
  /* server _window_harmonic_snr: median of the band from 0.5 f0 with the harmonic bins excluded */
  {
    unsigned n_lo = (unsigned)fmaxf((float)B_LO, f0 * 0.5f / BIN_HZ), m = 0u;
    for (unsigned i = n_lo; i <= B_HI; i++) if (!mask[i]) noise_lp[m++] = lp[i];
    const float noise = m ? expf(band_median_log(noise_lp, 0u, m - 1u)) : 0.0f;
    w->snr_db = (noise > 1e-30f && level > 0.0f) ? 10.0f * log10f(level / noise) : 0.0f;
  }
  /* a propulsion comb is strong at the bottom: two real teeth among the first four (a bird trill at 1.5 kHz
     fitted as a 16th harmonic has nothing there, nor has an MP3-high-passed recording) */
  w->comb = w->snr_db >= PRESENT_SNR_DB && w->contrast_db >= PRESENT_CONTRAST_DB && w->harmonic_count >= 2u && low_teeth >= 2u;
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
      for (unsigned k = 2u; k <= 3u; k++) { float up = f0s[i] * (float)k; if (fabsf(up - ref) <= 0.10f * ref) { f0s[i] = up; break; } }
      mean += f0s[i];
    }
    memcpy(sorted, f0s, ncomb * sizeof(float));
    r.f0_hz = median_of(sorted, ncomb);   /* folded median of the comb windows: what the source actually runs at */
    mean /= (float)ncomb;
    float var = 0.0f; for (unsigned i = 0u; i < ncomb; i++) { float d = f0s[i] - mean; var += d * d; } var /= (float)ncomb;
    r.steadiness_cv = mean > 0.0f ? sqrtf(var) / mean : 1.0f;
  }
  const float order_ratio = ncomb ? median_of(ratios, ncomb) : 0.0f;
  float cv_max = STEADINESS_CV_MAX;
  if (r.median_contrast_db >= RELAX_CONTRAST_DB) cv_max = fminf(cv_max * 2.0f, 0.20f);   /* server caps at 0.25; a 30 %/s glide reaches 0.24 */
  for (unsigned m = 50u; m <= 60u; m += 10u)
    if (r.f0_hz > 0.0f && fabsf(r.f0_hz - (float)m) <= 2.0f && (r.steadiness_cv <= 0.02f || order_ratio >= 0.95f)) r.mains = true;
  const bool strong = r.persistence >= 0.6f && r.median_contrast_db >= STRONG_CONTRAST_DB;
  const unsigned min_h = strong ? 2u : MIN_HARMONICS;
  /* the comb must still be there now: without this the history keeps "present" for seconds after the source stopped */
  const zs_air_window_t *last = &g->hist[(g->next + ZS_AIR_HISTORY - 1u) % ZS_AIR_HISTORY];
  const zs_air_window_t *prev = &g->hist[(g->next + ZS_AIR_HISTORY - 2u) % ZS_AIR_HISTORY];
  const bool current = last->comb || (n >= 2u && prev->comb);
  const bool airborne = r.f0_hz >= AIR_F0_MIN_HZ && r.f0_hz <= AIR_F0_MAX_HZ;
  r.present = n >= 2u && ncomb >= 3u && current && airborne && r.persistence >= PERSISTENCE_MIN && r.median_contrast_db >= PRESENT_CONTRAST_DB && r.steadiness_cv <= cv_max && hmax >= min_h && !r.mains;
  float score = 0.40f * fminf(r.persistence / 0.6f, 1.0f) + 0.30f * fminf(fmaxf(r.median_contrast_db, 0.0f) / 10.0f, 1.0f) +
                0.20f * (1.0f - fminf(r.steadiness_cv / 0.1f, 1.0f)) + 0.10f * fminf((float)hmax / 8.0f, 1.0f);
  if (!r.present) score *= 0.5f;
  r.confidence_u8 = (uint8_t)(fminf(fmaxf(score, 0.0f), 1.0f) * 255.0f + 0.5f);
  /* other sources only beside a present source: without one the classifier gets the window as it is */
  r.secondary_count = r.present ? g->secondary_count : 0u;
  for (unsigned i = 0u; i < ZS_AIR_MAX_SECONDARY; i++) r.secondary_f0_hz[i] = i < r.secondary_count ? g->secondary_window_hz[i] : 0.0f;
  return r;
}

bool zs_air_gate_push(zs_air_gate_t *g, const int16_t *pcm, size_t n, zs_complex_t *scratch, zs_air_gate_result_t *out) {
  if (!g || !pcm || !scratch || n < ZS_AIR_WINDOW_SAMPLES || !out) { if (out) memset(out, 0, sizeof(*out)); return false; }
  /* per-window work areas (the window's power spectrum included) live in the scratch tail beyond the FFT,
     so the target overlays everything on DSP memory and the gate state keeps only the running average */
  float *spectrum = (float *)(void *)(scratch + ZS_AIR_FFT), *tmp_p = spectrum + BINS, *tmp_lp = tmp_p + BINS, *tmp_noise = tmp_lp + BINS;
  uint8_t *tmp_mask = (uint8_t *)(void *)(tmp_noise + BINS);
  if (!window_spectrum(pcm, scratch, spectrum)) { memset(out, 0, sizeof(*out)); return false; }
  /* running geometric mean over the history depth */
  const float alpha = 1.0f / (float)(g->count < ZS_AIR_HISTORY ? g->count + 1u : ZS_AIR_HISTORY);
  for (unsigned i = 0u; i < BINS; i++) { float l = logf(spectrum[i]); g->avg_log[i] += (l - g->avg_log[i]) * alpha; }
  for (unsigned i = 0u; i < BINS; i++) tmp_lp[i] = logf(spectrum[i]);
  fit_comb(g->avg_log, tmp_p, tmp_noise, spectrum, band_median_log(tmp_lp, B_LO, B_HI), g);
  for (unsigned i = 0u; i < g->secondary_count; i++) g->secondary_window_hz[i] = refine_f0(spectrum, g->secondary_f0_hz[i], 0.05f);
  zs_air_window_t w;
  measure_window(spectrum, g->f0_hz, g->anchor_hz, tmp_lp, tmp_mask, tmp_noise, &w);
  g->hist[g->next] = w;
  g->next = (uint8_t)((g->next + 1u) % ZS_AIR_HISTORY);
  if (g->count < ZS_AIR_HISTORY) g->count++;
  *out = zs_air_gate_evaluate(g);
  return true;
}

/* y[n] = x[n] - x[n - T] + rho y[n - T] with T = fs / f0 (linear fractional delay): zeros at every harmonic of f0,
   poles just inside them, so the response is flat between the notches.  y is written in place; x[n - T] comes from
   a ring of the last input samples. */
static int16_t suppress_x[SUPPRESS_MAX_DELAY];
static void comb_notch(int16_t *pcm, size_t n, float f0) {
  const float period = (float)ZS_AIR_SAMPLE_RATE / f0;
  const unsigned ti = (unsigned)period;
  const float fr = period - (float)ti;
  if (f0 < SECONDARY_F0_MIN_HZ || ti + 2u > SUPPRESS_MAX_DELAY) return;
  memset(suppress_x, 0, sizeof(suppress_x));
  for (size_t i = 0u; i < n; i++) {
    const float x = (float)pcm[i];
    float xd = 0.0f, yd = 0.0f;
    if (i >= (size_t)ti + 1u) {
      xd = (1.0f - fr) * (float)suppress_x[(i - ti) % SUPPRESS_MAX_DELAY] + fr * (float)suppress_x[(i - ti - 1u) % SUPPRESS_MAX_DELAY];
      yd = (1.0f - fr) * (float)pcm[i - ti] + fr * (float)pcm[i - ti - 1u];
    }
    suppress_x[i % SUPPRESS_MAX_DELAY] = pcm[i];
    float y = x - xd + SUPPRESS_RHO * yd;
    y = y > 32767.0f ? 32767.0f : (y < -32768.0f ? -32768.0f : y);
    pcm[i] = (int16_t)lrintf(y);
  }
}

void zs_air_gate_suppress_secondary(int16_t *pcm, size_t n, const zs_air_gate_result_t *r) {
  if (!pcm || !r) return;
  for (unsigned s = 0u; s < r->secondary_count && s < ZS_AIR_MAX_SECONDARY; s++) comb_notch(pcm, n, r->secondary_f0_hz[s]);
}

/*
 * A/B test: zs_dsp (host reference, double accumulations, recursive FFT) vs
 * zs_dsp_mcu on synthetic drone-like and background signals, judged with the
 * golden acceptance rule (median normalized error <= 3 %, p95 <= 5 %), with
 * absolute tolerances for the F0/harmonic features as in server/tools/golden.
 */
#include "zs_dsp.h"
#include "zs_dsp_mcu.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define N 32000u
static int16_t g_pcm[N];

static double urand(void) { return (double)rand() / RAND_MAX; }

/* kind 0: piston-engine harmonic series with slow F0 drift; 1: electric rotor + wind; 2: birds/insect background; 3: near silence + noise */
static void synth(unsigned kind, unsigned seed) {
  double phase = 0.0;
  srand(seed);
  for (unsigned i = 0u; i < N; i++) {
    double t = (double)i / 32000.0, v = 0.0;
    switch (kind) {
      case 0: {
        double f0 = 110.0 + 6.0 * sin(2.0 * M_PI * 0.4 * t) + 20.0 * urand() * 0.01;
        phase += 2.0 * M_PI * f0 / 32000.0;
        for (unsigned h = 1u; h <= 18u; h++) v += (1.0 / (double)h) * sin((double)h * phase + 0.3 * h);
        v = 0.35 * v + 0.03 * (urand() - 0.5);
        break;
      }
      case 1: {
        double f0 = 180.0 + 40.0 * sin(2.0 * M_PI * 1.3 * t);
        phase += 2.0 * M_PI * f0 / 32000.0;
        for (unsigned h = 1u; h <= 8u; h++) v += (h % 2 ? 0.5 : 0.2) / (double)h * sin((double)h * phase);
        v = 0.3 * v + 0.08 * (urand() - 0.5) * (1.0 + 0.5 * sin(2.0 * M_PI * 0.2 * t));
        break;
      }
      case 2: {
        double chirp = sin(2.0 * M_PI * (3000.0 + 2500.0 * sin(2.0 * M_PI * 3.0 * t)) * t);
        v = 0.15 * chirp * (sin(2.0 * M_PI * 7.0 * t) > 0.6 ? 1.0 : 0.05) + 0.06 * (urand() - 0.5);
        break;
      }
      default:
        v = 0.02 * (urand() - 0.5);
        break;
    }
    if (v > 0.98) v = 0.98;
    if (v < -0.98) v = -0.98;
    g_pcm[i] = (int16_t)(v * 20000.0);
  }
}

static const char *const names[ZS_FEATURE_COUNT] = {
  "fundamental_hz", "harmonic_count", "harmonic_step_hz", "harmonic_stability", "average_energy", "rms", "zero_crossing_rate",
  "spectral_centroid_hz", "spectral_flatness", "spectral_bandwidth_hz", "noise_floor", "high_band_energy", "fundamental_variation",
  "harmonic_variation", "frequency_modulation_index", "spectral_roughness", "doppler_stability",
  "mfcc_mean_0", "mfcc_mean_1", "mfcc_mean_2", "mfcc_mean_3", "mfcc_mean_4", "mfcc_mean_5", "mfcc_mean_6", "mfcc_mean_7", "mfcc_mean_8",
  "mfcc_mean_9", "mfcc_mean_10", "mfcc_mean_11", "mfcc_mean_12",
  "mfcc_std_0", "mfcc_std_1", "mfcc_std_2", "mfcc_std_3", "mfcc_std_4", "mfcc_std_5", "mfcc_std_6", "mfcc_std_7", "mfcc_std_8",
  "mfcc_std_9", "mfcc_std_10", "mfcc_std_11", "mfcc_std_12"};

/* Normalized error with the golden rule: relative to the reference magnitude, with a floor so
   near-zero features are judged on an absolute scale (Hz for F0/step, 1.0 for counts, 0.01 otherwise). */
static double norm_err(unsigned idx, double ref, double got) {
  double floor_abs = (idx == 0u || idx == 2u) ? 2.0 : (idx == 1u ? 1.0 : (idx >= 17u ? 1.0 : 0.01));
  double denom = fabs(ref) > floor_abs ? fabs(ref) : floor_abs;
  return fabs(got - ref) / denom;
}

static int cmp_double(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }

int main(void) {
  static double errs[16u * ZS_FEATURE_COUNT];
  unsigned ne = 0u;
  double worst = 0.0; unsigned worst_idx = 0u, worst_case = 0u;
  double t_ref = 0.0, t_mcu = 0.0;
  zs_dsp_ctx_t ref_ctx, mcu_ctx;
  zs_dsp_init(&ref_ctx);
  zs_dsp_mcu_init(&mcu_ctx);
  printf("zs_dsp_mcu scratch: %zu bytes\n", zs_dsp_mcu_scratch_bytes());
  for (unsigned c = 0u; c < 16u; c++) {
    float a[ZS_FEATURE_COUNT], b[ZS_FEATURE_COUNT];
    clock_t t0;
    synth(c % 4u, 100u + c);
    t0 = clock(); assert(zs_dsp_extract_1s(&ref_ctx, g_pcm, N, a)); t_ref += (double)(clock() - t0) / CLOCKS_PER_SEC;
    t0 = clock(); assert(zs_dsp_mcu_extract_1s(&mcu_ctx, g_pcm, N, b)); t_mcu += (double)(clock() - t0) / CLOCKS_PER_SEC;
    for (unsigned k = 0u; k < ZS_FEATURE_COUNT; k++) {
      double e = norm_err(k, a[k], b[k]);
      errs[ne++] = e;
      if (e > worst) { worst = e; worst_idx = k; worst_case = c; }
      assert(isfinite(b[k]));
    }
    if (c < 4u) printf("case %u: f0 %.2f/%.2f harmonics %.0f/%.0f step %.2f/%.2f centroid %.1f/%.1f mfcc0 %.3f/%.3f\n", c,
                       a[0], b[0], a[1], b[1], a[2], b[2], a[7], b[7], a[17], b[17]);
  }
  qsort(errs, ne, sizeof(double), cmp_double);
  {
    double median = errs[ne / 2u], p95 = errs[(ne * 95u) / 100u];
    printf("normalized error over %u values: median %.4f  p95 %.4f  max %.4f (%s, case %u)\n", ne, median, p95, worst, names[worst_idx], worst_case);
    printf("time per window: reference %.1f ms, mcu %.1f ms\n", 1000.0 * t_ref / 16.0, 1000.0 * t_mcu / 16.0);
    assert(median <= 0.03);
    assert(p95 <= 0.05);
  }
  printf("dsp_mcu A/B test passed\n");
  return 0;
}

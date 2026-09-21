#include "zs_fft_mixed.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* Double-precision reference with the same decimation structure (radix 4/5/2). */
typedef struct { double re, im; } cd_t;
static void ref_rec(cd_t *out, const double *in, unsigned offset, unsigned stride, unsigned n) {
  if (n == 1u) { out[0].re = in[offset]; out[0].im = 0.0; return; }
  unsigned r = (n % 4u == 0u) ? 4u : ((n % 5u == 0u) ? 5u : 2u), m = n / r;
  for (unsigned p = 0u; p < r; p++) ref_rec(out + p * m, in, offset + p * stride, stride * r, m);
  for (unsigned k = 0u; k < m; k++) {
    cd_t a[5], res[5];
    for (unsigned p = 0u; p < r; p++) {
      double th = -2.0 * M_PI * (double)(k * p) / (double)n;
      cd_t v = out[p * m + k];
      a[p].re = v.re * cos(th) - v.im * sin(th);
      a[p].im = v.re * sin(th) + v.im * cos(th);
    }
    for (unsigned q = 0u; q < r; q++) {
      double sr = 0.0, si = 0.0;
      for (unsigned p = 0u; p < r; p++) {
        double th = -2.0 * M_PI * (double)(q * p) / (double)r;
        sr += a[p].re * cos(th) - a[p].im * sin(th);
        si += a[p].re * sin(th) + a[p].im * cos(th);
      }
      res[q].re = sr; res[q].im = si;
    }
    for (unsigned q = 0u; q < r; q++) out[q * m + k] = res[q];
  }
}

#define N 32000u
static float g_signal[N];
static double g_signal_d[N];
static cd_t g_ref[N];
static zs_complex_t g_work[N / 2u];
static float g_mag[N];
static zs_complex_t g_c[8192], g_cs[8192];

static float sample_cb(const void *ctx, unsigned i) { return ((const float *)ctx)[i]; }

static void fill_signal(unsigned seed) {
  srand(seed);
  for (unsigned i = 0u; i < N; i++) {
    double t = (double)i / 32000.0;
    double v = 0.6 * sin(2.0 * M_PI * 137.5 * t) + 0.3 * sin(2.0 * M_PI * 275.0 * t + 0.3) + 0.15 * sin(2.0 * M_PI * 4123.0 * t)
             + 0.05 * ((double)rand() / RAND_MAX - 0.5);
    double w = 0.5 - 0.5 * cos(2.0 * M_PI * (double)i / (double)(N - 1u)); /* Hann, as the host global spectrum */
    g_signal_d[i] = v * w;
    g_signal[i] = (float)(v * w);
  }
}

static void test_real_32000(void) {
  float max_mag = 0.0f;
  double max_ref = 0.0, err_abs_max = 0.0, err_rel_sum = 0.0;
  unsigned rel_count = 0u;
  clock_t t0;
  fill_signal(1u);
  ref_rec(g_ref, g_signal_d, 0u, 1u, N);
  t0 = clock();
  assert(zs_fft_mixed_real_magnitude(sample_cb, g_signal, N, g_work, g_mag, &max_mag));
  printf("real 32000-point FFT: %.1f ms on host\n", 1000.0 * (double)(clock() - t0) / CLOCKS_PER_SEC);
  for (unsigned k = 0u; k <= N / 2u; k++) {
    double r = sqrt(g_ref[k].re * g_ref[k].re + g_ref[k].im * g_ref[k].im);
    if (r > max_ref) max_ref = r;
  }
  for (unsigned k = 0u; k <= N / 2u; k++) {
    double r = sqrt(g_ref[k].re * g_ref[k].re + g_ref[k].im * g_ref[k].im);
    double e = fabs((double)g_mag[k] - r);
    if (e > err_abs_max) err_abs_max = e;
    if (r > 1e-3 * max_ref) { err_rel_sum += e / r; rel_count++; }
  }
  printf("  max |err| = %.3e (%.2e of peak), mean relative error on bins > -60 dB: %.2e over %u bins\n",
         err_abs_max, err_abs_max / max_ref, err_rel_sum / rel_count, rel_count);
  assert(fabs((double)max_mag - max_ref) / max_ref < 1e-4);
  assert(err_abs_max / max_ref < 1e-5);          /* float32 with resynchronised twiddles */
  assert(err_rel_sum / rel_count < 1e-4);
  /* peaks land on the right bins: 137.5 Hz -> bin 137/138, 275 -> 275, 4123 -> 4123 */
  {
    unsigned b = 0u; float bm = 0.0f;
    for (unsigned k = 100u; k < 200u; k++) if (g_mag[k] > bm) { bm = g_mag[k]; b = k; }
    assert(b == 137u || b == 138u);
    b = 0u; bm = 0.0f;
    for (unsigned k = 4000u; k < 4300u; k++) if (g_mag[k] > bm) { bm = g_mag[k]; b = k; }
    assert(b == 4123u);
  }
}

static void test_complex_sizes(void) {
  static const unsigned sizes[] = {2u, 5u, 8u, 20u, 100u, 2048u, 8000u, 8192u};
  for (unsigned s = 0u; s < sizeof(sizes) / sizeof(sizes[0]); s++) {
    unsigned n = sizes[s];
    static double in_d[8192]; static cd_t ref[8192];
    srand(n);
    for (unsigned i = 0u; i < n; i++) { in_d[i] = (double)rand() / RAND_MAX - 0.5; g_c[i].re = (float)in_d[i]; g_c[i].im = 0.0f; }
    ref_rec(ref, in_d, 0u, 1u, n);
    assert(zs_fft_mixed_complex(g_c, g_cs, n));
    double maxe = 0.0, maxr = 0.0;
    for (unsigned k = 0u; k < n; k++) {
      double e = hypot((double)g_c[k].re - ref[k].re, (double)g_c[k].im - ref[k].im);
      double r = hypot(ref[k].re, ref[k].im);
      if (e > maxe) maxe = e;
      if (r > maxr) maxr = r;
    }
    assert(maxe / maxr < 2e-6 * (1.0 + log2((double)n)));
  }
  assert(!zs_fft_mixed_supported(3u) && !zs_fft_mixed_supported(1u) && zs_fft_mixed_supported(32000u) && !zs_fft_mixed_supported(48000u));
  assert(!zs_fft_mixed_complex(g_c, g_cs, 12u));
  assert(!zs_fft_mixed_real_magnitude(sample_cb, g_signal, 32001u, g_work, g_mag, NULL));
}

int main(void) {
  test_complex_sizes();
  test_real_32000();
  printf("fft_mixed tests passed\n");
  return 0;
}

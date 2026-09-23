#include "zs_fft_mixed.h"

#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define TWIDDLE_RESYNC 32u

bool zs_fft_mixed_supported(unsigned n) {
  if (n < 2u) return false;
  while (n % 2u == 0u) n /= 2u;
  while (n % 5u == 0u) n /= 5u;
  return n == 1u;
}

/* Radix schedule identical to zs_dsp.c: 4 while divisible by 4, then 5, then 2. */
static unsigned radix_for(unsigned n) { return (n % 4u == 0u) ? 4u : ((n % 5u == 0u) ? 5u : 2u); }

/* r-point DFT of a[0..r) into res[0..r) (r = 2, 4, 5), the same arithmetic in both decimation orders. */
static void butterfly(unsigned r, const zs_complex_t *a, zs_complex_t *res) {
  switch (r) {
    case 2:
      res[0].re = a[0].re + a[1].re; res[0].im = a[0].im + a[1].im;
      res[1].re = a[0].re - a[1].re; res[1].im = a[0].im - a[1].im;
      break;
    case 4: {
      zs_complex_t s02 = {a[0].re + a[2].re, a[0].im + a[2].im}, d02 = {a[0].re - a[2].re, a[0].im - a[2].im};
      zs_complex_t s13 = {a[1].re + a[3].re, a[1].im + a[3].im}, d13 = {a[1].re - a[3].re, a[1].im - a[3].im};
      res[0].re = s02.re + s13.re; res[0].im = s02.im + s13.im;
      res[2].re = s02.re - s13.re; res[2].im = s02.im - s13.im;
      /* -i * d13 */
      res[1].re = d02.re + d13.im; res[1].im = d02.im - d13.re;
      res[3].re = d02.re - d13.im; res[3].im = d02.im + d13.re;
      break;
    }
    default: { /* radix 5 */
      static const float c1 = 0.30901699437494745f, c2 = -0.8090169943749473f;   /* cos(2pi/5), cos(4pi/5) */
      static const float s1 = -0.9510565162951535f, s2 = -0.5877852522924732f;  /* sin(-2pi/5), sin(-4pi/5) */
      float sr14 = a[1].re + a[4].re, si14 = a[1].im + a[4].im, dr14 = a[1].re - a[4].re, di14 = a[1].im - a[4].im;
      float sr23 = a[2].re + a[3].re, si23 = a[2].im + a[3].im, dr23 = a[2].re - a[3].re, di23 = a[2].im - a[3].im;
      float t1r = a[0].re + c1 * sr14 + c2 * sr23, t1i = a[0].im + c1 * si14 + c2 * si23;
      float t2r = a[0].re + c2 * sr14 + c1 * sr23, t2i = a[0].im + c2 * si14 + c1 * si23;
      float u1r = s1 * dr14 + s2 * dr23, u1i = s1 * di14 + s2 * di23;   /* multiplied by i below */
      float u2r = s2 * dr14 - s1 * dr23, u2i = s2 * di14 - s1 * di23;
      res[0].re = a[0].re + sr14 + sr23; res[0].im = a[0].im + si14 + si23;
      res[1].re = t1r - u1i; res[1].im = t1i + u1r;
      res[4].re = t1r + u1i; res[4].im = t1i - u1r;
      res[2].re = t2r - u2i; res[2].im = t2i + u2r;
      res[3].re = t2r + u2i; res[3].im = t2i - u2r;
      break;
    }
  }
}

/* Decimation in time: out[0..n) <- FFT of in[offset + p*stride], p = 0..n-1. */
static void fft_rec(zs_complex_t *out, const zs_complex_t *in, unsigned offset, unsigned stride, unsigned n) {
  if (n == 1u) { out[0] = in[offset]; return; }
  {
    const unsigned r = radix_for(n), m = n / r;
    for (unsigned p = 0u; p < r; p++) fft_rec(out + p * m, in, offset + p * stride, stride * r, m);
    /* stage twiddle w_n^k by rotation, re-synchronised with sincos every TWIDDLE_RESYNC steps */
    const float step = -2.0f * (float)M_PI / (float)n;
    const float br = cosf(step), bi = sinf(step);
    float wr = 1.0f, wi = 0.0f;
    for (unsigned k = 0u; k < m; k++) {
      zs_complex_t a[5], res[5];
      float tr = 1.0f, ti = 0.0f; /* w_n^{k p} */
      if ((k % TWIDDLE_RESYNC) == 0u) { wr = cosf(step * (float)k); wi = sinf(step * (float)k); }
      for (unsigned p = 0u; p < r; p++) {
        zs_complex_t v = out[p * m + k];
        a[p].re = v.re * tr - v.im * ti;
        a[p].im = v.re * ti + v.im * tr;
        { float ntr = tr * wr - ti * wi; ti = tr * wi + ti * wr; tr = ntr; }
      }
      butterfly(r, a, res);
      for (unsigned q = 0u; q < r; q++) out[q * m + k] = res[q];
      { float nwr = wr * br - wi * bi; wi = wr * bi + wi * br; wr = nwr; }
    }
  }
}

/*
 * In-place decimation in frequency (Gentleman-Sande) with the same radix schedule and twiddle scheme.
 * Input in natural order; on return x holds the spectrum in digit-reversed order: the value of
 * frequency f sits at dif_position(f) (see below).  No scratch.
 */
static void fft_dif_inplace(zs_complex_t *x, unsigned n) {
  for (unsigned L = n; L > 1u;) {
    const unsigned r = radix_for(L), m = L / r;
    const float step = -2.0f * (float)M_PI / (float)L;
    const float br = cosf(step), bi = sinf(step);
    float wr = 1.0f, wi = 0.0f;                       /* w_L^k */
    for (unsigned k = 0u; k < m; k++) {
      if ((k % TWIDDLE_RESYNC) == 0u) { wr = cosf(step * (float)k); wi = sinf(step * (float)k); }
      for (unsigned b = 0u; b < n; b += L) {
        zs_complex_t *blk = x + b + k, a[5], res[5];
        float tr = 1.0f, ti = 0.0f;                   /* w_L^{q k} */
        for (unsigned p = 0u; p < r; p++) a[p] = blk[p * m];
        butterfly(r, a, res);
        for (unsigned q = 0u; q < r; q++) {
          blk[q * m].re = res[q].re * tr - res[q].im * ti;
          blk[q * m].im = res[q].re * ti + res[q].im * tr;
          { float ntr = tr * wr - ti * wi; ti = tr * wi + ti * wr; tr = ntr; }
        }
      }
      { float nwr = wr * br - wi * bi; wi = wr * bi + wi * br; wr = nwr; }
    }
    L = m;
  }
}

#define DIF_MAX_STAGES 32u
typedef struct { unsigned count, radix[DIF_MAX_STAGES], block[DIF_MAX_STAGES]; } dif_schedule_t;

static void dif_schedule(dif_schedule_t *sc, unsigned n) {
  sc->count = 0u;
  for (unsigned L = n; L > 1u && sc->count < DIF_MAX_STAGES; sc->count++) {
    const unsigned r = radix_for(L), m = L / r;
    sc->radix[sc->count] = r;
    sc->block[sc->count] = m;
    L = m;
  }
}

/* Position of frequency f after fft_dif_inplace: stage i (radix r_i, sub-block m_i) contributes (f_i mod r_i) * m_i. */
static unsigned dif_position(const dif_schedule_t *sc, unsigned f) {
  unsigned pos = 0u;
  for (unsigned i = 0u; i < sc->count; i++) {
    pos += (f % sc->radix[i]) * sc->block[i];
    f /= sc->radix[i];
  }
  return pos;
}

bool zs_fft_mixed_complex(zs_complex_t *x, zs_complex_t *scratch, unsigned n) {
  if (!x || !scratch || !zs_fft_mixed_supported(n)) return false;
  memcpy(scratch, x, (size_t)n * sizeof(*x));
  fft_rec(x, scratch, 0u, 1u, n);
  return true;
}

/* X[k] = (Z[k] + conj Z[h-k])/2 - i e^{-2 pi i k/n} (Z[k] - conj Z[h-k])/2, k = 0..h; Z read through `sc` when
   it is digit-reversed.  Returns the maximum magnitude. */
static float split_magnitudes(const zs_complex_t *z, const dif_schedule_t *sc, unsigned n, float *mag) {
  const unsigned h = n / 2u;
  const float step = -2.0f * (float)M_PI / (float)n;
  const float br = cosf(step), bi = sinf(step);
  float wr = 1.0f, wi = 0.0f, mx = 0.0f;
  for (unsigned k = 0u; k <= h; k++) {
    const unsigned ik = k == h ? 0u : k, ic = k == 0u ? 0u : h - k;
    zs_complex_t zk = z[sc ? dif_position(sc, ik) : ik], zc = z[sc ? dif_position(sc, ic) : ic];
    float er = 0.5f * (zk.re + zc.re), ei = 0.5f * (zk.im - zc.im);   /* even part */
    float orr = 0.5f * (zk.im + zc.im), oi = -0.5f * (zk.re - zc.re); /* odd part: (Z[k]-conj Z[h-k]) / (2i) */
    float xr, xi;
    if ((k % TWIDDLE_RESYNC) == 0u) { wr = cosf(step * (float)k); wi = sinf(step * (float)k); }
    if (k == h) { xr = er - orr; xi = 0.0f; }          /* w^h = -1 */
    else { xr = er + (orr * wr - oi * wi); xi = ei + (orr * wi + oi * wr); }
    if (k == 0u) xi = 0.0f;
    mag[k] = sqrtf(xr * xr + xi * xi);
    if (mag[k] > mx) mx = mag[k];
    { float nwr = wr * br - wi * bi; wi = wr * bi + wi * br; wr = nwr; }
  }
  return mx;
}

bool zs_fft_mixed_real_magnitude(zs_fft_sample_fn_t sample, const void *ctx, unsigned n,
                                 zs_complex_t *work, float *mag, float *max_mag) {
  unsigned h;
  float mx;
  if (!sample || !work || !mag || (n & 1u) || n < 4u || !zs_fft_mixed_supported(n / 2u)) return false;
  h = n / 2u;
  /* pack z[k] = x[2k] + i x[2k+1] into the mag area (n floats = n/2 complex); the decimation-in-time
     recursion reads it and writes the spectrum into `work`; mag is then overwritten by the magnitudes. */
  {
    zs_complex_t *in = (zs_complex_t *)(void *)mag;
    for (unsigned k = 0u; k < h; k++) { in[k].re = sample(ctx, 2u * k); in[k].im = sample(ctx, 2u * k + 1u); }
    fft_rec(work, in, 0u, 1u, h);
  }
  mx = split_magnitudes(work, NULL, n, mag);
  if (max_mag) *max_mag = mx;
  return true;
}

bool zs_fft_mixed_real_magnitude_inplace(zs_fft_sample_fn_t sample, const void *ctx, unsigned n,
                                         zs_complex_t *work, float *mag, float *max_mag) {
  dif_schedule_t sc;
  unsigned h;
  float mx;
  if (!sample || !work || !mag || (n & 1u) || n < 4u || !zs_fft_mixed_supported(n / 2u)) return false;
  h = n / 2u;
  for (unsigned k = 0u; k < h; k++) { work[k].re = sample(ctx, 2u * k); work[k].im = sample(ctx, 2u * k + 1u); }
  fft_dif_inplace(work, h);
  dif_schedule(&sc, h);
  mx = split_magnitudes(work, &sc, n, mag);
  if (max_mag) *max_mag = mx;
  return true;
}

/* Bearings of several sources at once (zs_comb_bearing): three propulsion combs from three directions at the same
   level, each bearing follows its own source, while the full-band bearing of the same mixture follows the loudest
   direction at best; a strong and a weaker source; two combs too close to tell apart give no bearing; the ring path. */
#include "array_render.h"
#include "zs_audio.h"
#include "zs_bearing.h"
#include "zs_comb_bearing.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define FS 32000u
#define LEN (ZS_COMB_BEARING_SPAN + ZS_COMB_BEARING_TAPS - 1u)

static uint32_t rng = 0x9e3779b9u;
static float urand(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return (float)(rng & 0xffffffu) / 16777216.0f; }
static float gauss(void) { return 0.866f * ((urand() * 2 - 1) + (urand() * 2 - 1) + (urand() * 2 - 1)); }
static float angle_error(float a, float b) { return fabsf(fmodf(a - b + 540.0f, 360.0f) - 180.0f); }

typedef struct { float f0, az, el, gain; double phase[40]; array_render_t r; } source_t;

static int16_t ch[4][LEN];
static float memory[ZS_COMB_BEARING_MEMORY];
static zs_comb_bearing_workspace_t ws;
static zs_spatial_gcc_workspace_t gcc;

/* a propulsion comb: harmonics up to 3.4 kHz falling ~ k^-0.8, f0 drifting 1 % over the span (Doppler) */
static float source_next(source_t *s, unsigned n) {
  float v = 0.0f;
  const double f0 = s->f0 * (1.0 + 0.01 * (double)n / LEN);
  for (unsigned k = 1u; k <= 40u && k * s->f0 < 3400.0f; k++) {
    s->phase[k - 1u] += 2.0 * 3.14159265358979 * f0 * k / FS;
    v += (float)(pow((double)k, -0.8) * sin(s->phase[k - 1u]));
  }
  return s->gain * 0.12f * v;
}

static void render(source_t *src, unsigned n_src, float noise_rms) {
  for (unsigned s = 0u; s < n_src; s++) {
    memset(src[s].phase, 0, sizeof(src[s].phase));
    for (unsigned k = 0u; k < 40u; k++) src[s].phase[k] = 0.7 * k * (s + 1u);   /* incoherent harmonic phases */
    array_render_init(&src[s].r, NULL, (float)FS);
    array_render_set_direction(&src[s].r, src[s].az, src[s].el, 15.0f);
  }
  for (unsigned n = 0u; n < LEN + ARRAY_RENDER_HISTORY; n++) {
    float sum[4] = {0};
    for (unsigned s = 0u; s < n_src; s++) {
      float out[4];
      array_render_push(&src[s].r, source_next(&src[s], n), out);
      for (unsigned c = 0u; c < 4u; c++) sum[c] += out[c];
    }
    if (n < ARRAY_RENDER_HISTORY) continue;
    for (unsigned c = 0u; c < 4u; c++) {
      float v = sum[c] + noise_rms * gauss();
      v = v > 1.0f ? 1.0f : (v < -1.0f ? -1.0f : v);
      ch[c][n - ARRAY_RENDER_HISTORY] = (int16_t)(v * 20000.0f);
    }
  }
}

static void test_three_sources(void) {
  static source_t src[3] = {{.f0 = 185.0f, .az = 40.0f, .el = 15.0f, .gain = 1.0f},
                            {.f0 = 120.0f, .az = 200.0f, .el = 10.0f, .gain = 1.0f},
                            {.f0 = 290.0f, .az = 310.0f, .el = 25.0f, .gain = 1.0f}};
  const float f0[3] = {185.0f, 120.0f, 290.0f};
  const int16_t *p[4] = {ch[0], ch[1], ch[2], ch[3]};
  zs_bearing_ctx_t ctx;
  zs_comb_bearing_stats_t st;
  zs_bearing_t out[3], full;
  float worst = 0.0f, full_err = 1e9f;
  zs_bearing_init(&ctx, NULL);
  for (unsigned trial = 0u; trial < 4u; trial++) {
    src[0].az = 40.0f + 25.0f * trial; src[1].az = 200.0f - 30.0f * trial; src[2].az = 310.0f + 10.0f * trial;
    render(src, 3u, 0.03f);
    memset(&st, 0, sizeof(st));
    assert(zs_comb_bearings_from_channels(&ctx, &st, p, LEN, f0, 3u, 15.0f, memory, &ws, out) == 3u);
    for (unsigned s = 0u; s < 3u; s++) {
      const float e = angle_error(out[s].azimuth_deg, src[s].az);
      printf("  trial %u source %.0f Hz: az %.1f (truth %.1f) el %.1f (truth %.1f) sigma %.2f conf %.2f\n", trial, f0[s],
             out[s].azimuth_deg, src[s].az, out[s].elevation_deg, src[s].el, out[s].sigma_deg, out[s].confidence);
      assert(out[s].valid && out[s].f0_hz == f0[s] && out[s].frames_used == ZS_COMB_BEARING_FRAMES);
      assert(fabsf(out[s].elevation_deg - src[s].el) < 8.0f);
      assert(e <= 3.0f * out[s].sigma_deg + 1.0f);                /* the sigma tells the truth */
      if (e > worst) worst = e;
    }
    /* the full-band bearing of the same mixture, for comparison: one direction at most */
    if (zs_bearing_from_channels(&ctx, p + 0, LEN, FS, 15.0f, &gcc, &full)) {
      float e = 1e9f;
      for (unsigned s = 0u; s < 3u; s++) e = fminf(e, angle_error(full.azimuth_deg, src[s].az));
      if (e < full_err) full_err = e;
      printf("  trial %u full band: az %.1f sigma %.1f (nearest source %.1f deg off)\n", trial, full.azimuth_deg, full.sigma_deg, e);
    }
  }
  printf("three sources at once: worst azimuth error %.2f deg\n", worst);
  assert(worst < 5.0f);
}

static void test_one_source_and_a_weaker_one(void) {
  static source_t src[2] = {{.f0 = 110.0f, .az = 133.0f, .el = 30.0f, .gain = 1.0f},
                            {.f0 = 192.0f, .az = 250.0f, .el = 5.0f, .gain = 0.3f}};   /* 10 dB below */
  const float f0[2] = {110.0f, 192.0f};
  const int16_t *p[4] = {ch[0], ch[1], ch[2], ch[3]};
  zs_bearing_ctx_t ctx;
  zs_bearing_t out[2];
  zs_bearing_init(&ctx, NULL);
  render(src, 1u, 0.03f);
  assert(zs_comb_bearings_from_channels(&ctx, NULL, p, LEN, f0, 1u, 15.0f, memory, &ws, out) == 1u);
  assert(angle_error(out[0].azimuth_deg, 133.0f) < 2.0f && out[0].sigma_deg < 5.0f);
  render(src, 2u, 0.03f);
  assert(zs_comb_bearings_from_channels(&ctx, NULL, p, LEN, f0, 2u, 15.0f, memory, &ws, out) == 2u);
  printf("strong + weak: %.1f (133) / %.1f (250), sigma %.2f / %.2f\n", out[0].azimuth_deg, out[1].azimuth_deg, out[0].sigma_deg, out[1].sigma_deg);
  assert(angle_error(out[0].azimuth_deg, 133.0f) < 2.0f && angle_error(out[1].azimuth_deg, 250.0f) < 4.0f);
}

static void test_no_bearing_without_own_bins_or_source(void) {
  static source_t src[1] = {{.f0 = 150.0f, .az = 10.0f, .el = 10.0f, .gain = 1.0f}};
  const int16_t *p[4] = {ch[0], ch[1], ch[2], ch[3]};
  zs_bearing_ctx_t ctx;
  zs_comb_bearing_stats_t st;
  zs_bearing_t out[3];
  zs_bearing_init(&ctx, NULL);
  render(src, 1u, 0.03f);
  /* two fundamentals within the tolerance exclude each other everywhere */
  {
    const float f0[2] = {150.0f, 150.5f};
    memset(&st, 0, sizeof(st));
    assert(zs_comb_bearings_from_channels(&ctx, &st, p, LEN, f0, 2u, 15.0f, memory, &ws, out) == 0u);
    assert(st.few_bins == 2u && !out[0].valid && !out[1].valid && out[1].f0_hz == 150.5f);
  }
  /* a comb nobody plays: incoherent bins */
  {
    const float f0[1] = {233.0f};
    memset(&st, 0, sizeof(st));
    render(src, 0u, 0.05f);
    assert(zs_comb_bearings_from_channels(&ctx, &st, p, LEN, f0, 1u, 15.0f, memory, &ws, out) == 0u);
    assert(st.weak == 1u);
  }
  /* arguments */
  {
    const float bad[1] = {10.0f}, ok[4] = {100.0f, 200.0f, 300.0f, 400.0f};
    assert(zs_comb_bearings_from_channels(&ctx, NULL, p, LEN, bad, 1u, 15.0f, memory, &ws, out) == 0u);
    assert(zs_comb_bearings_from_channels(&ctx, NULL, p, LEN, ok, 4u, 15.0f, memory, &ws, out) == 0u);
    assert(zs_comb_bearings_from_channels(&ctx, NULL, p, LEN - 1u, ok, 1u, 15.0f, memory, &ws, out) == 0u);
  }
}

static void test_ring_path(void) {
  static int16_t storage[40000u * ZS_AUDIO_CHANNELS];
  static source_t src[2] = {{.f0 = 185.0f, .az = 75.0f, .el = 12.0f, .gain = 1.0f}, {.f0 = 120.0f, .az = 290.0f, .el = 8.0f, .gain = 1.0f}};
  const float f0[2] = {185.0f, 120.0f};
  zs_audio_ring_t ring;
  zs_bearing_ctx_t ctx;
  zs_comb_bearing_stats_t st;
  zs_bearing_t a[2], b[2];
  const int16_t *p[4] = {ch[0], ch[1], ch[2], ch[3]};
  zs_bearing_init(&ctx, NULL);
  render(src, 2u, 0.03f);
  zs_audio_ring_init(&ring, storage, 40000u, FS);
  for (uint32_t i = 0u; i < 5000u; i++) { int16_t z[4] = {0}; zs_audio_ring_push(&ring, z); }
  for (uint32_t i = 0u; i < LEN; i++) { int16_t f[4] = {ch[0][i], ch[1][i], ch[2][i], ch[3][i]}; zs_audio_ring_push(&ring, f); }
  memset(&st, 0, sizeof(st));
  assert(zs_comb_bearings_from_ring(&ctx, &st, &ring, ring.total_frames, f0, 2u, 15.0f, memory, &ws, a) == 2u);
  assert(zs_comb_bearings_from_channels(&ctx, NULL, p, LEN, f0, 2u, 15.0f, memory, &ws, b) == 2u);
  for (unsigned s = 0u; s < 2u; s++) assert(fabsf(a[s].azimuth_deg - b[s].azimuth_deg) < 1e-3f);
  assert(st.attempts == 2u && st.computed == 2u);
  /* a span no longer in the ring */
  for (uint32_t i = 0u; i < 40000u; i++) { int16_t z[4] = {0}; zs_audio_ring_push(&ring, z); }
  memset(&st, 0, sizeof(st));
  assert(zs_comb_bearings_from_ring(&ctx, &st, &ring, ring.total_frames - 30000u, f0, 2u, 15.0f, memory, &ws, a) == 0u);
  assert(st.no_audio == 2u);
}

int main(void) {
  test_three_sources();
  test_one_source_and_a_weaker_one();
  test_no_bearing_without_own_bins_or_source();
  test_ring_path();
  printf("comb bearing tests passed\n");
  return 0;
}

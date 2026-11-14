/* On-board bearing of the 3+1 array (zs_bearing): shared-reference GCC-PHAT equals the pairwise one, bearings of a
   rendered piston-UAV plane wave in noise match the truth, noise alone gives no bearing, the ring path and its
   bounds. */
#include "array_render.h"
#include "zs_audio.h"
#include "zs_bearing.h"
#include "zs_station_pipeline.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define FS 32000u
#define SPAN 16000u                      /* the last 0.5 s of a window, as the pipeline asks */

static uint32_t rng = 0x2545f491u;
static float urand(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return (float)(rng & 0xffffffu) / 16777216.0f; }
static float gauss(void) { return 0.866f * ((urand() * 2 - 1) + (urand() * 2 - 1) + (urand() * 2 - 1)); }

static float angle_error(float a, float b) { return fabsf(fmodf(a - b + 540.0f, 360.0f) - 180.0f); }

/* piston UAV: f0 ~ 110 Hz, 20 harmonics falling ~ k^-0.8 */
static double phase[20];
static float source_sample(unsigned n) {
  float s = 0.0f;
  const double f0 = 110.0 * (1.0 + 0.01 * sin(2.0 * 3.14159265 * 0.5 * n / FS));
  for (unsigned k = 1u; k <= 20u; k++) {
    phase[k - 1u] += 2.0 * 3.14159265358979 * f0 * k / FS;
    s += (float)(pow((double)k, -0.8) * sin(phase[k - 1u]));
  }
  return 0.15f * s;
}

static int16_t ch[4][SPAN];
static zs_spatial_gcc_workspace_t ws;

/* noise_rms relative to the source rms (source rms ~0.15*~1.3/sqrt2 ~ 0.14) */
static void render(float az, float el, float noise_rms) {
  array_render_t r;
  array_render_init(&r, NULL, (float)FS);
  array_render_set_direction(&r, az, el, 15.0f);
  memset(phase, 0, sizeof(phase));
  for (unsigned n = 0u; n < SPAN + ARRAY_RENDER_HISTORY; n++) {
    float out[4];
    array_render_push(&r, source_sample(n), out);
    if (n < ARRAY_RENDER_HISTORY) continue;
    for (unsigned c = 0u; c < 4u; c++) {
      float v = out[c] + noise_rms * gauss();
      v = v > 1.0f ? 1.0f : (v < -1.0f ? -1.0f : v);
      ch[c][n - ARRAY_RENDER_HISTORY] = (int16_t)(v * 20000.0f);
    }
  }
}

static void test_shared_reference_matches_pairwise(void) {
  const int16_t *p[4] = {ch[0], ch[1], ch[2], ch[3]};
  float d3[3], q3[3];
  render(47.0f, 18.0f, 0.05f);
  assert(zs_spatial_gcc_phat_reference_delays(p, ZS_SPATIAL_GCC_N, FS, 600.0f, 80.0f, 3000.0f, &ws, d3, q3));
  for (unsigned j = 0u; j < 3u; j++) {
    float d, q;
    assert(zs_spatial_gcc_phat_delay_us(ch[0], ch[j + 1u], ZS_SPATIAL_GCC_N, FS, 600.0f, 80.0f, 3000.0f, &ws, &d, &q));
    assert(fabsf(d - d3[j]) < 1e-3f && q > 0.0f && q3[j] > 0.0f && q3[j] <= 1.0f);
  }
  /* argument checks */
  assert(!zs_spatial_gcc_phat_reference_delays(p, 512u, FS, 600.0f, 80.0f, 3000.0f, &ws, d3, q3));
  assert(!zs_spatial_gcc_phat_reference_delays(p, ZS_SPATIAL_GCC_N, FS, 600.0f, 3000.0f, 80.0f, &ws, d3, q3));
}

static void test_bearings_match_truth(void) {
  static const float cases[][2] = {{0.0f, 10.0f}, {47.0f, 18.0f}, {133.0f, 30.0f}, {220.0f, 5.0f}, {301.0f, 45.0f}, {359.0f, 25.0f}};
  zs_bearing_ctx_t ctx;
  const int16_t *p[4] = {ch[0], ch[1], ch[2], ch[3]};
  float worst_az = 0.0f, worst_el = 0.0f;
  zs_bearing_init(&ctx, NULL);
  for (unsigned i = 0u; i < sizeof(cases) / sizeof(cases[0]); i++) {
    zs_bearing_t b;
    render(cases[i][0], cases[i][1], 0.10f);     /* broadband noise ~ -3 dB below the source */
    assert(zs_bearing_from_channels(&ctx, p, SPAN, FS, 15.0f, &ws, &b));
    assert(b.valid && b.frames_used >= ZS_BEARING_MIN_FRAMES);
    const float eaz = angle_error(b.azimuth_deg, cases[i][0]), eel = fabsf(b.elevation_deg - cases[i][1]);
    printf("bearing truth %6.1f/%4.1f -> %6.1f/%4.1f sigma %.1f frames %u residual %.1f us\n", cases[i][0], cases[i][1],
           b.azimuth_deg, b.elevation_deg, b.sigma_deg, b.frames_used, b.residual_us);
    if (eaz > worst_az) worst_az = eaz;
    if (eel > worst_el) worst_el = eel;
    assert(b.sigma_deg >= 0.5f && b.sigma_deg <= 45.0f);
  }
  printf("bearing worst error az %.2f el %.2f deg\n", worst_az, worst_el);
  assert(worst_az < 5.0f && worst_el < 6.0f);
  assert(ctx.computed == sizeof(cases) / sizeof(cases[0]));
}

static void test_noise_alone_gives_no_bearing(void) {
  zs_bearing_ctx_t ctx;
  zs_bearing_t b;
  const int16_t *p[4] = {ch[0], ch[1], ch[2], ch[3]};
  zs_bearing_init(&ctx, NULL);
  for (unsigned c = 0u; c < 4u; c++) for (unsigned n = 0u; n < SPAN; n++) ch[c][n] = (int16_t)(gauss() * 4000.0f);
  assert(!zs_bearing_from_channels(&ctx, p, SPAN, FS, 15.0f, &ws, &b));
  assert(!b.valid && ctx.weak == 1u && ctx.computed == 0u);
}

static void test_ring_path(void) {
  static int16_t storage[36000u * ZS_AUDIO_CHANNELS];
  static int16_t frames[ZS_BEARING_FRAME_MEMORY];
  zs_audio_ring_t ring;
  zs_bearing_ctx_t ctx;
  zs_bearing_t b;
  zs_audio_ring_init(&ring, storage, 36000u, FS);
  render(250.0f, 20.0f, 0.05f);
  for (unsigned n = 0u; n < SPAN; n++) {
    const int16_t f[4] = {ch[0][n], ch[1][n], ch[2][n], ch[3][n]};
    zs_audio_ring_push(&ring, f);
  }
  zs_bearing_init(&ctx, NULL);
  assert(zs_bearing_from_ring(&ctx, &ring, SPAN, SPAN, 15.0f, frames, &ws, &b));
  assert(angle_error(b.azimuth_deg, 250.0f) < 5.0f);
  assert(!zs_bearing_from_ring(&ctx, &ring, SPAN + 1u, SPAN, 15.0f, frames, &ws, &b));     /* not yet recorded */
  for (unsigned n = 0u; n < 30000u; n++) { const int16_t z[4] = {0, 0, 0, 0}; zs_audio_ring_push(&ring, z); }
  assert(!zs_bearing_from_ring(&ctx, &ring, SPAN, SPAN, 15.0f, frames, &ws, &b));          /* overwritten */
  assert(ctx.no_audio == 2u && ctx.attempts == 3u);
  assert(!zs_bearing_from_ring(&ctx, &ring, 100u, SPAN, 15.0f, frames, &ws, &b));          /* bad span */
}

static bool fake_extract(void *c, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) { (void)c; (void)pcm; (void)n; memset(out, 0, ZS_FEATURE_COUNT * sizeof(float)); return true; }
static bool fake_emit(void *c, const zs_detection_t *d) { (void)c; (void)d; return true; }

/* The event carries the window's bearing as DOA (key 11) and reference TDOAs (key 14); azimuth wraps into 0..35999. */
static void test_detection_carries_bearing(void) {
  static zs_complex_t scratch[ZS_AIR_SCRATCH_COMPLEX];
  static int16_t window[ZS_PIPELINE_WINDOW_SAMPLES] __attribute__((aligned(4)));   /* the pipeline lends it as floats */
  static zs_station_pipeline_t p;
  const zs_station_pipeline_port_t port = {NULL, fake_extract, NULL, fake_emit, 17u, 5u, 0u, 0u, NULL, NULL};
  zs_detection_t d;
  assert(zs_station_pipeline_init(&p, &port, scratch, window));
  p.last_bearing = (zs_bearing_t){.azimuth_deg = 359.996f, .elevation_deg = -3.2f, .sigma_deg = 2.25f, .residual_us = 6.4f,
                                  .tdoa_us = {-120.4f, 233.6f, -401.2f}, .confidence = 0.9f, .frames_used = 8u, .valid = true};
  p.last_bearing_end = 64000u;
  zs_station_pipeline_fill_detection(&p, 64000u, &d);
  assert(d.doa.valid && d.doa.azimuth_cdeg == 0u && d.doa.elevation_cdeg == -320 && d.doa.sigma_cdeg == 225u);
  assert(d.spatial.tdoa12_us == -120 && d.spatial.tdoa13_us == 234 && d.spatial.tdoa14_us == -401);
  assert(d.spatial.residual_us == 6u && d.spatial.confidence_u8 == 230u && d.spatial.geometry_id == 1u && d.spatial.valid_flags == 3u);
  p.last_bearing.azimuth_deg = 271.23f;
  zs_station_pipeline_fill_detection(&p, 64000u, &d);
  assert(d.doa.azimuth_cdeg == 27123u);
  zs_station_pipeline_fill_detection(&p, 80000u, &d);                    /* a later window without its own bearing */
  assert(!d.doa.valid && d.spatial.valid_flags == 0u);
}

int main(void) {
  test_detection_carries_bearing();
  test_shared_reference_matches_pairwise();
  test_bearings_match_truth();
  test_noise_alone_gives_no_bearing();
  test_ring_path();
  puts("bearing tests passed");
  return 0;
}

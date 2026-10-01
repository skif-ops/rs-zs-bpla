/* Several targets by direction first (zs_doa_sep): three propulsion combs from three directions, two of them exactly
   2:3 (one comb to the gate), each found as its own confirmed direction track with its own label; a source 6 dB below
   two louder ones adds up over windows; a high source (vertical pair wraps); a fast pass across north keeps one track;
   a target fading for five windows comes back under its id; spatially white noise and a one-window burst confirm
   nothing; the target's own window keeps its source and drops the other; one track resynthesises the input. */
#include "array_render.h"
#include "zs_audio.h"
#include "zs_bearing.h"
#include "zs_comb_bearing.h"
#include "zs_doa_sep.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FS 32000u
#define HOP 16000u                                   /* the pipeline's 0.5 s hop = the span */
#define WINDOWS 12u
#define LEN (WINDOWS * HOP + ZS_COMB_BEARING_TAPS)

static uint32_t rng = 0x2545f491u;
static float urand(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return (float)(rng & 0xffffffu) / 16777216.0f; }
static float gauss(void) { return 0.866f * ((urand() * 2 - 1) + (urand() * 2 - 1) + (urand() * 2 - 1)); }
static float angle_error(float a, float b) { return fabsf(fmodf(a - b + 540.0f, 360.0f) - 180.0f); }

typedef struct {
  float f0, az, el, gain;
  float rate;                                        /* azimuth change, degrees per second (a pass) */
  unsigned on_from, on_to;                           /* active samples [on_from, on_to); 0, 0 = always */
  unsigned gap_from, gap_to;                         /* silent samples [gap_from, gap_to) (a fade) */
  double phase[48];
  array_render_t r;
} source_t;

static int16_t ch[4][LEN];
static float memory[ZS_COMB_BEARING_MEMORY];
static zs_doa_workspace_t ws;
static zs_doa_mask_workspace_t mws;

/* a propulsion comb: harmonics up to 3.4 kHz falling ~ k^-0.8, slow f0 wander of 0.5 % */
static float source_next(source_t *s, unsigned n) {
  if (s->on_to > s->on_from && (n < s->on_from || n >= s->on_to)) return 0.0f;
  if (s->gap_to > s->gap_from && n >= s->gap_from && n < s->gap_to) return 0.0f;
  float v = 0.0f;
  const double f0 = s->f0 * (1.0 + 0.005 * sin(2.0 * 3.14159265358979 * (double)n / (FS * 3.0)));
  for (unsigned k = 1u; k <= 48u && k * s->f0 < 3400.0f; k++) {
    s->phase[k - 1u] += 2.0 * 3.14159265358979 * f0 * k / FS;
    v += (float)(pow((double)k, -0.8) * sin(s->phase[k - 1u]));
  }
  return s->gain * 0.10f * v;
}

static void render(source_t *src, unsigned n_src, float noise_rms) {
  for (unsigned s = 0u; s < n_src; s++) {
    memset(src[s].phase, 0, sizeof(src[s].phase));
    for (unsigned k = 0u; k < 48u; k++) src[s].phase[k] = 0.9 * k * (s + 1u) + 0.37 * k * k;
    array_render_init(&src[s].r, NULL, (float)FS);
    array_render_set_direction(&src[s].r, src[s].az, src[s].el, 15.0f);
  }
  for (unsigned n = 0u; n < LEN + ARRAY_RENDER_HISTORY; n++) {
    float sum[4] = {0};
    for (unsigned s = 0u; s < n_src; s++) {
      float out[4];
      if (src[s].rate != 0.0f && n % 320u == 0u)          /* a pass: re-aim every 10 ms */
        array_render_set_direction(&src[s].r, fmodf(src[s].az + src[s].rate * (float)n / (float)FS + 360.0f, 360.0f), src[s].el, 15.0f);
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

/* runs the windows; returns the confirmed targets of the last window, counts windows each truth is confirmed in */
typedef struct { unsigned confirmed[3]; float worst_err[3]; float label[3]; unsigned ghosts; } run_t;

static run_t run(const source_t *truth, unsigned n_truth, unsigned skip) {
  zs_doa_sep_t s;
  zs_bearing_ctx_t ctx;
  run_t r;
  memset(&r, 0, sizeof(r));
  zs_doa_sep_init(&s);
  zs_bearing_init(&ctx, NULL);
  for (unsigned w = 0u; w < WINDOWS; w++) {
    const int16_t *p[4] = {ch[0] + w * HOP, ch[1] + w * HOP, ch[2] + w * HOP, ch[3] + w * HOP};
    zs_doa_target_t out[ZS_DOA_MAX_TRACKS];
    assert(zs_comb_bearing_decimate_channels(p, HOP + ZS_COMB_BEARING_TAPS - 1u, memory));
    const unsigned n = zs_doa_sep_push(&s, &ctx, memory, 15.0f, &ws, out);
    if (w < skip) continue;
    for (unsigned i = 0u; i < n; i++) {
      if (!out[i].confirmed || !out[i].has_bearing) continue;
      int hit = -1;
      for (unsigned t = 0u; t < n_truth; t++)
        if (angle_error(out[i].bearing.azimuth_deg, truth[t].az) <= 8.0f) hit = (int)t;
      if (hit < 0) { r.ghosts++; continue; }
      r.confirmed[hit]++;
      const float e = angle_error(out[i].bearing.azimuth_deg, truth[hit].az);
      if (e > r.worst_err[hit]) r.worst_err[hit] = e;
      r.label[hit] = out[i].bearing.f0_hz;
    }
  }
  return r;
}

static bool near_ratio(float label, float f0) {      /* the label names the source's comb (an integer ratio) */
  if (label <= 0.0f) return false;
  const float q = label >= f0 ? label / f0 : f0 / label, k = roundf(q);
  return k >= 1.0f && fabsf(q - k) <= 0.04f * k;
}

static void test_three_targets_one_with_2_to_3(void) {
  source_t src[3] = {{.f0 = 174.0f, .az = 40.0f, .el = 10.0f, .gain = 1.0f},
                     {.f0 = 261.0f, .az = 160.0f, .el = 15.0f, .gain = 1.0f},
                     {.f0 = 118.0f, .az = 280.0f, .el = 5.0f, .gain = 1.0f}};
  render(src, 3u, 0.01f);
  const run_t r = run(src, 3u, 4u);
  for (unsigned t = 0u; t < 3u; t++) {
    printf("doa three: target %u (f0 %.0f az %.0f) confirmed %u/8 worst %.2f deg label %.1f\n", t, src[t].f0, src[t].az,
           r.confirmed[t], r.worst_err[t], r.label[t]);
    assert(r.confirmed[t] >= 7u);
    assert(r.worst_err[t] <= 3.0f);
    assert(near_ratio(r.label[t], src[t].f0));
  }
  assert(r.ghosts == 0u);
  /* the 2:3 pair keeps two labels: no common sub-harmonic */
  assert(fabsf(r.label[0] - r.label[1]) > 0.1f * r.label[0]);
}

static void test_masked_target_adds_up(void) {
  source_t src[3] = {{.f0 = 174.0f, .az = 40.0f, .el = 10.0f, .gain = 0.5f},      /* 6 dB below the others */
                     {.f0 = 261.0f, .az = 100.0f, .el = 15.0f, .gain = 1.0f},
                     {.f0 = 135.0f, .az = 220.0f, .el = 5.0f, .gain = 1.0f}};
  render(src, 3u, 0.01f);
  const run_t r = run(src, 3u, 4u);
  printf("doa weak: confirmed %u %u %u /8, ghosts %u\n", r.confirmed[0], r.confirmed[1], r.confirmed[2], r.ghosts);
  assert(r.confirmed[0] >= 5u && r.confirmed[1] >= 7u && r.confirmed[2] >= 7u);
  assert(r.ghosts == 0u);
}

static void test_high_source(void) {
  source_t src[1] = {{.f0 = 190.0f, .az = 125.0f, .el = 55.0f, .gain = 1.0f}};
  render(src, 1u, 0.01f);
  const run_t r = run(src, 1u, 4u);
  printf("doa high: confirmed %u/8 worst %.2f deg\n", r.confirmed[0], r.worst_err[0]);
  assert(r.confirmed[0] >= 7u && r.worst_err[0] <= 3.0f && r.ghosts == 0u);
}

/* a fast pass across north (8 degrees per second, 4 per window): one track all along, its bearings follow */
static void test_fast_pass_keeps_its_track(void) {
  source_t src[1] = {{.f0 = 180.0f, .az = 340.0f, .el = 10.0f, .gain = 1.0f, .rate = 8.0f}};
  zs_doa_sep_t s;
  zs_bearing_ctx_t ctx;
  uint16_t id = 0u;
  unsigned confirmed = 0u, switches = 0u;
  float worst = 0.0f;
  render(src, 1u, 0.01f);
  zs_doa_sep_init(&s);
  zs_bearing_init(&ctx, NULL);
  for (unsigned w = 0u; w < WINDOWS; w++) {
    const int16_t *p[4] = {ch[0] + w * HOP, ch[1] + w * HOP, ch[2] + w * HOP, ch[3] + w * HOP};
    zs_doa_target_t out[ZS_DOA_MAX_TRACKS];
    assert(zs_comb_bearing_decimate_channels(p, HOP + ZS_COMB_BEARING_TAPS - 1u, memory));
    const unsigned n = zs_doa_sep_push(&s, &ctx, memory, 15.0f, &ws, out);
    /* the truth at the span's middle (the span is the window's 0.5 s) */
    const float truth = fmodf(340.0f + 8.0f * ((float)w * 0.5f + 0.25f) + 360.0f, 360.0f);
    for (unsigned i = 0u; i < n; i++) {
      if (!out[i].confirmed || !out[i].has_bearing) continue;
      if (id && out[i].id != id) switches++;
      id = out[i].id;
      confirmed++;
      const float e = angle_error(out[i].bearing.azimuth_deg, truth);
      if (e > worst) worst = e;
    }
  }
  printf("doa pass: confirmed %u windows, track switches %u, worst %.2f deg\n", confirmed, switches, worst);
  assert(confirmed >= 9u && switches == 0u && worst <= 3.0f);
}

/* a target fading for five windows comes back under its id where its turn put it */
static void test_fade_keeps_its_id(void) {
  source_t src[1] = {{.f0 = 160.0f, .az = 100.0f, .el = 10.0f, .gain = 1.0f, .rate = 4.0f, .gap_from = 4u * HOP, .gap_to = 9u * HOP}};
  zs_doa_sep_t s;
  zs_bearing_ctx_t ctx;
  uint16_t before = 0u, after = 0u;
  render(src, 1u, 0.01f);
  zs_doa_sep_init(&s);
  zs_bearing_init(&ctx, NULL);
  for (unsigned w = 0u; w < WINDOWS; w++) {
    const int16_t *p[4] = {ch[0] + w * HOP, ch[1] + w * HOP, ch[2] + w * HOP, ch[3] + w * HOP};
    zs_doa_target_t out[ZS_DOA_MAX_TRACKS];
    assert(zs_comb_bearing_decimate_channels(p, HOP + ZS_COMB_BEARING_TAPS - 1u, memory));
    const unsigned n = zs_doa_sep_push(&s, &ctx, memory, 15.0f, &ws, out);
    for (unsigned i = 0u; i < n; i++) {
      if (!out[i].has_bearing) continue;
      if (w < 4u) before = out[i].id;
      if (w >= 10u) after = out[i].id;
    }
  }
  printf("doa fade: id %u before, %u after\n", before, after);
  assert(before != 0u && after == before);
}

static void test_noise_and_burst_confirm_nothing(void) {
  /* spatially white noise only */
  render(NULL, 0u, 0.05f);
  run_t r = run(NULL, 0u, 0u);
  assert(r.ghosts == 0u);
  /* a comb heard in one window only (a horn, a passing bird) */
  source_t burst[1] = {{.f0 = 400.0f, .az = 70.0f, .el = 5.0f, .gain = 2.0f, .on_from = 5u * HOP, .on_to = 6u * HOP}};
  render(burst, 1u, 0.02f);
  r = run(burst, 1u, 0u);
  printf("doa burst: confirmed %u, ghosts %u\n", r.confirmed[0], r.ghosts);
  assert(r.confirmed[0] == 0u && r.ghosts == 0u);
}

/* the power of a tone near f in x (single-bin DFT with a Hann window) */
static double tone_power(const int16_t *x, unsigned n, float f) {
  double re = 0.0, im = 0.0;
  for (unsigned i = 0u; i < n; i++) {
    const double w = 0.5 - 0.5 * cos(2.0 * 3.14159265358979 * i / (n - 1u));
    re += w * x[i] * cos(2.0 * 3.14159265358979 * f * i / FS);
    im -= w * x[i] * sin(2.0 * 3.14159265358979 * f * i / FS);
  }
  return re * re + im * im;
}

static void test_mask_window(void) {
  static int16_t storage[4u * 120000u];
  static int16_t out[32000u], mono[32000u];
  zs_audio_ring_t ring;
  zs_bearing_ctx_t ctx;
  source_t src[2] = {{.f0 = 174.0f, .az = 40.0f, .el = 10.0f, .gain = 1.0f},
                     {.f0 = 261.0f, .az = 200.0f, .el = 15.0f, .gain = 1.0f}};
  zs_bearing_init(&ctx, NULL);
  render(src, 2u, 0.005f);
  zs_audio_ring_init(&ring, storage, 120000u, FS);
  for (uint32_t i = 0u; i < 3u * HOP; i++) { const int16_t f[4] = {ch[0][i], ch[1][i], ch[2][i], ch[3][i]}; zs_audio_ring_push(&ring, f); }
  const uint64_t end = ring.total_frames;
  zs_bearing_t tracks[2];
  memset(tracks, 0, sizeof(tracks));
  tracks[0].azimuth_deg = 40.0f; tracks[0].elevation_deg = 10.0f;
  tracks[1].azimuth_deg = 200.0f; tracks[1].elevation_deg = 15.0f;
  /* one track: the resynthesis is the input */
  assert(zs_doa_sep_mask_window(&ctx, &ring, end, 32000u, tracks, 1u, 0u, 15.0f, &mws, out));
  assert(zs_audio_ring_copy_mono(&ring, end, 32000u, mono, 0u));
  int worst = 0;
  for (unsigned i = 0u; i < 32000u; i++) { const int d = abs(out[i] - mono[i]); if (d > worst) worst = d; }
  printf("doa mask: one track max error %d LSB\n", worst);
  assert(worst <= 2);
  /* two tracks: each window keeps its own lines, the other's drop */
  for (unsigned which = 0u; which < 2u; which++) {
    assert(zs_doa_sep_mask_window(&ctx, &ring, end, 32000u, tracks, 2u, which, 15.0f, &mws, out));
    double own = 0.0, other = 0.0, own_in = 0.0, other_in = 0.0;
    for (unsigned k = 1u; k <= 4u; k++) {
      own += tone_power(out, 32000u, src[which].f0 * k);
      other += tone_power(out, 32000u, src[1u - which].f0 * k);
      own_in += tone_power(mono, 32000u, src[which].f0 * k);
      other_in += tone_power(mono, 32000u, src[1u - which].f0 * k);
    }
    const double kept = 10.0 * log10(own / own_in), dropped = 10.0 * log10(other / other_in);
    printf("doa mask: target %u keeps %.1f dB of its lines, other's %.1f dB\n", which, kept, dropped);
    assert(kept >= -2.0 && dropped <= -15.0);
  }
  /* not enough audio in the ring */
  assert(!zs_doa_sep_mask_window(&ctx, &ring, end + 100000u, 32000u, tracks, 2u, 0u, 15.0f, &mws, out));
}

int main(void) {
  test_three_targets_one_with_2_to_3();
  test_masked_target_adds_up();
  test_high_source();
  test_fast_pass_keeps_its_track();
  test_fade_keeps_its_id();
  test_noise_and_burst_confirm_nothing();
  test_mask_window();
  puts("doa_sep: ok");
  return 0;
}

/* Station pipeline with several sources at once (zs_station_pipeline.h, source tracks): two propulsion combs from two
   directions are classified in turn and each gets its own bearing with its fundamental; the same two combs from one
   direction (one multirotor's rotors) are one target: no rotation, one bearing.  With a stash (targets by direction,
   zs_doa_sep.h): the two directions are classified on their own windows and each gets its own bearing with its label;
   a UAV beside a tractor (the extractor stub tells them by whose lines dominate the window it is given) gets bearings,
   the tractor's direction none. */
#include "array_render.h"
#include "zs_model_centroids.h"
#include "zs_station_pipeline.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define FS 32000u
#define RING_FRAMES 36000u
static int16_t ring_storage[RING_FRAMES * ZS_AUDIO_CHANNELS];
static zs_complex_t scratch[ZS_AIR_SCRATCH_COMPLEX];
static int16_t window[ZS_PIPELINE_WINDOW_SAMPLES] __attribute__((aligned(4)));

typedef struct { float f0, gain; double phase[24]; array_render_t r; } source_t;
typedef struct {
  unsigned bearings[2], emitted, extracted;
  unsigned toward[2];              /* bearings within 10 degrees of each source's direction, whatever their label */
  bool tractor;                    /* source 1 is a tractor: a window its lines dominate is classified as one */
  float az_sum[2], az_err_max[2];
  float truth_az[2], truth_f0[2];
  float other_f0;                  /* bearings whose fundamental matches neither source */
} world_t;

/* power of the first four harmonics of f0 in the window (Goertzel) */
static double comb_power(const int16_t *pcm, size_t n, float f0) {
  double total = 0.0;
  for (unsigned h = 1u; h <= 4u; h++) {
    const double w = 2.0 * M_PI * f0 * h / FS, c = 2.0 * cos(w);
    double s1 = 0.0, s2 = 0.0;
    for (size_t i = 0u; i < n; i++) { const double s0 = pcm[i] + c * s1 - s2; s2 = s1; s1 = s0; }
    total += s1 * s1 + s2 * s2 - c * s1 * s2;
  }
  return total;
}

static bool extract(void *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) {
  world_t *W = ctx;
  /* FP-1 (centroid 0), or a tractor (centroid 24, class 14) when the tractor's lines dominate the window given */
  const bool ground = W->tractor && comb_power(pcm, n, W->truth_f0[1]) > comb_power(pcm, n, W->truth_f0[0]);
  const unsigned c = ground ? 24u : 0u;
  for (unsigned i = 0u; i < ZS_FEATURE_COUNT; i++) out[i] = zs_model_mean[i] + zs_model_std[i] * zs_model_centroid[c][i];
  W->extracted++;
  return true;
}
static bool emit(void *ctx, const zs_detection_t *d) { world_t *W = ctx; (void)d; W->emitted++; return true; }
static void bearing(void *ctx, const zs_bearing_t *b, uint64_t end_sample, uint64_t track) {
  world_t *W = ctx;
  (void)end_sample; (void)track;
  for (unsigned s = 0u; s < 2u; s++)
    if (fabsf(fmodf(b->azimuth_deg - W->truth_az[s] + 540.0f, 360.0f) - 180.0f) <= 10.0f) W->toward[s]++;
  for (unsigned s = 0u; s < 2u; s++) {
    if (fabsf(b->f0_hz - W->truth_f0[s]) > 0.08f * W->truth_f0[s]) continue;
    const float e = fabsf(fmodf(b->azimuth_deg - W->truth_az[s] + 540.0f, 360.0f) - 180.0f);
    W->bearings[s]++;
    W->az_sum[s] += e;
    if (e > W->az_err_max[s]) W->az_err_max[s] = e;
    return;
  }
  W->other_f0 = b->f0_hz;
}

static float comb_next(source_t *s) {
  float v = 0.0f;
  for (unsigned k = 1u; k <= 24u && k * s->f0 < 3400.0f; k++) {
    s->phase[k - 1u] += 2.0 * M_PI * s->f0 * k / FS;
    v += (float)(pow((double)k, -0.7) * sin(s->phase[k - 1u] + 0.4 * k));
  }
  return 0.1f * v;
}

/* `seconds` of the two sources (az a0 and a1, elevation 10 deg) and a little noise into the ring, polled every 0.5 s */
static void run(zs_audio_ring_t *ring, zs_station_pipeline_t *p, source_t src[2], double seconds) {
  static uint32_t rng = 1u;
  for (unsigned hop = 0u; hop < (unsigned)(seconds * 2.0); hop++) {
    for (unsigned i = 0u; i < FS / 2u; i++) {
      float sum[4] = {0}, o[4];
      for (unsigned s = 0u; s < 2u; s++) {
        array_render_push(&src[s].r, src[s].gain * comb_next(&src[s]), o);
        for (unsigned c = 0u; c < 4u; c++) sum[c] += o[c];
      }
      int16_t frame[4];
      for (unsigned c = 0u; c < 4u; c++) {
        rng = rng * 1103515245u + 12345u;
        const float v = sum[c] + 0.01f * ((float)((rng >> 8) & 0xffff) / 65535.0f - 0.5f);
        frame[c] = (int16_t)(v * 20000.0f);
      }
      zs_audio_ring_push(ring, frame);
    }
    (void)zs_station_pipeline_poll(p, ring);
  }
}

static int16_t stash[ZS_PIPELINE_HOP_SAMPLES];

static void scenario(float az0, float az1, bool with_stash, bool tractor, world_t *W, zs_station_pipeline_t *P) {
  static source_t src[2];
  zs_audio_ring_t ring;
  const zs_station_pipeline_port_t port = {W, extract, NULL, emit, 21u, 3u, 0u, 0u, NULL, bearing};
  memset(W, 0, sizeof(*W));
  memset(src, 0, sizeof(src));
  W->tractor = tractor;
  src[0].f0 = 183.0f; src[1].f0 = 120.0f;
  src[0].gain = tractor ? 1.4f : 1.0f; src[1].gain = 1.0f;     /* the UAV is the louder: the mixture sounds like one */
  W->truth_f0[0] = 183.0f; W->truth_f0[1] = 120.0f;
  W->truth_az[0] = az0; W->truth_az[1] = az1;
  for (unsigned s = 0u; s < 2u; s++) {
    array_render_init(&src[s].r, NULL, (float)FS);
    array_render_set_direction(&src[s].r, s ? az1 : az0, 10.0f, 15.0f);
  }
  zs_audio_ring_init(&ring, ring_storage, RING_FRAMES, FS);
  assert(zs_station_pipeline_init(P, &port, scratch, window));
  if (with_stash) zs_station_pipeline_set_stash(P, stash);
  run(&ring, P, src, 30.0);
  printf("sources at %.0f / %.0f deg: windows %u mixture %u one-target %u, confirmed %u, bearings %u (mean err %.2f max %.2f) / %u (mean err %.2f max %.2f), "
         "comb asked %u computed %u | directions %u several %u classified %u bearings %u, toward %u / %u\n", az0, az1, P->windows,
         P->separated_windows, P->merged_windows, P->confirmed_windows,
         W->bearings[0], W->bearings[0] ? W->az_sum[0] / W->bearings[0] : 0.0f, W->az_err_max[0],
         W->bearings[1], W->bearings[1] ? W->az_sum[1] / W->bearings[1] : 0.0f, W->az_err_max[1], P->comb_stats.attempts, P->comb_stats.computed,
         P->doa_windows, P->doa_mixture_windows, P->doa_classified_windows, P->doa_bearings, W->toward[0], W->toward[1]);
}

int main(void) {
  static world_t W;
  static zs_station_pipeline_t P;
  /* two targets from two directions: both followed, each bearing its own source's direction and fundamental */
  scenario(40.0f, 230.0f, false, false, &W, &P);
  assert(P.separated_windows >= 10u && P.confirmed_windows >= 30u && W.emitted >= 1u);
  assert(W.bearings[0] >= 8u && W.bearings[1] >= 8u && W.other_f0 == 0.0f);
  assert(W.az_sum[0] / W.bearings[0] < 3.0f && W.az_sum[1] / W.bearings[1] < 3.0f);
  assert(P.doa_windows == 0u);                                  /* no stash: the directions are off */
  /* the same with a stash: classified by direction, each its own bearing and label */
  scenario(40.0f, 230.0f, true, false, &W, &P);
  assert(P.doa_mixture_windows >= 30u && P.doa_classified_windows >= 15u && P.doa_bearings >= 20u);
  assert(W.bearings[0] >= 8u && W.bearings[1] >= 8u && W.other_f0 == 0.0f);
  assert(W.az_sum[0] / W.bearings[0] < 1.0f && W.az_sum[1] / W.bearings[1] < 1.0f);   /* the first windows: comb bearings */
  assert(W.az_err_max[0] < 5.0f && W.az_err_max[1] < 5.0f);
  /* a UAV beside a tractor: the tractor's direction is never a target */
  scenario(40.0f, 230.0f, true, true, &W, &P);
  assert(P.doa_mixture_windows >= 30u && W.toward[0] >= 8u && W.toward[1] == 0u);
  /* the same two combs from one direction: one target (a multirotor's rotors), classified as one, one bearing */
  scenario(75.0f, 75.0f, false, false, &W, &P);
  assert(P.merged_windows >= 15u && P.separated_windows == 0u && P.confirmed_windows >= 30u);
  assert(W.bearings[0] + W.bearings[1] >= 15u && (W.bearings[0] == 0u || W.bearings[1] == 0u));   /* one source's bearings */
  /* ... and with a stash: one direction, no classification by direction, the same one bearing */
  scenario(75.0f, 75.0f, true, false, &W, &P);
  assert(P.doa_mixture_windows == 0u && P.confirmed_windows >= 30u);
  assert(W.bearings[0] + W.bearings[1] >= 15u && (W.bearings[0] == 0u || W.bearings[1] == 0u));
  printf("pipeline sources tests passed\n");
  return 0;
}

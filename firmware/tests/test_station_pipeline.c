/* Station audio pipeline: ring -> windows at 0.5 s hop -> features -> votes + gate -> level 1 -> detection events. */
#include "zs_station_pipeline.h"
#include "zs_model_centroids.h"
#include "zs_protocol.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RING_FRAMES 64000u   /* 2 s x 4 channels, as APP_AUDIO_RING_FRAMES_B1 */
static int16_t ring_storage[RING_FRAMES * ZS_AUDIO_CHANNELS];
static zs_complex_t scratch[ZS_AIR_SCRATCH_COMPLEX];
static int16_t window[ZS_PIPELINE_WINDOW_SAMPLES];

typedef struct {
  unsigned feature_centroid;       /* which centroid the stub extractor returns (de-normalized) */
  unsigned extracted, emitted;
  zs_detection_t last;
  uint64_t last_sample;
  bool refuse;
} world_t;

static bool extract(void *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) {
  world_t *W = ctx;
  assert(n == ZS_PIPELINE_WINDOW_SAMPLES && pcm);
  for (unsigned i = 0u; i < ZS_FEATURE_COUNT; i++) out[i] = zs_model_mean[i] + zs_model_std[i] * zs_model_centroid[W->feature_centroid][i];
  W->extracted++;
  return true;
}
static int64_t sample_time(void *ctx, uint64_t sample) { world_t *W = ctx; W->last_sample = sample; return 1800000000000000LL + (int64_t)sample * 1000000LL / 32000; }
static bool emit(void *ctx, const zs_detection_t *d) { world_t *W = ctx; if (W->refuse) return false; W->emitted++; W->last = *d; return true; }

/* piston-like comb at 94 Hz (16 teeth) or white noise, written to all four channels */
static void push_seconds(zs_audio_ring_t *r, double seconds, bool comb, unsigned *seed) {
  static double phase = 0.0;
  const unsigned n = (unsigned)(seconds * 32000.0);
  for (unsigned i = 0u; i < n; i++) {
    double v = 0.0;
    *seed = *seed * 1103515245u + 12345u;
    if (comb) {
      phase += 2.0 * M_PI * 94.0 / 32000.0;
      for (unsigned h = 1u; h <= 16u; h++) v += (1.0 / (double)h) * sin((double)h * phase + 0.2 * h);
      v = 0.3 * v + 0.02 * (((*seed >> 8) & 0xffff) / 65535.0 - 0.5);
    } else {
      v = 0.3 * (((*seed >> 8) & 0xffff) / 65535.0 - 0.5);
    }
    int16_t frame[ZS_AUDIO_CHANNELS];
    for (unsigned c = 0u; c < ZS_AUDIO_CHANNELS; c++) frame[c] = (int16_t)(v * 20000.0);
    zs_audio_ring_push(r, frame);
  }
}

/* Pushes audio in 0.5 s hops and polls after each hop (what the audio task does at 100 ms); returns windows processed. */
static unsigned step(zs_audio_ring_t *r, zs_station_pipeline_t *p, double seconds, bool comb, unsigned *seed) {
  unsigned done = 0u;
  for (unsigned i = 0u; i < (unsigned)(seconds / 0.5 + 0.5); i++) { push_seconds(r, 0.5, comb, seed); done += zs_station_pipeline_poll(p, r); }
  return done;
}

int main(void) {
  static world_t W;
  static zs_station_pipeline_t P;
  zs_audio_ring_t ring;
  unsigned seed = 7u;
  const unsigned uav_centroid = 0u, background_centroid = 43u;  /* FP-1 (class 1) / природный фон (class 18) */
  assert(zs_model_class_id[uav_centroid] == ZS_CLASS_PISTON_UAV && zs_model_class_id[background_centroid] == ZS_CLASS_WIND);
  const zs_station_pipeline_port_t port = {&W, extract, sample_time, emit, 12u, 0x5a5au, 0u, 6u};
  zs_audio_ring_init(&ring, ring_storage, RING_FRAMES, 32000u);
  assert(zs_station_pipeline_init(&P, &port, scratch, window));
  assert(zs_station_pipeline_poll(&P, &ring) == 0u && P.windows == 0u);     /* nothing captured yet */

  /* 3 s of background polled every 1.5 s (the 2 s ring holds everything): windows end at 1.0, 1.5 | 2.0, 2.5, 3.0 s */
  W.feature_centroid = background_centroid;
  assert(step(&ring, &P, 1.5, false, &seed) == 2u);
  assert(step(&ring, &P, 1.5, false, &seed) == 3u && P.windows == 5u && W.extracted == 5u && W.emitted == 0u);
  assert(P.presence.level == ZS_PRESENCE_NONE && !P.confirmed && P.windows_dropped == 0u);
  assert(zs_station_pipeline_poll(&P, &ring) == 0u);                          /* idempotent without new audio */

  /* a UAV arrives: comb + UAV features. Votes need 4 windows with a 5/8 majority, so the rising edge lands
     when the UAV windows outvote the background history. */
  W.feature_centroid = uav_centroid;
  assert(step(&ring, &P, 0.5, true, &seed) == 1u && W.emitted == 0u);          /* 1 UAV vote among 6 */
  assert(step(&ring, &P, 1.5, true, &seed) == 3u);
  printf("after 2 s of comb: level %u uav_votes %u weak %u comb %d gate f0 %.1f\n", P.presence.level, P.presence.uav_votes, P.presence.uav_weak_votes, P.presence.comb, P.last_gate.f0_hz);
  assert(P.last_window.class_id == ZS_CLASS_PISTON_UAV && P.last_window.confidence_u8 > 200u);
  assert(P.presence.level == ZS_PRESENCE_CONFIRMED && P.confirmed && W.emitted == 1u);
  /* the rising-edge event: identity, time from the sample counter, consensus + level-1 confidence, features */
  assert(W.last.schema_ver == 4u && W.last.station_id == 12u && W.last.boot_id == 0x5a5au && W.last.seq_no == 1u);
  assert(W.last.event_id == ((0x5a5aull << 32) | 1u) && W.last.sample_rate_hz == 32000u);
  assert(W.last.event_time_us == 1800000000000000LL + (int64_t)W.last_sample * 1000000LL / 32000 && W.last_sample % ZS_PIPELINE_HOP_SAMPLES == 0u);
  /* level 1 confirmed on gate + 4 UAV votes, before the 5/8 type consensus: the leading UAV class is named, `unknown` stays */
  assert(W.last.classification.class_id == ZS_CLASS_PISTON_UAV && W.last.classification.unknown && W.last.classification.confidence_u8 == P.presence.confidence_u8);
  assert(W.last.hierarchy.family_id == ZS_FAMILY_UNKNOWN && W.last.hierarchy.family_status == ZS_DECISION_CANDIDATE && W.last.detector_profile == 0u);
  assert(fabsf(W.last.features[0] - zs_model_mean[0] - zs_model_std[0] * zs_model_centroid[uav_centroid][0]) < 1e-3f);
  { uint8_t buf[600]; assert(zs_protocol_encode_detection(&W.last, buf, sizeof(buf)) > 100u); }   /* it is a valid wire event */

  /* keep-alive: an update every 6 windows (3 s) while confirmed; nothing on the intermediate windows */
  {
    const unsigned before = W.emitted, remaining = 6u - P.windows_since_event;
    assert(step(&ring, &P, 0.5 * (remaining - 1u), true, &seed) == remaining - 1u && W.emitted == before);
    assert(step(&ring, &P, 0.5, true, &seed) == 1u && W.emitted == before + 1u && W.last.seq_no == 2u);
    /* by now the votes are all UAV: the update carries the type consensus and the piston profile */
    assert(!W.last.classification.unknown && W.last.classification.class_id == ZS_CLASS_PISTON_UAV);
    assert(W.last.hierarchy.family_id == ZS_FAMILY_PROP_PISTON && W.last.hierarchy.family_status != ZS_DECISION_UNKNOWN && W.last.detector_profile == 1u);
    assert(step(&ring, &P, 3.0, true, &seed) == 6u && W.emitted == before + 2u);
  }
  /* the sink refuses: counted, the pipeline keeps going */
  W.refuse = true; (void)step(&ring, &P, 3.0, true, &seed);
  assert(P.events_refused == 1u && P.events_emitted == 3u); W.refuse = false;

  /* the UAV leaves: background again; level drops, no event; a new arrival is a new rising edge */
  W.feature_centroid = background_centroid;
  (void)step(&ring, &P, 4.0, false, &seed);
  assert(P.presence.level != ZS_PRESENCE_CONFIRMED && !P.confirmed);
  { const unsigned before = W.emitted;
    W.feature_centroid = uav_centroid; (void)step(&ring, &P, 4.0, true, &seed);
    assert(P.confirmed && W.emitted >= before + 1u); }

  /* ring overrun: 5 s pass without polling on a 2 s ring -> the lost hops are counted, analysis resumes */
  { const uint32_t w0 = P.windows;
    push_seconds(&ring, 5.0, true, &seed);
    const unsigned got = zs_station_pipeline_poll(&P, &ring);
    printf("overrun: %u windows processed, %u dropped\n", got, P.windows_dropped);
    assert(P.windows_dropped >= 6u && got >= 2u && got <= 3u && P.windows == w0 + got); }

  printf("station pipeline: %u windows, confirmed %u suspect %u engine %u, events %u refused %u\n",
         P.windows, P.confirmed_windows, P.suspect_windows, P.engine_windows, P.events_emitted, P.events_refused);
  printf("station pipeline tests passed\n");
  return 0;
}

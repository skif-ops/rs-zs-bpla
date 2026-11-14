/* End-to-end level 1 on the host: PCM16LE 32 kHz mono stream -> the station pipeline (zs_station_pipeline: AIR gate,
   a mixture's sources classified in turn with the others suppressed, zs_dsp features, centroid classifier votes,
   zs_presence), one line per 1 s window at 0.5 s hop.  The recording goes through the capture ring as on the station,
   as a plane wave from one direction on the 3+1 array: channel 1 is the recording itself (the analysed one, so the
   classifier sees exactly the file), the others the recording at their arrival offsets (windowed-sinc fractional
   delay over the whole file).  The bearings of a mixture run too: all its combs come from one direction, as for one
   target.
   Used by server/tools/eval_presence_wavs.py. */
#include "zs_dsp.h"
#include "zs_spatial.h"
#include "zs_station_pipeline.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static zs_complex_t scratch[ZS_AIR_SCRATCH_COMPLEX];
static int16_t window[ZS_PIPELINE_WINDOW_SAMPLES] __attribute__((aligned(4)));
static zs_dsp_ctx_t dsp;
static zs_station_pipeline_t pipeline;
#define RING_FRAMES 36000u
static int16_t ring_storage[RING_FRAMES * ZS_AUDIO_CHANNELS];
static zs_audio_ring_t ring;
#define SINC_HALF 8
/* the recording at a fractional sample position (Hann-windowed sinc, 17 taps; zero outside) */
static float at(const int16_t *x, size_t n, double pos) {
  const long i0 = (long)floor(pos);
  const double fr = pos - (double)i0;
  double acc = 0.0;
  for (long k = -SINC_HALF; k <= SINC_HALF; k++) {
    const long i = i0 + k;
    if (i < 0 || (size_t)i >= n) continue;
    const double d = (double)k - fr;
    const double sinc = fabs(d) < 1e-9 ? 1.0 : sin(M_PI * d) / (M_PI * d);
    const double w = 0.5 + 0.5 * cos(M_PI * d / (SINC_HALF + 1));
    acc += x[i] * sinc * w;
  }
  return (float)acc;
}
static bool extract(void *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) { (void)ctx; return zs_dsp_extract_1s(&dsp, pcm, n, out); }
static bool emit(void *ctx, const zs_detection_t *d) { (void)ctx; (void)d; return true; }
static const char *level_name(uint8_t l) { return l == ZS_PRESENCE_CONFIRMED ? "confirmed" : l == ZS_PRESENCE_ENGINE_UNCONFIRMED ? "engine" : l == ZS_PRESENCE_SUSPECT ? "suspect" : "none"; }
int main(int argc, char **argv) {
  static const zs_station_pipeline_port_t port = {NULL, extract, NULL, emit, 1u, 1u, 0u, 0u, NULL, NULL};
  if (argc != 2) { fprintf(stderr, "usage: presence_eval <pcm16le-32k-mono>\n"); return 2; }
  FILE *f = fopen(argv[1], "rb");
  if (!f) return 3;
  fseek(f, 0, SEEK_END); long bytes = ftell(f); fseek(f, 0, SEEK_SET);
  size_t n = (size_t)bytes / sizeof(int16_t);
  int16_t *pcm = malloc(n * sizeof(int16_t));
  if (!pcm || fread(pcm, sizeof(int16_t), n, f) != n) { fclose(f); return 4; }
  fclose(f);
  zs_dsp_init(&dsp);
  if (!zs_station_pipeline_init(&pipeline, &port, scratch, window)) return 7;
  printf("window,start_s,class_id,class_conf,gate_present,gate_conf,gate_f0_hz,uav_votes,ground_votes,level,confidence,secondary_count,secondary_f0_1_hz,secondary_f0_2_hz,sources_confirmed\n");
  zs_audio_ring_init(&ring, ring_storage, RING_FRAMES, ZS_AIR_SAMPLE_RATE);
  zs_spatial_geometry_t geometry;
  float tdoa_us[ZS_SPATIAL_REF_TDOA_COUNT];
  zs_spatial_geometry_3p1_default(&geometry);
  if (!zs_spatial_reference_tdoas_from_angles(&geometry, 37.0f, 12.0f, 15.0f, tdoa_us)) return 8;
  size_t pushed = 0u;
  for (size_t i = 0u;; i++) {
    while (!pipeline.pending && pushed < n && !zs_station_pipeline_fetch(&pipeline, &ring)) {
      int16_t frame[ZS_AUDIO_CHANNELS];
      frame[0] = pcm[pushed];
      for (unsigned c = 1u; c < ZS_AUDIO_CHANNELS; c++) {
        const float v = at(pcm, n, (double)pushed - tdoa_us[c - 1u] * 1e-6 * ZS_AIR_SAMPLE_RATE);
        frame[c] = (int16_t)(v > 32767.0f ? 32767.0f : (v < -32768.0f ? -32768.0f : v));
      }
      zs_audio_ring_push(&ring, frame);
      pushed++;
    }
    if (!pipeline.pending) break;
    const size_t start = (size_t)(pipeline.pending_end - ZS_PIPELINE_WINDOW_SAMPLES);
    if (!zs_station_pipeline_run_pending(&pipeline)) return 6;
    const zs_air_gate_result_t *g = &pipeline.last_gate;
    const zs_presence_t *p = &pipeline.presence;
    unsigned confirmed_sources = 0u;
    for (unsigned s = 0u; s < pipeline.source_count; s++)
      confirmed_sources += pipeline.sources[pipeline.source_of[s]].presence.level == ZS_PRESENCE_CONFIRMED;
    printf("%zu,%.1f,%u,%u,%d,%u,%.1f,%u,%u,%s,%u,%u,%.1f,%.1f,%u\n", i, (double)start / ZS_AIR_SAMPLE_RATE, pipeline.last_window.class_id,
           pipeline.last_window.confidence_u8, g->present, g->confidence_u8, g->f0_hz, p->uav_votes, p->ground_votes, level_name(p->level),
           p->confidence_u8, g->secondary_count, g->secondary_f0_hz[0], g->secondary_f0_hz[1], confirmed_sources);
  }
  fprintf(stderr, "mixture windows %lu, of one target %lu; comb bearings asked %lu computed %lu (few bins %lu, weak %lu, unsolved %lu)\n",
          (unsigned long)pipeline.separated_windows, (unsigned long)pipeline.merged_windows, (unsigned long)pipeline.comb_stats.attempts,
          (unsigned long)pipeline.comb_stats.computed, (unsigned long)pipeline.comb_stats.few_bins, (unsigned long)pipeline.comb_stats.weak,
          (unsigned long)pipeline.comb_stats.unsolved);
  free(pcm);
  return 0;
}

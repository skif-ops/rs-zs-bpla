/* End-to-end level 1 on the host: PCM16LE 32 kHz mono stream -> zs_dsp features -> centroid classifier votes
   (zs_classifier_consensus) + AIR gate (zs_air_gate) -> zs_presence, one line per 1 s window at 0.5 s hop.
   Used by server/tools/eval_presence_wavs.py. */
#include "zs_air_gate.h"
#include "zs_classifier.h"
#include "zs_classifier_consensus.h"
#include "zs_dsp.h"
#include "zs_presence.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static zs_complex_t scratch[ZS_AIR_SCRATCH_COMPLEX];
static zs_air_gate_t gate;
static const char *level_name(uint8_t l) { return l == ZS_PRESENCE_CONFIRMED ? "confirmed" : l == ZS_PRESENCE_ENGINE_UNCONFIRMED ? "engine" : l == ZS_PRESENCE_SUSPECT ? "suspect" : "none"; }
int main(int argc, char **argv) {
  if (argc != 2) { fprintf(stderr, "usage: presence_eval <pcm16le-32k-mono>\n"); return 2; }
  FILE *f = fopen(argv[1], "rb");
  if (!f) return 3;
  fseek(f, 0, SEEK_END); long bytes = ftell(f); fseek(f, 0, SEEK_SET);
  size_t n = (size_t)bytes / sizeof(int16_t);
  int16_t *pcm = malloc(n * sizeof(int16_t));
  if (!pcm || fread(pcm, sizeof(int16_t), n, f) != n) { fclose(f); return 4; }
  fclose(f);
  zs_dsp_ctx_t dsp; zs_dsp_init(&dsp);
  zs_classifier_consensus_t votes; zs_classifier_consensus_init(&votes);
  zs_air_gate_init(&gate);
  printf("window,start_s,class_id,class_conf,gate_present,gate_conf,gate_f0_hz,uav_votes,ground_votes,level,confidence\n");
  for (size_t start = 0u, i = 0u; start + ZS_AIR_WINDOW_SAMPLES <= n; start += ZS_AIR_WINDOW_SAMPLES / 2u, i++) {
    float feat[ZS_FEATURE_COUNT];
    zs_classification_t c; zs_hier_classification_t h;
    zs_air_gate_result_t g;
    if (!zs_dsp_extract_1s(&dsp, pcm + start, ZS_AIR_WINDOW_SAMPLES, feat)) return 5;
    const zs_classifier_result_t w = zs_classifier_predict_centroid(feat);
    (void)zs_classifier_consensus_push(&votes, w, &c, &h);
    if (!zs_air_gate_push(&gate, pcm + start, ZS_AIR_WINDOW_SAMPLES, scratch, &g)) return 6;
    const zs_presence_t p = zs_presence_evaluate(&votes, &g);
    printf("%zu,%.1f,%u,%u,%d,%u,%.1f,%u,%u,%s,%u\n", i, (double)start / ZS_AIR_SAMPLE_RATE, w.class_id, w.confidence_u8, g.present, g.confidence_u8, g.f0_hz, p.uav_votes, p.ground_votes, level_name(p.level), p.confidence_u8);
  }
  free(pcm);
  return 0;
}

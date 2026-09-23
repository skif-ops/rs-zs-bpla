/* Runs the station AIR gate over a whole PCM16LE mono 32 kHz stream (1 s windows, 0.5 s hop) and prints
   one line per window: index, start_s, f0, contrast_db, harmonics, comb, persistence, cv, present, confidence.
   Used by server/tools/eval_air_gate_wavs.py. */
#include "zs_air_gate.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static zs_complex_t scratch[ZS_AIR_FFT];
static zs_air_gate_t gate;
int main(int argc, char **argv) {
  if (argc != 2) { fprintf(stderr, "usage: air_gate_eval <pcm16le-32k-mono>\n"); return 2; }
  FILE *f = fopen(argv[1], "rb");
  if (!f) return 3;
  fseek(f, 0, SEEK_END); long bytes = ftell(f); fseek(f, 0, SEEK_SET);
  size_t n = (size_t)bytes / sizeof(int16_t);
  int16_t *pcm = malloc(n * sizeof(int16_t));
  if (!pcm || fread(pcm, sizeof(int16_t), n, f) != n) { fclose(f); return 4; }
  fclose(f);
  zs_air_gate_init(&gate);
  const size_t hop = ZS_AIR_WINDOW_SAMPLES / 2u;
  printf("window,start_s,f0_hz,contrast_db,snr_db,harmonics,comb,persistence,steadiness_cv,present,confidence\n");
  for (size_t start = 0u, i = 0u; start + ZS_AIR_WINDOW_SAMPLES <= n; start += hop, i++) {
    zs_air_gate_result_t r;
    if (!zs_air_gate_push(&gate, pcm + start, ZS_AIR_WINDOW_SAMPLES, scratch, &r)) return 5;
    const zs_air_window_t *w = zs_air_gate_last(&gate);
    printf("%zu,%.1f,%.2f,%.2f,%.2f,%u,%d,%.3f,%.4f,%d,%u\n", i, (double)start / ZS_AIR_SAMPLE_RATE, w->f0_hz, w->contrast_db, w->snr_db, w->harmonic_count, w->comb, r.persistence, r.steadiness_cv, r.present, r.confidence_u8);
  }
  free(pcm);
  return 0;
}

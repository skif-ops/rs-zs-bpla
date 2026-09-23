/* Same contract as eval_golden.c but through the MCU extractor (zs_dsp_mcu): one 1 s PCM16LE window -> 43 features. */
#include "zs_dsp_mcu.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  FILE *f = fopen(argv[1], "rb");
  if (!f) return 3;
  int16_t *pcm = malloc(32000 * sizeof(int16_t));
  if (!pcm) return 4;
  size_t n = fread(pcm, sizeof(int16_t), 32000, f);
  fclose(f);
  if (n != 32000) { free(pcm); return 5; }
  static zs_dsp_ctx_t ctx;
  zs_dsp_mcu_init(&ctx);
  float v[ZS_FEATURE_COUNT];
  if (!zs_dsp_mcu_extract_1s(&ctx, pcm, 32000, v)) { free(pcm); return 6; }
  for (unsigned i = 0; i < ZS_FEATURE_COUNT; i++) printf(i ? ",%.9g" : "%.9g", v[i]);
  printf("\n");
  free(pcm);
  return 0;
}

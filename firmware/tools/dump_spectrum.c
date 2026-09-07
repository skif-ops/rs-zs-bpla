#include "zs_dsp.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
  if (argc != 3) {
    return 2;
  }

  FILE *in = fopen(argv[1], "rb");
  if (!in) {
    return 3;
  }

  int16_t *pcm = malloc(32000u * sizeof(*pcm));
  if (!pcm) {
    fclose(in);
    return 4;
  }
  const size_t samples = fread(pcm, sizeof(*pcm), 32000u, in);
  if (fclose(in) != 0 || samples != 32000u) {
    free(pcm);
    return 5;
  }

  float *magnitude = malloc(16001u * sizeof(*magnitude));
  if (!magnitude) {
    free(pcm);
    return 6;
  }
  if (!zs_dsp_debug_global_magnitude(pcm, 32000u, magnitude, 16001u)) {
    free(magnitude);
    free(pcm);
    return 7;
  }
  free(pcm);

  FILE *out = fopen(argv[2], "wb");
  if (!out) {
    free(magnitude);
    return 8;
  }
  const size_t written = fwrite(magnitude, sizeof(*magnitude), 16001u, out);
  const int close_result = fclose(out);
  free(magnitude);

  if (written != 16001u || close_result != 0) {
    return 9;
  }
  return 0;
}

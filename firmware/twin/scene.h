#ifndef TWIN_SCENE_H
#define TWIN_SCENE_H
/* Synthetic acoustic scenes for the station twin: 32 kHz mono, deterministic (xorshift RNG), 4 identical channels
   pushed to the audio ring (per-channel delays for TDOA come with the multi-station phase). */
#include <stdint.h>
#include <stddef.h>

typedef enum { SCENE_SILENCE = 0, SCENE_DRONE_FLYBY, SCENE_GROUND_VEHICLE } scene_kind_t;

typedef struct {
  scene_kind_t kind;
  uint32_t start_ms, end_ms;     /* when the source is audible (the background noise is always there) */
  float f0_hz;                   /* drone: blade-pass fundamental */
  float level;                   /* 0..1 */
} scene_segment_t;

typedef struct {
  const scene_segment_t *segments;
  size_t count;
  float noise;                   /* background level 0..1 */
  uint32_t rng;
  double phase[24];
  double pink;
  uint64_t sample;
} scene_t;

void scene_init(scene_t *s, const scene_segment_t *segments, size_t count, float noise, uint32_t seed);
/* Next mono sample in [-1, 1]. */
float scene_next(scene_t *s);
#endif

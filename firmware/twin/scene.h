#ifndef TWIN_SCENE_H
#define TWIN_SCENE_H
/* Synthetic acoustic scenes for the station twin: 32 kHz, deterministic (xorshift RNG).  The source part is rendered
   onto the 3+1 array as a plane wave from the segment's direction (array_render.h); the background is diffuse:
   independent per microphone (channel 0 keeps the historical mono sequence). */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

typedef enum { SCENE_SILENCE = 0, SCENE_DRONE_FLYBY, SCENE_GROUND_VEHICLE } scene_kind_t;

typedef struct {
  scene_kind_t kind;
  uint32_t start_ms, end_ms;     /* when the source is audible (the background noise is always there) */
  float f0_hz;                   /* drone: blade-pass fundamental */
  float level;                   /* 0..1 */
  float az_start_deg, az_end_deg; /* direction of arrival, linear over the segment (0/0 = north on the horizon) */
  float el_deg;
} scene_segment_t;

typedef struct {
  const scene_segment_t *segments;
  size_t count;
  float noise;                   /* background level 0..1 */
  uint32_t rng;
  double phase[24];
  double pink;
  uint64_t sample;
  uint32_t bg_rng[3];            /* independent backgrounds of microphones 2..4 */
  double bg_pink[3];
} scene_t;

void scene_init(scene_t *s, const scene_segment_t *segments, size_t count, float noise, uint32_t seed);
/* Next mono sample in [-1, 1] (source + background of microphone 1). */
float scene_next(scene_t *s);
/* Next sample split into the source (to be rendered per microphone) and the background of microphone 1. */
void scene_next_parts(scene_t *s, float *source, float *background);
/* Background of microphone ch (1..3) for the same sample: same statistics, independent. */
float scene_background(scene_t *s, unsigned ch);
/* Direction of the audible source at the current sample (the first active segment); false when none. */
bool scene_direction(const scene_t *s, float *azimuth_deg, float *elevation_deg);
#endif

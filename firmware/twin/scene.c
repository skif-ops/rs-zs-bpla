#include "scene.h"
#include <math.h>

#define SR 32000.0

static float rnd(scene_t *s) { s->rng ^= s->rng << 13; s->rng ^= s->rng >> 17; s->rng ^= s->rng << 5; return ((float)(s->rng & 0xffffffu) / 8388608.0f) - 1.0f; }
static float gauss(scene_t *s) { return 0.866f * (rnd(s) + rnd(s) + rnd(s)); }   /* variance ~1 */

void scene_init(scene_t *s, const scene_segment_t *segments, size_t count, float noise, uint32_t seed) {
  size_t i;
  s->segments = segments; s->count = count; s->noise = noise; s->rng = seed ? seed : 0x9e3779b9u;
  for (i = 0u; i < 24u; i++) s->phase[i] = 0.0;
  s->pink = 0.0; s->sample = 0u;
}

float scene_next(scene_t *s) {
  const double t = (double)s->sample / SR;
  const uint32_t ms = (uint32_t)(t * 1000.0);
  float out = 0.0f;
  for (size_t i = 0u; i < s->count; i++) {
    const scene_segment_t *g = &s->segments[i];
    double env, dur, mid, f;
    if (ms < g->start_ms || ms >= g->end_ms) continue;
    dur = (double)(g->end_ms - g->start_ms) / 1000.0; mid = (double)g->start_ms / 1000.0 + dur / 2.0;
    if (g->kind == SCENE_DRONE_FLYBY) {
      /* approach - closest - recede: Gaussian level profile, slight Doppler-like f0 drift and rotor wobble */
      const double x = (t - mid) / (dur / 4.0);
      env = 0.05 + 0.95 * exp(-x * x);
      f = g->f0_hz * (1.0 + 0.03 * tanh(-(t - mid) / (dur / 6.0)) + 0.015 * sin(2.0 * M_PI * 0.7 * t) + 0.004 * sin(2.0 * M_PI * 7.3 * t));
      for (unsigned k = 1u; k <= 18u; k++) {
        const double amp = (1.0 / pow((double)k, 0.9)) * (1.0 + 0.3 * sin(2.0 * M_PI * 0.3 * k * t));
        s->phase[k - 1u] += 2.0 * M_PI * f * k / SR;
        out += (float)(amp * sin(s->phase[k - 1u]));
      }
      out *= (float)(env * 0.25 * g->level);
    } else if (g->kind == SCENE_GROUND_VEHICLE) {
      for (unsigned k = 1u; k <= 6u; k++) { s->phase[18u + k - 1u] += 2.0 * M_PI * 32.0 * k / SR; out += (float)(sin(s->phase[18u + k - 1u]) / k); }
      out = out * 0.25f * g->level + 0.6f * g->level * gauss(s) * 0.15f;
    }
  }
  /* background: broadband ambient (white + a slow low-frequency wander), no harmonic structure */
  s->pink = 0.995 * s->pink + gauss(s) * 0.02;
  out += s->noise * (float)(0.6 * gauss(s) + s->pink);
  s->sample++;
  return out > 1.0f ? 1.0f : (out < -1.0f ? -1.0f : out);
}

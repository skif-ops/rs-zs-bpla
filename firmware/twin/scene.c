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
  for (i = 0u; i < 3u; i++) { s->bg_rng[i] = (s->rng ^ (0x85ebca6bu * (uint32_t)(i + 1u))) | 1u; s->bg_pink[i] = 0.0; }
}

static float rnd_state(uint32_t *r) { *r ^= *r << 13; *r ^= *r >> 17; *r ^= *r << 5; return ((float)(*r & 0xffffffu) / 8388608.0f) - 1.0f; }

float scene_background(scene_t *s, unsigned ch) {
  uint32_t *r;
  float g1, g2;
  if (ch < 1u || ch > 3u) return 0.0f;
  r = &s->bg_rng[ch - 1u];
  g1 = 0.866f * (rnd_state(r) + rnd_state(r) + rnd_state(r));
  g2 = 0.866f * (rnd_state(r) + rnd_state(r) + rnd_state(r));
  s->bg_pink[ch - 1u] = 0.995 * s->bg_pink[ch - 1u] + g1 * 0.02;
  return s->noise * (float)(0.6 * g2 + s->bg_pink[ch - 1u]);
}

bool scene_direction(const scene_t *s, float *azimuth_deg, float *elevation_deg) {
  const uint32_t ms = (uint32_t)((double)s->sample / SR * 1000.0);
  for (size_t i = 0u; i < s->count; i++) {
    const scene_segment_t *g = &s->segments[i];
    if (ms < g->start_ms || ms >= g->end_ms) continue;
    const float f = (float)(ms - g->start_ms) / (float)(g->end_ms - g->start_ms);
    *azimuth_deg = g->az_start_deg + f * (g->az_end_deg - g->az_start_deg);
    *elevation_deg = g->el_deg;
    return true;
  }
  return false;
}

float scene_next(scene_t *s) {
  float src, bg, out;
  scene_next_parts(s, &src, &bg);
  out = src + bg;
  return out > 1.0f ? 1.0f : (out < -1.0f ? -1.0f : out);
}

void scene_next_parts(scene_t *s, float *source, float *background) {
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
  *source = out;
  *background = s->noise * (float)(0.6 * gauss(s) + s->pink);
  s->sample++;
}

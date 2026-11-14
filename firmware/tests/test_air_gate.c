/* Station AIR gate: synthetic sources (comb, noise, chirp, impulses, mains, two combs at once) and the 100 «Лютый» golden windows. */
#include "zs_air_gate.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static zs_complex_t scratch[ZS_AIR_SCRATCH_COMPLEX];
static int16_t pcm[ZS_AIR_WINDOW_SAMPLES];
static uint32_t rng = 12345u;
static float noise(void) { rng = rng * 1664525u + 1013904223u; return ((float)(rng >> 8) / 16777216.0f - 0.5f) * 2.0f; }

/* Comb of `harm` harmonics on f0 (with a slow drift ratio per second, or a siren-like ±wobble with a 2 s period when
   wobble > 0), plus white noise of the given relative level. */
static float g_wobble;
static void synth_comb(float f0, unsigned harm, float noise_level, float drift, unsigned second) {
  double phase[24] = {0};
  for (unsigned i = 0u; i < ZS_AIR_WINDOW_SAMPLES; i++) {
    double t = (double)second + (double)i / ZS_AIR_SAMPLE_RATE;
    float f = f0 * (1.0f + drift * (float)t + g_wobble * sinf(2.0f * (float)M_PI * (float)t / 2.0f));
    float s = 0.0f;
    for (unsigned k = 1u; k <= harm; k++) { phase[k] += 2.0 * M_PI * f * k / ZS_AIR_SAMPLE_RATE; s += (float)sin(phase[k]) / (float)k; }
    s = s * 0.3f + noise_level * noise();
    if (s > 0.99f) s = 0.99f;
    if (s < -0.99f) s = -0.99f;
    pcm[i] = (int16_t)(s * 32767.0f);
  }
}

/* Two combs at once (two targets): f0a and f0b with 8 harmonics each (1/k), the second `gain_b` as loud, slow
   Doppler drifts of 0.2 and 0.1 %/s, plus white noise. */
static void synth_two(float f0a, float f0b, float gain_b, unsigned second) {
  static double pa[9], pb[9];
  if (second == 0u) { memset(pa, 0, sizeof(pa)); memset(pb, 0, sizeof(pb)); }
  for (unsigned i = 0u; i < ZS_AIR_WINDOW_SAMPLES; i++) {
    const double t = (double)second + (double)i / ZS_AIR_SAMPLE_RATE;
    const double fa = f0a * (1.0 + 0.002 * t), fb = f0b * (1.0 + 0.001 * t);
    float s = 0.0f;
    for (unsigned k = 1u; k <= 8u; k++) {
      pa[k] += 2.0 * M_PI * fa * k / ZS_AIR_SAMPLE_RATE; pb[k] += 2.0 * M_PI * fb * k / ZS_AIR_SAMPLE_RATE;
      s += (float)(sin(pa[k]) + gain_b * sin(pb[k])) / (float)k;
    }
    s = s * 0.2f + 0.05f * noise();
    if (s > 0.99f) s = 0.99f;
    if (s < -0.99f) s = -0.99f;
    pcm[i] = (int16_t)(s * 32767.0f);
  }
}

static void synth_noise(float level) { for (unsigned i = 0u; i < ZS_AIR_WINDOW_SAMPLES; i++) pcm[i] = (int16_t)(level * noise() * 32767.0f); }
static void synth_chirp(void) { /* bird-like sweep 2..4 kHz plus noise: tonal but out of band / unsteady */
  for (unsigned i = 0u; i < ZS_AIR_WINDOW_SAMPLES; i++) { float t = (float)i / ZS_AIR_SAMPLE_RATE; float f = 2000.0f + 2000.0f * t; pcm[i] = (int16_t)((0.4f * sinf(2.0f * (float)M_PI * f * t) + 0.05f * noise()) * 32767.0f); }
}
static void synth_impulses(void) { /* gunfire-like clicks over a low noise floor */
  synth_noise(0.02f);
  for (unsigned c = 0u; c < 6u; c++) { unsigned at = 3000u + c * 5000u; for (unsigned i = 0u; i < 300u; i++) pcm[at + i] = (int16_t)(0.9f * 32767.0f * expf(-(float)i / 40.0f) * noise()); }
}

static zs_air_gate_t gate;
static void run_sequence(void (*gen)(unsigned), unsigned seconds, zs_air_gate_result_t *last) {
  zs_air_gate_init(&gate);
  for (unsigned s = 0u; s < seconds; s++) { gen(s); assert(zs_air_gate_push(&gate, pcm, ZS_AIR_WINDOW_SAMPLES, scratch, last)); }
}

static void gen_drone(unsigned s) { synth_comb(73.0f, 12u, 0.08f, 0.01f, s); }        /* piston-like comb, slow Doppler drift */
static void gen_quad(unsigned s) { synth_comb(170.0f, 6u, 0.15f, 0.005f, s); }        /* high blade-pass, few harmonics in band */
static void gen_noise(unsigned s) { (void)s; synth_noise(0.3f); }
static void gen_chirp(unsigned s) { (void)s; synth_chirp(); }
static void gen_impulses(unsigned s) { (void)s; synth_impulses(); }
static void gen_mains(unsigned s) { synth_comb(50.0f, 8u, 0.05f, 0.0f, s); }           /* rock-steady 50 Hz comb = hum */
static void gen_unsteady(unsigned s) { synth_comb(60.0f, 8u, 0.05f, 0.15f, s); }   /* siren-like glide, +15 %/s: 60 -> 114 Hz over 6 s */

static void gen_two(unsigned s) { synth_two(120.0f, 183.0f, 0.7f, s); }   /* 120 + 183 Hz: both near multiples of 61 Hz */

/* Two sources at once (zs_air_gate.h): the single-comb fit takes their common sub-harmonic, 61 Hz, which the gate
   would reject as mains; the gate finds both combs instead, tracks the stronger one and reports the other for
   suppression.  A single source never gets a secondary comb. */
static void test_two_sources(void) {
  zs_air_gate_result_t r;
  unsigned separated = 0u, present = 0u;
  zs_air_gate_init(&gate);
  for (unsigned s = 0u; s < 20u; s++) {
    gen_two(s);
    assert(zs_air_gate_push(&gate, pcm, ZS_AIR_WINDOW_SAMPLES, scratch, &r));
    if (s < 6u) continue;
    if (r.present) present++;
    if (r.secondary_count == 1u) {
      separated++;
      /* the stronger comb is the gate's line, the other one the secondary */
      const float lo = fminf(gate.f0_hz, r.secondary_f0_hz[0]), hi = fmaxf(gate.f0_hz, r.secondary_f0_hz[0]);
      assert(fabsf(lo - 120.0f) < 8.0f && fabsf(hi - 183.0f) < 8.0f && !r.mains);
    }
  }
  printf("air gate two sources: present %u/14, separated %u/14 (main %.1f Hz, other %.1f Hz)\n", present, separated, r.f0_hz, r.secondary_f0_hz[0]);
  assert(present >= 12u && separated >= 12u);
  run_sequence(gen_drone, 20u, &r);    assert(r.present && r.secondary_count == 0u);
  run_sequence(gen_quad, 20u, &r);     assert(r.present && r.secondary_count == 0u);
  /* the suppression removes the other comb's lines and leaves the tracked one */
  {
    float before_b = 0.0f, after_b = 0.0f, before_a = 0.0f, after_a = 0.0f;
    static int16_t copy[ZS_AIR_WINDOW_SAMPLES];
    run_sequence(gen_two, 20u, &r);
    gen_two(20u);
    memcpy(copy, pcm, sizeof(copy));
    zs_air_gate_suppress_secondary(copy, ZS_AIR_WINDOW_SAMPLES, &r);
    for (unsigned k = 1u; k <= 3u; k++) {   /* Goertzel-like power at the first teeth of each comb */
      const bool a_main = fabsf(gate.f0_hz - 120.0f) < fabsf(gate.f0_hz - 183.0f);
      const float f120 = 120.0f * (1.0f + 0.002f * 20.5f) * (float)k, f183 = 183.0f * (1.0f + 0.001f * 20.5f) * (float)k;
      const float fa = a_main ? f120 : f183, fb = a_main ? f183 : f120;   /* a: the tracked comb, b: the other */
      float ar = 0, ai = 0, br = 0, bi = 0, ar2 = 0, ai2 = 0, br2 = 0, bi2 = 0;
      for (unsigned i = 0u; i < ZS_AIR_WINDOW_SAMPLES; i++) {
        const float t = (float)i / ZS_AIR_SAMPLE_RATE, ca = cosf(2.0f * (float)M_PI * fa * t), sa = sinf(2.0f * (float)M_PI * fa * t);
        const float cb = cosf(2.0f * (float)M_PI * fb * t), sb = sinf(2.0f * (float)M_PI * fb * t);
        ar += pcm[i] * ca; ai += pcm[i] * sa; br += pcm[i] * cb; bi += pcm[i] * sb;
        ar2 += copy[i] * ca; ai2 += copy[i] * sa; br2 += copy[i] * cb; bi2 += copy[i] * sb;
      }
      before_a += ar * ar + ai * ai; after_a += ar2 * ar2 + ai2 * ai2; before_b += br * br + bi * bi; after_b += br2 * br2 + bi2 * bi2;
    }
    printf("  suppression: tracked comb %.1f dB, other comb %.1f dB\n", 10.0f * log10f(after_a / before_a), 10.0f * log10f(after_b / before_b));
    assert(after_b < 0.25f * before_b && after_a > 0.5f * before_a);   /* at least 6 dB off the other comb, the tracked one kept */
  }
}

static void test_synthetic(void) {
  zs_air_gate_result_t r;
  run_sequence(gen_drone, 1u, &r);
  { const zs_air_window_t *w = zs_air_gate_last(&gate); assert(w && fabsf(gate.f0_hz - 73.0f) < 1.5f && w->harmonic_count >= 8u && w->snr_db > 12.0f && w->contrast_db > 12.0f && w->comb && !r.present); } /* one window: comb seen, gate needs history */
  run_sequence(gen_drone, 6u, &r);     assert(r.present && !r.mains && r.persistence == 1.0f && r.steadiness_cv < 0.12f && fabsf(r.f0_hz - 73.0f) < 6.0f && r.confidence_u8 > 180u);
  run_sequence(gen_quad, 6u, &r);      assert(r.present && r.harmonic_count >= 4u);
  run_sequence(gen_noise, 6u, &r);     assert(!r.present && r.persistence < 0.35f);
  run_sequence(gen_chirp, 6u, &r);     assert(!r.present);
  run_sequence(gen_impulses, 6u, &r);  assert(!r.present);
  run_sequence(gen_mains, 6u, &r);     assert(!r.present && r.mains);
  run_sequence(gen_unsteady, 6u, &r);  assert(!r.present && r.steadiness_cv > 0.12f);
  printf("air gate synthetic ok\n");
}

/* Golden windows of the Lyuty recording (server/tools/golden_lyuty): vec_000..015 = file 1 (sequential 0.5 s
   hop, loud close pass), vec_016..031 = file 2 (maneuvering, weaker), vec_032..099 = file 3 (55 s, sampled,
   distant/windy).  The gate is asserted on file 1; the other files are reported for the record. */
static void test_lyuty(const char *dir) {
  char path[512];
  unsigned comb_windows = 0u, present_file1 = 0u, present_file2 = 0u, present_file3 = 0u;
  zs_air_gate_init(&gate);
  for (unsigned v = 0u; v < 100u; v++) {
    zs_air_gate_result_t r;
    snprintf(path, sizeof(path), "%s/pcm16le/vec_%03u.bin", dir, v);
    FILE *f = fopen(path, "rb");
    if (!f) { printf("air gate lyuty: %s not found, skipped\n", path); return; }
    size_t n = fread(pcm, sizeof(int16_t), ZS_AIR_WINDOW_SAMPLES, f); fclose(f);
    assert(n == ZS_AIR_WINDOW_SAMPLES);
    if (v == 16u || v == 32u) zs_air_gate_init(&gate);   /* new source file */
    assert(zs_air_gate_push(&gate, pcm, ZS_AIR_WINDOW_SAMPLES, scratch, &r));
    const zs_air_window_t *w = zs_air_gate_last(&gate);
    if (w->comb) comb_windows++;
    if (v >= 2u && v < 16u && r.present) present_file1++;
    if (v >= 18u && v < 32u && r.present) present_file2++;
    if (v >= 34u && r.present) present_file3++;
    if (v % 10u == 0u) printf("  vec_%03u f0 %.1f Hz contrast %.1f dB harmonics %u -> persistence %.2f cv %.3f present %d\n", v, w->f0_hz, w->contrast_db, w->harmonic_count, r.persistence, r.steadiness_cv, r.present);
  }
  printf("air gate lyuty: comb windows %u/100; present: file 1 %u/14, file 2 %u/14, file 3 %u/66\n", comb_windows, present_file1, present_file2, present_file3);
  assert(comb_windows >= 30u);
  assert(present_file1 >= 12u);
  assert(present_file2 >= 8u);
}

int main(int argc, char **argv) {
  test_synthetic();
  test_two_sources();
  test_lyuty(argc > 1 ? argv[1] : "../server/tools/golden_lyuty");
  printf("air gate tests passed\n");
  return 0;
}

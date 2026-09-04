#include "zs_spatial.h"

#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static float angle_error(float a, float b) {
  float d = fmodf(a - b + 540.0f, 360.0f) - 180.0f;
  return fabsf(d);
}

static uint32_t prng_state = 0x12345678u;
static int16_t noise_sample(void) {
  prng_state = prng_state * 1664525u + 1013904223u;
  return (int16_t)((int32_t)(prng_state >> 16) - 32768);
}

static void test_geometry_and_roundtrip(void) {
  zs_spatial_geometry_t g;
  zs_spatial_geometry_3p1_default(&g);
  const float baseline = zs_spatial_max_baseline_m(&g);
  assert(baseline > 0.14f && baseline < 0.20f);

  const float cases[][2] = {
      {0.0f, 15.0f},
      {73.0f, 32.0f},
      {215.0f, 55.0f},
      {315.0f, 8.0f},
  };
  for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
    float t[3];
    zs_spatial_solution_t s;
    assert(zs_spatial_reference_tdoas_from_angles(&g, cases[i][0], cases[i][1], 20.0f, t));
    assert(zs_spatial_direction_from_reference_tdoas(&g, t, 20.0f, &s));
    assert(s.valid);
    assert(angle_error(s.azimuth_deg, cases[i][0]) < 0.01f);
    assert(fabsf(s.elevation_deg - cases[i][1]) < 0.01f);
    assert(s.residual_us < 0.01f);
    assert(s.confidence > 0.99f);
  }
}

static void test_quantized_microseconds(void) {
  zs_spatial_geometry_t g;
  zs_spatial_geometry_3p1_default(&g);
  float t[3];
  zs_spatial_solution_t s;
  assert(zs_spatial_reference_tdoas_from_angles(&g, 128.0f, 28.0f, 20.0f, t));
  for (unsigned i = 0; i < 3; ++i) t[i] = roundf(t[i]);
  assert(zs_spatial_direction_from_reference_tdoas(&g, t, 20.0f, &s));
  assert(angle_error(s.azimuth_deg, 128.0f) < 1.0f);
  assert(fabsf(s.elevation_deg - 28.0f) < 1.0f);
}

static void test_impossible_tdoa_rejected(void) {
  zs_spatial_geometry_t g;
  zs_spatial_geometry_3p1_default(&g);
  const float t[3] = {10000.0f, 0.0f, 0.0f};
  zs_spatial_solution_t s;
  assert(!zs_spatial_direction_from_reference_tdoas(&g, t, 20.0f, &s));
  assert(!s.valid);
}

static void test_gcc_delay(void) {
  static int16_t reference[ZS_SPATIAL_GCC_N];
  static int16_t signal[ZS_SPATIAL_GCC_N];
  static zs_spatial_gcc_workspace_t workspace;
  const unsigned delay_samples = 7u;
  for (unsigned i = 0; i < ZS_SPATIAL_GCC_N; ++i) reference[i] = noise_sample();
  memset(signal, 0, sizeof(signal));
  for (unsigned i = delay_samples; i < ZS_SPATIAL_GCC_N; ++i) {
    signal[i] = reference[i - delay_samples];
  }
  float delay_us = 0.0f;
  float quality = 0.0f;
  assert(zs_spatial_gcc_phat_delay_us(reference,
                                      signal,
                                      ZS_SPATIAL_GCC_N,
                                      32000u,
                                      1000.0f,
                                      80.0f,
                                      5000.0f,
                                      &workspace,
                                      &delay_us,
                                      &quality));
  const float expected_us = (float)delay_samples / 32000.0f * 1.0e6f;
  assert(fabsf(delay_us - expected_us) < 20.0f);
  assert(quality > 2.0f);
}

int main(void) {
  test_geometry_and_roundtrip();
  test_quantized_microseconds();
  test_impossible_tdoa_rejected();
  test_gcc_delay();
  puts("zs_spatial_tests: OK");
  return 0;
}

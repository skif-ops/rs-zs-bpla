#ifndef ZS_SPATIAL_H
#define ZS_SPATIAL_H

#include "zs_fft.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_SPATIAL_MIC_COUNT 4u
#define ZS_SPATIAL_REF_TDOA_COUNT 3u
#define ZS_SPATIAL_GCC_N 1024u

typedef struct {
  float position_m[ZS_SPATIAL_MIC_COUNT][3];
  uint8_t geometry_id;
} zs_spatial_geometry_t;

typedef struct {
  float azimuth_deg;
  float elevation_deg;
  float residual_us;
  float confidence;
  float raw_vector_norm;
  bool valid;
} zs_spatial_solution_t;

typedef struct {
  zs_complex_t signal[ZS_SPATIAL_GCC_N];
  zs_complex_t reference[ZS_SPATIAL_GCC_N];
} zs_spatial_gcc_workspace_t;

void zs_spatial_geometry_3p1_default(zs_spatial_geometry_t *geometry);
float zs_spatial_speed_of_sound(float temperature_c);
float zs_spatial_max_baseline_m(const zs_spatial_geometry_t *geometry);

bool zs_spatial_reference_tdoas_from_angles(const zs_spatial_geometry_t *geometry,
                                            float azimuth_deg,
                                            float elevation_deg,
                                            float temperature_c,
                                            float out_tdoa_us[ZS_SPATIAL_REF_TDOA_COUNT]);

bool zs_spatial_direction_from_reference_tdoas(const zs_spatial_geometry_t *geometry,
                                               const float tdoa_us[ZS_SPATIAL_REF_TDOA_COUNT],
                                               float temperature_c,
                                               zs_spatial_solution_t *out);

bool zs_spatial_gcc_phat_delay_us(const int16_t *reference,
                                  const int16_t *signal,
                                  size_t sample_count,
                                  uint32_t sample_rate_hz,
                                  float max_delay_us,
                                  float fmin_hz,
                                  float fmax_hz,
                                  zs_spatial_gcc_workspace_t *workspace,
                                  float *delay_us,
                                  float *quality);

/* The three reference delays of one frame (t_j - t_1, j = 2..4, microseconds) with a single transform of the
   reference channel: 4 FFT + 3 IFFT instead of 6 + 3.  Same results as three zs_spatial_gcc_phat_delay_us() calls
   against channels[0]; coherence[j] is the PHAT peak relative to a fully coherent pair (0..1: ~0.1 for independent
   noise, ~0.3-0.9 for a source above the noise), a better gate than the peak-to-mean ratio of the short lag range. */
bool zs_spatial_gcc_phat_reference_delays(const int16_t *const channels[ZS_SPATIAL_MIC_COUNT],
                                          size_t sample_count,
                                          uint32_t sample_rate_hz,
                                          float max_delay_us,
                                          float fmin_hz,
                                          float fmax_hz,
                                          zs_spatial_gcc_workspace_t *workspace,
                                          float delay_us[ZS_SPATIAL_REF_TDOA_COUNT],
                                          float coherence[ZS_SPATIAL_REF_TDOA_COUNT]);

#endif

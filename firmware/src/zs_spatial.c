#include "zs_spatial.h"

#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static float clampf(float v, float lo, float hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

float zs_spatial_speed_of_sound(float temperature_c) {
  return 331.3f + 0.606f * temperature_c;
}

void zs_spatial_geometry_3p1_default(zs_spatial_geometry_t *geometry) {
  if (!geometry) return;
  const float side = 0.120f;
  const float h = 0.10392304845f; /* sqrt(3)/2 * 0.120 */
  memset(geometry, 0, sizeof(*geometry));
  geometry->position_m[0][0] = -side * 0.5f;
  geometry->position_m[0][1] = -h / 3.0f;
  geometry->position_m[1][0] = side * 0.5f;
  geometry->position_m[1][1] = -h / 3.0f;
  geometry->position_m[2][0] = 0.0f;
  geometry->position_m[2][1] = 2.0f * h / 3.0f;
  geometry->position_m[3][0] = 0.0f;
  geometry->position_m[3][1] = 0.0f;
  geometry->position_m[3][2] = 0.150f;
  geometry->geometry_id = 1u;
}

float zs_spatial_max_baseline_m(const zs_spatial_geometry_t *geometry) {
  if (!geometry) return 0.0f;
  float best = 0.0f;
  for (unsigned i = 0; i < ZS_SPATIAL_MIC_COUNT; ++i) {
    for (unsigned j = i + 1; j < ZS_SPATIAL_MIC_COUNT; ++j) {
      float d2 = 0.0f;
      for (unsigned k = 0; k < 3; ++k) {
        const float d = geometry->position_m[j][k] - geometry->position_m[i][k];
        d2 += d * d;
      }
      const float d = sqrtf(d2);
      if (d > best) best = d;
    }
  }
  return best;
}

static void unit_from_angles(float azimuth_deg, float elevation_deg, float u[3]) {
  const float az = azimuth_deg * (float)M_PI / 180.0f;
  const float el = elevation_deg * (float)M_PI / 180.0f;
  const float ce = cosf(el);
  u[0] = ce * sinf(az); /* east */
  u[1] = ce * cosf(az); /* north */
  u[2] = sinf(el);      /* up */
}

bool zs_spatial_reference_tdoas_from_angles(const zs_spatial_geometry_t *geometry,
                                            float azimuth_deg,
                                            float elevation_deg,
                                            float temperature_c,
                                            float out_tdoa_us[ZS_SPATIAL_REF_TDOA_COUNT]) {
  if (!geometry || !out_tdoa_us) return false;
  const float c = zs_spatial_speed_of_sound(temperature_c);
  if (!(c > 250.0f && c < 400.0f)) return false;
  float u[3];
  unit_from_angles(azimuth_deg, elevation_deg, u);
  for (unsigned row = 0; row < 3; ++row) {
    float dot = 0.0f;
    for (unsigned k = 0; k < 3; ++k) {
      const float baseline = geometry->position_m[row + 1u][k] - geometry->position_m[0][k];
      dot += baseline * u[k];
    }
    out_tdoa_us[row] = -dot / c * 1.0e6f;
  }
  return true;
}

static bool solve3(float a[3][4], float out[3]) {
  for (unsigned col = 0; col < 3; ++col) {
    unsigned pivot = col;
    float pivot_abs = fabsf(a[pivot][col]);
    for (unsigned row = col + 1; row < 3; ++row) {
      const float v = fabsf(a[row][col]);
      if (v > pivot_abs) {
        pivot = row;
        pivot_abs = v;
      }
    }
    if (pivot_abs < 1.0e-9f) return false;
    if (pivot != col) {
      for (unsigned k = col; k < 4; ++k) {
        const float tmp = a[col][k];
        a[col][k] = a[pivot][k];
        a[pivot][k] = tmp;
      }
    }
    const float scale = a[col][col];
    for (unsigned k = col; k < 4; ++k) a[col][k] /= scale;
    for (unsigned row = 0; row < 3; ++row) {
      if (row == col) continue;
      const float f = a[row][col];
      for (unsigned k = col; k < 4; ++k) a[row][k] -= f * a[col][k];
    }
  }
  for (unsigned i = 0; i < 3; ++i) out[i] = a[i][3];
  return true;
}

bool zs_spatial_direction_from_reference_tdoas(const zs_spatial_geometry_t *geometry,
                                               const float tdoa_us[ZS_SPATIAL_REF_TDOA_COUNT],
                                               float temperature_c,
                                               zs_spatial_solution_t *out) {
  if (!geometry || !tdoa_us || !out) return false;
  memset(out, 0, sizeof(*out));
  const float c = zs_spatial_speed_of_sound(temperature_c);
  const float max_delay_us = zs_spatial_max_baseline_m(geometry) / c * 1.0e6f + 5.0f;
  for (unsigned i = 0; i < 3; ++i) {
    if (!isfinite(tdoa_us[i]) || fabsf(tdoa_us[i]) > max_delay_us) return false;
  }

  float aug[3][4];
  for (unsigned row = 0; row < 3; ++row) {
    for (unsigned k = 0; k < 3; ++k) {
      aug[row][k] = geometry->position_m[row + 1u][k] - geometry->position_m[0][k];
    }
    aug[row][3] = -c * tdoa_us[row] * 1.0e-6f;
  }

  float raw[3];
  if (!solve3(aug, raw)) return false;
  const float raw_norm = sqrtf(raw[0] * raw[0] + raw[1] * raw[1] + raw[2] * raw[2]);
  out->raw_vector_norm = raw_norm;
  if (raw_norm < 1.0e-6f) return false;

  float u[3] = {raw[0] / raw_norm, raw[1] / raw_norm, raw[2] / raw_norm};
  float err2 = 0.0f;
  for (unsigned row = 0; row < 3; ++row) {
    float dot = 0.0f;
    for (unsigned k = 0; k < 3; ++k) {
      const float baseline = geometry->position_m[row + 1u][k] - geometry->position_m[0][k];
      dot += baseline * u[k];
    }
    const float predicted_us = -dot / c * 1.0e6f;
    const float e = predicted_us - tdoa_us[row];
    err2 += e * e;
  }
  out->residual_us = sqrtf(err2 / 3.0f);
  out->azimuth_deg = atan2f(u[0], u[1]) * 180.0f / (float)M_PI;
  if (out->azimuth_deg < 0.0f) out->azimuth_deg += 360.0f;
  out->elevation_deg = asinf(clampf(u[2], -1.0f, 1.0f)) * 180.0f / (float)M_PI;

  const float norm_error = fabsf(raw_norm - 1.0f);
  const float residual_score = expf(-powf(out->residual_us / 15.0f, 2.0f));
  const float norm_score = expf(-powf(norm_error / 0.15f, 2.0f));
  out->confidence = clampf(residual_score * norm_score, 0.0f, 1.0f);
  out->valid = out->residual_us <= 35.0f && norm_error <= 0.45f;
  if (!out->valid && out->confidence > 0.25f) out->confidence = 0.25f;
  return out->valid;
}

bool zs_spatial_gcc_phat_delay_us(const int16_t *reference,
                                  const int16_t *signal,
                                  size_t sample_count,
                                  uint32_t sample_rate_hz,
                                  float max_delay_us,
                                  float fmin_hz,
                                  float fmax_hz,
                                  zs_spatial_gcc_workspace_t *workspace,
                                  float *delay_us,
                                  float *quality) {
  if (!reference || !signal || !workspace || !delay_us || !quality) return false;
  if (sample_count != ZS_SPATIAL_GCC_N || sample_rate_hz == 0u) return false;
  if (!(fmin_hz >= 0.0f && fmax_hz > fmin_hz && fmax_hz <= 0.5f * sample_rate_hz)) return false;

  const float inv_scale = 1.0f / 32768.0f;
  for (size_t i = 0; i < ZS_SPATIAL_GCC_N; ++i) {
    const float w = 0.5f - 0.5f * cosf(2.0f * (float)M_PI * (float)i / (float)(ZS_SPATIAL_GCC_N - 1u));
    workspace->reference[i].re = (float)reference[i] * inv_scale * w;
    workspace->reference[i].im = 0.0f;
    workspace->signal[i].re = (float)signal[i] * inv_scale * w;
    workspace->signal[i].im = 0.0f;
  }
  if (!zs_fft_radix2(workspace->reference, ZS_SPATIAL_GCC_N) ||
      !zs_fft_radix2(workspace->signal, ZS_SPATIAL_GCC_N)) {
    return false;
  }

  for (size_t k = 0; k < ZS_SPATIAL_GCC_N; ++k) {
    const size_t folded = k <= ZS_SPATIAL_GCC_N / 2u ? k : ZS_SPATIAL_GCC_N - k;
    const float freq = (float)folded * (float)sample_rate_hz / (float)ZS_SPATIAL_GCC_N;
    if (freq < fmin_hz || freq > fmax_hz) {
      workspace->signal[k].re = 0.0f;
      workspace->signal[k].im = 0.0f;
      continue;
    }
    const float ar = workspace->signal[k].re;
    const float ai = workspace->signal[k].im;
    const float br = workspace->reference[k].re;
    const float bi = workspace->reference[k].im;
    const float cr = ar * br + ai * bi; /* signal * conj(reference) */
    const float ci = ai * br - ar * bi;
    const float mag = sqrtf(cr * cr + ci * ci);
    if (mag > 1.0e-12f) {
      workspace->signal[k].re = cr / mag;
      workspace->signal[k].im = ci / mag;
    } else {
      workspace->signal[k].re = 0.0f;
      workspace->signal[k].im = 0.0f;
    }
  }
  if (!zs_ifft_radix2(workspace->signal, ZS_SPATIAL_GCC_N)) return false;

  int max_lag = (int)ceilf(max_delay_us * 1.0e-6f * (float)sample_rate_hz) + 1;
  if (max_lag < 1) max_lag = 1;
  if (max_lag >= (int)ZS_SPATIAL_GCC_N / 2) max_lag = (int)ZS_SPATIAL_GCC_N / 2 - 1;

  int best_lag = 0;
  float best = -1.0f;
  float sum = 0.0f;
  unsigned count = 0u;
  for (int lag = -max_lag; lag <= max_lag; ++lag) {
    const size_t index = lag >= 0 ? (size_t)lag : ZS_SPATIAL_GCC_N + (size_t)lag;
    const float v = fabsf(workspace->signal[index].re);
    sum += v;
    ++count;
    if (v > best) {
      best = v;
      best_lag = lag;
    }
  }

  float frac = 0.0f;
  if (best_lag > -max_lag && best_lag < max_lag) {
    const int lag0 = best_lag - 1;
    const int lag2 = best_lag + 1;
    const size_t i0 = lag0 >= 0 ? (size_t)lag0 : ZS_SPATIAL_GCC_N + (size_t)lag0;
    const size_t i1 = best_lag >= 0 ? (size_t)best_lag : ZS_SPATIAL_GCC_N + (size_t)best_lag;
    const size_t i2 = lag2 >= 0 ? (size_t)lag2 : ZS_SPATIAL_GCC_N + (size_t)lag2;
    const float y0 = fabsf(workspace->signal[i0].re);
    const float y1 = fabsf(workspace->signal[i1].re);
    const float y2 = fabsf(workspace->signal[i2].re);
    const float denom = y0 - 2.0f * y1 + y2;
    if (fabsf(denom) > 1.0e-12f) frac = clampf(0.5f * (y0 - y2) / denom, -0.5f, 0.5f);
  }

  *delay_us = ((float)best_lag + frac) / (float)sample_rate_hz * 1.0e6f;
  const float mean = sum / (float)count + 1.0e-12f;
  *quality = best / mean;
  return isfinite(*delay_us) && isfinite(*quality);
}

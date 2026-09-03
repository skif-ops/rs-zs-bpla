#include "zs_adpcm.h"

#include <limits.h>
#include <string.h>

static const int8_t k_index_delta[16] = {
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8,
};

static const int16_t k_step_table[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31,
    34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
    157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544,
    598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707,
    1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871,
    5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
};

static int16_t clamp_i16(int32_t value) {
  if (value > INT16_MAX) return INT16_MAX;
  if (value < INT16_MIN) return INT16_MIN;
  return (int16_t)value;
}

static uint8_t encode_nibble(zs_ima_adpcm_encoder_t *encoder, int16_t sample) {
  int32_t predictor = encoder->predictor;
  int32_t diff = (int32_t)sample - predictor;
  uint8_t code = 0u;
  if (diff < 0) {
    code = 8u;
    diff = -diff;
  }

  const int32_t step = k_step_table[encoder->step_index];
  int32_t delta = step >> 3;
  if (diff >= step) {
    code |= 4u;
    diff -= step;
    delta += step;
  }
  if (diff >= (step >> 1)) {
    code |= 2u;
    diff -= step >> 1;
    delta += step >> 1;
  }
  if (diff >= (step >> 2)) {
    code |= 1u;
    delta += step >> 2;
  }

  predictor += (code & 8u) ? -delta : delta;
  encoder->predictor = clamp_i16(predictor);

  int32_t index = (int32_t)encoder->step_index + k_index_delta[code & 0x0fu];
  if (index < 0) index = 0;
  if (index > 88) index = 88;
  encoder->step_index = (uint8_t)index;
  return code;
}

void zs_ima_adpcm_encoder_reset(zs_ima_adpcm_encoder_t *encoder) {
  if (encoder) memset(encoder, 0, sizeof(*encoder));
}

bool zs_ima_adpcm_encoder_begin(zs_ima_adpcm_encoder_t *encoder,
                                int16_t first_sample,
                                uint8_t header[ZS_IMA_ADPCM_BLOCK_HEADER_BYTES]) {
  if (!encoder || !header) return false;
  zs_ima_adpcm_encoder_reset(encoder);
  encoder->predictor = first_sample;
  encoder->step_index = 0u;
  encoder->initialized = true;
  encoder->samples_encoded = 1u;
  const uint16_t raw = (uint16_t)first_sample;
  header[0] = (uint8_t)(raw & 0xffu);
  header[1] = (uint8_t)(raw >> 8);
  header[2] = encoder->step_index;
  header[3] = 0u;
  return true;
}

bool zs_ima_adpcm_encoder_push(zs_ima_adpcm_encoder_t *encoder,
                               int16_t sample,
                               uint8_t *out_byte,
                               bool *byte_ready) {
  if (!encoder || !encoder->initialized || !out_byte || !byte_ready) return false;
  const uint8_t nibble = encode_nibble(encoder, sample);
  encoder->samples_encoded++;
  if (!encoder->low_nibble_pending) {
    encoder->pending_byte = nibble;
    encoder->low_nibble_pending = true;
    *byte_ready = false;
  } else {
    *out_byte = (uint8_t)(encoder->pending_byte | (uint8_t)(nibble << 4));
    encoder->pending_byte = 0u;
    encoder->low_nibble_pending = false;
    *byte_ready = true;
  }
  return true;
}

bool zs_ima_adpcm_encoder_finish(zs_ima_adpcm_encoder_t *encoder,
                                 uint8_t *out_byte,
                                 bool *byte_ready) {
  if (!encoder || !encoder->initialized || !out_byte || !byte_ready) return false;
  if (encoder->low_nibble_pending) {
    *out_byte = encoder->pending_byte;
    *byte_ready = true;
    encoder->pending_byte = 0u;
    encoder->low_nibble_pending = false;
  } else {
    *byte_ready = false;
  }
  encoder->initialized = false;
  return true;
}

size_t zs_ima_adpcm_block_bytes_for_samples(uint32_t sample_count) {
  if (sample_count == 0u) return 0u;
  const uint64_t nibble_count = (uint64_t)sample_count - 1u;
  const uint64_t payload = (nibble_count + 1u) / 2u;
  const uint64_t total = ZS_IMA_ADPCM_BLOCK_HEADER_BYTES + payload;
  return total > SIZE_MAX ? 0u : (size_t)total;
}

bool zs_ima_adpcm_encode_block(const int16_t *samples,
                               uint32_t sample_count,
                               uint8_t *out,
                               size_t out_capacity,
                               size_t *out_bytes) {
  if (!samples || sample_count == 0u || !out || !out_bytes) return false;
  const size_t required = zs_ima_adpcm_block_bytes_for_samples(sample_count);
  if (required == 0u || out_capacity < required) return false;

  zs_ima_adpcm_encoder_t encoder;
  if (!zs_ima_adpcm_encoder_begin(&encoder, samples[0], out)) return false;
  size_t pos = ZS_IMA_ADPCM_BLOCK_HEADER_BYTES;
  for (uint32_t i = 1u; i < sample_count; ++i) {
    uint8_t b = 0u;
    bool ready = false;
    if (!zs_ima_adpcm_encoder_push(&encoder, samples[i], &b, &ready)) return false;
    if (ready) out[pos++] = b;
  }
  uint8_t tail = 0u;
  bool tail_ready = false;
  if (!zs_ima_adpcm_encoder_finish(&encoder, &tail, &tail_ready)) return false;
  if (tail_ready) out[pos++] = tail;
  if (pos != required) return false;
  *out_bytes = pos;
  return true;
}

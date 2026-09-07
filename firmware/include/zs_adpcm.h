#ifndef ZS_ADPCM_H
#define ZS_ADPCM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_IMA_ADPCM_BLOCK_HEADER_BYTES 4u

typedef struct {
  int16_t predictor;
  uint8_t step_index;
  bool initialized;
  bool low_nibble_pending;
  uint8_t pending_byte;
  uint32_t samples_encoded;
} zs_ima_adpcm_encoder_t;

void zs_ima_adpcm_encoder_reset(zs_ima_adpcm_encoder_t *encoder);

/*
 * Starts an independent IMA ADPCM block. The first PCM sample is stored as the
 * predictor in the canonical 4-byte little-endian header:
 * predictor[15:0], step_index, reserved(0).
 */
bool zs_ima_adpcm_encoder_begin(zs_ima_adpcm_encoder_t *encoder,
                                int16_t first_sample,
                                uint8_t header[ZS_IMA_ADPCM_BLOCK_HEADER_BYTES]);

/* Encodes one PCM sample after the predictor sample. Produces one byte for each pair of nibbles. */
bool zs_ima_adpcm_encoder_push(zs_ima_adpcm_encoder_t *encoder,
                               int16_t sample,
                               uint8_t *out_byte,
                               bool *byte_ready);

/* Flushes a final odd low nibble with zero in the unused high nibble. */
bool zs_ima_adpcm_encoder_finish(zs_ima_adpcm_encoder_t *encoder,
                                 uint8_t *out_byte,
                                 bool *byte_ready);

size_t zs_ima_adpcm_block_bytes_for_samples(uint32_t sample_count);

/* Convenience block encoder for host tools/tests. */
bool zs_ima_adpcm_encode_block(const int16_t *samples,
                               uint32_t sample_count,
                               uint8_t *out,
                               size_t out_capacity,
                               size_t *out_bytes);

#endif

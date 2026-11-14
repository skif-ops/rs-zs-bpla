/* Audio upload chunks (ICD addendum B): segment -> chunks, canonical encoding, limits, and the shared vector with
   server/tests/test_audio_chunk_codec.py (a 2-second IMA-ADPCM segment at 1 kHz, decoded by the server). */
#include "zs_adpcm.h"
#include "zs_audio_chunk.h"
#include "zs_audio_chunk_vector.h"
#include "zs_sha256.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* reference IMA decoder (mirror of the encoder's reconstruction) */
static const int8_t idx_delta[16] = {-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8};
static const int16_t steps[89] = {7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143,
  157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707,
  1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
  15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767};
static void decode_block(const uint8_t *b, uint32_t samples, int16_t *out) {
  int32_t pred = (int16_t)(b[0] | (b[1] << 8));
  int idx = b[2];
  out[0] = (int16_t)pred;
  for (uint32_t i = 1u; i < samples; i++) {
    const uint8_t byte = b[4 + (i - 1u) / 2u]; const uint8_t code = ((i - 1u) & 1u) ? (byte >> 4) : (byte & 0x0f);
    const int32_t step = steps[idx]; int32_t delta = step >> 3;
    if (code & 4) delta += step;
    if (code & 2) delta += step >> 1;
    if (code & 1) delta += step >> 2;
    pred += (code & 8) ? -delta : delta;
    if (pred > 32767) pred = 32767;
    if (pred < -32768) pred = -32768;
    idx += idx_delta[code];
    if (idx < 0) idx = 0;
    if (idx > 88) idx = 88;
    out[i] = (int16_t)pred;
  }
}

int main(void) {
  enum { RATE = 1000, SECONDS = 2 };
  static int16_t pcm[RATE * SECONDS], dec[RATE];
  static uint8_t segment[2 * 504 + 8], chunk[ZS_AUDIO_CHUNK_MAX_BYTES];
  size_t seg_len = 0u, n;
  double err = 0.0, sig = 0.0;
  zs_audio_chunk_t c;
  for (unsigned i = 0u; i < RATE * SECONDS; i++) pcm[i] = (int16_t)(12000.0 * sin(2.0 * M_PI * 50.0 * i / RATE));
  for (unsigned s = 0u; s < SECONDS; s++) {
    size_t b;
    assert(zs_ima_adpcm_encode_block(pcm + s * RATE, RATE, segment + seg_len, sizeof(segment) - seg_len, &b) && b == zs_ima_adpcm_block_bytes_for_samples(RATE));
    decode_block(segment + seg_len, RATE, dec);
    for (unsigned i = 0u; i < RATE; i++) { const double e = dec[i] - pcm[s * RATE + i]; err += e * e; sig += (double)pcm[s * RATE + i] * pcm[s * RATE + i]; }
    seg_len += b;
  }
  printf("segment %zu bytes, ADPCM SNR %.1f dB\n", seg_len, 10.0 * log10(sig / err));
  assert(seg_len == 1008u && 10.0 * log10(sig / err) > 18.0);
  /* bit-exact against the server mirror of the encoder (tools/generate_audio_chunk_vector.py) */
  assert(seg_len == sizeof(zs_audio_chunk_vector_segment) && memcmp(segment, zs_audio_chunk_vector_segment, seg_len) == 0);

  memset(&c, 0, sizeof(c));
  c.station_id = 17u; for (unsigned i = 0u; i < 16u; i++) c.command_id[i] = (uint8_t)(0x10u + i);
  c.event_id = ZS_AUDIO_CHUNK_VECTOR_EVENT_ID; c.segment = 0u; c.chunk_index = 0u; c.chunk_count = zs_audio_chunk_count(seg_len);
  c.codec = ZS_AUDIO_CODEC_IMA_ADPCM_1S; c.sample_rate = RATE; c.segment_start_time_us = ZS_AUDIO_CHUNK_VECTOR_START_US;
  zs_sha256_digest(segment, seg_len, c.segment_sha256);
  c.data = segment; c.data_len = seg_len;
  assert(c.chunk_count == 1u);
  n = zs_audio_chunk_encode(&c, chunk, sizeof(chunk));
  assert(n > seg_len && n < seg_len + 128u && chunk[0] == 0xad && chunk[1] == 0x00 && chunk[2] == 0x01);   /* map(13), key 0, schema 1 */
  assert(n == sizeof(zs_audio_chunk_vector_chunk) && memcmp(chunk, zs_audio_chunk_vector_chunk, n) == 0);

  /* a real 30 s pre segment at 32 kHz: 30 blocks of 16004 bytes -> 157 chunks of <= 3072 B, each < 4096 B on the wire */
  assert(zs_ima_adpcm_block_bytes_for_samples(32000u) == 16004u);
  assert(zs_audio_chunk_count(30u * 16004u) == 157u && zs_audio_chunk_count(0u) == 0u && zs_audio_chunk_count((size_t)ZS_AUDIO_CHUNK_DATA_MAX * 1025u) == 0u);
  { static uint8_t big[ZS_AUDIO_CHUNK_DATA_MAX]; c.data = big; c.data_len = sizeof(big); c.chunk_count = 157u; c.chunk_index = 156u; c.sample_rate = 32000u;
    n = zs_audio_chunk_encode(&c, chunk, sizeof(chunk)); assert(n > 0u && n <= ZS_AUDIO_CHUNK_MAX_BYTES && n < 4096u);
    printf("full chunk %zu B on the wire\n", n); }
  /* invalid chunks */
  c.data_len = ZS_AUDIO_CHUNK_DATA_MAX + 1u; assert(zs_audio_chunk_encode(&c, chunk, sizeof(chunk)) == 0u); c.data_len = 100u;
  c.chunk_index = 157u; assert(zs_audio_chunk_encode(&c, chunk, sizeof(chunk)) == 0u); c.chunk_index = 0u;
  c.segment = 2u; assert(zs_audio_chunk_encode(&c, chunk, sizeof(chunk)) == 0u); c.segment = 1u;
  c.codec = 2u; assert(zs_audio_chunk_encode(&c, chunk, sizeof(chunk)) == 0u); c.codec = ZS_AUDIO_CODEC_IMA_ADPCM_1S;
  c.event_id = 0u; assert(zs_audio_chunk_encode(&c, chunk, sizeof(chunk)) == 0u); c.event_id = 1u;
  assert(zs_audio_chunk_encode(&c, chunk, 50u) == 0u);                           /* buffer too small */
  assert(zs_audio_chunk_encode(&c, chunk, sizeof(chunk)) > 0u);
  printf("audio chunk tests passed\n");
  return 0;
}

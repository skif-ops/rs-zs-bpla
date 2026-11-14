#include "zs_audio_chunk.h"
#include "zs_cbor.h"

uint16_t zs_audio_chunk_count(size_t segment_bytes) {
  const size_t n = (segment_bytes + ZS_AUDIO_CHUNK_DATA_MAX - 1u) / ZS_AUDIO_CHUNK_DATA_MAX;
  return (segment_bytes == 0u || n > ZS_AUDIO_SEGMENT_MAX_CHUNKS) ? 0u : (uint16_t)n;
}

size_t zs_audio_chunk_encode(const zs_audio_chunk_t *c, uint8_t *out, size_t cap) {
  zs_cbor_t w;
  if (!c || !out || c->station_id == 0u || c->event_id == 0u || c->segment > 1u || c->chunk_count == 0u ||
      c->chunk_count > ZS_AUDIO_SEGMENT_MAX_CHUNKS || c->chunk_index >= c->chunk_count || c->codec != ZS_AUDIO_CODEC_IMA_ADPCM_1S ||
      c->sample_rate == 0u || !c->data || c->data_len == 0u || c->data_len > ZS_AUDIO_CHUNK_DATA_MAX)
    return 0u;
  zs_cbor_init(&w, out, cap);
  zs_cbor_map(&w, 13u);
  zs_cbor_uint(&w, 0u); zs_cbor_uint(&w, ZS_AUDIO_CHUNK_SCHEMA);
  zs_cbor_uint(&w, 1u); zs_cbor_uint(&w, ZS_AUDIO_CHUNK_MESSAGE_TYPE);
  zs_cbor_uint(&w, 2u); zs_cbor_uint(&w, c->station_id);
  zs_cbor_uint(&w, 3u); zs_cbor_bytes(&w, c->command_id, 16u);
  zs_cbor_uint(&w, 4u); zs_cbor_uint(&w, c->event_id);
  zs_cbor_uint(&w, 5u); zs_cbor_uint(&w, c->segment);
  zs_cbor_uint(&w, 6u); zs_cbor_uint(&w, c->chunk_index);
  zs_cbor_uint(&w, 7u); zs_cbor_uint(&w, c->chunk_count);
  zs_cbor_uint(&w, 8u); zs_cbor_uint(&w, c->codec);
  zs_cbor_uint(&w, 9u); zs_cbor_uint(&w, c->sample_rate);
  zs_cbor_uint(&w, 10u); zs_cbor_int(&w, c->segment_start_time_us);
  zs_cbor_uint(&w, 11u); zs_cbor_bytes(&w, c->segment_sha256, 32u);
  zs_cbor_uint(&w, 12u); zs_cbor_bytes(&w, c->data, c->data_len);
  return w.error ? 0u : w.len;
}

#ifndef ZS_AUDIO_CHUNK_H
#define ZS_AUDIO_CHUNK_H
/*
 * Audio upload over MQTT (MQTT_TLS_ICD_v0_1 addendum B): the answer to CMD_REQUEST_AUDIO.  A requested segment
 * (pre or post) is the concatenation of the station's 1-second IMA-ADPCM prehistory blocks; it is split into chunks
 * of at most ZS_AUDIO_CHUNK_DATA_MAX bytes and published QoS 1 on zs/v1/{tenant}/{station_id}/audio.  Every chunk
 * carries the SHA-256 of the whole segment so the server can verify the assembly; the command ACK follows the last
 * chunk.  Canonical CBOR, keys 0..12, message type 7.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_AUDIO_CHUNK_SCHEMA 1u
#define ZS_AUDIO_CHUNK_MESSAGE_TYPE 7u
#define ZS_AUDIO_CHUNK_DATA_MAX 3072u
#define ZS_AUDIO_CHUNK_MAX_BYTES (ZS_AUDIO_CHUNK_DATA_MAX + 128u)   /* < 4096 B of a BG95 QMTPUB */
#define ZS_AUDIO_CODEC_IMA_ADPCM_1S 1u    /* independent IMA-ADPCM blocks of sample_rate samples (zs_adpcm) */
#define ZS_AUDIO_SEGMENT_MAX_CHUNKS 1024u

typedef struct {
  uint32_t station_id;
  uint8_t command_id[16];
  uint64_t event_id;
  uint8_t segment;            /* 0 pre, 1 post */
  uint16_t chunk_index, chunk_count;
  uint8_t codec;
  uint32_t sample_rate;
  int64_t segment_start_time_us;
  uint8_t segment_sha256[32];
  const uint8_t *data;
  size_t data_len;
} zs_audio_chunk_t;

/* Encodes one chunk; returns the CBOR length or 0 on an invalid chunk / small buffer. */
size_t zs_audio_chunk_encode(const zs_audio_chunk_t *c, uint8_t *out, size_t cap);
/* Number of chunks for a segment of `segment_bytes`. */
uint16_t zs_audio_chunk_count(size_t segment_bytes);
#endif

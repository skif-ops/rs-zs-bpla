#ifndef ZS_ARCHIVE_H
#define ZS_ARCHIVE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_ARCHIVE_MAGIC 0x5A534152u /* ZSAR */
#define ZS_ARCHIVE_VERSION 1u
#define ZS_ARCHIVE_HEADER_BYTES 256u
#define ZS_ARCHIVE_DEFAULT_SLOTS 3u

/* Series design basis: compact mono prehistory, original 4-channel PCM after trigger. */
#define ZS_ARCHIVE_PRE_SAMPLE_RATE 32000u
#define ZS_ARCHIVE_POST_SAMPLE_RATE 32000u
#define ZS_ARCHIVE_POST_CHANNELS 4u
#define ZS_ARCHIVE_PRE_SECONDS 30u
#define ZS_ARCHIVE_POST_SECONDS 30u
#define ZS_ARCHIVE_PRE_ADPCM_BLOCK_SECONDS 1u
#define ZS_ARCHIVE_PRE_ADPCM_BLOCK_HEADER_BYTES 4u
/* Effective bytes/sample including one 4-byte IMA block header per 32000 samples. */
#define ZS_ARCHIVE_PRE_ADPCM_BYTES_PER_SAMPLE_NUM 4001u
#define ZS_ARCHIVE_PRE_ADPCM_BYTES_PER_SAMPLE_DEN 8000u

typedef enum {
  ZS_ARCHIVE_CODEC_UNKNOWN = 0,
  ZS_ARCHIVE_CODEC_IMA_ADPCM_MONO = 1,
  ZS_ARCHIVE_CODEC_PCM16_INTERLEAVED = 2
} zs_archive_codec_t;

typedef struct {
  void *ctx;
  uint32_t size_bytes;
  uint32_t erase_block_bytes;
  int (*read)(void *ctx, uint32_t address, uint8_t *data, size_t len);
  int (*write)(void *ctx, uint32_t address, const uint8_t *data, size_t len);
  int (*erase)(void *ctx, uint32_t address, size_t len);
} zs_archive_storage_t;

typedef struct {
  uint32_t base_address;
  uint32_t total_bytes;
  uint32_t prehistory_ring_bytes;
  uint32_t slot_bytes;
  uint8_t slot_count;
  uint32_t max_pre_bytes;
  uint32_t max_post_bytes;
} zs_archive_layout_t;

typedef struct {
  uint32_t magic;
  uint16_t version;
  uint16_t header_bytes;
  uint8_t slot_index;
  uint8_t pre_codec;
  uint8_t post_codec;
  uint8_t post_channels;
  uint32_t pre_sample_rate;
  uint32_t post_sample_rate;
  uint32_t pre_duration_ms;
  uint32_t post_duration_ms;
  uint64_t event_id;
  int64_t event_time_us;
  uint32_t pre_bytes;
  uint32_t post_bytes;
  uint32_t pre_crc32;
  uint32_t post_crc32;
  uint32_t header_crc32;
} zs_archive_header_t;

typedef struct {
  zs_archive_storage_t storage;
  zs_archive_layout_t layout;
  bool active;
  uint8_t slot_index;
  uint64_t event_id;
  int64_t event_time_us;
  uint32_t pre_written;
  uint32_t post_written;
  uint32_t pre_crc32;
  uint32_t post_crc32;
} zs_archive_t;

uint32_t zs_archive_align_up(uint32_t value, uint32_t alignment);
uint32_t zs_archive_crc32_update(uint32_t crc, const uint8_t *data, size_t len);

/*
 * Builds the recommended 64 MiB-class layout for 30 s mono IMA ADPCM
 * prehistory as independent 1-second blocks, 30 s original 4-channel PCM16
 * after trigger, and 3 event slots. prehistory_ring_bytes is a separate
 * continuously wear-levelled region.
 */
bool zs_archive_make_default_layout(uint32_t base_address,
                                    uint32_t total_bytes,
                                    uint32_t erase_block_bytes,
                                    zs_archive_layout_t *out);

bool zs_archive_init(zs_archive_t *archive,
                     const zs_archive_storage_t *storage,
                     const zs_archive_layout_t *layout);

/* Erase the fixed event slot during idle/maintenance, never on the detector critical path. */
bool zs_archive_prepare_slot(zs_archive_t *archive, uint8_t slot_index);

/* Begin assumes the selected slot has already been erased by zs_archive_prepare_slot(). */
bool zs_archive_begin(zs_archive_t *archive,
                      uint8_t slot_index,
                      uint64_t event_id,
                      int64_t event_time_us);

bool zs_archive_write_pre(zs_archive_t *archive, const uint8_t *data, size_t len);
bool zs_archive_write_post(zs_archive_t *archive, const uint8_t *data, size_t len);

bool zs_archive_finalize(zs_archive_t *archive,
                         uint32_t pre_duration_ms,
                         uint32_t post_duration_ms,
                         zs_archive_codec_t pre_codec,
                         zs_archive_codec_t post_codec,
                         uint8_t post_channels,
                         uint32_t pre_sample_rate,
                         uint32_t post_sample_rate);

bool zs_archive_read_header(const zs_archive_t *archive,
                            uint8_t slot_index,
                            zs_archive_header_t *out);

uint32_t zs_archive_slot_address(const zs_archive_t *archive, uint8_t slot_index);
uint32_t zs_archive_pre_payload_address(const zs_archive_t *archive, uint8_t slot_index);
uint32_t zs_archive_post_payload_address(const zs_archive_t *archive, uint8_t slot_index);

#endif

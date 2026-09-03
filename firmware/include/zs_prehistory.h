#ifndef ZS_PREHISTORY_H
#define ZS_PREHISTORY_H

#include "zs_adpcm.h"
#include "zs_archive.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_PREHISTORY_MAGIC 0x5A535052u /* ZSPR */
#define ZS_PREHISTORY_VERSION 1u
#define ZS_PREHISTORY_HEADER_BYTES 64u
#define ZS_PREHISTORY_ERASE_BLOCKS_PER_RECORD 4u
#define ZS_PREHISTORY_FRAME_SECONDS 1u

typedef struct {
  uint64_t sequence;
  int64_t start_time_us;
  uint32_t sample_count;
  uint32_t payload_bytes;
  uint32_t payload_crc32;
  uint32_t header_crc32;
} zs_prehistory_record_info_t;

typedef struct {
  uint32_t records_copied;
  uint32_t bytes_copied;
  int64_t start_time_us;
  int64_t end_time_us;
} zs_prehistory_copy_result_t;

typedef struct {
  zs_archive_storage_t storage;
  uint32_t base_address;
  uint32_t ring_bytes;
  uint32_t record_bytes;
  uint32_t record_count;
  uint32_t sample_rate;
  uint64_t next_sequence;
  uint32_t available_records;

  bool active;
  uint32_t current_slot;
  uint64_t current_sequence;
  int64_t current_start_time_us;
  uint32_t current_samples;
  uint32_t payload_written;
  uint32_t payload_crc32;
  zs_ima_adpcm_encoder_t encoder;
} zs_prehistory_t;

bool zs_prehistory_init(zs_prehistory_t *ring,
                        const zs_archive_storage_t *storage,
                        uint32_t base_address,
                        uint32_t ring_bytes,
                        uint32_t sample_rate);

/* Scans only 64-byte record headers and reconstructs the latest contiguous sequence. */
bool zs_prehistory_recover(zs_prehistory_t *ring);

/* Erases the next fixed record and starts one independent 1-second ADPCM frame. */
bool zs_prehistory_begin_frame(zs_prehistory_t *ring, int64_t start_time_us);

/* Accepts arbitrary PCM chunk sizes; no full-second PCM or ADPCM buffer is required. */
bool zs_prehistory_push_pcm(zs_prehistory_t *ring,
                            const int16_t *samples,
                            uint32_t sample_count);

/* Requires exactly sample_rate samples. Record header is committed last. */
bool zs_prehistory_finalize_frame(zs_prehistory_t *ring);
void zs_prehistory_abort_frame(zs_prehistory_t *ring);

bool zs_prehistory_read_record_info(const zs_prehistory_t *ring,
                                    uint64_t sequence,
                                    zs_prehistory_record_info_t *out);

/*
 * Verifies CRC for all selected records first, then copies chronological IMA
 * blocks into the active event archive using only the caller scratch buffer.
 */
bool zs_prehistory_copy_latest(zs_prehistory_t *ring,
                               zs_archive_t *archive,
                               uint32_t record_count,
                               uint8_t *scratch,
                               size_t scratch_bytes,
                               zs_prehistory_copy_result_t *out);

#endif

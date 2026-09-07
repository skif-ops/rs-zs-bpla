#include "zs_prehistory.h"

#include <limits.h>
#include <string.h>

#define REC_MAGIC_OFF 0u
#define REC_VERSION_OFF 4u
#define REC_HEADER_BYTES_OFF 6u
#define REC_SEQUENCE_OFF 8u
#define REC_START_TIME_OFF 16u
#define REC_SAMPLE_COUNT_OFF 24u
#define REC_PAYLOAD_BYTES_OFF 28u
#define REC_PAYLOAD_CRC_OFF 32u
#define REC_HEADER_CRC_OFF 36u

#define ENCODE_BUFFER_BYTES 128u

static void put_u16le(uint8_t *p, uint16_t v) {
  p[0] = (uint8_t)(v & 0xffu);
  p[1] = (uint8_t)(v >> 8);
}

static void put_u32le(uint8_t *p, uint32_t v) {
  for (unsigned i = 0; i < 4u; ++i) p[i] = (uint8_t)(v >> (8u * i));
}

static void put_u64le(uint8_t *p, uint64_t v) {
  for (unsigned i = 0; i < 8u; ++i) p[i] = (uint8_t)(v >> (8u * i));
}

static uint16_t get_u16le(const uint8_t *p) {
  return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t get_u32le(const uint8_t *p) {
  uint32_t v = 0u;
  for (unsigned i = 0; i < 4u; ++i) v |= (uint32_t)p[i] << (8u * i);
  return v;
}

static uint64_t get_u64le(const uint8_t *p) {
  uint64_t v = 0u;
  for (unsigned i = 0; i < 8u; ++i) v |= (uint64_t)p[i] << (8u * i);
  return v;
}

static uint32_t expected_payload_bytes(const zs_prehistory_t *ring) {
  if (!ring) return 0u;
  const size_t n = zs_ima_adpcm_block_bytes_for_samples(ring->sample_rate);
  return n == 0u || n > UINT32_MAX ? 0u : (uint32_t)n;
}

static uint32_t record_address_for_slot(const zs_prehistory_t *ring, uint32_t slot) {
  if (!ring || slot >= ring->record_count) return UINT32_MAX;
  const uint64_t address = (uint64_t)ring->base_address + (uint64_t)slot * ring->record_bytes;
  return address > UINT32_MAX ? UINT32_MAX : (uint32_t)address;
}

static uint32_t record_address_for_sequence(const zs_prehistory_t *ring, uint64_t sequence) {
  if (!ring || ring->record_count == 0u) return UINT32_MAX;
  return record_address_for_slot(ring, (uint32_t)(sequence % ring->record_count));
}

static bool decode_record_header(const zs_prehistory_t *ring,
                                 uint8_t raw[ZS_PREHISTORY_HEADER_BYTES],
                                 zs_prehistory_record_info_t *out) {
  if (!ring || !raw || !out) return false;
  if (get_u32le(raw + REC_MAGIC_OFF) != ZS_PREHISTORY_MAGIC ||
      get_u16le(raw + REC_VERSION_OFF) != ZS_PREHISTORY_VERSION ||
      get_u16le(raw + REC_HEADER_BYTES_OFF) != ZS_PREHISTORY_HEADER_BYTES) {
    return false;
  }
  const uint32_t stored_crc = get_u32le(raw + REC_HEADER_CRC_OFF);
  put_u32le(raw + REC_HEADER_CRC_OFF, 0u);
  const uint32_t calc_crc =
      zs_archive_crc32_update(0xffffffffu, raw, ZS_PREHISTORY_HEADER_BYTES) ^ 0xffffffffu;
  if (stored_crc != calc_crc) return false;

  const uint32_t sample_count = get_u32le(raw + REC_SAMPLE_COUNT_OFF);
  const uint32_t payload_bytes = get_u32le(raw + REC_PAYLOAD_BYTES_OFF);
  const uint32_t expected = expected_payload_bytes(ring);
  if (sample_count != ring->sample_rate || payload_bytes != expected ||
      payload_bytes > ring->record_bytes - ZS_PREHISTORY_HEADER_BYTES) {
    return false;
  }

  *out = (zs_prehistory_record_info_t){
      .sequence = get_u64le(raw + REC_SEQUENCE_OFF),
      .start_time_us = (int64_t)get_u64le(raw + REC_START_TIME_OFF),
      .sample_count = sample_count,
      .payload_bytes = payload_bytes,
      .payload_crc32 = get_u32le(raw + REC_PAYLOAD_CRC_OFF),
      .header_crc32 = stored_crc,
  };
  return true;
}

static bool read_slot_info(const zs_prehistory_t *ring,
                           uint32_t slot,
                           zs_prehistory_record_info_t *out) {
  if (!ring || !out || slot >= ring->record_count) return false;
  uint8_t raw[ZS_PREHISTORY_HEADER_BYTES];
  const uint32_t address = record_address_for_slot(ring, slot);
  if (address == UINT32_MAX ||
      ring->storage.read(ring->storage.ctx, address, raw, sizeof(raw)) != 0) {
    return false;
  }
  return decode_record_header(ring, raw, out);
}

bool zs_prehistory_init(zs_prehistory_t *ring,
                        const zs_archive_storage_t *storage,
                        uint32_t base_address,
                        uint32_t ring_bytes,
                        uint32_t sample_rate) {
  if (!ring || !storage || !storage->read || !storage->write || !storage->erase ||
      storage->erase_block_bytes == 0u || sample_rate == 0u || ring_bytes == 0u) {
    return false;
  }
  if ((base_address % storage->erase_block_bytes) != 0u ||
      (ring_bytes % storage->erase_block_bytes) != 0u) {
    return false;
  }
  const uint64_t end = (uint64_t)base_address + ring_bytes;
  if (end > storage->size_bytes) return false;

  const uint64_t record_bytes64 =
      (uint64_t)storage->erase_block_bytes * ZS_PREHISTORY_ERASE_BLOCKS_PER_RECORD;
  if (record_bytes64 > UINT32_MAX) return false;
  const uint32_t record_bytes = (uint32_t)record_bytes64;
  const size_t payload = zs_ima_adpcm_block_bytes_for_samples(sample_rate);
  if (payload == 0u || payload > UINT32_MAX ||
      ZS_PREHISTORY_HEADER_BYTES + payload > record_bytes) {
    return false;
  }
  const uint32_t record_count = ring_bytes / record_bytes;
  if (record_count < (ZS_ARCHIVE_PRE_SECONDS + 1u)) return false;

  memset(ring, 0, sizeof(*ring));
  ring->storage = *storage;
  ring->base_address = base_address;
  ring->ring_bytes = ring_bytes;
  ring->record_bytes = record_bytes;
  ring->record_count = record_count;
  ring->sample_rate = sample_rate;
  return true;
}

bool zs_prehistory_read_record_info(const zs_prehistory_t *ring,
                                    uint64_t sequence,
                                    zs_prehistory_record_info_t *out) {
  if (!ring || !out || ring->record_count == 0u) return false;
  const uint32_t slot = (uint32_t)(sequence % ring->record_count);
  zs_prehistory_record_info_t info;
  if (!read_slot_info(ring, slot, &info) || info.sequence != sequence) return false;
  *out = info;
  return true;
}

bool zs_prehistory_recover(zs_prehistory_t *ring) {
  if (!ring || ring->active || ring->record_count == 0u) return false;
  bool found = false;
  uint64_t latest = 0u;
  for (uint32_t slot = 0u; slot < ring->record_count; ++slot) {
    zs_prehistory_record_info_t info;
    if (read_slot_info(ring, slot, &info) && (!found || info.sequence > latest)) {
      latest = info.sequence;
      found = true;
    }
  }
  if (!found) {
    ring->next_sequence = 0u;
    ring->available_records = 0u;
    return true;
  }
  if (latest == UINT64_MAX) return false;

  uint32_t contiguous = 0u;
  uint64_t sequence = latest;
  while (contiguous < ring->record_count) {
    zs_prehistory_record_info_t info;
    if (!zs_prehistory_read_record_info(ring, sequence, &info)) break;
    contiguous++;
    if (sequence == 0u) break;
    sequence--;
  }
  ring->next_sequence = latest + 1u;
  ring->available_records = contiguous;
  return true;
}

bool zs_prehistory_begin_frame(zs_prehistory_t *ring, int64_t start_time_us) {
  if (!ring || ring->active || ring->record_count == 0u || ring->next_sequence == UINT64_MAX) {
    return false;
  }
  const uint32_t slot = (uint32_t)(ring->next_sequence % ring->record_count);
  const uint32_t address = record_address_for_slot(ring, slot);
  if (address == UINT32_MAX ||
      ring->storage.erase(ring->storage.ctx, address, ring->record_bytes) != 0) {
    return false;
  }
  if (ring->available_records == ring->record_count) ring->available_records--;

  ring->active = true;
  ring->current_slot = slot;
  ring->current_sequence = ring->next_sequence;
  ring->current_start_time_us = start_time_us;
  ring->current_samples = 0u;
  ring->payload_written = 0u;
  ring->payload_crc32 = 0xffffffffu;
  zs_ima_adpcm_encoder_reset(&ring->encoder);
  return true;
}

static bool write_payload(zs_prehistory_t *ring, const uint8_t *data, size_t len) {
  if (!ring || !ring->active || (!data && len != 0u) || len > UINT32_MAX) return false;
  const uint32_t expected = expected_payload_bytes(ring);
  if (ring->payload_written > expected || len > (size_t)(expected - ring->payload_written)) {
    return false;
  }
  const uint32_t record_address = record_address_for_slot(ring, ring->current_slot);
  if (record_address == UINT32_MAX) return false;
  const uint64_t address64 = (uint64_t)record_address + ZS_PREHISTORY_HEADER_BYTES +
                             ring->payload_written;
  if (address64 > UINT32_MAX) return false;
  if (len != 0u && ring->storage.write(ring->storage.ctx, (uint32_t)address64, data, len) != 0) {
    return false;
  }
  ring->payload_crc32 = zs_archive_crc32_update(ring->payload_crc32, data, len);
  ring->payload_written += (uint32_t)len;
  return true;
}

bool zs_prehistory_push_pcm(zs_prehistory_t *ring,
                            const int16_t *samples,
                            uint32_t sample_count) {
  if (!ring || !ring->active || (!samples && sample_count != 0u)) return false;
  if (sample_count > ring->sample_rate - ring->current_samples) return false;
  if (sample_count == 0u) return true;

  uint8_t encoded[ENCODE_BUFFER_BYTES];
  size_t encoded_count = 0u;
  uint32_t input_index = 0u;
  if (ring->current_samples == 0u) {
    uint8_t block_header[ZS_IMA_ADPCM_BLOCK_HEADER_BYTES];
    if (!zs_ima_adpcm_encoder_begin(&ring->encoder, samples[0], block_header) ||
        !write_payload(ring, block_header, sizeof(block_header))) {
      return false;
    }
    ring->current_samples = 1u;
    input_index = 1u;
  }

  for (; input_index < sample_count; ++input_index) {
    uint8_t byte = 0u;
    bool ready = false;
    if (!zs_ima_adpcm_encoder_push(&ring->encoder, samples[input_index], &byte, &ready)) {
      return false;
    }
    ring->current_samples++;
    if (ready) {
      encoded[encoded_count++] = byte;
      if (encoded_count == sizeof(encoded)) {
        if (!write_payload(ring, encoded, encoded_count)) return false;
        encoded_count = 0u;
      }
    }
  }
  return encoded_count == 0u || write_payload(ring, encoded, encoded_count);
}

static void encode_record_header(uint8_t raw[ZS_PREHISTORY_HEADER_BYTES],
                                 const zs_prehistory_t *ring) {
  memset(raw, 0, ZS_PREHISTORY_HEADER_BYTES);
  put_u32le(raw + REC_MAGIC_OFF, ZS_PREHISTORY_MAGIC);
  put_u16le(raw + REC_VERSION_OFF, ZS_PREHISTORY_VERSION);
  put_u16le(raw + REC_HEADER_BYTES_OFF, ZS_PREHISTORY_HEADER_BYTES);
  put_u64le(raw + REC_SEQUENCE_OFF, ring->current_sequence);
  put_u64le(raw + REC_START_TIME_OFF, (uint64_t)ring->current_start_time_us);
  put_u32le(raw + REC_SAMPLE_COUNT_OFF, ring->current_samples);
  put_u32le(raw + REC_PAYLOAD_BYTES_OFF, ring->payload_written);
  put_u32le(raw + REC_PAYLOAD_CRC_OFF, ring->payload_crc32 ^ 0xffffffffu);
  put_u32le(raw + REC_HEADER_CRC_OFF, 0u);
  const uint32_t crc =
      zs_archive_crc32_update(0xffffffffu, raw, ZS_PREHISTORY_HEADER_BYTES) ^ 0xffffffffu;
  put_u32le(raw + REC_HEADER_CRC_OFF, crc);
}

bool zs_prehistory_finalize_frame(zs_prehistory_t *ring) {
  if (!ring || !ring->active || ring->current_samples != ring->sample_rate) return false;
  uint8_t tail = 0u;
  bool tail_ready = false;
  if (!zs_ima_adpcm_encoder_finish(&ring->encoder, &tail, &tail_ready)) return false;
  if (tail_ready && !write_payload(ring, &tail, 1u)) return false;
  if (ring->payload_written != expected_payload_bytes(ring)) return false;

  uint8_t raw[ZS_PREHISTORY_HEADER_BYTES];
  encode_record_header(raw, ring);
  const uint32_t address = record_address_for_slot(ring, ring->current_slot);
  if (address == UINT32_MAX ||
      ring->storage.write(ring->storage.ctx, address, raw, sizeof(raw)) != 0) {
    return false;
  }

  ring->active = false;
  ring->next_sequence = ring->current_sequence + 1u;
  if (ring->available_records < ring->record_count) ring->available_records++;
  return true;
}

void zs_prehistory_abort_frame(zs_prehistory_t *ring) {
  if (!ring) return;
  ring->active = false;
  ring->current_samples = 0u;
  ring->payload_written = 0u;
  zs_ima_adpcm_encoder_reset(&ring->encoder);
}

static bool verify_payload_crc(const zs_prehistory_t *ring,
                               const zs_prehistory_record_info_t *info,
                               uint8_t *scratch,
                               size_t scratch_bytes) {
  if (!ring || !info || !scratch || scratch_bytes == 0u) return false;
  const uint32_t record_address = record_address_for_sequence(ring, info->sequence);
  if (record_address == UINT32_MAX) return false;
  uint32_t offset = 0u;
  uint32_t crc = 0xffffffffu;
  while (offset < info->payload_bytes) {
    const uint32_t remaining = info->payload_bytes - offset;
    const size_t chunk = remaining < scratch_bytes ? remaining : scratch_bytes;
    const uint64_t address64 = (uint64_t)record_address + ZS_PREHISTORY_HEADER_BYTES + offset;
    if (address64 > UINT32_MAX ||
        ring->storage.read(ring->storage.ctx, (uint32_t)address64, scratch, chunk) != 0) {
      return false;
    }
    crc = zs_archive_crc32_update(crc, scratch, chunk);
    offset += (uint32_t)chunk;
  }
  return (crc ^ 0xffffffffu) == info->payload_crc32;
}

bool zs_prehistory_copy_latest(zs_prehistory_t *ring,
                               zs_archive_t *archive,
                               uint32_t record_count,
                               uint8_t *scratch,
                               size_t scratch_bytes,
                               zs_prehistory_copy_result_t *out) {
  if (!ring || !archive || !archive->active || !scratch || scratch_bytes == 0u ||
      !out || record_count == 0u || record_count > ring->available_records ||
      archive->pre_written != 0u || ring->next_sequence == 0u) {
    return false;
  }
  memset(out, 0, sizeof(*out));
  const uint64_t latest = ring->next_sequence - 1u;
  const uint64_t first = latest - (record_count - 1u);
  uint64_t total_bytes = 0u;
  int64_t first_time = 0;
  int64_t last_time = 0;

  /* First pass: validate every selected record and payload CRC before mutating event slot. */
  for (uint32_t i = 0u; i < record_count; ++i) {
    const uint64_t sequence = first + i;
    zs_prehistory_record_info_t info;
    if (!zs_prehistory_read_record_info(ring, sequence, &info) ||
        !verify_payload_crc(ring, &info, scratch, scratch_bytes)) {
      return false;
    }
    total_bytes += info.payload_bytes;
    if (total_bytes > archive->layout.max_pre_bytes) return false;
    if (i == 0u) first_time = info.start_time_us;
    if (i + 1u == record_count) last_time = info.start_time_us;
  }

  /* Second pass: chronological payload copy using bounded scratch RAM. */
  for (uint32_t i = 0u; i < record_count; ++i) {
    const uint64_t sequence = first + i;
    zs_prehistory_record_info_t info;
    if (!zs_prehistory_read_record_info(ring, sequence, &info)) return false;
    const uint32_t record_address = record_address_for_sequence(ring, sequence);
    if (record_address == UINT32_MAX) return false;
    uint32_t offset = 0u;
    while (offset < info.payload_bytes) {
      const uint32_t remaining = info.payload_bytes - offset;
      const size_t chunk = remaining < scratch_bytes ? remaining : scratch_bytes;
      const uint64_t address64 = (uint64_t)record_address + ZS_PREHISTORY_HEADER_BYTES + offset;
      if (address64 > UINT32_MAX ||
          ring->storage.read(ring->storage.ctx, (uint32_t)address64, scratch, chunk) != 0 ||
          !zs_archive_write_pre(archive, scratch, chunk)) {
        return false;
      }
      offset += (uint32_t)chunk;
    }
  }

  out->records_copied = record_count;
  out->bytes_copied = (uint32_t)total_bytes;
  out->start_time_us = first_time;
  out->end_time_us = last_time + 1000000LL * ZS_PREHISTORY_FRAME_SECONDS;
  return true;
}

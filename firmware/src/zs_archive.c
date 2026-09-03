#include "zs_archive.h"

#include <string.h>

#define HDR_MAGIC_OFF 0u
#define HDR_VERSION_OFF 4u
#define HDR_HEADER_BYTES_OFF 6u
#define HDR_SLOT_OFF 8u
#define HDR_PRE_CODEC_OFF 9u
#define HDR_POST_CODEC_OFF 10u
#define HDR_CHANNELS_OFF 11u
#define HDR_PRE_SR_OFF 12u
#define HDR_POST_SR_OFF 16u
#define HDR_PRE_MS_OFF 20u
#define HDR_POST_MS_OFF 24u
#define HDR_EVENT_ID_OFF 28u
#define HDR_EVENT_TIME_OFF 36u
#define HDR_PRE_BYTES_OFF 44u
#define HDR_POST_BYTES_OFF 48u
#define HDR_PRE_CRC_OFF 52u
#define HDR_POST_CRC_OFF 56u
#define HDR_HEADER_CRC_OFF 60u

static void put_u16le(uint8_t *p, uint16_t v) {
  p[0] = (uint8_t)(v & 0xffu);
  p[1] = (uint8_t)((v >> 8) & 0xffu);
}

static void put_u32le(uint8_t *p, uint32_t v) {
  for (unsigned i = 0; i < 4; ++i) {
    p[i] = (uint8_t)(v >> (8u * i));
  }
}

static void put_u64le(uint8_t *p, uint64_t v) {
  for (unsigned i = 0; i < 8; ++i) {
    p[i] = (uint8_t)(v >> (8u * i));
  }
}

static uint16_t get_u16le(const uint8_t *p) {
  return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t get_u32le(const uint8_t *p) {
  uint32_t v = 0;
  for (unsigned i = 0; i < 4; ++i) {
    v |= ((uint32_t)p[i]) << (8u * i);
  }
  return v;
}

static uint64_t get_u64le(const uint8_t *p) {
  uint64_t v = 0;
  for (unsigned i = 0; i < 8; ++i) {
    v |= ((uint64_t)p[i]) << (8u * i);
  }
  return v;
}

uint32_t zs_archive_align_up(uint32_t value, uint32_t alignment) {
  if (alignment == 0u) {
    return value;
  }
  const uint32_t rem = value % alignment;
  if (rem == 0u) {
    return value;
  }
  const uint32_t add = alignment - rem;
  if (value > UINT32_MAX - add) {
    return 0u;
  }
  return value + add;
}

uint32_t zs_archive_crc32_update(uint32_t crc, const uint8_t *data, size_t len) {
  if (!data && len != 0u) {
    return crc;
  }
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (unsigned bit = 0; bit < 8; ++bit) {
      const uint32_t mask = (uint32_t)-(int32_t)(crc & 1u);
      crc = (crc >> 1) ^ (0xedb88320u & mask);
    }
  }
  return crc;
}

bool zs_archive_make_default_layout(uint32_t base_address,
                                    uint32_t total_bytes,
                                    uint32_t erase_block_bytes,
                                    zs_archive_layout_t *out) {
  if (!out || erase_block_bytes == 0u || total_bytes < erase_block_bytes) {
    return false;
  }

  const uint64_t pre_bytes64 =
      ((uint64_t)ZS_ARCHIVE_PRE_SAMPLE_RATE * ZS_ARCHIVE_PRE_SECONDS *
       ZS_ARCHIVE_PRE_ADPCM_BYTES_PER_SAMPLE_NUM) /
      ZS_ARCHIVE_PRE_ADPCM_BYTES_PER_SAMPLE_DEN;
  const uint64_t post_bytes64 =
      (uint64_t)ZS_ARCHIVE_POST_SAMPLE_RATE * ZS_ARCHIVE_POST_SECONDS *
      ZS_ARCHIVE_POST_CHANNELS * sizeof(int16_t);
  if (pre_bytes64 > UINT32_MAX || post_bytes64 > UINT32_MAX) {
    return false;
  }

  const uint32_t max_pre = (uint32_t)pre_bytes64;
  const uint32_t max_post = (uint32_t)post_bytes64;
  const uint64_t raw_slot = (uint64_t)ZS_ARCHIVE_HEADER_BYTES + max_pre + max_post;
  if (raw_slot > UINT32_MAX) {
    return false;
  }
  const uint32_t slot_bytes = zs_archive_align_up((uint32_t)raw_slot, erase_block_bytes);
  if (slot_bytes == 0u) {
    return false;
  }

  const uint64_t slots_total = (uint64_t)slot_bytes * ZS_ARCHIVE_DEFAULT_SLOTS;
  if (slots_total >= total_bytes) {
    return false;
  }
  uint32_t prehistory = (uint32_t)(total_bytes - slots_total);
  prehistory -= prehistory % erase_block_bytes;
  if (prehistory < erase_block_bytes) {
    return false;
  }

  *out = (zs_archive_layout_t){
      .base_address = base_address,
      .total_bytes = total_bytes,
      .prehistory_ring_bytes = prehistory,
      .slot_bytes = slot_bytes,
      .slot_count = ZS_ARCHIVE_DEFAULT_SLOTS,
      .max_pre_bytes = max_pre,
      .max_post_bytes = max_post,
  };
  return true;
}

static bool range_in_storage(const zs_archive_t *a, uint32_t address, uint32_t len) {
  if (!a) {
    return false;
  }
  const uint64_t end = (uint64_t)address + len;
  return end <= a->storage.size_bytes;
}

bool zs_archive_init(zs_archive_t *archive,
                     const zs_archive_storage_t *storage,
                     const zs_archive_layout_t *layout) {
  if (!archive || !storage || !layout || !storage->read || !storage->write ||
      !storage->erase || storage->erase_block_bytes == 0u || layout->slot_count == 0u) {
    return false;
  }
  if (layout->base_address % storage->erase_block_bytes != 0u ||
      layout->prehistory_ring_bytes % storage->erase_block_bytes != 0u ||
      layout->slot_bytes % storage->erase_block_bytes != 0u) {
    return false;
  }
  const uint64_t required = (uint64_t)layout->base_address + layout->prehistory_ring_bytes +
                            (uint64_t)layout->slot_bytes * layout->slot_count;
  if (required > storage->size_bytes || layout->total_bytes > storage->size_bytes - layout->base_address) {
    return false;
  }
  if (ZS_ARCHIVE_HEADER_BYTES + layout->max_pre_bytes + layout->max_post_bytes > layout->slot_bytes) {
    return false;
  }

  memset(archive, 0, sizeof(*archive));
  archive->storage = *storage;
  archive->layout = *layout;
  return true;
}

uint32_t zs_archive_slot_address(const zs_archive_t *archive, uint8_t slot_index) {
  if (!archive || slot_index >= archive->layout.slot_count) {
    return UINT32_MAX;
  }
  return archive->layout.base_address + archive->layout.prehistory_ring_bytes +
         (uint32_t)slot_index * archive->layout.slot_bytes;
}

uint32_t zs_archive_pre_payload_address(const zs_archive_t *archive, uint8_t slot_index) {
  const uint32_t slot = zs_archive_slot_address(archive, slot_index);
  return slot == UINT32_MAX ? UINT32_MAX : slot + ZS_ARCHIVE_HEADER_BYTES;
}

uint32_t zs_archive_post_payload_address(const zs_archive_t *archive, uint8_t slot_index) {
  const uint32_t pre = zs_archive_pre_payload_address(archive, slot_index);
  return pre == UINT32_MAX ? UINT32_MAX : pre + archive->layout.max_pre_bytes;
}

bool zs_archive_prepare_slot(zs_archive_t *archive, uint8_t slot_index) {
  if (!archive || archive->active || slot_index >= archive->layout.slot_count) {
    return false;
  }
  const uint32_t addr = zs_archive_slot_address(archive, slot_index);
  if (addr == UINT32_MAX || !range_in_storage(archive, addr, archive->layout.slot_bytes)) {
    return false;
  }
  return archive->storage.erase(archive->storage.ctx, addr, archive->layout.slot_bytes) == 0;
}

bool zs_archive_begin(zs_archive_t *archive,
                      uint8_t slot_index,
                      uint64_t event_id,
                      int64_t event_time_us) {
  if (!archive || archive->active || slot_index >= archive->layout.slot_count) {
    return false;
  }
  archive->active = true;
  archive->slot_index = slot_index;
  archive->event_id = event_id;
  archive->event_time_us = event_time_us;
  archive->pre_written = 0u;
  archive->post_written = 0u;
  archive->pre_crc32 = 0xffffffffu;
  archive->post_crc32 = 0xffffffffu;
  return true;
}

static bool append_payload(zs_archive_t *archive,
                           bool pre,
                           const uint8_t *data,
                           size_t len) {
  if (!archive || !archive->active || (!data && len != 0u) || len > UINT32_MAX) {
    return false;
  }
  uint32_t *written = pre ? &archive->pre_written : &archive->post_written;
  uint32_t *crc = pre ? &archive->pre_crc32 : &archive->post_crc32;
  const uint32_t limit = pre ? archive->layout.max_pre_bytes : archive->layout.max_post_bytes;
  if (*written > limit || len > (size_t)(limit - *written)) {
    return false;
  }
  const uint32_t base = pre ? zs_archive_pre_payload_address(archive, archive->slot_index)
                            : zs_archive_post_payload_address(archive, archive->slot_index);
  if (base == UINT32_MAX || !range_in_storage(archive, base + *written, (uint32_t)len)) {
    return false;
  }
  if (len != 0u && archive->storage.write(archive->storage.ctx, base + *written, data, len) != 0) {
    return false;
  }
  *crc = zs_archive_crc32_update(*crc, data, len);
  *written += (uint32_t)len;
  return true;
}

bool zs_archive_write_pre(zs_archive_t *archive, const uint8_t *data, size_t len) {
  return append_payload(archive, true, data, len);
}

bool zs_archive_write_post(zs_archive_t *archive, const uint8_t *data, size_t len) {
  return append_payload(archive, false, data, len);
}

static void encode_header(uint8_t raw[ZS_ARCHIVE_HEADER_BYTES],
                          const zs_archive_t *a,
                          uint32_t pre_duration_ms,
                          uint32_t post_duration_ms,
                          zs_archive_codec_t pre_codec,
                          zs_archive_codec_t post_codec,
                          uint8_t post_channels,
                          uint32_t pre_sample_rate,
                          uint32_t post_sample_rate) {
  memset(raw, 0, ZS_ARCHIVE_HEADER_BYTES);
  put_u32le(raw + HDR_MAGIC_OFF, ZS_ARCHIVE_MAGIC);
  put_u16le(raw + HDR_VERSION_OFF, ZS_ARCHIVE_VERSION);
  put_u16le(raw + HDR_HEADER_BYTES_OFF, ZS_ARCHIVE_HEADER_BYTES);
  raw[HDR_SLOT_OFF] = a->slot_index;
  raw[HDR_PRE_CODEC_OFF] = (uint8_t)pre_codec;
  raw[HDR_POST_CODEC_OFF] = (uint8_t)post_codec;
  raw[HDR_CHANNELS_OFF] = post_channels;
  put_u32le(raw + HDR_PRE_SR_OFF, pre_sample_rate);
  put_u32le(raw + HDR_POST_SR_OFF, post_sample_rate);
  put_u32le(raw + HDR_PRE_MS_OFF, pre_duration_ms);
  put_u32le(raw + HDR_POST_MS_OFF, post_duration_ms);
  put_u64le(raw + HDR_EVENT_ID_OFF, a->event_id);
  put_u64le(raw + HDR_EVENT_TIME_OFF, (uint64_t)a->event_time_us);
  put_u32le(raw + HDR_PRE_BYTES_OFF, a->pre_written);
  put_u32le(raw + HDR_POST_BYTES_OFF, a->post_written);
  put_u32le(raw + HDR_PRE_CRC_OFF, a->pre_crc32 ^ 0xffffffffu);
  put_u32le(raw + HDR_POST_CRC_OFF, a->post_crc32 ^ 0xffffffffu);
  put_u32le(raw + HDR_HEADER_CRC_OFF, 0u);
  const uint32_t crc = zs_archive_crc32_update(0xffffffffu, raw, ZS_ARCHIVE_HEADER_BYTES) ^ 0xffffffffu;
  put_u32le(raw + HDR_HEADER_CRC_OFF, crc);
}

bool zs_archive_finalize(zs_archive_t *archive,
                         uint32_t pre_duration_ms,
                         uint32_t post_duration_ms,
                         zs_archive_codec_t pre_codec,
                         zs_archive_codec_t post_codec,
                         uint8_t post_channels,
                         uint32_t pre_sample_rate,
                         uint32_t post_sample_rate) {
  if (!archive || !archive->active || pre_codec == ZS_ARCHIVE_CODEC_UNKNOWN ||
      post_codec == ZS_ARCHIVE_CODEC_UNKNOWN || post_channels == 0u ||
      pre_sample_rate == 0u || post_sample_rate == 0u) {
    return false;
  }

  uint8_t raw[ZS_ARCHIVE_HEADER_BYTES];
  encode_header(raw, archive, pre_duration_ms, post_duration_ms, pre_codec, post_codec,
                post_channels, pre_sample_rate, post_sample_rate);
  const uint32_t addr = zs_archive_slot_address(archive, archive->slot_index);
  if (addr == UINT32_MAX || archive->storage.write(archive->storage.ctx, addr, raw, sizeof(raw)) != 0) {
    return false;
  }
  archive->active = false;
  return true;
}

bool zs_archive_read_header(const zs_archive_t *archive,
                            uint8_t slot_index,
                            zs_archive_header_t *out) {
  if (!archive || !out || slot_index >= archive->layout.slot_count) {
    return false;
  }
  uint8_t raw[ZS_ARCHIVE_HEADER_BYTES];
  const uint32_t addr = zs_archive_slot_address(archive, slot_index);
  if (addr == UINT32_MAX || archive->storage.read(archive->storage.ctx, addr, raw, sizeof(raw)) != 0) {
    return false;
  }
  if (get_u32le(raw + HDR_MAGIC_OFF) != ZS_ARCHIVE_MAGIC ||
      get_u16le(raw + HDR_VERSION_OFF) != ZS_ARCHIVE_VERSION ||
      get_u16le(raw + HDR_HEADER_BYTES_OFF) != ZS_ARCHIVE_HEADER_BYTES) {
    return false;
  }

  const uint32_t stored_crc = get_u32le(raw + HDR_HEADER_CRC_OFF);
  put_u32le(raw + HDR_HEADER_CRC_OFF, 0u);
  const uint32_t calc_crc = zs_archive_crc32_update(0xffffffffu, raw, sizeof(raw)) ^ 0xffffffffu;
  if (stored_crc != calc_crc) {
    return false;
  }

  memset(out, 0, sizeof(*out));
  out->magic = ZS_ARCHIVE_MAGIC;
  out->version = ZS_ARCHIVE_VERSION;
  out->header_bytes = ZS_ARCHIVE_HEADER_BYTES;
  out->slot_index = raw[HDR_SLOT_OFF];
  out->pre_codec = raw[HDR_PRE_CODEC_OFF];
  out->post_codec = raw[HDR_POST_CODEC_OFF];
  out->post_channels = raw[HDR_CHANNELS_OFF];
  out->pre_sample_rate = get_u32le(raw + HDR_PRE_SR_OFF);
  out->post_sample_rate = get_u32le(raw + HDR_POST_SR_OFF);
  out->pre_duration_ms = get_u32le(raw + HDR_PRE_MS_OFF);
  out->post_duration_ms = get_u32le(raw + HDR_POST_MS_OFF);
  out->event_id = get_u64le(raw + HDR_EVENT_ID_OFF);
  out->event_time_us = (int64_t)get_u64le(raw + HDR_EVENT_TIME_OFF);
  out->pre_bytes = get_u32le(raw + HDR_PRE_BYTES_OFF);
  out->post_bytes = get_u32le(raw + HDR_POST_BYTES_OFF);
  out->pre_crc32 = get_u32le(raw + HDR_PRE_CRC_OFF);
  out->post_crc32 = get_u32le(raw + HDR_POST_CRC_OFF);
  out->header_crc32 = stored_crc;

  if (out->slot_index != slot_index || out->pre_bytes > archive->layout.max_pre_bytes ||
      out->post_bytes > archive->layout.max_post_bytes) {
    return false;
  }
  return true;
}

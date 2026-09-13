#include "zs_event_outbox.h"

#include "zs_protocol.h"

#include <string.h>

#define OUTBOX_MAGIC UINT32_C(0x4f45535a) /* ZSEO */
#define OUTBOX_FORMAT UINT16_C(1)
#define OUTBOX_METADATA_CRC_OFFSET 76u
#define OUTBOX_PAYLOAD_OFFSET 80u
#define OUTBOX_COMMIT_OFFSET 592u
#define OUTBOX_RETRY_BITMAP_OFFSET 596u
#define OUTBOX_RETRY_BITMAP_BYTES 16u
#define OUTBOX_DELIVERED_OFFSET 612u
#define OUTBOX_COMMIT UINT32_C(0x54494d43) /* CMIT */
#define OUTBOX_DELIVERED UINT32_C(0x444b4341) /* ACKD */

_Static_assert(OUTBOX_PAYLOAD_OFFSET + ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES ==
                   OUTBOX_COMMIT_OFFSET,
               "outbox payload layout drift");
_Static_assert(OUTBOX_RETRY_BITMAP_BYTES * 8u ==
                   ZS_EVENT_OUTBOX_MAX_RETRIES,
               "outbox retry layout drift");
_Static_assert(OUTBOX_DELIVERED_OFFSET + 4u == ZS_EVENT_OUTBOX_SLOT_BYTES,
               "outbox slot layout drift");

typedef enum {
  SLOT_INCOMPLETE = 0,
  SLOT_VALID,
  SLOT_CORRUPT,
  SLOT_IO_ERROR
} slot_state_t;

typedef struct {
  zs_event_outbox_item_t item;
  bool delivered;
} decoded_slot_t;

static uint16_t get_u16(const uint8_t *p) {
  return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t get_u32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t get_u64(const uint8_t *p) {
  uint64_t value = 0u;
  for (unsigned i = 0u; i < 8u; ++i) value |= (uint64_t)p[i] << (8u * i);
  return value;
}

static void put_u16(uint8_t *p, uint16_t value) {
  p[0] = (uint8_t)value;
  p[1] = (uint8_t)(value >> 8);
}

static void put_u32(uint8_t *p, uint32_t value) {
  for (unsigned i = 0u; i < 4u; ++i) p[i] = (uint8_t)(value >> (8u * i));
}

static void put_u64(uint8_t *p, uint64_t value) {
  for (unsigned i = 0u; i < 8u; ++i) p[i] = (uint8_t)(value >> (8u * i));
}

static uint32_t crc32(const uint8_t *data, size_t size) {
  uint32_t crc = UINT32_MAX;
  for (size_t i = 0u; i < size; ++i) {
    crc ^= data[i];
    for (unsigned bit = 0u; bit < 8u; ++bit) {
      crc = (crc >> 1) ^
            (UINT32_C(0xedb88320) & (uint32_t)-(int32_t)(crc & 1u));
    }
  }
  return ~crc;
}

static bool io_valid(const zs_event_outbox_io_t *io) {
  return io && io->slot_count > 0u && io->read && io->erase && io->write;
}

static bool generation_newer(uint32_t candidate, uint32_t reference) {
  return candidate != reference &&
         (uint32_t)(candidate - reference) < UINT32_C(0x80000000);
}

static bool all_value(const uint8_t *data, size_t size, uint8_t value) {
  for (size_t i = 0u; i < size; ++i) {
    if (data[i] != value) return false;
  }
  return true;
}

static unsigned zero_bit_count(const uint8_t *bitmap, size_t size) {
  unsigned count = 0u;
  for (size_t i = 0u; i < size; ++i) {
    uint8_t value = bitmap[i];
    for (unsigned bit = 0u; bit < 8u; ++bit) {
      if ((value & (uint8_t)(1u << bit)) == 0u) ++count;
    }
  }
  return count;
}

static bool first_set_bit(const uint8_t *bitmap, size_t size,
                          unsigned *bit_index) {
  for (size_t i = 0u; i < size; ++i) {
    for (unsigned bit = 0u; bit < 8u; ++bit) {
      if ((bitmap[i] & (uint8_t)(1u << bit)) != 0u) {
        *bit_index = (unsigned)(i * 8u) + bit;
        return true;
      }
    }
  }
  return false;
}

static bool event_valid(const zs_event_outbox_event_t *event) {
  return event && event->station_id != 0u && event->event_id != 0u &&
         event->event_time_us > 0 &&
         event->priority <= ZS_EVENT_OUTBOX_PRIORITY_MAX && event->payload &&
         event->payload_size > 0u &&
         event->payload_size <= ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES;
}

static slot_state_t read_slot(const zs_event_outbox_io_t *io, uint16_t slot,
                              decoded_slot_t *decoded) {
  uint8_t raw[ZS_EVENT_OUTBOX_SLOT_BYTES];
  uint8_t digest[ZS_SHA256_DIGEST_BYTES];
  uint16_t payload_size;
  if (!io->read(io->ctx, slot, 0u, raw, sizeof(raw))) return SLOT_IO_ERROR;
  if (get_u32(&raw[OUTBOX_COMMIT_OFFSET]) != OUTBOX_COMMIT)
    return SLOT_INCOMPLETE;
  payload_size = get_u16(&raw[8]);
  if (get_u32(&raw[0]) != OUTBOX_MAGIC ||
      get_u16(&raw[4]) != OUTBOX_FORMAT || raw[6] != 1u ||
      raw[7] > ZS_EVENT_OUTBOX_PRIORITY_MAX || payload_size == 0u ||
      payload_size > ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES ||
      get_u32(&raw[12]) == 0u || get_u64(&raw[24]) == 0u ||
      (int64_t)get_u64(&raw[32]) <= 0 || get_u32(&raw[40]) == 0u ||
      get_u32(&raw[OUTBOX_METADATA_CRC_OFFSET]) !=
          crc32(raw, OUTBOX_METADATA_CRC_OFFSET))
    return SLOT_CORRUPT;
  zs_sha256_digest(&raw[OUTBOX_PAYLOAD_OFFSET], payload_size, digest);
  if (memcmp(digest, &raw[44], sizeof(digest)) != 0) {
    memset(digest, 0, sizeof(digest));
    return SLOT_CORRUPT;
  }
  memset(digest, 0, sizeof(digest));
  memset(decoded, 0, sizeof(*decoded));
  decoded->item.storage_slot = slot;
  decoded->item.storage_generation = get_u32(&raw[40]);
  decoded->item.station_id = get_u32(&raw[12]);
  decoded->item.boot_id = get_u32(&raw[16]);
  decoded->item.seq_no = get_u32(&raw[20]);
  decoded->item.event_id = get_u64(&raw[24]);
  decoded->item.event_time_us = (int64_t)get_u64(&raw[32]);
  decoded->item.priority = raw[7];
  decoded->item.retry_count = (uint16_t)zero_bit_count(
      &raw[OUTBOX_RETRY_BITMAP_OFFSET], OUTBOX_RETRY_BITMAP_BYTES);
  decoded->item.payload_size = payload_size;
  memcpy(decoded->item.payload_sha256, &raw[44], ZS_SHA256_DIGEST_BYTES);
  memcpy(decoded->item.payload, &raw[OUTBOX_PAYLOAD_OFFSET], payload_size);
  decoded->delivered =
      get_u32(&raw[OUTBOX_DELIVERED_OFFSET]) == OUTBOX_DELIVERED;
  return SLOT_VALID;
}

static zs_event_outbox_result_t slot_error(slot_state_t state) {
  return state == SLOT_IO_ERROR ? ZS_EVENT_OUTBOX_IO_ERROR
                                : ZS_EVENT_OUTBOX_CORRUPT;
}

static bool same_event(const zs_event_outbox_item_t *item,
                       const zs_event_outbox_event_t *event,
                       const uint8_t digest[ZS_SHA256_DIGEST_BYTES]) {
  return item->station_id == event->station_id &&
         item->boot_id == event->boot_id && item->seq_no == event->seq_no &&
         item->event_id == event->event_id &&
         item->event_time_us == event->event_time_us &&
         item->priority == event->priority &&
         item->payload_size == event->payload_size &&
         memcmp(item->payload_sha256, digest, ZS_SHA256_DIGEST_BYTES) == 0;
}

static void encode_event(uint8_t raw[ZS_EVENT_OUTBOX_SLOT_BYTES],
                         const zs_event_outbox_event_t *event,
                         uint32_t generation,
                         const uint8_t digest[ZS_SHA256_DIGEST_BYTES]) {
  memset(raw, 0xff, ZS_EVENT_OUTBOX_SLOT_BYTES);
  put_u32(&raw[0], OUTBOX_MAGIC);
  put_u16(&raw[4], OUTBOX_FORMAT);
  raw[6] = 1u; /* detection event */
  raw[7] = event->priority;
  put_u16(&raw[8], (uint16_t)event->payload_size);
  put_u32(&raw[12], event->station_id);
  put_u32(&raw[16], event->boot_id);
  put_u32(&raw[20], event->seq_no);
  put_u64(&raw[24], event->event_id);
  put_u64(&raw[32], (uint64_t)event->event_time_us);
  put_u32(&raw[40], generation);
  memcpy(&raw[44], digest, ZS_SHA256_DIGEST_BYTES);
  put_u32(&raw[OUTBOX_METADATA_CRC_OFFSET],
          crc32(raw, OUTBOX_METADATA_CRC_OFFSET));
  memcpy(&raw[OUTBOX_PAYLOAD_OFFSET], event->payload, event->payload_size);
}

zs_event_outbox_result_t zs_event_outbox_enqueue(
    const zs_event_outbox_io_t *io,
    const zs_event_outbox_event_t *event) {
  uint8_t digest[ZS_SHA256_DIGEST_BYTES];
  uint8_t raw[ZS_EVENT_OUTBOX_SLOT_BYTES];
  uint8_t dynamic[OUTBOX_RETRY_BITMAP_BYTES + 4u];
  decoded_slot_t decoded;
  uint16_t target_slot = 0u;
  uint16_t delivered_slot = 0u;
  uint32_t newest_generation = 0u;
  uint32_t delivered_generation = 0u;
  bool target_found = false;
  bool delivered_found = false;
  bool generation_found = false;
  uint32_t generation;
  slot_state_t state;
  if (!io_valid(io)) return ZS_EVENT_OUTBOX_INVALID_ARGUMENT;
  if (!event_valid(event)) return ZS_EVENT_OUTBOX_INVALID_EVENT;
  zs_sha256_digest(event->payload, event->payload_size, digest);

  for (uint16_t slot = 0u; slot < io->slot_count; ++slot) {
    state = read_slot(io, slot, &decoded);
    if (state == SLOT_IO_ERROR || state == SLOT_CORRUPT) {
      memset(digest, 0, sizeof(digest));
      return slot_error(state);
    }
    if (state == SLOT_INCOMPLETE) {
      if (!target_found) {
        target_found = true;
        target_slot = slot;
      }
      continue;
    }
    if (!generation_found ||
        generation_newer(decoded.item.storage_generation, newest_generation)) {
      generation_found = true;
      newest_generation = decoded.item.storage_generation;
    }
    if (decoded.item.station_id == event->station_id &&
        decoded.item.event_id == event->event_id) {
      bool equal = same_event(&decoded.item, event, digest);
      memset(digest, 0, sizeof(digest));
      if (!equal) return ZS_EVENT_OUTBOX_CONFLICT;
      return decoded.delivered ? ZS_EVENT_OUTBOX_ALREADY_ACKED
                               : ZS_EVENT_OUTBOX_ALREADY_PENDING;
    }
    if (decoded.delivered &&
        (!delivered_found ||
         generation_newer(delivered_generation,
                          decoded.item.storage_generation))) {
      delivered_found = true;
      delivered_slot = slot;
      delivered_generation = decoded.item.storage_generation;
    }
  }
  if (!target_found && delivered_found) {
    target_found = true;
    target_slot = delivered_slot;
  }
  if (!target_found) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_FULL;
  }
  generation = generation_found ? newest_generation + 1u : 1u;
  if (generation == 0u) generation = 1u;
  encode_event(raw, event, generation, digest);
  if (!io->erase(io->ctx, target_slot)) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_IO_ERROR;
  }
  if (!io->read(io->ctx, target_slot, OUTBOX_RETRY_BITMAP_OFFSET,
                dynamic, sizeof(dynamic))) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_IO_ERROR;
  }
  if (!all_value(dynamic, sizeof(dynamic), 0xffu)) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_VERIFY_FAILED;
  }
  if (!io->write(io->ctx, target_slot, 0u, raw,
                 OUTBOX_PAYLOAD_OFFSET + event->payload_size)) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_IO_ERROR;
  }
  put_u32(raw, OUTBOX_COMMIT);
  if (!io->write(io->ctx, target_slot, OUTBOX_COMMIT_OFFSET, raw, 4u)) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_IO_ERROR;
  }
  state = read_slot(io, target_slot, &decoded);
  if (state == SLOT_IO_ERROR) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_IO_ERROR;
  }
  if (state != SLOT_VALID) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_VERIFY_FAILED;
  }
  if (decoded.delivered || decoded.item.retry_count != 0u ||
      decoded.item.storage_generation != generation ||
      !same_event(&decoded.item, event, digest)) {
    memset(digest, 0, sizeof(digest));
    return ZS_EVENT_OUTBOX_VERIFY_FAILED;
  }
  memset(digest, 0, sizeof(digest));
  return ZS_EVENT_OUTBOX_OK;
}

zs_event_outbox_result_t zs_event_outbox_enqueue_detection(
    const zs_event_outbox_io_t *io,
    const zs_detection_t *detection,
    uint8_t priority,
    uint8_t *workspace,
    size_t workspace_size) {
  zs_event_outbox_event_t event;
  size_t payload_size;
  if (!io_valid(io) || !detection || !workspace ||
      workspace_size < ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES)
    return ZS_EVENT_OUTBOX_INVALID_ARGUMENT;
  if (detection->schema_ver != 4u || detection->station_id == 0u ||
      detection->event_id == 0u || detection->event_time_us <= 0 ||
      priority > ZS_EVENT_OUTBOX_PRIORITY_MAX)
    return ZS_EVENT_OUTBOX_INVALID_EVENT;
  payload_size = zs_protocol_encode_detection(detection, workspace,
                                               workspace_size);
  if (payload_size == 0u ||
      payload_size > ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES)
    return ZS_EVENT_OUTBOX_INVALID_EVENT;
  event = (zs_event_outbox_event_t){
      detection->station_id, detection->boot_id, detection->seq_no,
      detection->event_id, detection->event_time_us, priority,
      workspace, payload_size};
  return zs_event_outbox_enqueue(io, &event);
}

zs_event_outbox_result_t zs_event_outbox_peek(
    const zs_event_outbox_io_t *io,
    zs_event_outbox_item_t *item) {
  decoded_slot_t decoded;
  bool found = false;
  slot_state_t state;
  if (!io_valid(io) || !item) return ZS_EVENT_OUTBOX_INVALID_ARGUMENT;
  memset(item, 0, sizeof(*item));
  for (uint16_t slot = 0u; slot < io->slot_count; ++slot) {
    state = read_slot(io, slot, &decoded);
    if (state == SLOT_IO_ERROR || state == SLOT_CORRUPT)
      return slot_error(state);
    if (state != SLOT_VALID || decoded.delivered) continue;
    if (!found || decoded.item.priority > item->priority ||
        (decoded.item.priority == item->priority &&
         generation_newer(item->storage_generation,
                          decoded.item.storage_generation)) ||
        (decoded.item.priority == item->priority &&
         decoded.item.storage_generation == item->storage_generation &&
         decoded.item.storage_slot < item->storage_slot)) {
      *item = decoded.item;
      found = true;
    }
  }
  return found ? ZS_EVENT_OUTBOX_OK : ZS_EVENT_OUTBOX_EMPTY;
}

static zs_event_outbox_result_t load_matching(
    const zs_event_outbox_io_t *io,
    const zs_event_outbox_item_t *item,
    decoded_slot_t *decoded) {
  slot_state_t state;
  if (!io_valid(io) || !item || !decoded || item->storage_slot >= io->slot_count)
    return ZS_EVENT_OUTBOX_INVALID_ARGUMENT;
  state = read_slot(io, item->storage_slot, decoded);
  if (state == SLOT_INCOMPLETE) return ZS_EVENT_OUTBOX_STALE_ITEM;
  if (state != SLOT_VALID) return slot_error(state);
  if (decoded->item.storage_generation != item->storage_generation ||
      decoded->item.station_id != item->station_id ||
      decoded->item.boot_id != item->boot_id ||
      decoded->item.seq_no != item->seq_no ||
      decoded->item.event_id != item->event_id ||
      decoded->item.event_time_us != item->event_time_us ||
      decoded->item.priority != item->priority ||
      decoded->item.payload_size != item->payload_size ||
      memcmp(decoded->item.payload_sha256, item->payload_sha256,
             ZS_SHA256_DIGEST_BYTES) != 0)
    return ZS_EVENT_OUTBOX_STALE_ITEM;
  return ZS_EVENT_OUTBOX_OK;
}

zs_event_outbox_result_t zs_event_outbox_note_attempt(
    const zs_event_outbox_io_t *io,
    const zs_event_outbox_item_t *item) {
  decoded_slot_t decoded;
  uint8_t bitmap[OUTBOX_RETRY_BITMAP_BYTES];
  uint8_t byte;
  uint8_t verify;
  unsigned bit_index;
  uint16_t previous_retry_count;
  zs_event_outbox_result_t loaded = load_matching(io, item, &decoded);
  if (loaded != ZS_EVENT_OUTBOX_OK) return loaded;
  if (decoded.delivered) return ZS_EVENT_OUTBOX_ALREADY_ACKED;
  if (decoded.item.retry_count >= ZS_EVENT_OUTBOX_MAX_RETRIES)
    return ZS_EVENT_OUTBOX_RETRY_EXHAUSTED;
  previous_retry_count = decoded.item.retry_count;
  if (!io->read(io->ctx, item->storage_slot, OUTBOX_RETRY_BITMAP_OFFSET,
                bitmap, sizeof(bitmap)) ||
      !first_set_bit(bitmap, sizeof(bitmap), &bit_index))
    return ZS_EVENT_OUTBOX_IO_ERROR;
  byte = bitmap[bit_index / 8u];
  byte &= (uint8_t)~(uint8_t)(1u << (bit_index % 8u));
  if (!io->write(io->ctx, item->storage_slot,
                 OUTBOX_RETRY_BITMAP_OFFSET + bit_index / 8u, &byte, 1u)) {
    if (!io->read(io->ctx, item->storage_slot,
                  OUTBOX_RETRY_BITMAP_OFFSET + bit_index / 8u, &verify, 1u) ||
        (verify & (uint8_t)(1u << (bit_index % 8u))) != 0u)
      return ZS_EVENT_OUTBOX_IO_ERROR;
  }
  loaded = load_matching(io, item, &decoded);
  if (loaded != ZS_EVENT_OUTBOX_OK) return loaded;
  return decoded.item.retry_count == previous_retry_count + 1u
             ? ZS_EVENT_OUTBOX_OK
             : ZS_EVENT_OUTBOX_VERIFY_FAILED;
}

zs_event_outbox_result_t zs_event_outbox_mark_application_acked(
    const zs_event_outbox_io_t *io,
    const zs_event_outbox_item_t *item) {
  decoded_slot_t decoded;
  uint8_t marker[4];
  uint8_t verify[4];
  zs_event_outbox_result_t loaded = load_matching(io, item, &decoded);
  if (loaded != ZS_EVENT_OUTBOX_OK) return loaded;
  if (decoded.delivered) return ZS_EVENT_OUTBOX_ALREADY_ACKED;
  put_u32(marker, OUTBOX_DELIVERED);
  if (!io->write(io->ctx, item->storage_slot, OUTBOX_DELIVERED_OFFSET,
                 marker, sizeof(marker))) {
    if (!io->read(io->ctx, item->storage_slot, OUTBOX_DELIVERED_OFFSET,
                  verify, sizeof(verify)) ||
        get_u32(verify) != OUTBOX_DELIVERED)
      return ZS_EVENT_OUTBOX_IO_ERROR;
  }
  loaded = load_matching(io, item, &decoded);
  if (loaded != ZS_EVENT_OUTBOX_OK) return loaded;
  return decoded.delivered ? ZS_EVENT_OUTBOX_OK
                           : ZS_EVENT_OUTBOX_VERIFY_FAILED;
}

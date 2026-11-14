#include "zs_event_outbox.h"
#include "zs_protocol.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define TEST_SLOTS 4u

typedef struct {
  uint8_t slots[TEST_SLOTS][ZS_EVENT_OUTBOX_SLOT_BYTES];
  uint16_t slot_count;
  unsigned write_calls;
  unsigned fail_write_call;
  size_t partial_write_bytes;
  int fail_read_slot;
} memory_outbox_t;

static void memory_init(memory_outbox_t *memory, uint16_t slot_count) {
  memset(memory, 0xff, sizeof(*memory));
  memory->slot_count = slot_count;
  memory->write_calls = 0u;
  memory->fail_write_call = 0u;
  memory->partial_write_bytes = 0u;
  memory->fail_read_slot = -1;
}

static bool memory_read(void *ctx, uint16_t slot, uint32_t offset,
                        uint8_t *data, size_t size) {
  memory_outbox_t *memory = ctx;
  if (!data || slot >= memory->slot_count ||
      (int)slot == memory->fail_read_slot ||
      offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  memcpy(data, &memory->slots[slot][offset], size);
  return true;
}

static bool memory_erase(void *ctx, uint16_t slot) {
  memory_outbox_t *memory = ctx;
  if (slot >= memory->slot_count) return false;
  memset(memory->slots[slot], 0xff, ZS_EVENT_OUTBOX_SLOT_BYTES);
  return true;
}

static bool program(memory_outbox_t *memory, uint16_t slot, uint32_t offset,
                    const uint8_t *data, size_t size) {
  for (size_t i = 0u; i < size; ++i) {
    if ((memory->slots[slot][offset + i] & data[i]) != data[i]) return false;
    memory->slots[slot][offset + i] = data[i];
  }
  return true;
}

static bool memory_write(void *ctx, uint16_t slot, uint32_t offset,
                         const uint8_t *data, size_t size) {
  memory_outbox_t *memory = ctx;
  size_t partial;
  if (!data || slot >= memory->slot_count ||
      offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  ++memory->write_calls;
  if (memory->fail_write_call != 0u &&
      memory->write_calls == memory->fail_write_call) {
    partial = memory->partial_write_bytes < size
                  ? memory->partial_write_bytes
                  : size;
    if (partial > 0u && !program(memory, slot, offset, data, partial))
      return false;
    return false;
  }
  return program(memory, slot, offset, data, size);
}

static zs_event_outbox_io_t memory_io(memory_outbox_t *memory) {
  const zs_event_outbox_io_t io = {
      memory, memory->slot_count, memory_read, memory_erase, memory_write};
  return io;
}

static zs_event_outbox_event_t event(uint64_t id, uint8_t priority,
                                     const uint8_t *payload,
                                     size_t payload_size) {
  const zs_event_outbox_event_t value = {
      .station_id = 17u,
      .boot_id = 9u,
      .seq_no = (uint32_t)id,
      .event_id = id,
      .event_time_us = (int64_t)(UINT64_C(1000000) + id),
      .priority = priority,
      .payload = payload,
      .payload_size = payload_size};
  return value;
}

static void test_priority_fifo_attempt_and_reclaim(void) {
  static const uint8_t one[] = {0xa1u, 0x00u, 0x01u};
  static const uint8_t two[] = {0xa1u, 0x00u, 0x02u};
  static const uint8_t three[] = {0xa1u, 0x00u, 0x03u};
  static const uint8_t four[] = {0xa1u, 0x00u, 0x04u};
  memory_outbox_t memory;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item;
  zs_event_outbox_event_t value;
  memory_init(&memory, 3u);
  io = memory_io(&memory);

  value = event(1u, 0u, one, sizeof(one));
  assert(zs_event_outbox_enqueue(&io, &value) == ZS_EVENT_OUTBOX_OK);
  value = event(2u, 3u, two, sizeof(two));
  assert(zs_event_outbox_enqueue(&io, &value) == ZS_EVENT_OUTBOX_OK);
  value = event(3u, 3u, three, sizeof(three));
  assert(zs_event_outbox_enqueue(&io, &value) == ZS_EVENT_OUTBOX_OK);

  { uint16_t pending = 0u; assert(zs_event_outbox_pending_count(&io, &pending) == ZS_EVENT_OUTBOX_OK && pending == 3u); }
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.event_id == 2u && item.retry_count == 0u);
  assert(memcmp(item.payload, two, sizeof(two)) == 0);
  assert(zs_event_outbox_note_attempt(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_note_attempt(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.event_id == 2u && item.retry_count == 2u);
  assert(zs_event_outbox_mark_application_acked(&io, &item) ==
         ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_mark_application_acked(&io, &item) ==
         ZS_EVENT_OUTBOX_ALREADY_ACKED);
  { uint16_t pending = 0u; assert(zs_event_outbox_pending_count(&io, &pending) == ZS_EVENT_OUTBOX_OK && pending == 2u); }
  assert(zs_event_outbox_pending_count(&io, NULL) == ZS_EVENT_OUTBOX_INVALID_ARGUMENT);

  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.event_id == 3u); /* same priority, older generation first */
  assert(zs_event_outbox_mark_application_acked(&io, &item) ==
         ZS_EVENT_OUTBOX_OK);
  value = event(4u, 2u, four, sizeof(four));
  assert(zs_event_outbox_enqueue(&io, &value) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.event_id == 4u); /* delivered slot reclaimed; pending id 1 kept */
}

static void test_duplicate_conflict_and_full(void) {
  static const uint8_t payload[] = {0x01u, 0x00u, 0x02u};
  static const uint8_t changed[] = {0x01u, 0x00u, 0x03u};
  memory_outbox_t memory;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item;
  zs_event_outbox_event_t first, conflict, second, third;
  memory_init(&memory, 2u);
  io = memory_io(&memory);
  first = event(10u, 1u, payload, sizeof(payload));
  conflict = event(10u, 1u, changed, sizeof(changed));
  second = event(11u, 1u, payload, sizeof(payload));
  third = event(12u, 1u, payload, sizeof(payload));

  assert(zs_event_outbox_enqueue(&io, &first) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_enqueue(&io, &first) ==
         ZS_EVENT_OUTBOX_ALREADY_PENDING);
  assert(zs_event_outbox_enqueue(&io, &conflict) ==
         ZS_EVENT_OUTBOX_CONFLICT);
  assert(zs_event_outbox_enqueue(&io, &second) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_enqueue(&io, &third) == ZS_EVENT_OUTBOX_FULL);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.event_id == first.event_id);
  assert(zs_event_outbox_mark_application_acked(&io, &item) ==
         ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_enqueue(&io, &first) ==
         ZS_EVENT_OUTBOX_ALREADY_ACKED);
  assert(zs_event_outbox_enqueue(&io, &third) == ZS_EVENT_OUTBOX_OK);
}

static void test_power_loss_is_at_least_once(void) {
  static const uint8_t payload[] = {0xa2u, 0x00u, 0x01u, 0x01u, 0x00u};
  memory_outbox_t memory;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item;
  zs_event_outbox_event_t value = event(20u, 2u, payload, sizeof(payload));
  memory_init(&memory, 2u);
  io = memory_io(&memory);

  memory.fail_write_call = 2u;
  memory.partial_write_bytes = 2u; /* torn commit marker */
  assert(zs_event_outbox_enqueue(&io, &value) == ZS_EVENT_OUTBOX_IO_ERROR);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_EMPTY);
  memory.write_calls = 0u;
  memory.fail_write_call = 0u;
  assert(zs_event_outbox_enqueue(&io, &value) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);

  memory.write_calls = 0u;
  memory.fail_write_call = 1u;
  memory.partial_write_bytes = 1u; /* write happened before reported loss */
  assert(zs_event_outbox_note_attempt(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.retry_count == 1u);

  memory.write_calls = 0u;
  memory.fail_write_call = 1u;
  memory.partial_write_bytes = 2u; /* torn application-ACK marker */
  assert(zs_event_outbox_mark_application_acked(&io, &item) ==
         ZS_EVENT_OUTBOX_IO_ERROR);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.event_id == value.event_id); /* safe duplicate, never lost */
  memory.write_calls = 0u;
  memory.fail_write_call = 0u;
  assert(zs_event_outbox_mark_application_acked(&io, &item) ==
         ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_EMPTY);
}

static void test_corruption_io_retry_limit_and_stale_token(void) {
  static const uint8_t payload[] = {0x82u, 0x00u, 0x01u};
  memory_outbox_t memory;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t old_item, current;
  zs_event_outbox_event_t first = event(30u, 1u, payload, sizeof(payload));
  zs_event_outbox_event_t next = event(31u, 1u, payload, sizeof(payload));
  memory_init(&memory, 1u);
  io = memory_io(&memory);
  assert(zs_event_outbox_enqueue(&io, &first) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(&io, &old_item) == ZS_EVENT_OUTBOX_OK);
  for (unsigned i = 0u; i < ZS_EVENT_OUTBOX_MAX_RETRIES; ++i)
    assert(zs_event_outbox_note_attempt(&io, &old_item) ==
           ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_note_attempt(&io, &old_item) ==
         ZS_EVENT_OUTBOX_RETRY_EXHAUSTED);
  assert(zs_event_outbox_peek(&io, &current) == ZS_EVENT_OUTBOX_OK);
  assert(current.retry_count == ZS_EVENT_OUTBOX_MAX_RETRIES);
  assert(zs_event_outbox_mark_application_acked(&io, &current) ==
         ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_enqueue(&io, &next) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_mark_application_acked(&io, &old_item) ==
         ZS_EVENT_OUTBOX_STALE_ITEM);

  memory.fail_read_slot = 0;
  assert(zs_event_outbox_peek(&io, &current) == ZS_EVENT_OUTBOX_IO_ERROR);
  memory.fail_read_slot = -1;
  memory.slots[0][80] ^= 1u;
  assert(zs_event_outbox_peek(&io, &current) == ZS_EVENT_OUTBOX_CORRUPT);
  assert(zs_event_outbox_enqueue(&io, &first) == ZS_EVENT_OUTBOX_CORRUPT);
}

static void test_real_detection_payload_and_argument_guards(void) {
  uint8_t encoded[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES];
  uint8_t oversized[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES + 1u] = {0};
  uint8_t digest[ZS_SHA256_DIGEST_BYTES];
  zs_detection_t detection;
  memory_outbox_t memory;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item;
  zs_event_outbox_event_t value;
  size_t encoded_size;
  memset(&detection, 0, sizeof(detection));
  detection.schema_ver = 4u;
  detection.station_id = 17u;
  detection.boot_id = 9u;
  detection.seq_no = 40u;
  detection.event_id = 40u;
  detection.event_time_us = INT64_C(1700000040);
  encoded_size = zs_protocol_encode_detection(&detection, encoded,
                                               sizeof(encoded));
  assert(encoded_size > 0u && encoded_size <= sizeof(encoded));
  memory_init(&memory, 1u);
  io = memory_io(&memory);
  assert(zs_event_outbox_enqueue_detection(&io, &detection, 3u, encoded,
                                            sizeof(encoded)) ==
         ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.payload_size == encoded_size);
  assert(memcmp(item.payload, encoded, encoded_size) == 0);
  zs_sha256_digest(encoded, encoded_size, digest);
  assert(memcmp(item.payload_sha256, digest, sizeof(digest)) == 0);

  value = event(40u, 3u, encoded, encoded_size);
  value.station_id = 0u;
  assert(zs_event_outbox_enqueue(&io, &value) ==
         ZS_EVENT_OUTBOX_INVALID_EVENT);
  value = event(41u, ZS_EVENT_OUTBOX_PRIORITY_MAX + 1u, encoded, encoded_size);
  assert(zs_event_outbox_enqueue(&io, &value) ==
         ZS_EVENT_OUTBOX_INVALID_EVENT);
  value = event(41u, 1u, oversized, sizeof(oversized));
  assert(zs_event_outbox_enqueue(&io, &value) ==
         ZS_EVENT_OUTBOX_INVALID_EVENT);
  assert(zs_event_outbox_enqueue(NULL, &value) ==
         ZS_EVENT_OUTBOX_INVALID_ARGUMENT);
  assert(zs_event_outbox_peek(&io, NULL) ==
         ZS_EVENT_OUTBOX_INVALID_ARGUMENT);
  assert(zs_event_outbox_enqueue_detection(
             &io, &detection, 3u, encoded, sizeof(encoded) - 1u) ==
         ZS_EVENT_OUTBOX_INVALID_ARGUMENT);

  memory_init(&memory, 1u);
  io = memory_io(&memory);
  value = event(42u, 1u, oversized, ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES);
  assert(zs_event_outbox_enqueue(&io, &value) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.payload_size == ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES);
  assert(memcmp(item.payload, oversized, item.payload_size) == 0);
}

int main(void) {
  test_priority_fifo_attempt_and_reclaim();
  test_duplicate_conflict_and_full();
  test_power_loss_is_at_least_once();
  test_corruption_io_retry_limit_and_stale_token();
  test_real_detection_payload_and_argument_guards();
  puts("zs_event_outbox_tests: OK");
  return 0;
}

#include "zs_command_journal.h"
#include "zs_command_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define TEST_SLOTS 4u

typedef struct {
  uint8_t slots[TEST_SLOTS][ZS_COMMAND_JOURNAL_SLOT_BYTES];
  uint16_t slot_count;
  unsigned write_calls;
  unsigned fail_write_call;
  int fail_read_slot;
} memory_journal_t;

static void memory_init(memory_journal_t *memory, uint16_t slot_count) {
  memset(memory, 0xff, sizeof(*memory));
  memory->slot_count = slot_count;
  memory->write_calls = 0u;
  memory->fail_write_call = 0u;
  memory->fail_read_slot = -1;
}

static bool memory_read(void *ctx, uint16_t slot, uint32_t offset,
                        uint8_t *data, size_t size) {
  memory_journal_t *memory = ctx;
  if (slot >= memory->slot_count || (int)slot == memory->fail_read_slot ||
      offset + size > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false;
  memcpy(data, &memory->slots[slot][offset], size);
  return true;
}

static bool memory_erase(void *ctx, uint16_t slot) {
  memory_journal_t *memory = ctx;
  if (slot >= memory->slot_count) return false;
  memset(memory->slots[slot], 0xff, ZS_COMMAND_JOURNAL_SLOT_BYTES);
  return true;
}

static bool memory_write(void *ctx, uint16_t slot, uint32_t offset,
                         const uint8_t *data, size_t size) {
  memory_journal_t *memory = ctx;
  if (slot >= memory->slot_count ||
      offset + size > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false;
  ++memory->write_calls;
  if (memory->fail_write_call != 0u &&
      memory->write_calls == memory->fail_write_call) return false;
  for (size_t i = 0u; i < size; ++i) {
    if ((memory->slots[slot][offset + i] & data[i]) != data[i]) return false;
    memory->slots[slot][offset + i] = data[i];
  }
  return true;
}

static zs_command_journal_io_t memory_io(memory_journal_t *memory) {
  const zs_command_journal_io_t io = {
      memory, memory->slot_count, memory_read, memory_erase, memory_write};
  return io;
}

static zs_command_t command(uint8_t id_tail, uint64_t created_us,
                            uint64_t expires_us) {
  static const uint8_t base_id[ZS_COMMAND_UUID_BYTES] = {
      0x12u, 0x34u, 0x56u, 0x78u, 0x12u, 0x34u, 0x56u, 0x78u,
      0x12u, 0x34u, 0x56u, 0x78u, 0x12u, 0x34u, 0x56u, 0x78u};
  zs_command_t value;
  memset(&value, 0, sizeof(value));
  value.station_id = 17u;
  memcpy(value.command_id, base_id, sizeof(base_id));
  value.command_id[ZS_COMMAND_UUID_BYTES - 1u] = id_tail;
  value.created_time_us = created_us;
  value.expires_time_us = expires_us;
  value.code = ZS_COMMAND_REQUEST_AUDIO;
  value.audio.event_id = 42u;
  value.audio.segment = ZS_AUDIO_SEGMENT_BOTH;
  return value;
}

static void test_persist_before_ack_and_dedup(void) {
  memory_journal_t memory;
  zs_command_journal_io_t io;
  zs_command_journal_record_t record;
  zs_command_t value;
  uint8_t ack[128];
  size_t ack_size;
  memory_init(&memory, TEST_SLOTS);
  io = memory_io(&memory);
  value = command(0x78u, UINT64_C(1000000), UINT64_C(2000000));

  assert(zs_command_journal_accept(NULL, &value, UINT64_C(1500000)) ==
         ZS_COMMAND_JOURNAL_INVALID_ARGUMENT);
  assert(zs_command_journal_dedup_lookup(&io, value.command_id) ==
         ZS_COMMAND_DEDUP_NOT_SEEN);
  assert(zs_command_journal_accept(&io, &value, UINT64_C(1500000)) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_dedup_lookup(&io, value.command_id) ==
         ZS_COMMAND_DEDUP_SEEN);
  assert(zs_command_journal_load(&io, value.command_id, &record) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(record.state == ZS_COMMAND_JOURNAL_STATE_ACCEPTED);
  assert(zs_command_journal_encode_ack(&io, value.command_id, ack,
                                       sizeof(ack)) == 0u);
  assert(zs_command_journal_accept(&io, &value, UINT64_C(1500001)) ==
         ZS_COMMAND_JOURNAL_ALREADY_ACCEPTED);

  zs_command_t conflict = value;
  conflict.audio.event_id = 43u;
  assert(zs_command_journal_accept(&io, &conflict, UINT64_C(1500001)) ==
         ZS_COMMAND_JOURNAL_CONFLICT);

  assert(zs_command_journal_complete(&io, value.command_id, ZS_COMMAND_ACK_OK,
                                     0u, UINT64_C(1750000)) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_load(&io, value.command_id, &record) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(record.state == ZS_COMMAND_JOURNAL_STATE_COMPLETED);
  ack_size = zs_command_journal_encode_ack(&io, value.command_id, ack,
                                            sizeof(ack));
  assert(ack_size == sizeof(zs_command_vector_ack));
  assert(memcmp(ack, zs_command_vector_ack, ack_size) == 0);
  assert(zs_command_journal_accept(&io, &value, UINT64_C(1800000)) ==
         ZS_COMMAND_JOURNAL_ALREADY_COMPLETED);
  assert(zs_command_journal_complete(&io, value.command_id,
                                     ZS_COMMAND_ACK_FAILED, 9u,
                                     UINT64_C(1800000)) ==
         ZS_COMMAND_JOURNAL_ALREADY_COMPLETED);
  assert(zs_command_journal_complete(&io, value.command_id,
                                     (zs_command_ack_result_t)-1, 0u,
                                     UINT64_C(1800000)) ==
         ZS_COMMAND_JOURNAL_INVALID_ARGUMENT);
}

static void test_power_loss_recovery(void) {
  memory_journal_t memory;
  zs_command_journal_io_t io;
  zs_command_journal_record_t record;
  zs_command_t value = command(1u, UINT64_C(1000000), UINT64_C(2000000));
  uint8_t ack[128];
  memory_init(&memory, TEST_SLOTS);
  io = memory_io(&memory);

  memory.fail_write_call = 2u; /* Body complete; commit marker absent. */
  assert(zs_command_journal_accept(&io, &value, UINT64_C(1500000)) ==
         ZS_COMMAND_JOURNAL_IO_ERROR);
  assert(zs_command_journal_load(&io, value.command_id, &record) ==
         ZS_COMMAND_JOURNAL_NOT_FOUND);

  memory.write_calls = 0u;
  memory.fail_write_call = 0u;
  assert(zs_command_journal_accept(&io, &value, UINT64_C(1500000)) ==
         ZS_COMMAND_JOURNAL_OK);
  memory.write_calls = 0u;
  memory.fail_write_call = 2u; /* COMPLETED is not committed. */
  assert(zs_command_journal_complete(&io, value.command_id,
                                     ZS_COMMAND_ACK_FAILED, 7u,
                                     UINT64_C(1700000)) ==
         ZS_COMMAND_JOURNAL_IO_ERROR);
  assert(zs_command_journal_load(&io, value.command_id, &record) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(record.state == ZS_COMMAND_JOURNAL_STATE_ACCEPTED);
  assert(zs_command_journal_encode_ack(&io, value.command_id, ack,
                                       sizeof(ack)) == 0u);

  memory.write_calls = 0u;
  memory.fail_write_call = 0u;
  assert(zs_command_journal_complete(&io, value.command_id,
                                     ZS_COMMAND_ACK_FAILED, 7u,
                                     UINT64_C(1700000)) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_encode_ack(&io, value.command_id, ack,
                                       sizeof(ack)) > 0u);
}

static void test_corruption_io_failure_and_bounded_reclaim(void) {
  memory_journal_t memory;
  zs_command_journal_io_t io;
  zs_command_journal_record_t record;
  zs_command_t first = command(2u, UINT64_C(1000000), UINT64_C(2000000));
  zs_command_t concurrent = command(4u, UINT64_C(1000000), UINT64_C(2000000));
  zs_command_t next = command(3u, UINT64_C(2100000), UINT64_C(3000000));
  memory_init(&memory, 2u);
  io = memory_io(&memory);
  assert(zs_command_journal_accept(&io, &first, UINT64_C(1500000)) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_complete(&io, first.command_id, ZS_COMMAND_ACK_OK,
                                     0u, UINT64_C(1700000)) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_accept(&io, &concurrent, UINT64_C(1800000)) ==
         ZS_COMMAND_JOURNAL_FULL);
  assert(zs_command_journal_accept(&io, &next, UINT64_C(1900000)) ==
         ZS_COMMAND_JOURNAL_INVALID_COMMAND);
  assert(zs_command_journal_accept(&io, &next, UINT64_C(2200000)) ==
         ZS_COMMAND_JOURNAL_OK);

  memory.fail_read_slot = 1;
  assert(zs_command_journal_load(&io, next.command_id, &record) ==
         ZS_COMMAND_JOURNAL_IO_ERROR);
  assert(zs_command_journal_dedup_lookup(&io, next.command_id) ==
         ZS_COMMAND_DEDUP_ERROR);
  memory.fail_read_slot = -1;
  memory.slots[0][76] ^= 0x01u;
  assert(zs_command_journal_load(&io, next.command_id, &record) ==
         ZS_COMMAND_JOURNAL_CORRUPT);
}

int main(void) {
  test_persist_before_ack_and_dedup();
  test_power_loss_recovery();
  test_corruption_io_failure_and_bounded_reclaim();
  puts("zs_command_journal_tests: OK");
  return 0;
}

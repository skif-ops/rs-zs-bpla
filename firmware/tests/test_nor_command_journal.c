#include "zs_nor_command_journal.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define MOCK_ERASE_BYTES 4096u
#define MOCK_BYTES (6u * MOCK_ERASE_BYTES)

typedef struct {
  uint8_t memory[MOCK_BYTES];
  uint8_t status;
  uint32_t millis;
  uint32_t erase_commands;
  uint32_t program_commands;
  uint32_t program_attempts;
  uint32_t fail_program_call;
} mock_nor_t;

static uint32_t mock_millis(void *ctx) {
  return ((mock_nor_t *)ctx)->millis;
}

static void mock_delay(void *ctx, uint32_t millis) {
  ((mock_nor_t *)ctx)->millis += millis;
}

static int mock_command(void *ctx, uint8_t opcode, uint32_t address,
                        uint8_t address_bytes, const uint8_t *tx,
                        size_t tx_size, uint8_t *rx, size_t rx_size) {
  mock_nor_t *mock = ctx;
  if (opcode == 0x05u) {
    if (!rx || rx_size != 1u) return -1;
    rx[0] = mock->status;
    return 0;
  }
  if (opcode == 0x06u) {
    mock->status |= 0x02u;
    return 0;
  }
  if (opcode == 0x13u) {
    if (address_bytes != 4u || !rx || tx || tx_size != 0u ||
        (uint64_t)address + rx_size > MOCK_BYTES)
      return -1;
    memcpy(rx, &mock->memory[address], rx_size);
    return 0;
  }
  if (opcode == 0x12u) {
    if (address_bytes != 4u || !tx || rx || rx_size != 0u || tx_size == 0u ||
        tx_size > 256u || (mock->status & 0x02u) == 0u ||
        address / 256u != (address + (uint32_t)tx_size - 1u) / 256u ||
        (uint64_t)address + tx_size > MOCK_BYTES)
      return -1;
    ++mock->program_attempts;
    if (mock->program_attempts == mock->fail_program_call) {
      mock->status &= (uint8_t)~0x02u;
      return -1;
    }
    for (size_t i = 0u; i < tx_size; ++i) {
      if ((mock->memory[address + i] & tx[i]) != tx[i]) return -1;
      mock->memory[address + i] = tx[i];
    }
    mock->status &= (uint8_t)~0x02u;
    ++mock->program_commands;
    return 0;
  }
  if (opcode == 0x21u) {
    if (address_bytes != 4u || tx || tx_size != 0u || rx || rx_size != 0u ||
        (mock->status & 0x02u) == 0u ||
        address % MOCK_ERASE_BYTES != 0u ||
        (uint64_t)address + MOCK_ERASE_BYTES > MOCK_BYTES)
      return -1;
    memset(&mock->memory[address], 0xff, MOCK_ERASE_BYTES);
    mock->status &= (uint8_t)~0x02u;
    ++mock->erase_commands;
    return 0;
  }
  return -1;
}

static zs_nor_t make_nor(mock_nor_t *mock) {
  const zs_nor_port_t port = {
      mock, mock_command, mock_millis, mock_delay};
  zs_nor_geometry_t geometry = zs_nor_geometry_64m_4byte();
  zs_nor_t nor;
  geometry.capacity_bytes = MOCK_BYTES;
  assert(zs_nor_init(&nor, &port, &geometry));
  return nor;
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

static void test_erase_isolation_roundtrip_and_restart(void) {
  mock_nor_t mock;
  zs_nor_t nor;
  zs_nor_command_journal_adapter_t adapter, restarted_adapter;
  zs_command_journal_io_t io, restarted_io;
  zs_command_journal_record_t record;
  zs_command_t first = command(1u, UINT64_C(1000000), UINT64_C(2000000));
  zs_command_t second = command(2u, UINT64_C(1000000), UINT64_C(2000000));

  memset(&mock, 0, sizeof(mock));
  memset(mock.memory, 0xff, sizeof(mock.memory));
  memset(&mock.memory[0], 0xa5, MOCK_ERASE_BYTES);
  memset(&mock.memory[5u * MOCK_ERASE_BYTES], 0x5a, MOCK_ERASE_BYTES);
  nor = make_nor(&mock);
  assert(zs_nor_command_journal_io_init(
      &adapter, &nor, MOCK_ERASE_BYTES, 3u, &io));
  assert(io.slot_count == 3u && io.ctx == &adapter);
  assert(zs_command_journal_accept(&io, &first, UINT64_C(1500000)) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_complete(
      &io, first.command_id, ZS_COMMAND_ACK_OK, 0u,
      UINT64_C(1700000)) == ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_accept(&io, &second, UINT64_C(1800000)) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(mock.erase_commands == 3u && mock.program_commands == 6u);

  assert(zs_nor_command_journal_io_init(
      &restarted_adapter, &nor, MOCK_ERASE_BYTES, 3u, &restarted_io));
  assert(zs_command_journal_load(
      &restarted_io, first.command_id, &record) == ZS_COMMAND_JOURNAL_OK);
  assert(record.state == ZS_COMMAND_JOURNAL_STATE_COMPLETED);
  assert(zs_command_journal_load(
      &restarted_io, second.command_id, &record) == ZS_COMMAND_JOURNAL_OK);
  assert(record.state == ZS_COMMAND_JOURNAL_STATE_ACCEPTED);
  for (size_t i = 0u; i < MOCK_ERASE_BYTES; ++i) {
    assert(mock.memory[i] == 0xa5u);
    assert(mock.memory[5u * MOCK_ERASE_BYTES + i] == 0x5au);
  }
}

static void test_torn_commit_is_reusable_without_neighbour_erase(void) {
  mock_nor_t mock;
  zs_nor_t nor;
  zs_nor_command_journal_adapter_t adapter;
  zs_command_journal_io_t io;
  zs_command_journal_record_t record;
  zs_command_t value = command(3u, UINT64_C(1000000), UINT64_C(2000000));
  uint8_t neighbour[MOCK_ERASE_BYTES];

  memset(&mock, 0, sizeof(mock));
  memset(mock.memory, 0xff, sizeof(mock.memory));
  memset(&mock.memory[4u * MOCK_ERASE_BYTES], 0x3c, MOCK_ERASE_BYTES);
  memcpy(neighbour, &mock.memory[4u * MOCK_ERASE_BYTES], sizeof(neighbour));
  nor = make_nor(&mock);
  assert(zs_nor_command_journal_io_init(
      &adapter, &nor, MOCK_ERASE_BYTES, 2u, &io));
  mock.fail_program_call = 2u;
  assert(zs_command_journal_accept(&io, &value, UINT64_C(1500000)) ==
         ZS_COMMAND_JOURNAL_IO_ERROR);
  assert(zs_command_journal_load(&io, value.command_id, &record) ==
         ZS_COMMAND_JOURNAL_NOT_FOUND);
  mock.fail_program_call = 0u;
  assert(zs_command_journal_accept(&io, &value, UINT64_C(1500000)) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(zs_command_journal_load(&io, value.command_id, &record) ==
         ZS_COMMAND_JOURNAL_OK);
  assert(record.state == ZS_COMMAND_JOURNAL_STATE_ACCEPTED);
  assert(memcmp(neighbour, &mock.memory[4u * MOCK_ERASE_BYTES],
                sizeof(neighbour)) == 0);
}

static void test_partition_and_callback_guards(void) {
  mock_nor_t mock;
  zs_nor_t nor, invalid;
  zs_nor_command_journal_adapter_t adapter;
  zs_command_journal_io_t io;
  uint8_t byte;

  memset(&mock, 0, sizeof(mock));
  memset(mock.memory, 0xff, sizeof(mock.memory));
  nor = make_nor(&mock);
  assert(!zs_nor_command_journal_io_init(
      &adapter, &nor, 1u, 2u, &io));
  assert(io.ctx == NULL && adapter.nor == NULL);
  assert(!zs_nor_command_journal_io_init(
      &adapter, &nor, MOCK_ERASE_BYTES, 1u, &io));
  assert(!zs_nor_command_journal_io_init(
      &adapter, &nor, 5u * MOCK_ERASE_BYTES, 2u, &io));
  invalid = nor;
  invalid.geometry.erase_bytes = 64u;
  assert(!zs_nor_command_journal_io_init(
      &adapter, &invalid, 0u, 2u, &io));
  invalid = nor;
  invalid.geometry.page_bytes = 0u;
  assert(!zs_nor_command_journal_io_init(
      &adapter, &invalid, 0u, 2u, &io));
  invalid = nor;
  invalid.port.millis = NULL;
  assert(!zs_nor_command_journal_io_init(
      &adapter, &invalid, 0u, 2u, &io));
  assert(zs_nor_command_journal_io_init(
      &adapter, &nor, MOCK_ERASE_BYTES, 2u, &io));
  assert(!io.read(io.ctx, 2u, 0u, &byte, 1u));
  assert(!io.read(io.ctx, 0u, ZS_COMMAND_JOURNAL_SLOT_BYTES, &byte, 1u));
  assert(!io.write(io.ctx, 0u, 0u, NULL, 1u));
}

int main(void) {
  test_erase_isolation_roundtrip_and_restart();
  test_torn_commit_is_reusable_without_neighbour_erase();
  test_partition_and_callback_guards();
  puts("zs_nor_command_journal_tests: OK");
  return 0;
}

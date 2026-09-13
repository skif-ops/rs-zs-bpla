#include "zs_nor_event_outbox.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define MOCK_ERASE_BYTES 4096u
#define MOCK_BYTES (5u * MOCK_ERASE_BYTES)

typedef struct {
  uint8_t memory[MOCK_BYTES];
  uint8_t status;
  uint32_t millis;
  uint32_t erase_commands;
  uint32_t program_commands;
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

static zs_event_outbox_event_t event(uint64_t event_id, uint8_t priority,
                                     const uint8_t *payload,
                                     size_t payload_size) {
  const zs_event_outbox_event_t value = {
      17u, 9u, (uint32_t)event_id, event_id, (int64_t)(1000u + event_id),
      priority, payload, payload_size};
  return value;
}

static void test_sector_isolation_reclaim_and_roundtrip(void) {
  static const uint8_t first_payload[] = {0xa1u, 0x01u, 0x02u};
  static const uint8_t second_payload[] = {0xa1u, 0x01u, 0x03u, 0x00u};
  static const uint8_t third_payload[] = {0xa1u, 0x01u, 0x04u};
  mock_nor_t mock;
  zs_nor_t nor;
  zs_nor_event_outbox_adapter_t adapter;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item;
  zs_event_outbox_event_t first, second, third;
  uint8_t preserved[MOCK_ERASE_BYTES];

  memset(&mock, 0, sizeof(mock));
  memset(mock.memory, 0xff, sizeof(mock.memory));
  memset(&mock.memory[0], 0xa5, MOCK_ERASE_BYTES);
  memset(&mock.memory[4u * MOCK_ERASE_BYTES], 0x5a, MOCK_ERASE_BYTES);
  nor = make_nor(&mock);
  assert(zs_nor_event_outbox_io_init(
      &adapter, &nor, MOCK_ERASE_BYTES, 2u, &io));
  assert(io.slot_count == 2u && io.ctx == &adapter);

  first = event(1u, 3u, first_payload, sizeof(first_payload));
  second = event(2u, 1u, second_payload, sizeof(second_payload));
  third = event(3u, 2u, third_payload, sizeof(third_payload));
  assert(zs_event_outbox_enqueue(&io, &first) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_enqueue(&io, &second) == ZS_EVENT_OUTBOX_OK);
  assert(mock.erase_commands == 2u);
  assert(zs_event_outbox_enqueue(&io, &third) == ZS_EVENT_OUTBOX_FULL);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.event_id == 1u && item.priority == 3u);
  assert(memcmp(item.payload, first_payload, sizeof(first_payload)) == 0);

  memcpy(preserved, &mock.memory[2u * MOCK_ERASE_BYTES], sizeof(preserved));
  assert(zs_event_outbox_mark_application_acked(&io, &item) ==
         ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_enqueue(&io, &third) == ZS_EVENT_OUTBOX_OK);
  assert(mock.erase_commands == 3u);
  assert(memcmp(preserved, &mock.memory[2u * MOCK_ERASE_BYTES],
                sizeof(preserved)) == 0);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.event_id == 3u && item.priority == 2u);

  for (size_t i = 0u; i < MOCK_ERASE_BYTES; ++i) {
    assert(mock.memory[i] == 0xa5u);
    assert(mock.memory[4u * MOCK_ERASE_BYTES + i] == 0x5au);
  }
  assert(mock.program_commands > 0u);
}

static void test_partition_and_callback_guards(void) {
  mock_nor_t mock;
  zs_nor_t nor, small_erase;
  zs_nor_event_outbox_adapter_t adapter;
  zs_event_outbox_io_t io;
  uint8_t byte;
  memset(&mock, 0, sizeof(mock));
  memset(mock.memory, 0xff, sizeof(mock.memory));
  nor = make_nor(&mock);

  assert(!zs_nor_event_outbox_io_init(&adapter, &nor, 1u, 1u, &io));
  assert(io.ctx == NULL && adapter.nor == NULL);
  assert(!zs_nor_event_outbox_io_init(
      &adapter, &nor, MOCK_ERASE_BYTES, 0u, &io));
  assert(!zs_nor_event_outbox_io_init(
      &adapter, &nor, 4u * MOCK_ERASE_BYTES, 2u, &io));
  small_erase = nor;
  small_erase.geometry.erase_bytes = 512u;
  assert(!zs_nor_event_outbox_io_init(
      &adapter, &small_erase, 0u, 1u, &io));
  small_erase = nor;
  small_erase.port.millis = NULL;
  assert(!zs_nor_event_outbox_io_init(
      &adapter, &small_erase, 0u, 1u, &io));
  assert(zs_nor_event_outbox_io_init(
      &adapter, &nor, MOCK_ERASE_BYTES, 2u, &io));
  assert(!io.read(io.ctx, 2u, 0u, &byte, 1u));
  assert(!io.read(io.ctx, 0u, ZS_EVENT_OUTBOX_SLOT_BYTES, &byte, 1u));
  assert(!io.write(io.ctx, 0u, 0u, NULL, 1u));
}

int main(void) {
  test_sector_isolation_reclaim_and_roundtrip();
  test_partition_and_callback_guards();
  puts("zs_nor_event_outbox_tests: OK");
  return 0;
}

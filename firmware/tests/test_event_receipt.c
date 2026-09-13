#include "zs_event_receipt.h"
#include "zs_event_receipt_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define TEST_SLOTS 2u

typedef struct {
  uint8_t slots[TEST_SLOTS][ZS_EVENT_OUTBOX_SLOT_BYTES];
  unsigned write_calls;
  unsigned fail_write_call;
  size_t partial_write_bytes;
} memory_outbox_t;

static void memory_init(memory_outbox_t *memory) {
  memset(memory, 0xff, sizeof(*memory));
  memory->write_calls = 0u;
  memory->fail_write_call = 0u;
  memory->partial_write_bytes = 0u;
}

static bool memory_read(void *ctx, uint16_t slot, uint32_t offset,
                        uint8_t *data, size_t size) {
  memory_outbox_t *memory = ctx;
  if (slot >= TEST_SLOTS || offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  memcpy(data, &memory->slots[slot][offset], size);
  return true;
}

static bool memory_erase(void *ctx, uint16_t slot) {
  memory_outbox_t *memory = ctx;
  if (slot >= TEST_SLOTS) return false;
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
  if (slot >= TEST_SLOTS || offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  ++memory->write_calls;
  if (memory->fail_write_call != 0u &&
      memory->write_calls == memory->fail_write_call) {
    partial = memory->partial_write_bytes < size
                  ? memory->partial_write_bytes
                  : size;
    if (partial > 0u) (void)program(memory, slot, offset, data, partial);
    return false;
  }
  return program(memory, slot, offset, data, size);
}

static zs_event_outbox_io_t memory_io(memory_outbox_t *memory) {
  const zs_event_outbox_io_t io = {
      memory, TEST_SLOTS, memory_read, memory_erase, memory_write};
  return io;
}

static zs_event_outbox_item_t enqueue_vector(
    memory_outbox_t *memory,
    zs_event_outbox_io_t *io) {
  zs_event_outbox_event_t event = {
      ZS_EVENT_RECEIPT_VECTOR_STATION_ID,
      ZS_EVENT_RECEIPT_VECTOR_BOOT_ID,
      ZS_EVENT_RECEIPT_VECTOR_SEQ_NO,
      ZS_EVENT_RECEIPT_VECTOR_EVENT_ID,
      ZS_EVENT_RECEIPT_VECTOR_EVENT_TIME_US,
      2u,
      zs_event_receipt_vector_event_payload,
      sizeof(zs_event_receipt_vector_event_payload)};
  zs_event_outbox_item_t item;
  memory_init(memory);
  *io = memory_io(memory);
  assert(zs_event_outbox_enqueue(io, &event) == ZS_EVENT_OUTBOX_OK);
  assert(zs_event_outbox_peek(io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(memcmp(item.payload_sha256,
                zs_event_receipt_vector_payload_sha256,
                ZS_SHA256_DIGEST_BYTES) == 0);
  return item;
}

static zs_event_receipt_transport_t make_transport(void) {
  static const uint8_t tenant[] = {'e', 'v', 't'};
  static const uint8_t expected[] = "zs/v1/evt/17/receipt";
  zs_event_receipt_transport_t transport;
  assert(zs_event_receipt_transport_init(
      &transport, ZS_EVENT_RECEIPT_VECTOR_STATION_ID,
      tenant, sizeof(tenant)));
  assert(transport.topic_size == sizeof(expected) - 1u);
  assert(memcmp(transport.topic, expected, sizeof(expected) - 1u) == 0);
  return transport;
}

static void test_server_vector_applies_after_exact_match(void) {
  memory_outbox_t memory;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item = enqueue_vector(&memory, &io);
  zs_event_outbox_item_t applied_item = item;
  zs_event_receipt_transport_t transport = make_transport();
  zs_event_receipt_status_t status;

  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      zs_event_receipt_vector_payload, sizeof(zs_event_receipt_vector_payload),
      ZS_EVENT_RECEIPT_QOS, false, &status) == ZS_EVENT_RECEIPT_APPLIED);
  assert(status == ZS_EVENT_RECEIPT_STATUS_OK);
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &applied_item, transport.topic, transport.topic_size,
      zs_event_receipt_vector_payload, sizeof(zs_event_receipt_vector_payload),
      ZS_EVENT_RECEIPT_QOS, false, &status) ==
         ZS_EVENT_RECEIPT_ALREADY_APPLIED);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_EMPTY);
}

static void test_topic_delivery_and_receipt_rejections(void) {
  static const uint8_t wrong_topic[] = "zs/v1/evt/18/receipt";
  memory_outbox_t memory;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item = enqueue_vector(&memory, &io);
  zs_event_receipt_transport_t transport = make_transport();
  zs_event_receipt_t decoded;
  zs_event_receipt_status_t status;
  uint8_t changed[ZS_EVENT_RECEIPT_MAX_BYTES + 1u];

  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, wrong_topic, sizeof(wrong_topic) - 1u,
      zs_event_receipt_vector_payload, sizeof(zs_event_receipt_vector_payload),
      1u, false, &status) == ZS_EVENT_RECEIPT_REJECTED_TOPIC);
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      zs_event_receipt_vector_payload, sizeof(zs_event_receipt_vector_payload),
      0u, false, &status) == ZS_EVENT_RECEIPT_REJECTED_DELIVERY);
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      zs_event_receipt_vector_payload, sizeof(zs_event_receipt_vector_payload),
      1u, true, &status) == ZS_EVENT_RECEIPT_REJECTED_DELIVERY);

  memcpy(changed, zs_event_receipt_vector_payload,
         sizeof(zs_event_receipt_vector_payload));
  changed[sizeof(zs_event_receipt_vector_payload) - 1u] ^= 1u;
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      changed, sizeof(zs_event_receipt_vector_payload), 1u, false,
      &status) == ZS_EVENT_RECEIPT_REJECTED_RECEIPT);
  assert(status == ZS_EVENT_RECEIPT_STATUS_SHA256_MISMATCH);

  memcpy(changed, zs_event_receipt_vector_payload,
         sizeof(zs_event_receipt_vector_payload));
  changed[6] = 18u;
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      changed, sizeof(zs_event_receipt_vector_payload), 1u, false,
      &status) == ZS_EVENT_RECEIPT_REJECTED_RECEIPT);
  assert(status == ZS_EVENT_RECEIPT_STATUS_STATION_MISMATCH);

  memcpy(changed, zs_event_receipt_vector_payload,
         sizeof(zs_event_receipt_vector_payload));
  changed[10] = 6u;
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      changed, sizeof(zs_event_receipt_vector_payload), 1u, false,
      &status) == ZS_EVENT_RECEIPT_REJECTED_RECEIPT);
  assert(status == ZS_EVENT_RECEIPT_STATUS_ITEM_MISMATCH);

  changed[0] = 0xa7u;
  changed[1] = 0x18u;
  changed[2] = 0x00u;
  memcpy(&changed[3], &zs_event_receipt_vector_payload[2],
         sizeof(zs_event_receipt_vector_payload) - 2u);
  assert(zs_event_receipt_decode(
      changed, sizeof(zs_event_receipt_vector_payload) + 1u,
      ZS_EVENT_RECEIPT_VECTOR_STATION_ID,
      &decoded) == ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR);

  memcpy(changed, zs_event_receipt_vector_payload,
         sizeof(zs_event_receipt_vector_payload));
  changed[sizeof(zs_event_receipt_vector_payload)] = 0u;
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      changed, sizeof(zs_event_receipt_vector_payload) + 1u, 1u, false,
      &status) == ZS_EVENT_RECEIPT_REJECTED_RECEIPT);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
}

static void test_torn_ack_marker_remains_pending(void) {
  memory_outbox_t memory;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item = enqueue_vector(&memory, &io);
  zs_event_receipt_transport_t transport = make_transport();
  zs_event_receipt_status_t status;
  memory.write_calls = 0u;
  memory.fail_write_call = 1u;
  memory.partial_write_bytes = 2u;
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      zs_event_receipt_vector_payload, sizeof(zs_event_receipt_vector_payload),
      1u, false, &status) == ZS_EVENT_RECEIPT_STORAGE_ERROR);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  memory.write_calls = 0u;
  memory.fail_write_call = 0u;
  assert(zs_event_receipt_transport_handle(
      &transport, &io, &item, transport.topic, transport.topic_size,
      zs_event_receipt_vector_payload, sizeof(zs_event_receipt_vector_payload),
      1u, false, &status) == ZS_EVENT_RECEIPT_APPLIED);
}

static void test_transport_and_argument_guards(void) {
  static const uint8_t invalid_tenant[] = "bad/+";
  zs_event_receipt_transport_t transport;
  zs_event_receipt_t receipt;
  assert(!zs_event_receipt_transport_init(
      &transport, 17u, invalid_tenant, sizeof(invalid_tenant) - 1u));
  assert(!zs_event_receipt_transport_init(&transport, 0u,
                                          invalid_tenant, 3u));
  assert(zs_event_receipt_decode(
      NULL, 0u, 17u, &receipt) == ZS_EVENT_RECEIPT_STATUS_INVALID_ARGUMENT);
  assert(zs_event_receipt_decode(
      zs_event_receipt_vector_payload,
      sizeof(zs_event_receipt_vector_payload), 0u,
      &receipt) == ZS_EVENT_RECEIPT_STATUS_INVALID_ARGUMENT);
}

int main(void) {
  test_server_vector_applies_after_exact_match();
  test_topic_delivery_and_receipt_rejections();
  test_torn_ack_marker_remains_pending();
  test_transport_and_argument_guards();
  puts("zs_event_receipt_tests: OK");
  return 0;
}

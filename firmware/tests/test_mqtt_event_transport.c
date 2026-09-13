#include "zs_mqtt_event_transport.h"
#include "zs_event_receipt_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define TEST_SLOTS 3u

typedef struct {
  uint8_t slots[TEST_SLOTS][ZS_EVENT_OUTBOX_SLOT_BYTES];
  unsigned write_calls;
  unsigned fail_write_call;
  size_t partial_write_bytes;
} fixture_t;

static void fixture_init(fixture_t *fixture) {
  memset(fixture, 0xff, sizeof(*fixture));
  fixture->write_calls = 0u;
  fixture->fail_write_call = 0u;
  fixture->partial_write_bytes = 0u;
}

static bool storage_read(void *ctx, uint16_t slot, uint32_t offset,
                         uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= TEST_SLOTS || offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  memcpy(data, &fixture->slots[slot][offset], size);
  return true;
}

static bool storage_erase(void *ctx, uint16_t slot) {
  fixture_t *fixture = ctx;
  if (slot >= TEST_SLOTS) return false;
  memset(fixture->slots[slot], 0xff, ZS_EVENT_OUTBOX_SLOT_BYTES);
  return true;
}

static bool program(fixture_t *fixture, uint16_t slot, uint32_t offset,
                    const uint8_t *data, size_t size) {
  for (size_t i = 0u; i < size; ++i) {
    if ((fixture->slots[slot][offset + i] & data[i]) != data[i]) return false;
    fixture->slots[slot][offset + i] = data[i];
  }
  return true;
}

static bool storage_write(void *ctx, uint16_t slot, uint32_t offset,
                          const uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  size_t partial;
  if (slot >= TEST_SLOTS || offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  ++fixture->write_calls;
  if (fixture->fail_write_call != 0u &&
      fixture->write_calls == fixture->fail_write_call) {
    partial = fixture->partial_write_bytes < size
                  ? fixture->partial_write_bytes
                  : size;
    if (partial > 0u) (void)program(fixture, slot, offset, data, partial);
    return false;
  }
  return program(fixture, slot, offset, data, size);
}

static zs_event_outbox_io_t fixture_io(fixture_t *fixture) {
  const zs_event_outbox_io_t io = {
      fixture, TEST_SLOTS, storage_read, storage_erase, storage_write};
  return io;
}

static void enqueue_vector(fixture_t *fixture, zs_event_outbox_io_t *io,
                           uint32_t station_id) {
  const zs_event_outbox_event_t event = {
      station_id,
      ZS_EVENT_RECEIPT_VECTOR_BOOT_ID,
      ZS_EVENT_RECEIPT_VECTOR_SEQ_NO,
      ZS_EVENT_RECEIPT_VECTOR_EVENT_ID,
      ZS_EVENT_RECEIPT_VECTOR_EVENT_TIME_US,
      2u,
      zs_event_receipt_vector_event_payload,
      sizeof(zs_event_receipt_vector_event_payload)};
  fixture_init(fixture);
  *io = fixture_io(fixture);
  assert(zs_event_outbox_enqueue(io, &event) == ZS_EVENT_OUTBOX_OK);
}

static zs_mqtt_event_transport_t make_transport(
    const zs_event_outbox_io_t *io) {
  static const uint8_t tenant[] = {'e', 'v', 't'};
  static const uint8_t expected_up[] = "zs/v1/evt/17/up";
  static const uint8_t expected_receipt[] = "zs/v1/evt/17/receipt";
  zs_mqtt_event_transport_t transport;
  assert(zs_mqtt_event_transport_init(
      &transport, io, ZS_EVENT_RECEIPT_VECTOR_STATION_ID,
      tenant, sizeof(tenant)));
  assert(transport.up_topic_size == sizeof(expected_up) - 1u);
  assert(memcmp(transport.up_topic, expected_up, sizeof(expected_up) - 1u) == 0);
  assert(transport.receipt.topic_size == sizeof(expected_receipt) - 1u);
  assert(memcmp(transport.receipt.topic, expected_receipt,
                sizeof(expected_receipt) - 1u) == 0);
  return transport;
}

static zs_mqtt_event_message_t receipt_message(
    const zs_mqtt_event_transport_t *transport) {
  const zs_mqtt_event_message_t message = {
      transport->receipt.topic,
      transport->receipt.topic_size,
      zs_event_receipt_vector_payload,
      sizeof(zs_event_receipt_vector_payload),
      ZS_MQTT_EVENT_QOS,
      false};
  return message;
}

static void test_retry_then_exact_receipt_lifecycle(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t pending;
  zs_mqtt_event_transport_t transport;
  zs_mqtt_event_message_t publication, receipt;
  zs_event_receipt_status_t status;
  enqueue_vector(&fixture, &io, ZS_EVENT_RECEIPT_VECTOR_STATION_ID);
  transport = make_transport(&io);

  assert(zs_mqtt_event_transport_prepare(&transport, &publication) ==
         ZS_MQTT_EVENT_PUBLICATION_READY);
  assert(publication.topic == transport.up_topic);
  assert(publication.topic_size == transport.up_topic_size);
  assert(publication.payload == transport.publication_item.payload);
  assert(publication.payload_size ==
         sizeof(zs_event_receipt_vector_event_payload));
  assert(memcmp(publication.payload, zs_event_receipt_vector_event_payload,
                publication.payload_size) == 0);
  assert(publication.qos == ZS_MQTT_EVENT_QOS && !publication.retained);
  assert(zs_event_outbox_peek(&io, &pending) == ZS_EVENT_OUTBOX_OK);
  assert(pending.retry_count == 1u);

  /* MQTT PUBACK is deliberately a no-op: an explicit retry returns same bytes. */
  assert(zs_mqtt_event_transport_prepare(&transport, &publication) ==
         ZS_MQTT_EVENT_PUBLICATION_READY);
  assert(memcmp(publication.payload, zs_event_receipt_vector_event_payload,
                publication.payload_size) == 0);
  assert(zs_event_outbox_peek(&io, &pending) == ZS_EVENT_OUTBOX_OK);
  assert(pending.retry_count == 2u);

  receipt = receipt_message(&transport);
  assert(zs_mqtt_event_transport_handle_receipt(
      &transport, &receipt, &status) == ZS_EVENT_RECEIPT_APPLIED);
  assert(status == ZS_EVENT_RECEIPT_STATUS_OK);
  assert(zs_mqtt_event_transport_prepare(&transport, &publication) ==
         ZS_MQTT_EVENT_EMPTY);
  assert(publication.topic == NULL && publication.payload == NULL);
  assert(zs_mqtt_event_transport_handle_receipt(
      &transport, &receipt, &status) == ZS_EVENT_RECEIPT_ALREADY_APPLIED);
}

static void test_queued_receipt_applies_after_transport_restart(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item;
  zs_mqtt_event_transport_t before_restart, after_restart;
  zs_mqtt_event_message_t publication, receipt;
  zs_event_receipt_status_t status;
  enqueue_vector(&fixture, &io, ZS_EVENT_RECEIPT_VECTOR_STATION_ID);
  before_restart = make_transport(&io);
  assert(zs_mqtt_event_transport_prepare(&before_restart, &publication) ==
         ZS_MQTT_EVENT_PUBLICATION_READY);

  after_restart = make_transport(&io);
  receipt = receipt_message(&after_restart);
  assert(zs_mqtt_event_transport_handle_receipt(
      &after_restart, &receipt, &status) == ZS_EVENT_RECEIPT_APPLIED);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_EMPTY);
}

static void test_receipt_rejection_and_attempt_storage_failure(void) {
  static const uint8_t wrong_topic[] = "zs/v1/evt/18/receipt";
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item;
  zs_mqtt_event_transport_t transport;
  zs_mqtt_event_message_t publication, receipt;
  zs_event_receipt_status_t status;
  uint8_t changed[sizeof(zs_event_receipt_vector_payload)];
  enqueue_vector(&fixture, &io, ZS_EVENT_RECEIPT_VECTOR_STATION_ID);
  transport = make_transport(&io);
  receipt = receipt_message(&transport);

  receipt.topic = wrong_topic;
  receipt.topic_size = sizeof(wrong_topic) - 1u;
  assert(zs_mqtt_event_transport_handle_receipt(
      &transport, &receipt, &status) == ZS_EVENT_RECEIPT_REJECTED_TOPIC);
  receipt = receipt_message(&transport);
  receipt.qos = 0u;
  assert(zs_mqtt_event_transport_handle_receipt(
      &transport, &receipt, &status) == ZS_EVENT_RECEIPT_REJECTED_DELIVERY);
  receipt.qos = 1u;
  receipt.retained = true;
  assert(zs_mqtt_event_transport_handle_receipt(
      &transport, &receipt, &status) == ZS_EVENT_RECEIPT_REJECTED_DELIVERY);
  receipt = receipt_message(&transport);
  memcpy(changed, receipt.payload, sizeof(changed));
  changed[sizeof(changed) - 1u] ^= 1u;
  receipt.payload = changed;
  assert(zs_mqtt_event_transport_handle_receipt(
      &transport, &receipt, &status) == ZS_EVENT_RECEIPT_REJECTED_RECEIPT);
  assert(status == ZS_EVENT_RECEIPT_STATUS_SHA256_MISMATCH);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);

  fixture.write_calls = 0u;
  fixture.fail_write_call = 1u;
  fixture.partial_write_bytes = 0u;
  assert(zs_mqtt_event_transport_prepare(&transport, &publication) ==
         ZS_MQTT_EVENT_STORAGE_ERROR);
  assert(publication.topic == NULL && publication.payload == NULL);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_OK);
  assert(item.retry_count == 0u);
}

static void test_retry_limit_station_and_argument_guards(void) {
  static const uint8_t tenant[] = "evt";
  static const uint8_t valid_max[] = "A2345678901234567890123456789012";
  static const uint8_t invalid_tenant[] = "bad/+";
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_mqtt_event_transport_t transport;
  zs_mqtt_event_message_t publication;

  enqueue_vector(&fixture, &io, 18u);
  transport = make_transport(&io);
  assert(zs_mqtt_event_transport_prepare(&transport, &publication) ==
         ZS_MQTT_EVENT_STATION_MISMATCH);
  assert(publication.topic == NULL && publication.payload == NULL);

  enqueue_vector(&fixture, &io, ZS_EVENT_RECEIPT_VECTOR_STATION_ID);
  transport = make_transport(&io);
  for (unsigned i = 0u; i < ZS_EVENT_OUTBOX_MAX_RETRIES; ++i) {
    assert(zs_mqtt_event_transport_prepare(&transport, &publication) ==
           ZS_MQTT_EVENT_PUBLICATION_READY);
  }
  assert(zs_mqtt_event_transport_prepare(&transport, &publication) ==
         ZS_MQTT_EVENT_RETRY_EXHAUSTED);
  assert(publication.topic == NULL && publication.payload == NULL);

  assert(sizeof(valid_max) - 1u == ZS_MQTT_EVENT_TENANT_MAX_BYTES);
  assert(zs_mqtt_event_transport_init(
      &transport, &io, UINT32_MAX, valid_max, sizeof(valid_max) - 1u));
  assert(!zs_mqtt_event_transport_init(
      &transport, &io, 17u, invalid_tenant, sizeof(invalid_tenant) - 1u));
  assert(transport.outbox == NULL && transport.up_topic_size == 0u);
  assert(!zs_mqtt_event_transport_init(
      &transport, &io, 0u, tenant, sizeof(tenant) - 1u));
  assert(!zs_mqtt_event_transport_init(
      NULL, &io, 17u, tenant, sizeof(tenant) - 1u));
  assert(zs_mqtt_event_transport_prepare(NULL, &publication) ==
         ZS_MQTT_EVENT_INVALID_ARGUMENT);
}

int main(void) {
  test_retry_then_exact_receipt_lifecycle();
  test_queued_receipt_applies_after_transport_restart();
  test_receipt_rejection_and_attempt_storage_failure();
  test_retry_limit_station_and_argument_guards();
  puts("zs_mqtt_event_transport_tests: OK");
  return 0;
}

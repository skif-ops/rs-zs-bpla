#include "zs_bg95_event_receipt.h"
#include "zs_event_receipt_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define TEST_SLOTS 2u

typedef struct {
  uint8_t slots[TEST_SLOTS][ZS_EVENT_OUTBOX_SLOT_BYTES];
  uint8_t uart[2048];
  size_t uart_size;
  unsigned uart_calls;
  unsigned fail_uart_call;
  unsigned short_uart_call;
} fixture_t;

static bool storage_read(void *ctx, uint16_t slot, uint32_t offset,
                         uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= TEST_SLOTS ||
      (uint64_t)offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
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

static bool storage_write(void *ctx, uint16_t slot, uint32_t offset,
                          const uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= TEST_SLOTS || !data ||
      (uint64_t)offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  for (size_t i = 0u; i < size; ++i) {
    if ((fixture->slots[slot][offset + i] & data[i]) != data[i])
      return false;
    fixture->slots[slot][offset + i] = data[i];
  }
  return true;
}

static int uart_write(void *ctx, unsigned channel,
                      const uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  (void)channel;
  ++fixture->uart_calls;
  if (fixture->uart_calls == fixture->fail_uart_call) return -1;
  if (fixture->uart_calls == fixture->short_uart_call)
    return size > 1u ? (int)(size - 1u) : -1;
  if (!data || fixture->uart_size + size > sizeof(fixture->uart)) return -1;
  memcpy(&fixture->uart[fixture->uart_size], data, size);
  fixture->uart_size += size;
  return 0;
}

static void setup(fixture_t *fixture, zs_event_outbox_io_t *io,
                  zs_mqtt_event_transport_t *transport, zs_bg95_t *modem,
                  zs_bg95_event_receipt_t *receiver) {
  static const uint8_t tenant[] = {'e', 'v', 't'};
  const zs_event_outbox_event_t event = {
      ZS_EVENT_RECEIPT_VECTOR_STATION_ID,
      ZS_EVENT_RECEIPT_VECTOR_BOOT_ID,
      ZS_EVENT_RECEIPT_VECTOR_SEQ_NO,
      ZS_EVENT_RECEIPT_VECTOR_EVENT_ID,
      ZS_EVENT_RECEIPT_VECTOR_EVENT_TIME_US,
      2u,
      zs_event_receipt_vector_event_payload,
      sizeof(zs_event_receipt_vector_event_payload)};
  zs_hal_port_t port = {0};

  memset(fixture, 0, sizeof(*fixture));
  memset(fixture->slots, 0xff, sizeof(fixture->slots));
  *io = (zs_event_outbox_io_t){
      fixture, TEST_SLOTS, storage_read, storage_erase, storage_write};
  assert(zs_event_outbox_enqueue(io, &event) == ZS_EVENT_OUTBOX_OK);
  assert(zs_mqtt_event_transport_init(
      transport, io, ZS_EVENT_RECEIPT_VECTOR_STATION_ID,
      tenant, sizeof(tenant)));
  port.ctx = fixture;
  port.uart_write = uart_write;
  zs_bg95_init(modem, &port, 1u, 2u, "internet");
  modem->state = ZS_BG95_ONLINE;
  modem->mqtt_connected = true;
  modem->mqtt_receive_length_enabled = true;
  modem->mqtt_client = 0u;
  assert(zs_bg95_event_receipt_init(
      receiver, modem, transport, true));
}

static void subscribe(fixture_t *fixture,
                      zs_bg95_event_receipt_t *receiver,
                      uint16_t message_id) {
  char expected_subscribe[160];
  int expected_size;
  assert(zs_bg95_event_receipt_subscribe(receiver, message_id, 100u) ==
         ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_STARTED);
  expected_size = snprintf(expected_subscribe, sizeof(expected_subscribe),
                           "AT+QMTSUB=0,%u,\"zs/v1/evt/17/receipt\",1\r\n",
                           message_id);
  assert(expected_size > 0 && (size_t)expected_size < sizeof(expected_subscribe));
  assert(fixture->uart_size == (size_t)expected_size);
  assert(memcmp(fixture->uart, expected_subscribe, (size_t)expected_size) == 0);
  assert(receiver->state == ZS_BG95_EVENT_RECEIPT_WAIT_SUBSCRIBE_RESULT);
  assert(zs_bg95_event_receipt_on_line(receiver, "OK", 101u));
  snprintf(expected_subscribe, sizeof(expected_subscribe),
           "+QMTSUB: 0,%u,0,1", message_id);
  assert(zs_bg95_event_receipt_on_line(receiver, expected_subscribe, 102u));
  assert(receiver->state == ZS_BG95_EVENT_RECEIPT_SUBSCRIBED);
  assert(receiver->last_outcome == ZS_BG95_EVENT_RECEIPT_OUTCOME_READY);
  zs_bg95_event_receipt_tick(receiver, 200000u);
  assert(receiver->state == ZS_BG95_EVENT_RECEIPT_SUBSCRIBED);
}

static size_t make_frame(uint8_t *frame, size_t capacity,
                         unsigned client, unsigned message_id,
                         const uint8_t *topic, size_t topic_size,
                         const uint8_t *payload, size_t payload_size,
                         size_t declared_payload_size, bool line_ending) {
  char prefix[96];
  int prefix_size = snprintf(prefix, sizeof(prefix),
                             "+QMTRECV: %u,%u,\"", client, message_id);
  size_t used;
  char length[32];
  int length_size;
  assert(prefix_size > 0 && (size_t)prefix_size < sizeof(prefix));
  used = (size_t)prefix_size;
  assert(used + topic_size + payload_size + 40u <= capacity);
  memcpy(frame, prefix, used);
  memcpy(&frame[used], topic, topic_size);
  used += topic_size;
  length_size = snprintf(length, sizeof(length), "\",%zu,\"",
                         declared_payload_size);
  assert(length_size > 0 && (size_t)length_size < sizeof(length));
  memcpy(&frame[used], length, (size_t)length_size);
  used += (size_t)length_size;
  memcpy(&frame[used], payload, payload_size);
  used += payload_size;
  frame[used++] = (uint8_t)'"';
  if (line_ending) {
    frame[used++] = (uint8_t)'\r';
    frame[used++] = (uint8_t)'\n';
  }
  return used;
}

static void test_subscription_and_binary_receipt_lifecycle(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t item;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_receipt_t receiver;
  zs_event_receipt_status_t status;
  uint8_t frame[512];
  size_t frame_size;

  setup(&fixture, &io, &transport, &modem, &receiver);
  subscribe(&fixture, &receiver, 41u);
  assert(zs_bg95_event_receipt_subscribe(&receiver, 42u, 104u) ==
         ZS_BG95_EVENT_RECEIPT_ALREADY_SUBSCRIBED);
  frame_size = make_frame(
      frame, sizeof(frame), 0u, 7u, transport.receipt.topic,
      transport.receipt.topic_size, zs_event_receipt_vector_payload,
      sizeof(zs_event_receipt_vector_payload),
      sizeof(zs_event_receipt_vector_payload), true);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, frame, frame_size, &status) ==
         ZS_BG95_EVENT_RECEIPT_APPLIED);
  assert(status == ZS_EVENT_RECEIPT_STATUS_OK);
  assert(zs_event_outbox_peek(&io, &item) == ZS_EVENT_OUTBOX_EMPTY);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, frame, frame_size - 2u, &status) ==
         ZS_BG95_EVENT_RECEIPT_ALREADY_APPLIED);
  assert(status == ZS_EVENT_RECEIPT_STATUS_OK);

  modem.mqtt_connected = false;
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, frame, frame_size, &status) ==
         ZS_BG95_EVENT_RECEIPT_RECEIVE_OFFLINE);
  assert(receiver.state == ZS_BG95_EVENT_RECEIPT_IDLE);
  assert(receiver.last_outcome == ZS_BG95_EVENT_RECEIPT_OUTCOME_OFFLINE);
}

static void test_length_delimited_payload_preserves_control_bytes(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_receipt_t receiver;
  zs_event_receipt_status_t status;
  uint8_t changed[sizeof(zs_event_receipt_vector_payload)];
  uint8_t frame[512];
  size_t frame_size;

  setup(&fixture, &io, &transport, &modem, &receiver);
  subscribe(&fixture, &receiver, 1u);
  memcpy(changed, zs_event_receipt_vector_payload, sizeof(changed));
  changed[17] = 0x00u;
  changed[18] = 0x22u;
  changed[19] = 0x0du;
  changed[20] = 0x0au;
  changed[21] = 0x1au;
  assert(memchr(changed, 0x00, sizeof(changed)) != NULL);
  assert(memchr(changed, 0x22, sizeof(changed)) != NULL);
  frame_size = make_frame(
      frame, sizeof(frame), 0u, 2u, transport.receipt.topic,
      transport.receipt.topic_size, changed, sizeof(changed),
      sizeof(changed), true);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, frame, frame_size, &status) ==
         ZS_BG95_EVENT_RECEIPT_REJECTED_RECEIPT);
  assert(status == ZS_EVENT_RECEIPT_STATUS_SHA256_MISMATCH);
  assert(receiver.state == ZS_BG95_EVENT_RECEIPT_SUBSCRIBED);
}

static void test_frame_topic_client_delivery_and_framing_guards(void) {
  static const uint8_t wrong_topic[] = "zs/v1/evt/18/receipt";
  static const uint8_t unrelated[] = "+QMTSTAT: 0,1";
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_receipt_t receiver;
  zs_event_receipt_status_t status;
  uint8_t frame[512];
  size_t frame_size;

  setup(&fixture, &io, &transport, &modem, &receiver);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, unrelated, sizeof(unrelated) - 1u, &status) ==
         ZS_BG95_EVENT_RECEIPT_NOT_SUBSCRIBED);
  subscribe(&fixture, &receiver, 3u);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, unrelated, sizeof(unrelated) - 1u, &status) ==
         ZS_BG95_EVENT_RECEIPT_NOT_RECEIPT_FRAME);

  frame_size = make_frame(
      frame, sizeof(frame), 1u, 4u, transport.receipt.topic,
      transport.receipt.topic_size, zs_event_receipt_vector_payload,
      sizeof(zs_event_receipt_vector_payload),
      sizeof(zs_event_receipt_vector_payload), true);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, frame, frame_size, &status) ==
         ZS_BG95_EVENT_RECEIPT_CLIENT_MISMATCH);

  frame_size = make_frame(
      frame, sizeof(frame), 0u, 4u, wrong_topic, sizeof(wrong_topic) - 1u,
      zs_event_receipt_vector_payload,
      sizeof(zs_event_receipt_vector_payload),
      sizeof(zs_event_receipt_vector_payload), true);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, frame, frame_size, &status) ==
         ZS_BG95_EVENT_RECEIPT_REJECTED_TOPIC);

  frame_size = make_frame(
      frame, sizeof(frame), 0u, 0u, transport.receipt.topic,
      transport.receipt.topic_size, zs_event_receipt_vector_payload,
      sizeof(zs_event_receipt_vector_payload),
      sizeof(zs_event_receipt_vector_payload), true);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, frame, frame_size, &status) ==
         ZS_BG95_EVENT_RECEIPT_REJECTED_DELIVERY);

  frame_size = make_frame(
      frame, sizeof(frame), 0u, 4u, transport.receipt.topic,
      transport.receipt.topic_size, zs_event_receipt_vector_payload,
      sizeof(zs_event_receipt_vector_payload),
      sizeof(zs_event_receipt_vector_payload) + 1u, true);
  assert(zs_bg95_event_receipt_on_frame(
      &receiver, frame, frame_size, &status) ==
         ZS_BG95_EVENT_RECEIPT_FRAMING_ERROR);
  assert(receiver.state == ZS_BG95_EVENT_RECEIPT_IDLE);
  assert(receiver.last_outcome ==
         ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR);
  assert(modem.state == ZS_BG95_ERROR && !modem.mqtt_connected);
}

static void test_setup_failures_and_policy_guard(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_receipt_t receiver;

  setup(&fixture, &io, &transport, &modem, &receiver);
  assert(!zs_bg95_event_receipt_init(
      &receiver, &modem, &transport, false));
  assert(receiver.modem == NULL && receiver.transport == NULL);

  setup(&fixture, &io, &transport, &modem, &receiver);
  fixture.short_uart_call = 1u;
  assert(zs_bg95_event_receipt_subscribe(&receiver, 1u, 0u) ==
         ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_IO_ERROR);
  assert(receiver.last_outcome == ZS_BG95_EVENT_RECEIPT_OUTCOME_IO_ERROR);
  assert(modem.state == ZS_BG95_ERROR && !modem.mqtt_connected);

  setup(&fixture, &io, &transport, &modem, &receiver);
  fixture.fail_uart_call = 1u;
  assert(zs_bg95_event_receipt_subscribe(&receiver, 2u, 10u) ==
         ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_IO_ERROR);
  assert(receiver.last_outcome == ZS_BG95_EVENT_RECEIPT_OUTCOME_IO_ERROR);

  setup(&fixture, &io, &transport, &modem, &receiver);
  modem.mqtt_receive_length_enabled = false;
  assert(zs_bg95_event_receipt_subscribe(&receiver, 2u, 10u) ==
         ZS_BG95_EVENT_RECEIPT_RECEIVE_MODE_REQUIRED);
  assert(fixture.uart_size == 0u);
  assert(receiver.last_outcome ==
         ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR);
  assert(modem.state == ZS_BG95_ERROR && !modem.mqtt_connected);

  setup(&fixture, &io, &transport, &modem, &receiver);
  assert(zs_bg95_event_receipt_subscribe(&receiver, 3u, 20u) ==
         ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_STARTED);
  zs_bg95_event_receipt_tick(
      &receiver, 20u + ZS_BG95_EVENT_RECEIPT_TIMEOUT_MS);
  assert(receiver.last_outcome == ZS_BG95_EVENT_RECEIPT_OUTCOME_TIMEOUT);

  setup(&fixture, &io, &transport, &modem, &receiver);
  assert(zs_bg95_event_receipt_subscribe(&receiver, 4u, 30u) ==
         ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_STARTED);
  assert(zs_bg95_event_receipt_on_line(&receiver, "OK", 31u));
  assert(zs_bg95_event_receipt_on_line(
      &receiver, "+QMTSUB: 0,4,0,0", 32u));
  assert(receiver.last_outcome ==
         ZS_BG95_EVENT_RECEIPT_OUTCOME_MODEM_REJECTED);

  setup(&fixture, &io, &transport, &modem, &receiver);
  assert(zs_bg95_event_receipt_subscribe(&receiver, 5u, 40u) ==
         ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_STARTED);
  assert(zs_bg95_event_receipt_on_line(&receiver, "OK", 41u));
  assert(zs_bg95_event_receipt_on_line(
      &receiver, "+QMTSUB: 1,5,0,1", 42u));
  assert(receiver.last_outcome ==
         ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR);

  setup(&fixture, &io, &transport, &modem, &receiver);
  modem.mqtt_connected = false;
  assert(zs_bg95_event_receipt_subscribe(&receiver, 6u, 50u) ==
         ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_OFFLINE);
  assert(zs_bg95_event_receipt_subscribe(&receiver, 0u, 50u) ==
         ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_INVALID_ARGUMENT);
}

int main(void) {
  test_subscription_and_binary_receipt_lifecycle();
  test_length_delimited_payload_preserves_control_bytes();
  test_frame_topic_client_delivery_and_framing_guards();
  test_setup_failures_and_policy_guard();
  puts("zs_bg95_event_receipt_tests: OK");
  return 0;
}

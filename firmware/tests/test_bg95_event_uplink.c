#include "zs_bg95_event_uplink.h"
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
  if (slot >= TEST_SLOTS || (uint64_t)offset + size >
                                ZS_EVENT_OUTBOX_SLOT_BYTES)
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

static void setup_payload(fixture_t *fixture, zs_event_outbox_io_t *io,
                          zs_mqtt_event_transport_t *transport,
                          zs_bg95_t *modem,
                          zs_bg95_event_uplink_t *uplink,
                          const uint8_t *payload, size_t payload_size) {
  static const uint8_t tenant[] = {'e', 'v', 't'};
  const zs_event_outbox_event_t event = {
      ZS_EVENT_RECEIPT_VECTOR_STATION_ID,
      ZS_EVENT_RECEIPT_VECTOR_BOOT_ID,
      ZS_EVENT_RECEIPT_VECTOR_SEQ_NO,
      ZS_EVENT_RECEIPT_VECTOR_EVENT_ID,
      ZS_EVENT_RECEIPT_VECTOR_EVENT_TIME_US,
      2u,
      payload,
      payload_size};
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
  modem->mqtt_client = 0u;
  assert(zs_bg95_event_uplink_init(uplink, modem, transport));
}

static void setup(fixture_t *fixture, zs_event_outbox_io_t *io,
                  zs_mqtt_event_transport_t *transport, zs_bg95_t *modem,
                  zs_bg95_event_uplink_t *uplink) {
  setup_payload(fixture, io, transport, modem, uplink,
                zs_event_receipt_vector_event_payload,
                sizeof(zs_event_receipt_vector_event_payload));
}

static void test_fixed_length_binary_publish_and_broker_ack(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t pending;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_uplink_t uplink;
  char expected[160];
  int expected_size;

  setup(&fixture, &io, &transport, &modem, &uplink);
  assert(memchr(zs_event_receipt_vector_event_payload, 0,
                sizeof(zs_event_receipt_vector_event_payload)) != NULL);
  assert(memchr(zs_event_receipt_vector_event_payload, 0x1a,
                sizeof(zs_event_receipt_vector_event_payload)) != NULL);
  assert(zs_bg95_event_uplink_start(&uplink, 23u, 100u) ==
         ZS_BG95_EVENT_UPLINK_STARTED);
  expected_size = snprintf(
      expected, sizeof(expected),
      "AT+QMTPUB=0,23,1,0,\"zs/v1/evt/17/up\",%zu\r\n",
      sizeof(zs_event_receipt_vector_event_payload));
  assert(expected_size > 0 && (size_t)expected_size < sizeof(expected));
  assert(fixture.uart_size == (size_t)expected_size);
  assert(memcmp(fixture.uart, expected, fixture.uart_size) == 0);
  assert(uplink.state == ZS_BG95_EVENT_UPLINK_WAIT_PROMPT);
  assert(zs_event_outbox_peek(&io, &pending) == ZS_EVENT_OUTBOX_OK);
  assert(pending.retry_count == 1u);

  assert(zs_bg95_event_uplink_on_prompt(&uplink, 101u));
  assert(uplink.state == ZS_BG95_EVENT_UPLINK_WAIT_RESULT);
  assert(fixture.uart_size ==
         (size_t)expected_size + sizeof(zs_event_receipt_vector_event_payload));
  assert(memcmp(&fixture.uart[expected_size],
                zs_event_receipt_vector_event_payload,
                sizeof(zs_event_receipt_vector_event_payload)) == 0);
  assert(fixture.uart[fixture.uart_size - 1u] ==
         zs_event_receipt_vector_event_payload[
             sizeof(zs_event_receipt_vector_event_payload) - 1u]);
  assert(zs_bg95_event_uplink_on_line(&uplink, "OK"));
  assert(uplink.state == ZS_BG95_EVENT_UPLINK_WAIT_RESULT);
  assert(zs_bg95_event_uplink_on_line(&uplink, "+QMTPUB: 0,23,0"));
  assert(uplink.state == ZS_BG95_EVENT_UPLINK_IDLE);
  assert(uplink.last_outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK);

  /* Broker ACK is not the server application receipt: the item stays pending. */
  assert(zs_event_outbox_peek(&io, &pending) == ZS_EVENT_OUTBOX_OK);
  assert(pending.retry_count == 1u);
}

static void test_busy_offline_timeout_and_protocol_guards(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t pending;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_uplink_t uplink;

  setup(&fixture, &io, &transport, &modem, &uplink);
  modem.mqtt_connected = false;
  assert(zs_bg95_event_uplink_start(&uplink, 1u, 0u) ==
         ZS_BG95_EVENT_UPLINK_OFFLINE);
  assert(zs_event_outbox_peek(&io, &pending) == ZS_EVENT_OUTBOX_OK);
  assert(pending.retry_count == 0u);

  modem.mqtt_connected = true;
  assert(zs_bg95_event_uplink_start(&uplink, 1u, 10u) ==
         ZS_BG95_EVENT_UPLINK_STARTED);
  assert(zs_bg95_event_uplink_start(&uplink, 2u, 11u) ==
         ZS_BG95_EVENT_UPLINK_BUSY);
  assert(!zs_bg95_event_uplink_on_line(&uplink, "+QMTRECV: 0,1"));
  assert(zs_bg95_event_uplink_on_line(&uplink, "+QMTPUB: 1,1,0"));
  assert(uplink.last_outcome ==
         ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR);
  assert(modem.state == ZS_BG95_ERROR && !modem.mqtt_connected);

  setup(&fixture, &io, &transport, &modem, &uplink);
  assert(zs_bg95_event_uplink_start(&uplink, 2u, 20u) ==
         ZS_BG95_EVENT_UPLINK_STARTED);
  assert(zs_bg95_event_uplink_on_prompt(&uplink, 21u));
  assert(zs_bg95_event_uplink_on_line(&uplink, "+QMTPUB: 0,2,1,3"));
  assert(uplink.last_outcome ==
         ZS_BG95_EVENT_UPLINK_OUTCOME_MODEM_REJECTED);

  setup(&fixture, &io, &transport, &modem, &uplink);
  assert(zs_bg95_event_uplink_start(&uplink, 3u, 30u) ==
         ZS_BG95_EVENT_UPLINK_STARTED);
  zs_bg95_event_uplink_tick(
      &uplink, 30u + ZS_BG95_EVENT_UPLINK_TIMEOUT_MS);
  assert(uplink.state == ZS_BG95_EVENT_UPLINK_IDLE);
  assert(uplink.last_outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_TIMEOUT);
  assert(modem.state == ZS_BG95_ERROR && !modem.mqtt_connected);
}

static void test_fixed_length_preserves_at_control_bytes(void) {
  static const uint8_t payload[] = {0x00u, 0x22u, 0x1au, 0xffu};
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_uplink_t uplink;
  size_t command_size;

  setup_payload(&fixture, &io, &transport, &modem, &uplink,
                payload, sizeof(payload));
  assert(zs_bg95_event_uplink_start(&uplink, 4u, 0u) ==
         ZS_BG95_EVENT_UPLINK_STARTED);
  command_size = fixture.uart_size;
  assert(zs_bg95_event_uplink_on_prompt(&uplink, 1u));
  assert(fixture.uart_size == command_size + sizeof(payload));
  assert(memcmp(&fixture.uart[command_size], payload, sizeof(payload)) == 0);
}

static void test_uart_failures_preserve_pending_event(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_event_outbox_item_t pending;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_uplink_t uplink;

  setup(&fixture, &io, &transport, &modem, &uplink);
  fixture.fail_uart_call = 1u;
  assert(zs_bg95_event_uplink_start(&uplink, 7u, 0u) ==
         ZS_BG95_EVENT_UPLINK_IO_ERROR);
  assert(uplink.last_outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_IO_ERROR);
  assert(zs_event_outbox_peek(&io, &pending) == ZS_EVENT_OUTBOX_OK);
  assert(pending.retry_count == 1u);

  setup(&fixture, &io, &transport, &modem, &uplink);
  fixture.short_uart_call = 2u;
  assert(zs_bg95_event_uplink_start(&uplink, 8u, 10u) ==
         ZS_BG95_EVENT_UPLINK_STARTED);
  assert(!zs_bg95_event_uplink_on_prompt(&uplink, 11u));
  assert(uplink.last_outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_IO_ERROR);
  assert(zs_event_outbox_peek(&io, &pending) == ZS_EVENT_OUTBOX_OK);
  assert(pending.retry_count == 1u);
}

static void test_argument_guards(void) {
  fixture_t fixture;
  zs_event_outbox_io_t io;
  zs_mqtt_event_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_event_uplink_t uplink;

  setup(&fixture, &io, &transport, &modem, &uplink);
  assert(zs_bg95_event_uplink_start(&uplink, 0u, 0u) ==
         ZS_BG95_EVENT_UPLINK_INVALID_ARGUMENT);
  assert(!zs_bg95_event_uplink_on_prompt(&uplink, 0u));
  assert(!zs_bg95_event_uplink_init(NULL, &modem, &transport));
  modem.mqtt_client = 6u;
  assert(!zs_bg95_event_uplink_init(&uplink, &modem, &transport));
  assert(uplink.modem == NULL && uplink.transport == NULL);

  setup(&fixture, &io, &transport, &modem, &uplink);
  transport.up_topic[0] = (uint8_t)'"';
  assert(zs_bg95_event_uplink_start(&uplink, 1u, 0u) ==
         ZS_BG95_EVENT_UPLINK_INVALID_ARGUMENT);
  assert(fixture.uart_size == 0u && modem.state == ZS_BG95_ERROR);
}

int main(void) {
  test_fixed_length_binary_publish_and_broker_ack();
  test_busy_offline_timeout_and_protocol_guards();
  test_fixed_length_preserves_at_control_bytes();
  test_uart_failures_preserve_pending_event();
  test_argument_guards();
  puts("zs_bg95_event_uplink_tests: OK");
  return 0;
}

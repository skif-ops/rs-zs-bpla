#include "zs_bg95_mqtt_session.h"
#include "zs_command_vector.h"
#include "zs_event_receipt_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define COMMAND_SLOTS 4u
#define EVENT_SLOTS 2u

typedef struct {
  uint8_t command_slots[COMMAND_SLOTS][ZS_COMMAND_JOURNAL_SLOT_BYTES];
  uint8_t event_slots[EVENT_SLOTS][ZS_EVENT_OUTBOX_SLOT_BYTES];
  uint8_t command_workspace[256];
  uint8_t uart[16384];
  size_t uart_size;
  unsigned execute_calls;
} fixture_t;

typedef struct {
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t command_transport;
  zs_event_outbox_io_t event_outbox;
  zs_mqtt_event_transport_t event_transport;
  zs_bg95_t modem;
  zs_bg95_command_transport_t command;
  zs_bg95_event_receipt_t receipt;
  zs_bg95_event_uplink_t uplink;
  zs_bg95_mqtt_session_t session;
} test_context_t;

static bool command_read(void *ctx, uint16_t slot, uint32_t offset,
                         uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= COMMAND_SLOTS ||
      (uint64_t)offset + size > ZS_COMMAND_JOURNAL_SLOT_BYTES)
    return false;
  memcpy(data, &fixture->command_slots[slot][offset], size);
  return true;
}

static bool command_erase(void *ctx, uint16_t slot) {
  fixture_t *fixture = ctx;
  if (slot >= COMMAND_SLOTS) return false;
  memset(fixture->command_slots[slot], 0xff,
         ZS_COMMAND_JOURNAL_SLOT_BYTES);
  return true;
}

static bool command_write(void *ctx, uint16_t slot, uint32_t offset,
                          const uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= COMMAND_SLOTS || !data ||
      (uint64_t)offset + size > ZS_COMMAND_JOURNAL_SLOT_BYTES)
    return false;
  for (size_t i = 0u; i < size; ++i) {
    if ((fixture->command_slots[slot][offset + i] & data[i]) != data[i])
      return false;
    fixture->command_slots[slot][offset + i] = data[i];
  }
  return true;
}

static bool event_read(void *ctx, uint16_t slot, uint32_t offset,
                       uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= EVENT_SLOTS ||
      (uint64_t)offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  memcpy(data, &fixture->event_slots[slot][offset], size);
  return true;
}

static bool event_erase(void *ctx, uint16_t slot) {
  fixture_t *fixture = ctx;
  if (slot >= EVENT_SLOTS) return false;
  memset(fixture->event_slots[slot], 0xff, ZS_EVENT_OUTBOX_SLOT_BYTES);
  return true;
}

static bool event_write(void *ctx, uint16_t slot, uint32_t offset,
                        const uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= EVENT_SLOTS || !data ||
      (uint64_t)offset + size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  for (size_t i = 0u; i < size; ++i) {
    if ((fixture->event_slots[slot][offset + i] & data[i]) != data[i])
      return false;
    fixture->event_slots[slot][offset + i] = data[i];
  }
  return true;
}

static int uart_write(void *ctx, unsigned channel,
                      const uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  (void)channel;
  if (!data || fixture->uart_size + size > sizeof(fixture->uart)) return -1;
  memcpy(&fixture->uart[fixture->uart_size], data, size);
  fixture->uart_size += size;
  return 0;
}

static bool verify_backend(
    void *ctx,
    const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES],
    const uint8_t *message,
    size_t message_size,
    const uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx;
  return memcmp(public_key, zs_command_vector_public_key,
                ZS_COMMAND_PUBLIC_KEY_BYTES) == 0 &&
         message_size == sizeof(zs_command_vector_signed_cbor) &&
         memcmp(message, zs_command_vector_signed_cbor, message_size) == 0 &&
         memcmp(signature, zs_command_vector_signature,
                ZS_COMMAND_SIGNATURE_BYTES) == 0;
}

static bool execute(void *ctx, const zs_command_t *command,
                    zs_command_ack_result_t *result,
                    uint16_t *detail_code) {
  fixture_t *fixture = ctx;
  ++fixture->execute_calls;
  assert(command->audio.event_id == ZS_EVENT_RECEIPT_VECTOR_EVENT_ID);
  *result = ZS_COMMAND_ACK_OK;
  *detail_code = 0u;
  return true;
}

static void setup(test_context_t *context) {
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
  zs_command_trust_key_t key = {0};
  zs_hal_port_t port = {0};

  memset(context, 0, sizeof(*context));
  memset(context->fixture.command_slots, 0xff,
         sizeof(context->fixture.command_slots));
  memset(context->fixture.event_slots, 0xff,
         sizeof(context->fixture.event_slots));
  memcpy(key.public_key, zs_command_vector_public_key,
         sizeof(key.public_key));
  key.enabled = true;
  context->journal = (zs_command_journal_io_t){
      &context->fixture, COMMAND_SLOTS,
      command_read, command_erase, command_write};
  assert(zs_command_trust_init(
      &context->trust, &key, 1u, verify_backend, &context->fixture));
  context->channel = (zs_command_channel_t){
      ZS_COMMAND_VECTOR_STATION_ID,
      &context->trust,
      &context->journal,
      execute,
      &context->fixture,
      context->fixture.command_workspace,
      sizeof(context->fixture.command_workspace)};
  assert(zs_mqtt_command_transport_init(
      &context->command_transport, &context->channel,
      tenant, sizeof(tenant)));
  context->event_outbox = (zs_event_outbox_io_t){
      &context->fixture, EVENT_SLOTS, event_read, event_erase, event_write};
  assert(zs_event_outbox_enqueue(&context->event_outbox, &event) ==
         ZS_EVENT_OUTBOX_OK);
  assert(zs_mqtt_event_transport_init(
      &context->event_transport, &context->event_outbox,
      ZS_EVENT_RECEIPT_VECTOR_STATION_ID, tenant, sizeof(tenant)));
  port.ctx = &context->fixture;
  port.uart_write = uart_write;
  zs_bg95_init(&context->modem, &port, 1u, 2u, "internet");
  context->modem.state = ZS_BG95_ONLINE;
  context->modem.mqtt_connected = true;
  context->modem.mqtt_receive_length_enabled = true;
  context->modem.mqtt_client = 0u;
  assert(zs_bg95_command_transport_init(
      &context->command, &context->modem,
      &context->command_transport, true));
  assert(zs_bg95_event_receipt_init(
      &context->receipt, &context->modem,
      &context->event_transport, true));
  assert(zs_bg95_event_uplink_init(
      &context->uplink, &context->modem, &context->event_transport));
  assert(zs_bg95_mqtt_session_init(
      &context->session, &context->modem, &context->command,
      &context->receipt, &context->uplink, 30u));
}

static size_t make_frame(uint8_t *frame, size_t capacity,
                         unsigned message_id,
                         const uint8_t *topic, size_t topic_size,
                         const uint8_t *payload, size_t payload_size) {
  char prefix[64];
  char length[32];
  int prefix_size = snprintf(
      prefix, sizeof(prefix), "+QMTRECV: 0,%u,\"", message_id);
  int length_size;
  size_t used;
  assert(prefix_size > 0 && (size_t)prefix_size < sizeof(prefix));
  used = (size_t)prefix_size;
  assert(used + topic_size + payload_size + 40u <= capacity);
  memcpy(frame, prefix, used);
  memcpy(&frame[used], topic, topic_size);
  used += topic_size;
  length_size = snprintf(length, sizeof(length), "\",%zu,\"", payload_size);
  assert(length_size > 0 && (size_t)length_size < sizeof(length));
  memcpy(&frame[used], length, (size_t)length_size);
  used += (size_t)length_size;
  memcpy(&frame[used], payload, payload_size);
  used += payload_size;
  frame[used++] = (uint8_t)'"';
  frame[used++] = (uint8_t)'\r';
  frame[used++] = (uint8_t)'\n';
  return used;
}

static void feed_chunks(zs_bg95_mqtt_session_t *session,
                        const uint8_t *data, size_t size,
                        uint32_t now_ms, uint64_t now_us) {
  static const size_t chunks[] = {1u, 3u, 7u, 2u, 11u};
  size_t offset = 0u;
  size_t chunk_index = 0u;
  while (offset < size) {
    size_t chunk = chunks[chunk_index %
                          (sizeof(chunks) / sizeof(chunks[0]))];
    bool accepted;
    if (chunk > size - offset) chunk = size - offset;
    accepted = zs_bg95_mqtt_session_feed_uart(
        session, &data[offset], chunk, now_ms, now_us, true);
    if (!accepted)
      fprintf(stderr,
              "UART feed rejected at offset=%zu chunk=%zu owner=%u rx=%zu "
              "outcome=%u\n",
              offset, chunk, (unsigned)session->owner, session->rx_size,
              (unsigned)session->last_input_outcome);
    assert(accepted);
    offset += chunk;
    ++chunk_index;
  }
}

static void feed_line(zs_bg95_mqtt_session_t *session, const char *line,
                      uint32_t now_ms) {
  uint8_t framed[192];
  size_t line_size = strlen(line);
  assert(line_size + 2u <= sizeof(framed));
  memcpy(framed, line, line_size);
  framed[line_size] = (uint8_t)'\r';
  framed[line_size + 1u] = (uint8_t)'\n';
  feed_chunks(session, framed, line_size + 2u, now_ms,
              UINT64_C(1750000));
}

static void establish_subscriptions(test_context_t *context) {
  static const char command_sub[] =
      "AT+QMTSUB=0,30,\"zs/v1/evt/17/down\",1\r\n";
  static const char receipt_sub[] =
      "AT+QMTSUB=0,31,\"zs/v1/evt/17/receipt\",1\r\n";
  size_t offset;

  zs_bg95_mqtt_session_tick(
      &context->session, 100u, UINT64_C(1750000), true);
  assert(context->session.owner == ZS_BG95_MQTT_OWNER_COMMAND_SUBSCRIBE);
  assert(context->fixture.uart_size == sizeof(command_sub) - 1u);
  assert(memcmp(context->fixture.uart, command_sub,
                sizeof(command_sub) - 1u) == 0);
  feed_line(&context->session, "OK", 101u);
  feed_line(&context->session, "+QMTSUB: 0,30,0,1", 102u);
  assert(context->session.owner == ZS_BG95_MQTT_OWNER_NONE);

  offset = context->fixture.uart_size;
  zs_bg95_mqtt_session_tick(
      &context->session, 103u, UINT64_C(1750001), true);
  assert(context->session.owner == ZS_BG95_MQTT_OWNER_RECEIPT_SUBSCRIBE);
  assert(context->fixture.uart_size == offset + sizeof(receipt_sub) - 1u);
  assert(memcmp(&context->fixture.uart[offset], receipt_sub,
                sizeof(receipt_sub) - 1u) == 0);
  feed_line(&context->session, "OK", 104u);
  feed_line(&context->session, "+QMTSUB: 0,31,0,1", 105u);
  assert(zs_bg95_mqtt_session_ready(&context->session));
  assert(context->session.owner == ZS_BG95_MQTT_OWNER_NONE);
}

static void test_serialized_fragmented_end_to_end_lifecycle(void) {
  test_context_t context;
  zs_event_outbox_item_t pending;
  uint8_t command_frame[512];
  uint8_t receipt_frame[256];
  size_t command_frame_size;
  size_t receipt_frame_size;
  size_t offset;
  char expected[160];
  int expected_size;

  setup(&context);
  establish_subscriptions(&context);
  offset = context.fixture.uart_size;
  assert(zs_bg95_mqtt_session_start_event(&context.session, 110u) ==
         ZS_BG95_EVENT_UPLINK_STARTED);
  expected_size = snprintf(
      expected, sizeof(expected),
      "AT+QMTPUB=0,32,1,0,\"zs/v1/evt/17/up\",%zu\r\n",
      sizeof(zs_event_receipt_vector_event_payload));
  assert(expected_size > 0 && (size_t)expected_size < sizeof(expected));
  assert(context.fixture.uart_size == offset + (size_t)expected_size);
  assert(memcmp(&context.fixture.uart[offset], expected,
                (size_t)expected_size) == 0);

  command_frame_size = make_frame(
      command_frame, sizeof(command_frame), 9u,
      context.command_transport.down_topic,
      context.command_transport.down_topic_size,
      zs_command_vector_payload, sizeof(zs_command_vector_payload));
  feed_chunks(&context.session, command_frame, command_frame_size,
              111u, UINT64_C(1750000));
  assert(context.session.last_input_outcome ==
         ZS_BG95_MQTT_INPUT_COMMAND_QUEUED);
  assert(context.session.queued_command_count == 1u);
  assert(context.fixture.execute_calls == 0u);
  feed_chunks(&context.session, command_frame, command_frame_size,
              112u, UINT64_C(1750001));
  assert(context.session.last_input_outcome ==
         ZS_BG95_MQTT_INPUT_COMMAND_RETRY_REQUIRED);
  assert(context.session.retry_required_count == 1u);

  offset = context.fixture.uart_size;
  feed_chunks(&context.session, (const uint8_t *)"> ", 2u,
              113u, UINT64_C(1750002));
  assert(context.fixture.uart_size ==
         offset + sizeof(zs_event_receipt_vector_event_payload));
  assert(memcmp(&context.fixture.uart[offset],
                zs_event_receipt_vector_event_payload,
                sizeof(zs_event_receipt_vector_event_payload)) == 0);
  feed_line(&context.session, "OK", 114u);
  feed_line(&context.session, "+QMTPUB: 0,32,0", 115u);
  assert(context.session.owner == ZS_BG95_MQTT_OWNER_NONE);
  assert(zs_event_outbox_peek(&context.event_outbox, &pending) ==
         ZS_EVENT_OUTBOX_OK);

  offset = context.fixture.uart_size;
  zs_bg95_mqtt_session_tick(
      &context.session, 116u, UINT64_C(1750100), true);
  assert(context.fixture.execute_calls == 1u);
  assert(context.session.owner == ZS_BG95_MQTT_OWNER_COMMAND_ACK);
  assert(context.session.last_command_result ==
         ZS_BG95_COMMAND_ACK_PUBLISH_STARTED);
  assert(context.session.last_command_status == ZS_COMMAND_STATUS_OK);
  expected_size = snprintf(
      expected, sizeof(expected),
      "AT+QMTPUB=0,33,1,0,\"zs/v1/evt/17/ack\",%zu\r\n",
      sizeof(zs_command_vector_ack));
  assert(expected_size > 0 && (size_t)expected_size < sizeof(expected));
  assert(context.fixture.uart_size == offset + (size_t)expected_size);
  assert(memcmp(&context.fixture.uart[offset], expected,
                (size_t)expected_size) == 0);
  offset = context.fixture.uart_size;
  feed_chunks(&context.session, (const uint8_t *)">", 1u,
              117u, UINT64_C(1750101));
  assert(context.fixture.uart_size ==
         offset + context.command.ack_publication.payload_size);
  assert(context.command.ack_publication.payload_size ==
         sizeof(zs_command_vector_ack));
  assert(memcmp(&context.fixture.uart[offset],
                context.command.ack_publication.payload,
                context.command.ack_publication.payload_size) == 0);
  feed_line(&context.session, "+QMTPUB: 0,33,0", 118u);
  assert(context.session.owner == ZS_BG95_MQTT_OWNER_NONE);
  assert(context.command.last_outcome ==
         ZS_BG95_COMMAND_TRANSPORT_OUTCOME_ACK_BROKER_ACK);

  receipt_frame_size = make_frame(
      receipt_frame, sizeof(receipt_frame), 10u,
      context.event_transport.receipt.topic,
      context.event_transport.receipt.topic_size,
      zs_event_receipt_vector_payload,
      sizeof(zs_event_receipt_vector_payload));
  feed_chunks(&context.session, receipt_frame, receipt_frame_size,
              119u, UINT64_C(1750102));
  assert(context.session.last_input_outcome == ZS_BG95_MQTT_INPUT_RECEIPT);
  assert(context.session.last_receipt_result ==
         ZS_BG95_EVENT_RECEIPT_APPLIED);
  assert(context.session.last_receipt_status == ZS_EVENT_RECEIPT_STATUS_OK);
  assert(zs_event_outbox_peek(&context.event_outbox, &pending) ==
         ZS_EVENT_OUTBOX_EMPTY);
}

static void test_binary_payload_and_protocol_guards(void) {
  static const uint8_t binary_payload[] = {
      0xa1u, 0x22u, 0x00u, 0x0du, 0x0au, 0x1au};
  test_context_t context;
  uint8_t frame[256];
  size_t frame_size;

  setup(&context);
  establish_subscriptions(&context);
  frame_size = make_frame(
      frame, sizeof(frame), 12u, context.command_transport.down_topic,
      context.command_transport.down_topic_size,
      binary_payload, sizeof(binary_payload));
  feed_chunks(&context.session, frame, frame_size,
              200u, UINT64_C(1750000));
  assert(context.session.last_input_outcome == ZS_BG95_MQTT_INPUT_COMMAND);
  assert(context.session.last_command_result ==
         ZS_BG95_COMMAND_REJECTED_COMMAND);
  assert(context.session.last_command_status == ZS_COMMAND_STATUS_INVALID_CBOR);
  assert(zs_bg95_online(&context.modem));

  assert(!zs_bg95_mqtt_session_feed_uart(
      &context.session, (const uint8_t *)">", 1u,
      201u, UINT64_C(1750001), true));
  assert(context.session.last_input_outcome ==
         ZS_BG95_MQTT_INPUT_PROTOCOL_ERROR);
  assert(context.modem.state == ZS_BG95_ERROR);

  setup(&context);
  assert(!zs_bg95_mqtt_session_feed_uart(
      &context.session,
      (const uint8_t *)"+QMTRECV: 0,1,\"zs/v1/evt/17/down\",2304,\"",
      sizeof("+QMTRECV: 0,1,\"zs/v1/evt/17/down\",2304,\"") - 1u,
      202u, UINT64_C(1750002), true));
  assert(context.modem.state == ZS_BG95_ERROR);
}

static void test_disconnect_discards_ram_queue_and_resubscribes(void) {
  test_context_t context;
  uint8_t command_frame[512];
  size_t command_frame_size;
  size_t offset;
  static const char command_sub[] =
      "AT+QMTSUB=0,33,\"zs/v1/evt/17/down\",1\r\n";

  setup(&context);
  establish_subscriptions(&context);
  assert(zs_bg95_mqtt_session_start_event(&context.session, 300u) ==
         ZS_BG95_EVENT_UPLINK_STARTED);
  command_frame_size = make_frame(
      command_frame, sizeof(command_frame), 14u,
      context.command_transport.down_topic,
      context.command_transport.down_topic_size,
      zs_command_vector_payload, sizeof(zs_command_vector_payload));
  feed_chunks(&context.session, command_frame, command_frame_size,
              301u, UINT64_C(1750000));
  assert(context.session.pending_command_size == command_frame_size - 2u);
  context.session.rx[0] = (uint8_t)'X';
  context.session.rx_size = 1u;
  context.modem.mqtt_connected = false;
  zs_bg95_mqtt_session_tick(
      &context.session, 302u, UINT64_C(1750001), true);
  assert(context.session.owner == ZS_BG95_MQTT_OWNER_NONE);
  assert(context.session.pending_command_size == 0u);
  assert(context.session.rx_size == 0u);
  assert(context.fixture.execute_calls == 0u);

  context.modem.state = ZS_BG95_ONLINE;
  context.modem.mqtt_connected = true;
  context.modem.mqtt_receive_length_enabled = true;
  offset = context.fixture.uart_size;
  zs_bg95_mqtt_session_tick(
      &context.session, 303u, UINT64_C(1750002), true);
  assert(context.session.owner == ZS_BG95_MQTT_OWNER_COMMAND_SUBSCRIBE);
  assert(context.fixture.uart_size == offset + sizeof(command_sub) - 1u);
  assert(memcmp(&context.fixture.uart[offset], command_sub,
                sizeof(command_sub) - 1u) == 0);
}

int main(void) {
  test_serialized_fragmented_end_to_end_lifecycle();
  test_binary_payload_and_protocol_guards();
  test_disconnect_discards_ram_queue_and_resubscribes();
  puts("zs_bg95_mqtt_session_tests: OK");
  return 0;
}

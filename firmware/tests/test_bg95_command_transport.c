#include "zs_bg95_command_transport.h"
#include "zs_bg95_mqtt_binary.h"
#include "zs_command_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define TEST_SLOTS 4u

typedef struct {
  uint8_t slots[TEST_SLOTS][ZS_COMMAND_JOURNAL_SLOT_BYTES];
  uint8_t uart[8192];
  uint8_t workspace[256];
  size_t uart_size;
  unsigned uart_calls;
  unsigned fail_uart_call;
  unsigned short_uart_call;
  unsigned execute_calls;
  unsigned backend_calls;
} fixture_t;

static bool storage_read(void *ctx, uint16_t slot, uint32_t offset,
                         uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= TEST_SLOTS ||
      (uint64_t)offset + size > ZS_COMMAND_JOURNAL_SLOT_BYTES)
    return false;
  memcpy(data, &fixture->slots[slot][offset], size);
  return true;
}

static bool storage_erase(void *ctx, uint16_t slot) {
  fixture_t *fixture = ctx;
  if (slot >= TEST_SLOTS) return false;
  memset(fixture->slots[slot], 0xff, ZS_COMMAND_JOURNAL_SLOT_BYTES);
  return true;
}

static bool storage_write(void *ctx, uint16_t slot, uint32_t offset,
                          const uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (slot >= TEST_SLOTS || !data ||
      (uint64_t)offset + size > ZS_COMMAND_JOURNAL_SLOT_BYTES)
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

static bool verify_backend(
    void *ctx,
    const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES],
    const uint8_t *message,
    size_t message_size,
    const uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES]) {
  fixture_t *fixture = ctx;
  ++fixture->backend_calls;
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
  assert(command->audio.event_id == 42u);
  *result = ZS_COMMAND_ACK_OK;
  *detail_code = 0u;
  return true;
}

static void reconnect(fixture_t *fixture, zs_bg95_t *modem,
                      zs_bg95_command_transport_t *binding,
                      zs_mqtt_command_transport_t *transport) {
  zs_hal_port_t port = {0};
  fixture->uart_size = 0u;
  fixture->uart_calls = 0u;
  fixture->fail_uart_call = 0u;
  fixture->short_uart_call = 0u;
  port.ctx = fixture;
  port.uart_write = uart_write;
  zs_bg95_init(modem, &port, 1u, 2u, "internet");
  modem->state = ZS_BG95_ONLINE;
  modem->mqtt_connected = true;
  modem->mqtt_receive_length_enabled = true;
  modem->mqtt_client = 0u;
  assert(zs_bg95_command_transport_init(
      binding, modem, transport, true));
}

static void setup(fixture_t *fixture,
                  zs_command_trust_t *trust,
                  zs_command_journal_io_t *journal,
                  zs_command_channel_t *channel,
                  zs_mqtt_command_transport_t *transport,
                  zs_bg95_t *modem,
                  zs_bg95_command_transport_t *binding) {
  static const uint8_t tenant[] = {'e', 'v', 't'};
  const zs_command_trust_key_t key = {
      .public_key = {
          0x79u, 0xb5u, 0x56u, 0x2eu, 0x8fu, 0xe6u, 0x54u, 0xf9u,
          0x40u, 0x78u, 0xb1u, 0x12u, 0xe8u, 0xa9u, 0x8bu, 0xa7u,
          0x90u, 0x1fu, 0x85u, 0x3au, 0xe6u, 0x95u, 0xbeu, 0xd7u,
          0xe0u, 0xe3u, 0x91u, 0x0bu, 0xadu, 0x04u, 0x96u, 0x64u},
      .enabled = true};
  memset(fixture, 0, sizeof(*fixture));
  memset(fixture->slots, 0xff, sizeof(fixture->slots));
  *journal = (zs_command_journal_io_t){
      fixture, TEST_SLOTS, storage_read, storage_erase, storage_write};
  assert(zs_command_trust_init(
      trust, &key, 1u, verify_backend, fixture));
  *channel = (zs_command_channel_t){
      ZS_COMMAND_VECTOR_STATION_ID, trust, journal, execute, fixture,
      fixture->workspace, sizeof(fixture->workspace)};
  assert(zs_mqtt_command_transport_init(
      transport, channel, tenant, sizeof(tenant)));
  reconnect(fixture, modem, binding, transport);
}

static void subscribe(fixture_t *fixture,
                      zs_bg95_command_transport_t *binding,
                      uint16_t message_id) {
  char expected[160];
  int expected_size;
  assert(zs_bg95_command_transport_subscribe(binding, message_id, 100u) ==
         ZS_BG95_COMMAND_SUBSCRIBE_STARTED);
  expected_size = snprintf(expected, sizeof(expected),
                           "AT+QMTSUB=0,%u,\"zs/v1/evt/17/down\",1\r\n",
                           message_id);
  assert(expected_size > 0 && (size_t)expected_size < sizeof(expected));
  assert(fixture->uart_size == (size_t)expected_size);
  assert(memcmp(fixture->uart, expected, (size_t)expected_size) == 0);
  assert(zs_bg95_command_transport_on_line(binding, "OK", 101u));
  snprintf(expected, sizeof(expected), "+QMTSUB: 0,%u,0,1", message_id);
  assert(zs_bg95_command_transport_on_line(binding, expected, 102u));
  assert(binding->state == ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED);
  assert(binding->last_outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_READY);
}

static size_t make_frame(uint8_t *frame, size_t capacity,
                         unsigned client, unsigned message_id,
                         const uint8_t *topic, size_t topic_size,
                         const uint8_t *payload, size_t payload_size,
                         size_t declared_payload_size) {
  char prefix[96];
  char length[32];
  int prefix_size = snprintf(prefix, sizeof(prefix),
                             "+QMTRECV: %u,%u,\"", client, message_id);
  int length_size;
  size_t used;
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
  frame[used++] = (uint8_t)'\r';
  frame[used++] = (uint8_t)'\n';
  return used;
}

static void test_shared_receive_numeric_bounds(void) {
  static const uint8_t topic[] = "zs/v1/evt/17/down";
  static const uint8_t payload[] = {0x00u};
  zs_bg95_mqtt_receive_frame_t received;
  uint8_t frame[160];
  size_t frame_size;

  frame_size = make_frame(
      frame, sizeof(frame), 6u, 1u, topic, sizeof(topic) - 1u,
      payload, sizeof(payload), sizeof(payload));
  assert(zs_bg95_mqtt_parse_receive_frame(
      frame, frame_size, &received) == ZS_BG95_MQTT_RECEIVE_MALFORMED);

  frame_size = make_frame(
      frame, sizeof(frame), 0u, 65536u, topic, sizeof(topic) - 1u,
      payload, sizeof(payload), sizeof(payload));
  assert(zs_bg95_mqtt_parse_receive_frame(
      frame, frame_size, &received) == ZS_BG95_MQTT_RECEIVE_MALFORMED);
}

static void test_binary_down_to_fixed_length_durable_ack(void) {
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_command_transport_t binding;
  zs_command_status_t status;
  uint8_t frame[4096];
  char expected[160];
  size_t frame_size, command_offset, command_size;
  int expected_size;

  setup(&fixture, &trust, &journal, &channel, &transport, &modem, &binding);
  subscribe(&fixture, &binding, 31u);
  frame_size = make_frame(
      frame, sizeof(frame), 0u, 7u, transport.down_topic,
      transport.down_topic_size, zs_command_vector_payload,
      sizeof(zs_command_vector_payload), sizeof(zs_command_vector_payload));
  assert(memchr(zs_command_vector_payload, 0,
                sizeof(zs_command_vector_payload)) != NULL);
  command_offset = fixture.uart_size;
  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 44u, UINT64_C(1750000), true, 200u,
      &status) == ZS_BG95_COMMAND_ACK_PUBLISH_STARTED);
  assert(status == ZS_COMMAND_STATUS_OK);
  assert(fixture.backend_calls == 1u && fixture.execute_calls == 1u);
  expected_size = snprintf(
      expected, sizeof(expected),
      "AT+QMTPUB=0,44,1,0,\"zs/v1/evt/17/ack\",%zu\r\n",
      sizeof(zs_command_vector_ack));
  assert(expected_size > 0 && (size_t)expected_size < sizeof(expected));
  command_size = (size_t)expected_size;
  assert(fixture.uart_size == command_offset + command_size);
  assert(memcmp(&fixture.uart[command_offset], expected, command_size) == 0);
  assert(binding.state == ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_PROMPT);
  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 45u, UINT64_C(1750001), true, 201u,
      &status) == ZS_BG95_COMMAND_BUSY);
  assert(fixture.execute_calls == 1u);

  assert(zs_bg95_command_transport_on_prompt(&binding, 202u));
  assert(fixture.uart_size ==
         command_offset + command_size + sizeof(zs_command_vector_ack));
  assert(memcmp(&fixture.uart[command_offset + command_size],
                zs_command_vector_ack, sizeof(zs_command_vector_ack)) == 0);
  assert(zs_bg95_command_transport_on_line(&binding, "OK", 203u));
  assert(zs_bg95_command_transport_on_line(
      &binding, "+QMTPUB: 0,44,0", 204u));
  assert(binding.state == ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED);
  assert(binding.last_outcome ==
         ZS_BG95_COMMAND_TRANSPORT_OUTCOME_ACK_BROKER_ACK);

  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 45u, UINT64_C(1750100), true, 205u,
      &status) == ZS_BG95_COMMAND_ACK_PUBLISH_STARTED);
  assert(status == ZS_COMMAND_STATUS_DUPLICATE);
  assert(fixture.execute_calls == 1u);
  assert(zs_bg95_command_transport_on_prompt(&binding, 206u));
  assert(zs_bg95_command_transport_on_line(
      &binding, "+QMTPUB: 0,45,1,3", 207u));
  assert(binding.state == ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED);
  assert(binding.last_outcome ==
         ZS_BG95_COMMAND_TRANSPORT_OUTCOME_MODEM_REJECTED);
}

static void test_receive_routing_and_framing_guards(void) {
  static const uint8_t wrong_topic[] = "zs/v1/evt/18/down";
  static const uint8_t unrelated[] = "+QMTSTAT: 0,1";
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_command_transport_t binding;
  zs_command_status_t status;
  uint8_t frame[4096];
  size_t frame_size;

  setup(&fixture, &trust, &journal, &channel, &transport, &modem, &binding);
  subscribe(&fixture, &binding, 1u);
  assert(zs_bg95_command_transport_on_frame(
      &binding, unrelated, sizeof(unrelated) - 1u, 2u,
      UINT64_C(1750000), true, 0u, &status) ==
         ZS_BG95_COMMAND_NOT_COMMAND_FRAME);
  frame_size = make_frame(
      frame, sizeof(frame), 1u, 2u, transport.down_topic,
      transport.down_topic_size, zs_command_vector_payload,
      sizeof(zs_command_vector_payload), sizeof(zs_command_vector_payload));
  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 2u, UINT64_C(1750000), true, 0u,
      &status) == ZS_BG95_COMMAND_CLIENT_MISMATCH);
  frame_size = make_frame(
      frame, sizeof(frame), 0u, 2u, wrong_topic, sizeof(wrong_topic) - 1u,
      zs_command_vector_payload, sizeof(zs_command_vector_payload),
      sizeof(zs_command_vector_payload));
  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 2u, UINT64_C(1750000), true, 0u,
      &status) == ZS_BG95_COMMAND_REJECTED_TOPIC);
  frame_size = make_frame(
      frame, sizeof(frame), 0u, 0u, transport.down_topic,
      transport.down_topic_size, zs_command_vector_payload,
      sizeof(zs_command_vector_payload), sizeof(zs_command_vector_payload));
  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 2u, UINT64_C(1750000), true, 0u,
      &status) == ZS_BG95_COMMAND_REJECTED_DELIVERY);
  frame_size = make_frame(
      frame, sizeof(frame), 0u, 2u, transport.down_topic,
      transport.down_topic_size, zs_command_vector_payload,
      sizeof(zs_command_vector_payload), sizeof(zs_command_vector_payload) + 1u);
  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 2u, UINT64_C(1750000), true, 0u,
      &status) == ZS_BG95_COMMAND_FRAMING_ERROR);
  assert(binding.state == ZS_BG95_COMMAND_TRANSPORT_IDLE);
  assert(modem.state == ZS_BG95_ERROR && !modem.mqtt_connected);
}

static void test_policy_setup_and_ack_uart_failures(void) {
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t transport;
  zs_bg95_t modem;
  zs_bg95_command_transport_t binding;
  zs_command_status_t status;
  uint8_t frame[4096];
  size_t frame_size;

  setup(&fixture, &trust, &journal, &channel, &transport, &modem, &binding);
  assert(!zs_bg95_command_transport_init(
      &binding, &modem, &transport, false));
  assert(binding.modem == NULL && binding.transport == NULL);

  reconnect(&fixture, &modem, &binding, &transport);
  modem.mqtt_receive_length_enabled = false;
  assert(zs_bg95_command_transport_subscribe(&binding, 1u, 0u) ==
         ZS_BG95_COMMAND_RECEIVE_MODE_REQUIRED);
  assert(modem.state == ZS_BG95_ERROR);

  reconnect(&fixture, &modem, &binding, &transport);
  fixture.short_uart_call = 1u;
  assert(zs_bg95_command_transport_subscribe(&binding, 2u, 0u) ==
         ZS_BG95_COMMAND_SUBSCRIBE_IO_ERROR);
  assert(modem.state == ZS_BG95_ERROR);

  reconnect(&fixture, &modem, &binding, &transport);
  assert(zs_bg95_command_transport_subscribe(&binding, 3u, 10u) ==
         ZS_BG95_COMMAND_SUBSCRIBE_STARTED);
  zs_bg95_command_transport_tick(
      &binding, 10u + ZS_BG95_COMMAND_TRANSPORT_TIMEOUT_MS);
  assert(binding.last_outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT);

  reconnect(&fixture, &modem, &binding, &transport);
  subscribe(&fixture, &binding, 4u);
  frame_size = make_frame(
      frame, sizeof(frame), 0u, 3u, transport.down_topic,
      transport.down_topic_size, zs_command_vector_payload,
      sizeof(zs_command_vector_payload), sizeof(zs_command_vector_payload));
  fixture.short_uart_call = fixture.uart_calls + 1u;
  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 5u, UINT64_C(1750000), true, 20u,
      &status) == ZS_BG95_COMMAND_ACK_IO_ERROR);
  assert(fixture.execute_calls == 1u);
  assert(modem.state == ZS_BG95_ERROR);

  /* Server retry after reconnect obtains durable ACK without re-execution. */
  reconnect(&fixture, &modem, &binding, &transport);
  subscribe(&fixture, &binding, 6u);
  assert(zs_bg95_command_transport_on_frame(
      &binding, frame, frame_size, 7u, UINT64_C(1750100), true, 30u,
      &status) == ZS_BG95_COMMAND_ACK_PUBLISH_STARTED);
  assert(status == ZS_COMMAND_STATUS_DUPLICATE);
  assert(fixture.execute_calls == 1u);
  fixture.short_uart_call = fixture.uart_calls + 1u;
  assert(!zs_bg95_command_transport_on_prompt(&binding, 31u));
  assert(binding.last_outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_IO_ERROR);
  assert(modem.state == ZS_BG95_ERROR);
}

int main(void) {
  test_shared_receive_numeric_bounds();
  test_binary_down_to_fixed_length_durable_ack();
  test_receive_routing_and_framing_guards();
  test_policy_setup_and_ack_uart_failures();
  puts("zs_bg95_command_transport_tests: OK");
  return 0;
}

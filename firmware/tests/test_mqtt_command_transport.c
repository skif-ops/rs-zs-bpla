#include "zs_mqtt_command_transport.h"
#include "zs_command_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define TEST_SLOTS 4u

typedef struct {
  uint8_t slots[TEST_SLOTS][ZS_COMMAND_JOURNAL_SLOT_BYTES];
  unsigned execute_calls;
  unsigned backend_calls;
  bool execute_ready;
  bool fail_reads;
} fixture_t;

static bool storage_read(void *ctx, uint16_t slot, uint32_t offset,
                         uint8_t *data, size_t size) {
  fixture_t *fixture = ctx;
  if (fixture->fail_reads || slot >= TEST_SLOTS ||
      offset + size > ZS_COMMAND_JOURNAL_SLOT_BYTES)
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
  if (slot >= TEST_SLOTS || offset + size > ZS_COMMAND_JOURNAL_SLOT_BYTES)
    return false;
  for (size_t i = 0u; i < size; ++i) {
    if ((fixture->slots[slot][offset + i] & data[i]) != data[i]) return false;
    fixture->slots[slot][offset + i] = data[i];
  }
  return true;
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
                    zs_command_ack_result_t *result, uint16_t *detail_code) {
  fixture_t *fixture = ctx;
  ++fixture->execute_calls;
  assert(command->audio.event_id == 42u);
  if (!fixture->execute_ready) return false;
  *result = ZS_COMMAND_ACK_OK;
  *detail_code = 0u;
  return true;
}

static zs_command_channel_t make_channel(
    fixture_t *fixture,
    zs_command_trust_t *trust,
    zs_command_journal_io_t *journal,
    uint8_t *workspace,
    size_t workspace_size) {
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
  assert(zs_command_trust_init(trust, &key, 1u, verify_backend, fixture));
  return (zs_command_channel_t){
      ZS_COMMAND_VECTOR_STATION_ID, trust, journal, execute, fixture,
      workspace, workspace_size};
}

static void test_binary_down_to_ack(void) {
  static const uint8_t tenant[] = {'e', 'v', 't'};
  static const uint8_t expected_down[] = "zs/v1/evt/17/down";
  static const uint8_t expected_ack[] = "zs/v1/evt/17/ack";
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t transport;
  zs_mqtt_command_message_t message, publication;
  zs_command_status_t decode_status;
  uint8_t workspace[256], ack[ZS_COMMAND_ACK_MAX_BYTES];

  channel = make_channel(&fixture, &trust, &journal, workspace,
                         sizeof(workspace));
  fixture.execute_ready = true;
  assert(zs_mqtt_command_transport_init(&transport, &channel, tenant,
                                        sizeof(tenant)));
  assert(transport.down_topic_size == sizeof(expected_down) - 1u);
  assert(memcmp(transport.down_topic, expected_down,
                sizeof(expected_down) - 1u) == 0);
  assert(memchr(zs_command_vector_payload, 0,
                sizeof(zs_command_vector_payload)) != NULL);

  message = (zs_mqtt_command_message_t){
      transport.down_topic, transport.down_topic_size,
      zs_command_vector_payload, sizeof(zs_command_vector_payload),
      ZS_MQTT_COMMAND_QOS, false};
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_ACK_READY);
  assert(decode_status == ZS_COMMAND_STATUS_OK);
  assert(fixture.backend_calls == 1u && fixture.execute_calls == 1u);
  assert(publication.topic_size == sizeof(expected_ack) - 1u);
  assert(memcmp(publication.topic, expected_ack,
                sizeof(expected_ack) - 1u) == 0);
  assert(publication.payload == ack);
  assert(publication.payload_size == sizeof(zs_command_vector_ack));
  assert(memcmp(publication.payload, zs_command_vector_ack,
                publication.payload_size) == 0);
  assert(publication.qos == ZS_MQTT_COMMAND_QOS && !publication.retained);
}

static void test_topic_and_delivery_rejection(void) {
  static const uint8_t tenant[] = "evt";
  static const uint8_t wrong_station[] = "zs/v1/evt/18/down";
  static const uint8_t leading_zero[] = "zs/v1/evt/017/down";
  static const uint8_t trailing_nul[] = "zs/v1/evt/17/down";
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t transport;
  zs_mqtt_command_message_t message, publication;
  zs_command_status_t decode_status;
  uint8_t workspace[256], ack[ZS_COMMAND_ACK_MAX_BYTES];

  channel = make_channel(&fixture, &trust, &journal, workspace,
                         sizeof(workspace));
  fixture.execute_ready = true;
  assert(zs_mqtt_command_transport_init(&transport, &channel, tenant,
                                        sizeof(tenant) - 1u));
  message = (zs_mqtt_command_message_t){
      wrong_station, sizeof(wrong_station) - 1u,
      zs_command_vector_payload, sizeof(zs_command_vector_payload), 1u, false};
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_REJECTED_TOPIC);
  assert(publication.topic == NULL && publication.payload == NULL);

  message.topic = leading_zero;
  message.topic_size = sizeof(leading_zero) - 1u;
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_REJECTED_TOPIC);
  message.topic = trailing_nul;
  message.topic_size = sizeof(trailing_nul);
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_REJECTED_TOPIC);

  message.topic = transport.down_topic;
  message.topic_size = transport.down_topic_size;
  message.qos = 0u;
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_REJECTED_DELIVERY);
  message.qos = 1u;
  message.retained = true;
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_REJECTED_DELIVERY);
  message.retained = false;
  transport.down_topic_size = ZS_MQTT_COMMAND_TOPIC_MAX_BYTES + 1u;
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_INVALID_ARGUMENT);
  assert(fixture.backend_calls == 0u && fixture.execute_calls == 0u);
}

static void test_result_mapping_without_ack(void) {
  static const uint8_t tenant[] = "evt";
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t transport;
  zs_mqtt_command_message_t message, publication;
  zs_command_status_t decode_status;
  uint8_t workspace[256], ack[ZS_COMMAND_ACK_MAX_BYTES], tampered[128];

  channel = make_channel(&fixture, &trust, &journal, workspace,
                         sizeof(workspace));
  assert(zs_mqtt_command_transport_init(&transport, &channel, tenant,
                                        sizeof(tenant) - 1u));
  message = (zs_mqtt_command_message_t){
      transport.down_topic, transport.down_topic_size,
      zs_command_vector_payload, sizeof(zs_command_vector_payload), 1u, false};
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_EXECUTION_RETRY);
  assert(publication.payload_size == 0u && fixture.execute_calls == 1u);

  memcpy(tampered, zs_command_vector_payload, sizeof(zs_command_vector_payload));
  tampered[43] ^= 1u;
  message.payload = tampered;
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_REJECTED_COMMAND);
  assert(publication.payload_size == 0u && fixture.execute_calls == 1u);

  message.payload = zs_command_vector_payload;
  fixture.fail_reads = true;
  assert(zs_mqtt_command_transport_handle(
      &transport, &message, UINT64_C(1750000), true, ack, sizeof(ack),
      &publication, &decode_status) == ZS_MQTT_COMMAND_STORAGE_ERROR);
  assert(decode_status == ZS_COMMAND_STATUS_DEDUP_STORAGE_ERROR);
  assert(publication.payload_size == 0u && fixture.execute_calls == 1u);
}

static void test_tenant_and_argument_guards(void) {
  static const uint8_t valid_max[] =
      "A2345678901234567890123456789012";
  static const uint8_t invalid_first[] = "_evt";
  static const uint8_t invalid_wildcard[] = "ev+";
  static const uint8_t invalid_slash[] = "ev/t";
  static const uint8_t embedded_nul[] = {'e', 0u, 't'};
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t transport;
  uint8_t workspace[256];

  channel = make_channel(&fixture, &trust, &journal, workspace,
                         sizeof(workspace));
  assert(sizeof(valid_max) - 1u == ZS_MQTT_COMMAND_TENANT_MAX_BYTES);
  assert(zs_mqtt_command_transport_init(&transport, &channel, valid_max,
                                        sizeof(valid_max) - 1u));
  assert(!zs_mqtt_command_transport_init(
      &transport, &channel, invalid_first, sizeof(invalid_first) - 1u));
  assert(transport.channel == NULL && transport.down_topic_size == 0u);
  assert(!zs_mqtt_command_transport_init(
      &transport, &channel, invalid_wildcard, sizeof(invalid_wildcard) - 1u));
  assert(!zs_mqtt_command_transport_init(
      &transport, &channel, invalid_slash, sizeof(invalid_slash) - 1u));
  assert(!zs_mqtt_command_transport_init(
      &transport, &channel, embedded_nul, sizeof(embedded_nul)));
  assert(!zs_mqtt_command_transport_init(&transport, &channel, valid_max, 0u));
  assert(!zs_mqtt_command_transport_init(NULL, &channel, valid_max,
                                         sizeof(valid_max) - 1u));
  channel.station_id = 0u;
  assert(!zs_mqtt_command_transport_init(
      &transport, &channel, valid_max, sizeof(valid_max) - 1u));
}

int main(void) {
  test_binary_down_to_ack();
  test_topic_and_delivery_rejection();
  test_result_mapping_without_ack();
  test_tenant_and_argument_guards();
  puts("zs_mqtt_command_transport_tests: OK");
  return 0;
}

#include "zs_command_channel.h"
#include "zs_command_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define TEST_SLOTS 4u

typedef struct {
  uint8_t slots[TEST_SLOTS][ZS_COMMAND_JOURNAL_SLOT_BYTES];
  unsigned execute_calls;
  bool execute_ready;
  unsigned backend_calls;
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
  *journal = (zs_command_journal_io_t){
      fixture, TEST_SLOTS, storage_read, storage_erase, storage_write};
  assert(zs_command_trust_init(trust, &key, 1u, verify_backend, fixture));
  return (zs_command_channel_t){
      ZS_COMMAND_VECTOR_STATION_ID, trust, journal, execute, fixture,
      workspace, workspace_size};
}

static void test_complete_then_duplicate_ack(void) {
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  uint8_t workspace[256], ack[ZS_COMMAND_ACK_MAX_BYTES];
  zs_command_channel_t channel;
  zs_command_status_t decode_status;
  size_t ack_size;
  memset(&fixture, 0, sizeof(fixture));
  memset(fixture.slots, 0xff, sizeof(fixture.slots));
  fixture.execute_ready = true;
  channel = make_channel(&fixture, &trust, &journal, workspace,
                         sizeof(workspace));

  assert(zs_command_channel_handle(
      &channel, zs_command_vector_payload, sizeof(zs_command_vector_payload),
      UINT64_C(1750000), true, ack, sizeof(ack), &ack_size,
      &decode_status) == ZS_COMMAND_CHANNEL_ACK_READY);
  assert(decode_status == ZS_COMMAND_STATUS_OK);
  assert(fixture.execute_calls == 1u && fixture.backend_calls == 1u);
  assert(ack_size == sizeof(zs_command_vector_ack));
  assert(memcmp(ack, zs_command_vector_ack, ack_size) == 0);

  assert(zs_command_channel_handle(
      &channel, zs_command_vector_payload, sizeof(zs_command_vector_payload),
      UINT64_C(1750000), true, ack, sizeof(ack), &ack_size,
      &decode_status) == ZS_COMMAND_CHANNEL_ACK_READY);
  assert(decode_status == ZS_COMMAND_STATUS_DUPLICATE);
  assert(fixture.execute_calls == 1u && fixture.backend_calls == 2u);
  assert(memcmp(ack, zs_command_vector_ack, ack_size) == 0);
}

static void test_retry_and_reject_paths(void) {
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  uint8_t workspace[256], ack[ZS_COMMAND_ACK_MAX_BYTES], tampered[128];
  zs_command_channel_t channel;
  zs_command_status_t decode_status;
  size_t ack_size = 99u;
  memset(&fixture, 0, sizeof(fixture));
  memset(fixture.slots, 0xff, sizeof(fixture.slots));
  channel = make_channel(&fixture, &trust, &journal, workspace,
                         sizeof(workspace));

  assert(zs_command_channel_handle(
      &channel, zs_command_vector_payload, sizeof(zs_command_vector_payload),
      UINT64_C(1500000), true, ack, sizeof(ack), &ack_size,
      &decode_status) == ZS_COMMAND_CHANNEL_EXECUTION_RETRY);
  assert(decode_status == ZS_COMMAND_STATUS_OK && ack_size == 0u);
  assert(fixture.execute_calls == 1u);
  fixture.execute_ready = true;
  assert(zs_command_channel_handle(
      &channel, zs_command_vector_payload, sizeof(zs_command_vector_payload),
      UINT64_C(1750000), true, ack, sizeof(ack), &ack_size,
      &decode_status) == ZS_COMMAND_CHANNEL_ACK_READY);
  assert(decode_status == ZS_COMMAND_STATUS_DUPLICATE);
  assert(fixture.execute_calls == 2u);
  assert(memcmp(ack, zs_command_vector_ack, ack_size) == 0);

  memcpy(tampered, zs_command_vector_payload, sizeof(zs_command_vector_payload));
  tampered[43] ^= 1u;
  assert(zs_command_channel_handle(
      &channel, tampered, sizeof(zs_command_vector_payload),
      UINT64_C(1750000), true, ack, sizeof(ack), &ack_size,
      &decode_status) == ZS_COMMAND_CHANNEL_REJECTED);
  assert(ack_size == 0u && fixture.execute_calls == 2u);
  fixture.fail_reads = true;
  assert(zs_command_channel_handle(
      &channel, zs_command_vector_payload, sizeof(zs_command_vector_payload),
      UINT64_C(1750000), true, ack, sizeof(ack), &ack_size,
      &decode_status) == ZS_COMMAND_CHANNEL_STORAGE_ERROR);
  assert(decode_status == ZS_COMMAND_STATUS_DEDUP_STORAGE_ERROR);
  assert(ack_size == 0u && fixture.execute_calls == 2u);
  fixture.fail_reads = false;
  assert(zs_command_channel_handle(
      &channel, zs_command_vector_payload, sizeof(zs_command_vector_payload),
      UINT64_C(1750000), true, ack, 1u, &ack_size,
      &decode_status) == ZS_COMMAND_CHANNEL_INVALID_ARGUMENT);
}

int main(void) {
  test_complete_then_duplicate_ack();
  test_retry_and_reject_paths();
  puts("zs_command_channel_tests: OK");
  return 0;
}

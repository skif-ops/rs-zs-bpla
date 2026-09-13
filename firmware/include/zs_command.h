#ifndef ZS_COMMAND_H
#define ZS_COMMAND_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_COMMAND_SCHEMA_VERSION 1u
#define ZS_COMMAND_MESSAGE_TYPE 4u
#define ZS_COMMAND_ACK_MESSAGE_TYPE 5u
#define ZS_COMMAND_MAX_BYTES 2048u
#define ZS_COMMAND_KEY_ID_BYTES 8u
#define ZS_COMMAND_UUID_BYTES 16u
#define ZS_COMMAND_SIGNATURE_BYTES 64u
#define ZS_COMMAND_MAX_TTL_US UINT64_C(900000000)

typedef enum {
  ZS_COMMAND_REQUEST_AUDIO = 1
} zs_command_code_t;

typedef enum {
  ZS_AUDIO_SEGMENT_PRE = 0,
  ZS_AUDIO_SEGMENT_POST = 1,
  ZS_AUDIO_SEGMENT_BOTH = 2,
  ZS_AUDIO_SEGMENT_RANGE = 3
} zs_audio_segment_t;

typedef struct {
  uint64_t event_id;
  zs_audio_segment_t segment;
  int32_t start_offset_ms;
  uint32_t duration_ms;
  bool has_range;
} zs_audio_request_command_t;

typedef struct {
  uint32_t station_id;
  uint8_t command_id[ZS_COMMAND_UUID_BYTES];
  uint64_t created_time_us;
  uint64_t expires_time_us;
  zs_command_code_t code;
  zs_audio_request_command_t audio;
  uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES];
} zs_command_t;

typedef enum {
  ZS_COMMAND_STATUS_OK = 0,
  ZS_COMMAND_STATUS_INVALID_ARGUMENT,
  ZS_COMMAND_STATUS_INVALID_CBOR,
  ZS_COMMAND_STATUS_UNSUPPORTED,
  ZS_COMMAND_STATUS_STATION_MISMATCH,
  ZS_COMMAND_STATUS_TIME_UNTRUSTED,
  ZS_COMMAND_STATUS_NOT_YET_VALID,
  ZS_COMMAND_STATUS_EXPIRED,
  ZS_COMMAND_STATUS_INVALID_TTL,
  ZS_COMMAND_STATUS_SIGNATURE_REJECTED,
  ZS_COMMAND_STATUS_DEDUP_REQUIRED,
  ZS_COMMAND_STATUS_DEDUP_STORAGE_ERROR,
  ZS_COMMAND_STATUS_DUPLICATE,
  ZS_COMMAND_STATUS_WORKSPACE_TOO_SMALL
} zs_command_status_t;

typedef bool (*zs_command_signature_verify_fn)(
    void *ctx,
    const uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES],
    const uint8_t *signed_cbor,
    size_t signed_cbor_size,
    const uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES]);

typedef enum {
  ZS_COMMAND_DEDUP_NOT_SEEN = 0,
  ZS_COMMAND_DEDUP_SEEN,
  ZS_COMMAND_DEDUP_ERROR
} zs_command_dedup_state_t;

typedef zs_command_dedup_state_t (*zs_command_dedup_lookup_fn)(
    void *ctx, const uint8_t command_id[ZS_COMMAND_UUID_BYTES]);

typedef enum {
  ZS_COMMAND_ACK_OK = 0,
  ZS_COMMAND_ACK_REJECTED = 1,
  ZS_COMMAND_ACK_FAILED = 2,
  ZS_COMMAND_ACK_EXPIRED = 3
} zs_command_ack_result_t;

/*
 * The verifier must resolve key_id only through the provisioned production
 * trust store and verify Ed25519 over signed_cbor. The dedup callback must read
 * durable state. An OK result establishes eligibility only: the caller must
 * execute idempotently and durably record the command result before publishing
 * its ACK. DUPLICATE must never repeat the command side effect.
 */
zs_command_status_t zs_command_decode_verify(
    const uint8_t *payload,
    size_t payload_size,
    uint32_t expected_station_id,
    uint64_t now_us,
    bool time_trusted,
    zs_command_signature_verify_fn verify,
    void *verify_ctx,
    zs_command_dedup_lookup_fn dedup_lookup,
    void *dedup_ctx,
    uint8_t *workspace,
    size_t workspace_size,
    zs_command_t *command);

size_t zs_command_encode_ack(
    uint32_t station_id,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    zs_command_ack_result_t result,
    uint64_t completed_time_us,
    uint16_t detail_code,
    uint8_t *output,
    size_t output_size);

const char *zs_command_status_name(zs_command_status_t status);

#endif

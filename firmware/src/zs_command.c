#include "zs_command.h"

#include "zs_cbor.h"

#include <limits.h>
#include <string.h>

typedef struct {
  const uint8_t *data;
  size_t size;
  size_t offset;
} command_reader_t;

static bool any_nonzero(const uint8_t *data, size_t size) {
  uint8_t combined = 0u;
  for (size_t i = 0u; i < size; ++i) combined |= data[i];
  return combined != 0u;
}

static bool read_argument(command_reader_t *reader, uint8_t *major, uint64_t *value) {
  uint8_t initial, additional;
  size_t bytes;
  uint64_t parsed = 0u;
  if (!reader || !major || !value || reader->offset >= reader->size) return false;
  initial = reader->data[reader->offset++];
  *major = initial >> 5;
  additional = initial & 0x1fu;
  if (additional < 24u) {
    *value = additional;
    return true;
  }
  if (additional == 24u) bytes = 1u;
  else if (additional == 25u) bytes = 2u;
  else if (additional == 26u) bytes = 4u;
  else if (additional == 27u) bytes = 8u;
  else return false;
  if (reader->offset + bytes > reader->size) return false;
  for (size_t i = 0u; i < bytes; ++i) {
    parsed = (parsed << 8) | reader->data[reader->offset++];
  }
  if ((bytes == 1u && parsed < 24u) ||
      (bytes == 2u && parsed <= UINT8_MAX) ||
      (bytes == 4u && parsed <= UINT16_MAX) ||
      (bytes == 8u && parsed <= UINT32_MAX)) return false;
  *value = parsed;
  return true;
}

static bool read_uint(command_reader_t *reader, uint64_t *value) {
  uint8_t major;
  return read_argument(reader, &major, value) && major == 0u;
}

static bool expect_uint(command_reader_t *reader, uint64_t expected) {
  uint64_t value;
  return read_uint(reader, &value) && value == expected;
}

static bool expect_map(command_reader_t *reader, uint64_t count) {
  uint8_t major;
  uint64_t value;
  return read_argument(reader, &major, &value) && major == 5u && value == count;
}

static bool read_bytes(command_reader_t *reader, uint8_t *output, size_t expected) {
  uint8_t major;
  uint64_t size;
  if (!read_argument(reader, &major, &size) || major != 2u || size != expected ||
      reader->offset + expected > reader->size) return false;
  memcpy(output, &reader->data[reader->offset], expected);
  reader->offset += expected;
  return true;
}

static bool read_nullable_int32(command_reader_t *reader, int32_t *output,
                                bool *present) {
  uint8_t major;
  uint64_t value;
  int64_t signed_value;
  if (reader->offset >= reader->size) return false;
  if (reader->data[reader->offset] == 0xf6u) {
    ++reader->offset;
    *output = 0;
    *present = false;
    return true;
  }
  if (!read_argument(reader, &major, &value) || major > 1u) return false;
  if (major == 0u) {
    if (value > INT32_MAX) return false;
    signed_value = (int64_t)value;
  } else {
    if (value > INT32_MAX) return false;
    signed_value = -1 - (int64_t)value;
  }
  *output = (int32_t)signed_value;
  *present = true;
  return true;
}

static bool read_nullable_uint32(command_reader_t *reader, uint32_t *output,
                                 bool *present) {
  uint64_t value;
  if (reader->offset >= reader->size) return false;
  if (reader->data[reader->offset] == 0xf6u) {
    ++reader->offset;
    *output = 0u;
    *present = false;
    return true;
  }
  if (!read_uint(reader, &value) || value == 0u || value > UINT32_MAX) return false;
  *output = (uint32_t)value;
  *present = true;
  return true;
}

static bool read_audio_payload(command_reader_t *reader,
                               zs_audio_request_command_t *audio) {
  uint64_t event_id, segment;
  bool start_present, duration_present;
  if (!expect_map(reader, 4u) ||
      !expect_uint(reader, 0u) || !read_uint(reader, &event_id) || event_id == 0u ||
      !expect_uint(reader, 1u) || !read_uint(reader, &segment) ||
      segment > ZS_AUDIO_SEGMENT_RANGE ||
      !expect_uint(reader, 2u) ||
      !read_nullable_int32(reader, &audio->start_offset_ms, &start_present) ||
      !expect_uint(reader, 3u) ||
      !read_nullable_uint32(reader, &audio->duration_ms, &duration_present)) return false;
  if (segment == ZS_AUDIO_SEGMENT_RANGE) {
    if (!start_present || !duration_present) return false;
    audio->has_range = true;
  } else {
    if (start_present || duration_present) return false;
    audio->has_range = false;
  }
  audio->event_id = event_id;
  audio->segment = (zs_audio_segment_t)segment;
  return true;
}

static zs_command_status_t decode_envelope(
    size_t payload_size, uint32_t expected_station_id,
    uint64_t now_us, bool time_trusted, command_reader_t *reader,
    zs_command_t *command, uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES],
    size_t *signed_size) {
  uint64_t value;
  if (!expect_map(reader, 10u)) return ZS_COMMAND_STATUS_INVALID_CBOR;
  if (!expect_uint(reader, 0u) || !expect_uint(reader, ZS_COMMAND_SCHEMA_VERSION) ||
      !expect_uint(reader, 1u) || !expect_uint(reader, ZS_COMMAND_MESSAGE_TYPE))
    return ZS_COMMAND_STATUS_UNSUPPORTED;
  if (!expect_uint(reader, 2u) || !read_uint(reader, &value) ||
      value == 0u || value > UINT32_MAX) return ZS_COMMAND_STATUS_INVALID_CBOR;
  command->station_id = (uint32_t)value;
  if (command->station_id != expected_station_id) return ZS_COMMAND_STATUS_STATION_MISMATCH;
  if (!expect_uint(reader, 3u) ||
      !read_bytes(reader, command->command_id, ZS_COMMAND_UUID_BYTES) ||
      !any_nonzero(command->command_id, ZS_COMMAND_UUID_BYTES) ||
      !expect_uint(reader, 4u) || !read_uint(reader, &command->created_time_us) ||
      !expect_uint(reader, 5u) || !read_uint(reader, &command->expires_time_us))
    return ZS_COMMAND_STATUS_INVALID_CBOR;
  if (command->expires_time_us <= command->created_time_us ||
      command->expires_time_us - command->created_time_us > ZS_COMMAND_MAX_TTL_US)
    return ZS_COMMAND_STATUS_INVALID_TTL;
  if (!time_trusted) return ZS_COMMAND_STATUS_TIME_UNTRUSTED;
  if (now_us < command->created_time_us) return ZS_COMMAND_STATUS_NOT_YET_VALID;
  if (now_us >= command->expires_time_us) return ZS_COMMAND_STATUS_EXPIRED;
  if (!expect_uint(reader, 6u) || !read_uint(reader, &value) ||
      value != ZS_COMMAND_REQUEST_AUDIO) return ZS_COMMAND_STATUS_UNSUPPORTED;
  command->code = (zs_command_code_t)value;
  if (!expect_uint(reader, 7u) || !read_audio_payload(reader, &command->audio) ||
      !expect_uint(reader, 8u) ||
      !read_bytes(reader, command->key_id, ZS_COMMAND_KEY_ID_BYTES))
    return ZS_COMMAND_STATUS_INVALID_CBOR;
  *signed_size = reader->offset;
  if (!expect_uint(reader, 9u) ||
      !read_bytes(reader, signature, ZS_COMMAND_SIGNATURE_BYTES) ||
      reader->offset != payload_size) return ZS_COMMAND_STATUS_INVALID_CBOR;
  return ZS_COMMAND_STATUS_OK;
}

zs_command_status_t zs_command_decode_verify(
    const uint8_t *payload, size_t payload_size, uint32_t expected_station_id,
    uint64_t now_us, bool time_trusted, zs_command_signature_verify_fn verify,
    void *verify_ctx, zs_command_dedup_lookup_fn dedup_lookup, void *dedup_ctx,
    uint8_t *workspace, size_t workspace_size, zs_command_t *command) {
  command_reader_t reader;
  zs_command_t decoded;
  uint8_t signature[ZS_COMMAND_SIGNATURE_BYTES];
  size_t signed_size = 0u;
  zs_command_status_t status;
  zs_command_dedup_state_t dedup;
  if (command) memset(command, 0, sizeof(*command));
  if (!payload || payload_size == 0u || payload_size > ZS_COMMAND_MAX_BYTES ||
      expected_station_id == 0u || !verify || !workspace || !command)
    return ZS_COMMAND_STATUS_INVALID_ARGUMENT;
  if (!dedup_lookup) return ZS_COMMAND_STATUS_DEDUP_REQUIRED;
  memset(&decoded, 0, sizeof(decoded));
  memset(signature, 0, sizeof(signature));
  reader.data = payload;
  reader.size = payload_size;
  reader.offset = 0u;
  status = decode_envelope(payload_size, expected_station_id, now_us,
                           time_trusted, &reader, &decoded, signature, &signed_size);
  if (status != ZS_COMMAND_STATUS_OK) return status;
  if (signed_size == 0u || workspace_size < signed_size)
    return ZS_COMMAND_STATUS_WORKSPACE_TOO_SMALL;
  workspace[0] = 0xa9u;
  memcpy(&workspace[1], &payload[1], signed_size - 1u);
  if (!verify(verify_ctx, decoded.key_id, workspace, signed_size, signature)) {
    memset(workspace, 0, signed_size);
    return ZS_COMMAND_STATUS_SIGNATURE_REJECTED;
  }
  memset(workspace, 0, signed_size);
  dedup = dedup_lookup(dedup_ctx, decoded.command_id);
  if (dedup == ZS_COMMAND_DEDUP_ERROR) return ZS_COMMAND_STATUS_DEDUP_STORAGE_ERROR;
  *command = decoded;
  return dedup == ZS_COMMAND_DEDUP_SEEN ? ZS_COMMAND_STATUS_DUPLICATE
                                        : ZS_COMMAND_STATUS_OK;
}

size_t zs_command_encode_ack(
    uint32_t station_id, const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    zs_command_ack_result_t result, uint64_t completed_time_us,
    uint16_t detail_code, uint8_t *output, size_t output_size) {
  zs_cbor_t cbor;
  if (station_id == 0u || !command_id ||
      (unsigned)result > (unsigned)ZS_COMMAND_ACK_EXPIRED ||
      !output || output_size == 0u) return 0u;
  zs_cbor_init(&cbor, output, output_size);
  zs_cbor_map(&cbor, 7u);
  zs_cbor_uint(&cbor, 0u); zs_cbor_uint(&cbor, ZS_COMMAND_SCHEMA_VERSION);
  zs_cbor_uint(&cbor, 1u); zs_cbor_uint(&cbor, ZS_COMMAND_ACK_MESSAGE_TYPE);
  zs_cbor_uint(&cbor, 2u); zs_cbor_uint(&cbor, station_id);
  zs_cbor_uint(&cbor, 3u); zs_cbor_bytes(&cbor, command_id, ZS_COMMAND_UUID_BYTES);
  zs_cbor_uint(&cbor, 4u); zs_cbor_uint(&cbor, (uint64_t)result);
  zs_cbor_uint(&cbor, 5u); zs_cbor_uint(&cbor, completed_time_us);
  zs_cbor_uint(&cbor, 6u); zs_cbor_uint(&cbor, detail_code);
  return cbor.error ? 0u : cbor.len;
}

const char *zs_command_status_name(zs_command_status_t status) {
  static const char *const names[] = {
      "OK", "INVALID_ARGUMENT", "INVALID_CBOR", "UNSUPPORTED",
      "STATION_MISMATCH", "TIME_UNTRUSTED", "NOT_YET_VALID", "EXPIRED",
      "INVALID_TTL", "SIGNATURE_REJECTED", "DEDUP_REQUIRED",
      "DEDUP_STORAGE_ERROR", "DUPLICATE", "WORKSPACE_TOO_SMALL"};
  return (unsigned)status <= (unsigned)ZS_COMMAND_STATUS_WORKSPACE_TOO_SMALL
             ? names[status]
             : "?";
}

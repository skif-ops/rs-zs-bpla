#include "zs_bg95_mqtt_binary.h"

#include <limits.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  const uint8_t *data;
  size_t size;
  size_t offset;
} byte_reader_t;

bool zs_bg95_mqtt_uart_write_all(zs_bg95_t *modem,
                                 const uint8_t *data,
                                 size_t size) {
  int result;
  if (!modem || !modem->io.uart_write || (!data && size != 0u) ||
      size > (size_t)INT_MAX)
    return false;
  result = modem->io.uart_write(
      modem->io.ctx, modem->uart_channel, data, size);
  return result == 0 || result == (int)size;
}

bool zs_bg95_mqtt_topic_is_at_safe(const uint8_t *topic, size_t size,
                                   size_t maximum_size) {
  if (!topic || size == 0u || maximum_size == 0u || size > maximum_size)
    return false;
  for (size_t i = 0u; i < size; ++i) {
    const uint8_t value = topic[i];
    const bool alpha = (value >= (uint8_t)'A' && value <= (uint8_t)'Z') ||
                       (value >= (uint8_t)'a' && value <= (uint8_t)'z');
    const bool digit = value >= (uint8_t)'0' && value <= (uint8_t)'9';
    if (!alpha && !digit && value != (uint8_t)'/' &&
        value != (uint8_t)'_' && value != (uint8_t)'-')
      return false;
  }
  return true;
}

void zs_bg95_mqtt_invalidate(zs_bg95_t *modem) {
  if (!modem) return;
  modem->command_pending = false;
  modem->mqtt_open = false;
  modem->mqtt_connected = false;
  modem->mqtt_receive_length_enabled = false;
  modem->network_settings.valid = false;
  modem->state = ZS_BG95_ERROR;
}

bool zs_bg95_mqtt_parse_subscribe_result(const char *line,
                                         unsigned *client,
                                         unsigned *message_id,
                                         unsigned *result,
                                         unsigned *granted_qos) {
  int consumed = 0;
  if (!line || !client || !message_id || !result || !granted_qos ||
      sscanf(line, "+QMTSUB: %u,%u,%u,%u%n", client, message_id,
             result, granted_qos, &consumed) != 4)
    return false;
  while (line[consumed] == ' ' || line[consumed] == '\t') ++consumed;
  return line[consumed] == '\0' && *client <= 5u &&
         *message_id <= UINT16_MAX && *result <= 2u && *granted_qos <= 2u;
}

bool zs_bg95_mqtt_parse_publish_result(const char *line,
                                       unsigned *client,
                                       unsigned *message_id,
                                       unsigned *result) {
  int consumed = 0;
  unsigned retry_count = 0u;
  if (!line || !client || !message_id || !result ||
      sscanf(line, "+QMTPUB: %u,%u,%u,%u%n", client, message_id, result,
             &retry_count, &consumed) != 4) {
    consumed = 0;
    if (!line || !client || !message_id || !result ||
        sscanf(line, "+QMTPUB: %u,%u,%u%n", client, message_id, result,
               &consumed) != 3)
      return false;
  } else if (*result != 1u) {
    return false;
  }
  while (line[consumed] == ' ' || line[consumed] == '\t') ++consumed;
  return line[consumed] == '\0' && *client <= 5u &&
         *message_id <= UINT16_MAX && *result <= 2u;
}

static bool reader_take(byte_reader_t *reader, uint8_t expected) {
  if (!reader || reader->offset >= reader->size ||
      reader->data[reader->offset] != expected)
    return false;
  ++reader->offset;
  return true;
}

static bool reader_take_literal(byte_reader_t *reader,
                                const uint8_t *literal,
                                size_t size) {
  if (!reader || !literal || reader->offset > reader->size ||
      size > reader->size - reader->offset ||
      memcmp(&reader->data[reader->offset], literal, size) != 0)
    return false;
  reader->offset += size;
  return true;
}

static bool reader_unsigned(byte_reader_t *reader, unsigned *value) {
  unsigned parsed = 0u;
  size_t digits = 0u;
  if (!reader || !value) return false;
  while (reader->offset < reader->size) {
    const uint8_t byte = reader->data[reader->offset];
    unsigned digit;
    if (byte < (uint8_t)'0' || byte > (uint8_t)'9') break;
    digit = (unsigned)(byte - (uint8_t)'0');
    if (parsed > (UINT_MAX - digit) / 10u) return false;
    parsed = parsed * 10u + digit;
    ++reader->offset;
    ++digits;
  }
  if (digits == 0u) return false;
  *value = parsed;
  return true;
}

zs_bg95_mqtt_receive_parse_result_t zs_bg95_mqtt_parse_receive_frame(
    const uint8_t *frame,
    size_t frame_size,
    zs_bg95_mqtt_receive_frame_t *received) {
  static const uint8_t marker[] = "+QMTRECV:";
  static const uint8_t prefix[] = "+QMTRECV: ";
  byte_reader_t reader = {frame, frame_size, 0u};
  unsigned payload_size;
  size_t topic_start;
  if (!frame || !received || frame_size == 0u)
    return ZS_BG95_MQTT_RECEIVE_MALFORMED;
  memset(received, 0, sizeof(*received));
  if (frame_size < sizeof(marker) - 1u ||
      memcmp(frame, marker, sizeof(marker) - 1u) != 0)
    return ZS_BG95_MQTT_RECEIVE_NOT_FRAME;
  if (!reader_take_literal(&reader, prefix, sizeof(prefix) - 1u) ||
      !reader_unsigned(&reader, &received->client) ||
      !reader_take(&reader, (uint8_t)',') ||
      !reader_unsigned(&reader, &received->message_id) ||
      !reader_take(&reader, (uint8_t)',') ||
      !reader_take(&reader, (uint8_t)'"'))
    return ZS_BG95_MQTT_RECEIVE_MALFORMED;
  if (received->client > 5u || received->message_id > UINT16_MAX)
    return ZS_BG95_MQTT_RECEIVE_MALFORMED;
  topic_start = reader.offset;
  while (reader.offset < reader.size &&
         reader.data[reader.offset] != (uint8_t)'"')
    ++reader.offset;
  if (reader.offset == reader.size)
    return ZS_BG95_MQTT_RECEIVE_MALFORMED;
  received->topic = &reader.data[topic_start];
  received->topic_size = reader.offset - topic_start;
  if (!reader_take(&reader, (uint8_t)'"') ||
      !reader_take(&reader, (uint8_t)',') ||
      !reader_unsigned(&reader, &payload_size) ||
      !reader_take(&reader, (uint8_t)',') ||
      !reader_take(&reader, (uint8_t)'"') ||
      (size_t)payload_size > reader.size - reader.offset)
    return ZS_BG95_MQTT_RECEIVE_MALFORMED;
  received->payload = &reader.data[reader.offset];
  received->payload_size = (size_t)payload_size;
  reader.offset += received->payload_size;
  if (!reader_take(&reader, (uint8_t)'"'))
    return ZS_BG95_MQTT_RECEIVE_MALFORMED;
  if (reader.offset == reader.size)
    return ZS_BG95_MQTT_RECEIVE_FRAME_OK;
  if (reader.size - reader.offset == 2u &&
      reader.data[reader.offset] == (uint8_t)'\r' &&
      reader.data[reader.offset + 1u] == (uint8_t)'\n')
    return ZS_BG95_MQTT_RECEIVE_FRAME_OK;
  return ZS_BG95_MQTT_RECEIVE_MALFORMED;
}

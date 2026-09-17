#include "zs_bg95_event_uplink.h"
#include "zs_bg95_mqtt_binary.h"

#include <stdio.h>
#include <string.h>

#define BG95_QMTPUB_COMMAND_MAX_BYTES 160u
#define BG95_QMTPUB_MAX_PAYLOAD_BYTES 4096u

static void finish(zs_bg95_event_uplink_t *uplink,
                   zs_bg95_event_uplink_outcome_t outcome) {
  if (outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_TIMEOUT ||
      outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_IO_ERROR ||
      outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR)
    zs_bg95_mqtt_invalidate(uplink->modem);
  uplink->state = ZS_BG95_EVENT_UPLINK_IDLE;
  uplink->last_outcome = outcome;
  uplink->message_id = 0u;
  uplink->deadline_ms = 0u;
  memset(&uplink->publication, 0, sizeof(uplink->publication));
}

static bool append_bytes(uint8_t *command, size_t *used,
                         const uint8_t *data, size_t size) {
  if (!command || !used || (!data && size != 0u) ||
      *used > BG95_QMTPUB_COMMAND_MAX_BYTES ||
      size > BG95_QMTPUB_COMMAND_MAX_BYTES - *used)
    return false;
  memcpy(&command[*used], data, size);
  *used += size;
  return true;
}

static bool send_publish_command(zs_bg95_event_uplink_t *uplink) {
  static const uint8_t topic_close[] = {'"', ','};
  uint8_t command[BG95_QMTPUB_COMMAND_MAX_BYTES];
  char text[64];
  size_t used = 0u;
  int text_size;

  text_size = snprintf(text, sizeof(text), "AT+QMTPUB=%u,%u,1,0,\"",
                       uplink->modem->mqtt_client, uplink->message_id);
  if (text_size < 0 || (size_t)text_size >= sizeof(text) ||
      !append_bytes(command, &used, (const uint8_t *)text,
                    (size_t)text_size) ||
      !append_bytes(command, &used, uplink->publication.topic,
                    uplink->publication.topic_size) ||
      !append_bytes(command, &used, topic_close, sizeof(topic_close)))
    return false;

  text_size = snprintf(text, sizeof(text), "%zu\r\n",
                       uplink->publication.payload_size);
  return text_size >= 0 && (size_t)text_size < sizeof(text) &&
         append_bytes(command, &used, (const uint8_t *)text,
                      (size_t)text_size) &&
         zs_bg95_mqtt_uart_write_all(uplink->modem, command, used);
}

bool zs_bg95_event_uplink_init(zs_bg95_event_uplink_t *uplink,
                               zs_bg95_t *modem,
                               zs_mqtt_event_transport_t *transport) {
  if (!uplink) return false;
  memset(uplink, 0, sizeof(*uplink));
  if (!modem || !transport || !transport->outbox ||
      modem->mqtt_client > 5u || !modem->io.uart_write)
    return false;
  uplink->modem = modem;
  uplink->transport = transport;
  return true;
}

zs_bg95_event_uplink_start_result_t zs_bg95_event_uplink_start(
    zs_bg95_event_uplink_t *uplink,
    uint16_t message_id,
    uint32_t now_ms) {
  zs_mqtt_event_prepare_result_t prepared;
  if (!uplink || !uplink->modem || !uplink->transport || message_id == 0u)
    return ZS_BG95_EVENT_UPLINK_INVALID_ARGUMENT;
  if (uplink->state != ZS_BG95_EVENT_UPLINK_IDLE)
    return ZS_BG95_EVENT_UPLINK_BUSY;
  if (!zs_bg95_online(uplink->modem)) {
    uplink->last_outcome = ZS_BG95_EVENT_UPLINK_OUTCOME_OFFLINE;
    return ZS_BG95_EVENT_UPLINK_OFFLINE;
  }

  prepared = zs_mqtt_event_transport_prepare(
      uplink->transport, &uplink->publication);
  if (prepared == ZS_MQTT_EVENT_EMPTY)
    return ZS_BG95_EVENT_UPLINK_EMPTY;
  if (prepared == ZS_MQTT_EVENT_RETRY_EXHAUSTED)
    return ZS_BG95_EVENT_UPLINK_RETRY_EXHAUSTED;
  if (prepared == ZS_MQTT_EVENT_STORAGE_ERROR)
    return ZS_BG95_EVENT_UPLINK_STORAGE_ERROR;
  if (prepared == ZS_MQTT_EVENT_STATION_MISMATCH)
    return ZS_BG95_EVENT_UPLINK_STATION_MISMATCH;
  if (prepared != ZS_MQTT_EVENT_PUBLICATION_READY ||
      !zs_bg95_mqtt_topic_is_at_safe(
          uplink->publication.topic, uplink->publication.topic_size,
          ZS_MQTT_EVENT_TOPIC_MAX_BYTES) ||
      !uplink->publication.payload || uplink->publication.payload_size == 0u ||
      uplink->publication.payload_size > BG95_QMTPUB_MAX_PAYLOAD_BYTES ||
      uplink->publication.qos != 1u || uplink->publication.retained) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR);
    return ZS_BG95_EVENT_UPLINK_INVALID_ARGUMENT;
  }

  uplink->message_id = message_id;
  uplink->last_outcome = ZS_BG95_EVENT_UPLINK_OUTCOME_NONE;
  if (!send_publish_command(uplink)) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_IO_ERROR);
    return ZS_BG95_EVENT_UPLINK_IO_ERROR;
  }
  uplink->state = ZS_BG95_EVENT_UPLINK_WAIT_PROMPT;
  uplink->deadline_ms = now_ms + ZS_BG95_EVENT_UPLINK_TIMEOUT_MS;
  return ZS_BG95_EVENT_UPLINK_STARTED;
}

bool zs_bg95_event_uplink_on_prompt(zs_bg95_event_uplink_t *uplink,
                                    uint32_t now_ms) {
  if (!uplink || !uplink->modem ||
      uplink->state != ZS_BG95_EVENT_UPLINK_WAIT_PROMPT ||
      !uplink->publication.payload ||
      uplink->publication.payload_size == 0u)
    return false;
  if (!zs_bg95_online(uplink->modem)) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_OFFLINE);
    return false;
  }
  if ((int32_t)(now_ms - uplink->deadline_ms) >= 0) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_TIMEOUT);
    return false;
  }
  if (!zs_bg95_mqtt_uart_write_all(
          uplink->modem, uplink->publication.payload,
          uplink->publication.payload_size)) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_IO_ERROR);
    return false;
  }
  uplink->state = ZS_BG95_EVENT_UPLINK_WAIT_RESULT;
  uplink->deadline_ms = now_ms + ZS_BG95_EVENT_UPLINK_TIMEOUT_MS;
  return true;
}

bool zs_bg95_event_uplink_on_line(zs_bg95_event_uplink_t *uplink,
                                  const char *line) {
  unsigned client = 0u, message_id = 0u, result = 0u;
  if (!uplink || !line || uplink->state == ZS_BG95_EVENT_UPLINK_IDLE)
    return false;
  if (!uplink->modem || !zs_bg95_online(uplink->modem)) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_OFFLINE);
    return false;
  }
  if (strcmp(line, "OK") == 0) {
    if (uplink->state == ZS_BG95_EVENT_UPLINK_WAIT_RESULT) return true;
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR);
    return true;
  }
  if (strcmp(line, "ERROR") == 0) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_MODEM_REJECTED);
    return true;
  }
  if (!zs_bg95_mqtt_parse_publish_result(
          line, &client, &message_id, &result)) {
    if (strncmp(line, "+QMTPUB:", 8u) == 0) {
      finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR);
      return true;
    }
    return false;
  }
  if (uplink->state != ZS_BG95_EVENT_UPLINK_WAIT_RESULT ||
      client != uplink->modem->mqtt_client ||
      message_id != uplink->message_id) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR);
    return true;
  }
  finish(uplink, result == 0u
                     ? ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK
                     : ZS_BG95_EVENT_UPLINK_OUTCOME_MODEM_REJECTED);
  return true;
}

void zs_bg95_event_uplink_tick(zs_bg95_event_uplink_t *uplink,
                               uint32_t now_ms) {
  if (!uplink || uplink->state == ZS_BG95_EVENT_UPLINK_IDLE) return;
  if (!uplink->modem || !zs_bg95_online(uplink->modem)) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_OFFLINE);
  } else if ((int32_t)(now_ms - uplink->deadline_ms) >= 0) {
    finish(uplink, ZS_BG95_EVENT_UPLINK_OUTCOME_TIMEOUT);
  }
}

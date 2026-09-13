#include "zs_bg95_command_transport.h"
#include "zs_bg95_mqtt_binary.h"

#include <stdio.h>
#include <string.h>

#define BG95_COMMAND_AT_MAX_BYTES 160u

static bool append_bytes(uint8_t *command, size_t *used,
                         const uint8_t *data, size_t size) {
  if (!command || !used || (!data && size != 0u) ||
      *used > BG95_COMMAND_AT_MAX_BYTES ||
      size > BG95_COMMAND_AT_MAX_BYTES - *used)
    return false;
  memcpy(&command[*used], data, size);
  *used += size;
  return true;
}

static void clear_ack(zs_bg95_command_transport_t *binding) {
  if (!binding) return;
  memset(binding->ack_buffer, 0, sizeof(binding->ack_buffer));
  memset(&binding->ack_publication, 0, sizeof(binding->ack_publication));
  binding->ack_message_id = 0u;
}

static void finish_setup(zs_bg95_command_transport_t *binding,
                         zs_bg95_command_transport_outcome_t outcome) {
  if (outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT ||
      outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_IO_ERROR ||
      outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR)
    zs_bg95_mqtt_invalidate(binding->modem);
  binding->state = ZS_BG95_COMMAND_TRANSPORT_IDLE;
  binding->last_outcome = outcome;
  binding->subscribe_message_id = 0u;
  binding->deadline_ms = 0u;
  clear_ack(binding);
}

static void finish_publish(zs_bg95_command_transport_t *binding,
                           zs_bg95_command_transport_outcome_t outcome) {
  if (outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT ||
      outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_IO_ERROR ||
      outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR) {
    zs_bg95_mqtt_invalidate(binding->modem);
    binding->state = ZS_BG95_COMMAND_TRANSPORT_IDLE;
  } else if (outcome == ZS_BG95_COMMAND_TRANSPORT_OUTCOME_OFFLINE) {
    binding->state = ZS_BG95_COMMAND_TRANSPORT_IDLE;
  } else {
    binding->state = ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED;
  }
  binding->last_outcome = outcome;
  binding->deadline_ms = 0u;
  clear_ack(binding);
}

static bool send_subscription(zs_bg95_command_transport_t *binding) {
  static const uint8_t suffix[] = {'"', ',', '1', '\r', '\n'};
  uint8_t command[BG95_COMMAND_AT_MAX_BYTES];
  char prefix[48];
  size_t used = 0u;
  int prefix_size = snprintf(prefix, sizeof(prefix), "AT+QMTSUB=%u,%u,\"",
                             binding->modem->mqtt_client,
                             binding->subscribe_message_id);
  return prefix_size >= 0 && (size_t)prefix_size < sizeof(prefix) &&
         append_bytes(command, &used, (const uint8_t *)prefix,
                      (size_t)prefix_size) &&
         append_bytes(command, &used, binding->transport->down_topic,
                      binding->transport->down_topic_size) &&
         append_bytes(command, &used, suffix, sizeof(suffix)) &&
         zs_bg95_mqtt_uart_write_all(binding->modem, command, used);
}

static bool send_ack_command(zs_bg95_command_transport_t *binding) {
  static const uint8_t topic_close[] = {'"', ','};
  uint8_t command[BG95_COMMAND_AT_MAX_BYTES];
  char text[64];
  size_t used = 0u;
  int text_size = snprintf(text, sizeof(text), "AT+QMTPUB=%u,%u,1,0,\"",
                           binding->modem->mqtt_client,
                           binding->ack_message_id);
  if (text_size < 0 || (size_t)text_size >= sizeof(text) ||
      !append_bytes(command, &used, (const uint8_t *)text,
                    (size_t)text_size) ||
      !append_bytes(command, &used, binding->ack_publication.topic,
                    binding->ack_publication.topic_size) ||
      !append_bytes(command, &used, topic_close, sizeof(topic_close)))
    return false;
  text_size = snprintf(text, sizeof(text), "%zu\r\n",
                       binding->ack_publication.payload_size);
  return text_size >= 0 && (size_t)text_size < sizeof(text) &&
         append_bytes(command, &used, (const uint8_t *)text,
                      (size_t)text_size) &&
         zs_bg95_mqtt_uart_write_all(binding->modem, command, used);
}

bool zs_bg95_command_transport_init(
    zs_bg95_command_transport_t *binding,
    zs_bg95_t *modem,
    zs_mqtt_command_transport_t *transport,
    bool authenticated_server_only_nonretained_down_route) {
  if (!binding) return false;
  memset(binding, 0, sizeof(*binding));
  if (!modem || !transport || !transport->channel ||
      !authenticated_server_only_nonretained_down_route ||
      modem->mqtt_client > 5u || !modem->io.uart_write ||
      !zs_bg95_mqtt_topic_is_at_safe(
          transport->down_topic, transport->down_topic_size,
          ZS_MQTT_COMMAND_TOPIC_MAX_BYTES) ||
      !zs_bg95_mqtt_topic_is_at_safe(
          transport->ack_topic, transport->ack_topic_size,
          ZS_MQTT_COMMAND_TOPIC_MAX_BYTES))
    return false;
  binding->modem = modem;
  binding->transport = transport;
  binding->authenticated_server_only_nonretained_down_route = true;
  return true;
}

zs_bg95_command_subscribe_result_t zs_bg95_command_transport_subscribe(
    zs_bg95_command_transport_t *binding,
    uint16_t message_id,
    uint32_t now_ms) {
  if (!binding || !binding->modem || !binding->transport ||
      !binding->authenticated_server_only_nonretained_down_route ||
      message_id == 0u)
    return ZS_BG95_COMMAND_SUBSCRIBE_INVALID_ARGUMENT;
  if (binding->state == ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED)
    return ZS_BG95_COMMAND_ALREADY_SUBSCRIBED;
  if (binding->state != ZS_BG95_COMMAND_TRANSPORT_IDLE)
    return ZS_BG95_COMMAND_SUBSCRIBE_BUSY;
  if (!zs_bg95_online(binding->modem)) {
    binding->last_outcome = ZS_BG95_COMMAND_TRANSPORT_OUTCOME_OFFLINE;
    return ZS_BG95_COMMAND_SUBSCRIBE_OFFLINE;
  }
  if (!binding->modem->mqtt_receive_length_enabled) {
    finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR);
    return ZS_BG95_COMMAND_RECEIVE_MODE_REQUIRED;
  }
  binding->subscribe_message_id = message_id;
  if (!send_subscription(binding)) {
    finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_IO_ERROR);
    return ZS_BG95_COMMAND_SUBSCRIBE_IO_ERROR;
  }
  binding->state = ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT;
  binding->last_outcome = ZS_BG95_COMMAND_TRANSPORT_OUTCOME_NONE;
  binding->deadline_ms = now_ms + ZS_BG95_COMMAND_TRANSPORT_TIMEOUT_MS;
  return ZS_BG95_COMMAND_SUBSCRIBE_STARTED;
}

bool zs_bg95_command_transport_on_line(zs_bg95_command_transport_t *binding,
                                      const char *line,
                                      uint32_t now_ms) {
  unsigned client = 0u, message_id = 0u, result = 0u, qos = 0u;
  if (!binding || !line ||
      binding->state == ZS_BG95_COMMAND_TRANSPORT_IDLE ||
      binding->state == ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED)
    return false;
  if (!binding->modem || !zs_bg95_online(binding->modem)) {
    finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_OFFLINE);
    return false;
  }
  if ((int32_t)(now_ms - binding->deadline_ms) >= 0) {
    if (binding->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT)
      finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT);
    else
      finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT);
    return false;
  }
  if (strcmp(line, "ERROR") == 0) {
    if (binding->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT)
      finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_MODEM_REJECTED);
    else
      finish_publish(binding,
                     ZS_BG95_COMMAND_TRANSPORT_OUTCOME_MODEM_REJECTED);
    return true;
  }
  if (binding->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT) {
    if (strcmp(line, "OK") == 0) return true;
    if (!zs_bg95_mqtt_parse_subscribe_result(
            line, &client, &message_id, &result, &qos)) {
      if (strncmp(line, "+QMTSUB:", 8u) != 0) return false;
      finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR);
      return true;
    }
    if (client != binding->modem->mqtt_client ||
        message_id != binding->subscribe_message_id) {
      finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR);
      return true;
    }
    if (result != 0u || qos != ZS_MQTT_COMMAND_QOS) {
      finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_MODEM_REJECTED);
      return true;
    }
    binding->state = ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED;
    binding->last_outcome = ZS_BG95_COMMAND_TRANSPORT_OUTCOME_READY;
    binding->deadline_ms = 0u;
    return true;
  }
  if (strcmp(line, "OK") == 0) {
    if (binding->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_RESULT)
      return true;
    finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR);
    return true;
  }
  if (!zs_bg95_mqtt_parse_publish_result(
          line, &client, &message_id, &result)) {
    if (strncmp(line, "+QMTPUB:", 8u) != 0) return false;
    finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR);
    return true;
  }
  if (binding->state != ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_RESULT ||
      client != binding->modem->mqtt_client ||
      message_id != binding->ack_message_id) {
    finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR);
    return true;
  }
  finish_publish(binding,
                 result == 0u
                     ? ZS_BG95_COMMAND_TRANSPORT_OUTCOME_ACK_BROKER_ACK
                     : ZS_BG95_COMMAND_TRANSPORT_OUTCOME_MODEM_REJECTED);
  return true;
}

static zs_bg95_command_receive_result_t map_command_result(
    zs_mqtt_command_transport_result_t result) {
  switch (result) {
    case ZS_MQTT_COMMAND_REJECTED_TOPIC:
      return ZS_BG95_COMMAND_REJECTED_TOPIC;
    case ZS_MQTT_COMMAND_REJECTED_DELIVERY:
      return ZS_BG95_COMMAND_REJECTED_DELIVERY;
    case ZS_MQTT_COMMAND_REJECTED_COMMAND:
      return ZS_BG95_COMMAND_REJECTED_COMMAND;
    case ZS_MQTT_COMMAND_STORAGE_ERROR:
      return ZS_BG95_COMMAND_STORAGE_ERROR;
    case ZS_MQTT_COMMAND_EXECUTION_RETRY:
      return ZS_BG95_COMMAND_EXECUTION_RETRY;
    case ZS_MQTT_COMMAND_INVALID_ARGUMENT:
    default:
      return ZS_BG95_COMMAND_INVALID_ARGUMENT;
  }
}

zs_bg95_command_receive_result_t zs_bg95_command_transport_on_frame(
    zs_bg95_command_transport_t *binding,
    const uint8_t *frame,
    size_t frame_size,
    uint16_t ack_message_id,
    uint64_t now_us,
    bool time_trusted,
    uint32_t now_ms,
    zs_command_status_t *decode_status) {
  zs_bg95_mqtt_receive_frame_t received;
  zs_bg95_mqtt_receive_parse_result_t parsed;
  zs_mqtt_command_message_t message;
  zs_mqtt_command_transport_result_t handled;
  if (decode_status) *decode_status = ZS_COMMAND_STATUS_INVALID_ARGUMENT;
  if (!binding || !frame || frame_size == 0u || ack_message_id == 0u ||
      !decode_status || !binding->modem || !binding->transport ||
      !binding->authenticated_server_only_nonretained_down_route)
    return ZS_BG95_COMMAND_INVALID_ARGUMENT;
  if (binding->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_PROMPT ||
      binding->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_RESULT)
    return ZS_BG95_COMMAND_BUSY;
  if (binding->state != ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED)
    return ZS_BG95_COMMAND_NOT_SUBSCRIBED;
  if (!zs_bg95_online(binding->modem)) {
    finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_OFFLINE);
    return ZS_BG95_COMMAND_RECEIVE_OFFLINE;
  }
  parsed = zs_bg95_mqtt_parse_receive_frame(frame, frame_size, &received);
  if (parsed == ZS_BG95_MQTT_RECEIVE_NOT_FRAME)
    return ZS_BG95_COMMAND_NOT_COMMAND_FRAME;
  if (parsed != ZS_BG95_MQTT_RECEIVE_FRAME_OK) {
    finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR);
    return ZS_BG95_COMMAND_FRAMING_ERROR;
  }
  if (received.client != binding->modem->mqtt_client)
    return ZS_BG95_COMMAND_CLIENT_MISMATCH;
  message.topic = received.topic;
  message.topic_size = received.topic_size;
  message.payload = received.payload;
  message.payload_size = received.payload_size;
  message.qos = received.message_id == 0u ? 0u : ZS_MQTT_COMMAND_QOS;
  /* Retain is not present in +QMTRECV; false is the asserted broker contract. */
  message.retained = false;
  handled = zs_mqtt_command_transport_handle(
      binding->transport, &message, now_us, time_trusted,
      binding->ack_buffer, sizeof(binding->ack_buffer),
      &binding->ack_publication, decode_status);
  if (handled != ZS_MQTT_COMMAND_ACK_READY) {
    clear_ack(binding);
    return map_command_result(handled);
  }
  if (!binding->ack_publication.topic ||
      !binding->ack_publication.payload ||
      binding->ack_publication.payload_size == 0u ||
      binding->ack_publication.payload_size > sizeof(binding->ack_buffer) ||
      binding->ack_publication.qos != ZS_MQTT_COMMAND_QOS ||
      binding->ack_publication.retained ||
      !zs_bg95_mqtt_topic_is_at_safe(
          binding->ack_publication.topic,
          binding->ack_publication.topic_size,
          ZS_MQTT_COMMAND_TOPIC_MAX_BYTES)) {
    finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR);
    return ZS_BG95_COMMAND_INVALID_ARGUMENT;
  }
  binding->ack_message_id = ack_message_id;
  if (!send_ack_command(binding)) {
    finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_IO_ERROR);
    return ZS_BG95_COMMAND_ACK_IO_ERROR;
  }
  binding->state = ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_PROMPT;
  binding->last_outcome = ZS_BG95_COMMAND_TRANSPORT_OUTCOME_NONE;
  binding->deadline_ms = now_ms + ZS_BG95_COMMAND_TRANSPORT_TIMEOUT_MS;
  return ZS_BG95_COMMAND_ACK_PUBLISH_STARTED;
}

bool zs_bg95_command_transport_on_prompt(zs_bg95_command_transport_t *binding,
                                        uint32_t now_ms) {
  if (!binding || !binding->modem ||
      binding->state != ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_PROMPT ||
      !binding->ack_publication.payload ||
      binding->ack_publication.payload_size == 0u)
    return false;
  if (!zs_bg95_online(binding->modem)) {
    finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_OFFLINE);
    return false;
  }
  if ((int32_t)(now_ms - binding->deadline_ms) >= 0) {
    finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT);
    return false;
  }
  if (!zs_bg95_mqtt_uart_write_all(
          binding->modem, binding->ack_publication.payload,
          binding->ack_publication.payload_size)) {
    finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_IO_ERROR);
    return false;
  }
  binding->state = ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_RESULT;
  binding->deadline_ms = now_ms + ZS_BG95_COMMAND_TRANSPORT_TIMEOUT_MS;
  return true;
}

void zs_bg95_command_transport_tick(zs_bg95_command_transport_t *binding,
                                    uint32_t now_ms) {
  if (!binding || binding->state == ZS_BG95_COMMAND_TRANSPORT_IDLE) return;
  if (!binding->modem || !zs_bg95_online(binding->modem)) {
    if (binding->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT ||
        binding->state == ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED)
      finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_OFFLINE);
    else
      finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_OFFLINE);
  } else if (binding->state != ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED &&
             (int32_t)(now_ms - binding->deadline_ms) >= 0) {
    if (binding->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT)
      finish_setup(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT);
    else
      finish_publish(binding, ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT);
  }
}

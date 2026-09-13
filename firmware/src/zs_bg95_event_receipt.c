#include "zs_bg95_event_receipt.h"
#include "zs_bg95_mqtt_binary.h"

#include <stdio.h>
#include <string.h>

#define BG95_RECEIPT_COMMAND_MAX_BYTES 160u

static void finish_setup(zs_bg95_event_receipt_t *receiver,
                         zs_bg95_event_receipt_outcome_t outcome) {
  if (outcome == ZS_BG95_EVENT_RECEIPT_OUTCOME_TIMEOUT ||
      outcome == ZS_BG95_EVENT_RECEIPT_OUTCOME_IO_ERROR ||
      outcome == ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR)
    zs_bg95_mqtt_invalidate(receiver->modem);
  receiver->state = ZS_BG95_EVENT_RECEIPT_IDLE;
  receiver->last_outcome = outcome;
  receiver->subscribe_message_id = 0u;
  receiver->deadline_ms = 0u;
}

static bool append_bytes(uint8_t *command, size_t *used,
                         const uint8_t *data, size_t size) {
  if (!command || !used || (!data && size != 0u) ||
      *used > BG95_RECEIPT_COMMAND_MAX_BYTES ||
      size > BG95_RECEIPT_COMMAND_MAX_BYTES - *used)
    return false;
  memcpy(&command[*used], data, size);
  *used += size;
  return true;
}

static bool send_subscription(zs_bg95_event_receipt_t *receiver) {
  static const uint8_t suffix[] = {'"', ',', '1', '\r', '\n'};
  uint8_t command[BG95_RECEIPT_COMMAND_MAX_BYTES];
  char prefix[48];
  size_t used = 0u;
  int prefix_size = snprintf(prefix, sizeof(prefix), "AT+QMTSUB=%u,%u,\"",
                             receiver->modem->mqtt_client,
                             receiver->subscribe_message_id);
  return prefix_size >= 0 && (size_t)prefix_size < sizeof(prefix) &&
         append_bytes(command, &used, (const uint8_t *)prefix,
                      (size_t)prefix_size) &&
         append_bytes(command, &used, receiver->transport->receipt.topic,
                      receiver->transport->receipt.topic_size) &&
         append_bytes(command, &used, suffix, sizeof(suffix)) &&
         zs_bg95_mqtt_uart_write_all(receiver->modem, command, used);
}

bool zs_bg95_event_receipt_init(
    zs_bg95_event_receipt_t *receiver,
    zs_bg95_t *modem,
    zs_mqtt_event_transport_t *transport,
    bool authenticated_server_only_nonretained_route) {
  if (!receiver) return false;
  memset(receiver, 0, sizeof(*receiver));
  if (!modem || !transport || !transport->outbox ||
      !authenticated_server_only_nonretained_route ||
      modem->mqtt_client > 5u || !modem->io.uart_write ||
      !zs_bg95_mqtt_topic_is_at_safe(
          transport->receipt.topic, transport->receipt.topic_size,
          ZS_MQTT_EVENT_TOPIC_MAX_BYTES))
    return false;
  receiver->modem = modem;
  receiver->transport = transport;
  receiver->authenticated_server_only_nonretained_route = true;
  return true;
}

zs_bg95_event_receipt_subscribe_result_t zs_bg95_event_receipt_subscribe(
    zs_bg95_event_receipt_t *receiver,
    uint16_t message_id,
    uint32_t now_ms) {
  if (!receiver || !receiver->modem || !receiver->transport ||
      !receiver->authenticated_server_only_nonretained_route ||
      message_id == 0u)
    return ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_INVALID_ARGUMENT;
  if (receiver->state == ZS_BG95_EVENT_RECEIPT_SUBSCRIBED)
    return ZS_BG95_EVENT_RECEIPT_ALREADY_SUBSCRIBED;
  if (receiver->state != ZS_BG95_EVENT_RECEIPT_IDLE)
    return ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_BUSY;
  if (!zs_bg95_online(receiver->modem)) {
    receiver->last_outcome = ZS_BG95_EVENT_RECEIPT_OUTCOME_OFFLINE;
    return ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_OFFLINE;
  }
  if (!receiver->modem->mqtt_receive_length_enabled) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR);
    return ZS_BG95_EVENT_RECEIPT_RECEIVE_MODE_REQUIRED;
  }
  receiver->subscribe_message_id = message_id;
  if (!send_subscription(receiver)) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_IO_ERROR);
    return ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_IO_ERROR;
  }
  receiver->state = ZS_BG95_EVENT_RECEIPT_WAIT_SUBSCRIBE_RESULT;
  receiver->last_outcome = ZS_BG95_EVENT_RECEIPT_OUTCOME_NONE;
  receiver->deadline_ms = now_ms + ZS_BG95_EVENT_RECEIPT_TIMEOUT_MS;
  return ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_STARTED;
}

bool zs_bg95_event_receipt_on_line(zs_bg95_event_receipt_t *receiver,
                                   const char *line,
                                   uint32_t now_ms) {
  unsigned client = 0u, message_id = 0u, result = 0u, granted_qos = 0u;
  if (!receiver || !line ||
      receiver->state == ZS_BG95_EVENT_RECEIPT_IDLE ||
      receiver->state == ZS_BG95_EVENT_RECEIPT_SUBSCRIBED)
    return false;
  if (!receiver->modem || !zs_bg95_online(receiver->modem)) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_OFFLINE);
    return false;
  }
  if ((int32_t)(now_ms - receiver->deadline_ms) >= 0) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_TIMEOUT);
    return false;
  }
  if (strcmp(line, "ERROR") == 0) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_MODEM_REJECTED);
    return true;
  }
  if (strcmp(line, "OK") == 0) {
    return true;
  }
  if (!zs_bg95_mqtt_parse_subscribe_result(
          line, &client, &message_id, &result, &granted_qos)) {
    if (strncmp(line, "+QMTSUB:", 8u) == 0) {
      finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR);
      return true;
    }
    return false;
  }
  if (receiver->state != ZS_BG95_EVENT_RECEIPT_WAIT_SUBSCRIBE_RESULT ||
      client != receiver->modem->mqtt_client ||
      message_id != receiver->subscribe_message_id) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR);
    return true;
  }
  if (result != 0u || granted_qos != ZS_MQTT_EVENT_QOS) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_MODEM_REJECTED);
    return true;
  }
  receiver->state = ZS_BG95_EVENT_RECEIPT_SUBSCRIBED;
  receiver->last_outcome = ZS_BG95_EVENT_RECEIPT_OUTCOME_READY;
  receiver->deadline_ms = 0u;
  return true;
}

static zs_bg95_event_receipt_receive_result_t map_receipt_result(
    zs_event_receipt_result_t result) {
  switch (result) {
    case ZS_EVENT_RECEIPT_APPLIED:
      return ZS_BG95_EVENT_RECEIPT_APPLIED;
    case ZS_EVENT_RECEIPT_ALREADY_APPLIED:
      return ZS_BG95_EVENT_RECEIPT_ALREADY_APPLIED;
    case ZS_EVENT_RECEIPT_REJECTED_TOPIC:
      return ZS_BG95_EVENT_RECEIPT_REJECTED_TOPIC;
    case ZS_EVENT_RECEIPT_REJECTED_DELIVERY:
      return ZS_BG95_EVENT_RECEIPT_REJECTED_DELIVERY;
    case ZS_EVENT_RECEIPT_REJECTED_RECEIPT:
      return ZS_BG95_EVENT_RECEIPT_REJECTED_RECEIPT;
    case ZS_EVENT_RECEIPT_STORAGE_ERROR:
      return ZS_BG95_EVENT_RECEIPT_STORAGE_ERROR;
    case ZS_EVENT_RECEIPT_INVALID_ARGUMENT:
    default:
      return ZS_BG95_EVENT_RECEIPT_INVALID_ARGUMENT;
  }
}

zs_bg95_event_receipt_receive_result_t zs_bg95_event_receipt_on_frame(
    zs_bg95_event_receipt_t *receiver,
    const uint8_t *frame,
    size_t frame_size,
    zs_event_receipt_status_t *decode_status) {
  zs_bg95_mqtt_receive_frame_t received;
  zs_bg95_mqtt_receive_parse_result_t parsed;
  zs_mqtt_event_message_t message;
  zs_event_receipt_result_t result;
  if (decode_status) *decode_status = ZS_EVENT_RECEIPT_STATUS_INVALID_ARGUMENT;
  if (!receiver || !frame || frame_size == 0u || !decode_status ||
      !receiver->modem || !receiver->transport ||
      !receiver->authenticated_server_only_nonretained_route)
    return ZS_BG95_EVENT_RECEIPT_INVALID_ARGUMENT;
  if (receiver->state != ZS_BG95_EVENT_RECEIPT_SUBSCRIBED)
    return ZS_BG95_EVENT_RECEIPT_NOT_SUBSCRIBED;
  if (!zs_bg95_online(receiver->modem)) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_OFFLINE);
    return ZS_BG95_EVENT_RECEIPT_RECEIVE_OFFLINE;
  }
  parsed = zs_bg95_mqtt_parse_receive_frame(frame, frame_size, &received);
  if (parsed == ZS_BG95_MQTT_RECEIVE_NOT_FRAME)
    return ZS_BG95_EVENT_RECEIPT_NOT_RECEIPT_FRAME;
  if (parsed != ZS_BG95_MQTT_RECEIVE_FRAME_OK) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR);
    return ZS_BG95_EVENT_RECEIPT_FRAMING_ERROR;
  }
  if (received.client != receiver->modem->mqtt_client)
    return ZS_BG95_EVENT_RECEIPT_CLIENT_MISMATCH;

  message.topic = received.topic;
  message.topic_size = received.topic_size;
  message.payload = received.payload;
  message.payload_size = received.payload_size;
  message.qos = received.message_id == 0u ? 0u : ZS_MQTT_EVENT_QOS;
  /* Retain is not present in +QMTRECV; false is the asserted broker contract. */
  message.retained = false;
  result = zs_mqtt_event_transport_handle_receipt(
      receiver->transport, &message, decode_status);
  return map_receipt_result(result);
}

void zs_bg95_event_receipt_tick(zs_bg95_event_receipt_t *receiver,
                                uint32_t now_ms) {
  if (!receiver || receiver->state == ZS_BG95_EVENT_RECEIPT_IDLE) return;
  if (!receiver->modem || !zs_bg95_online(receiver->modem)) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_OFFLINE);
  } else if (receiver->state != ZS_BG95_EVENT_RECEIPT_SUBSCRIBED &&
             (int32_t)(now_ms - receiver->deadline_ms) >= 0) {
    finish_setup(receiver, ZS_BG95_EVENT_RECEIPT_OUTCOME_TIMEOUT);
  }
}

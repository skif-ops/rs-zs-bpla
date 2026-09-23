#include "zs_bg95_mqtt_session.h"
#include "zs_bg95_mqtt_binary.h"

#include <limits.h>
#include <string.h>

typedef enum {
  FRAME_LENGTH_NEED_MORE = 0,
  FRAME_LENGTH_READY,
  FRAME_LENGTH_MALFORMED
} frame_length_result_t;

static uint16_t take_message_id(zs_bg95_mqtt_session_t *session) {
  uint16_t result = session->next_message_id;
  ++session->next_message_id;
  if (session->next_message_id == 0u) session->next_message_id = 1u;
  return result;
}

static bool topic_equal(const uint8_t *left, size_t left_size,
                        const uint8_t *right, size_t right_size) {
  return left && right && left_size == right_size &&
         memcmp(left, right, left_size) == 0;
}

static void consume(zs_bg95_mqtt_session_t *session, size_t size) {
  if (!session || size > session->rx_size) return;
  memmove(session->rx, &session->rx[size], session->rx_size - size);
  session->rx_size -= size;
}

static void protocol_error(zs_bg95_mqtt_session_t *session) {
  if (!session) return;
  zs_bg95_mqtt_invalidate(session->modem);
  session->owner = ZS_BG95_MQTT_OWNER_NONE;
  session->last_input_outcome = ZS_BG95_MQTT_INPUT_PROTOCOL_ERROR;
  session->rx_size = 0u;
  session->pending_command_size = 0u;
  session->skip_prompt_space = false;
}

static bool command_subscription_active(
    const zs_bg95_command_transport_t *command) {
  return command &&
         (command->state == ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED ||
          command->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_PROMPT ||
          command->state == ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_RESULT);
}

static void sync_owner(zs_bg95_mqtt_session_t *session) {
  if (!session) return;
  switch (session->owner) {
    case ZS_BG95_MQTT_OWNER_COMMAND_SUBSCRIBE:
      if (session->command->state !=
          ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT) {
        if (session->command->state != ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED &&
            zs_bg95_online(session->modem))
          zs_bg95_mqtt_invalidate(session->modem);
        session->owner = ZS_BG95_MQTT_OWNER_NONE;
      }
      break;
    case ZS_BG95_MQTT_OWNER_RECEIPT_SUBSCRIBE:
      if (session->receipt->state !=
          ZS_BG95_EVENT_RECEIPT_WAIT_SUBSCRIBE_RESULT) {
        if (session->receipt->state != ZS_BG95_EVENT_RECEIPT_SUBSCRIBED &&
            zs_bg95_online(session->modem))
          zs_bg95_mqtt_invalidate(session->modem);
        session->owner = ZS_BG95_MQTT_OWNER_NONE;
      }
      break;
    case ZS_BG95_MQTT_OWNER_EVENT_UPLINK:
      if (session->uplink->state == ZS_BG95_EVENT_UPLINK_IDLE)
        session->owner = ZS_BG95_MQTT_OWNER_NONE;
      break;
    case ZS_BG95_MQTT_OWNER_COMMAND_ACK:
      if (session->command->state !=
              ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_PROMPT &&
          session->command->state !=
              ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_RESULT)
        session->owner = ZS_BG95_MQTT_OWNER_NONE;
      break;
    case ZS_BG95_MQTT_OWNER_NONE:
    default:
      break;
  }
}

static void route_line(zs_bg95_mqtt_session_t *session, const char *line,
                       uint32_t now_ms) {
  bool handled = false;
  if (!session || !line) return;
  switch (session->owner) {
    case ZS_BG95_MQTT_OWNER_COMMAND_SUBSCRIBE:
    case ZS_BG95_MQTT_OWNER_COMMAND_ACK:
      handled = zs_bg95_command_transport_on_line(
          session->command, line, now_ms);
      break;
    case ZS_BG95_MQTT_OWNER_RECEIPT_SUBSCRIBE:
      handled = zs_bg95_event_receipt_on_line(
          session->receipt, line, now_ms);
      break;
    case ZS_BG95_MQTT_OWNER_EVENT_UPLINK:
      handled = zs_bg95_event_uplink_on_line(session->uplink, line);
      break;
    case ZS_BG95_MQTT_OWNER_NONE:
    default:
      break;
  }
  sync_owner(session);
  if (!handled) zs_bg95_on_line(session->modem, line, now_ms);
  session->last_input_outcome = ZS_BG95_MQTT_INPUT_LINE;
}

static bool route_prompt(zs_bg95_mqtt_session_t *session,
                         uint32_t now_ms) {
  bool handled = false;
  if (!session) return false;
  if (session->owner == ZS_BG95_MQTT_OWNER_EVENT_UPLINK)
    handled = zs_bg95_event_uplink_on_prompt(session->uplink, now_ms);
  else if (session->owner == ZS_BG95_MQTT_OWNER_COMMAND_ACK)
    handled = zs_bg95_command_transport_on_prompt(
        session->command, now_ms);
  if (!handled) {
    protocol_error(session);
    return false;
  }
  session->last_input_outcome = ZS_BG95_MQTT_INPUT_PROMPT;
  return true;
}

static void run_command(zs_bg95_mqtt_session_t *session,
                        const uint8_t *frame, size_t frame_size,
                        uint32_t now_ms, uint64_t now_us,
                        bool time_trusted) {
  session->last_command_result = zs_bg95_command_transport_on_frame(
      session->command, frame, frame_size, take_message_id(session), now_us,
      time_trusted, now_ms, &session->last_command_status);
  session->last_input_outcome = ZS_BG95_MQTT_INPUT_COMMAND;
  if (session->last_command_result ==
      ZS_BG95_COMMAND_ACK_PUBLISH_STARTED)
    session->owner = ZS_BG95_MQTT_OWNER_COMMAND_ACK;
}

static bool route_frame(zs_bg95_mqtt_session_t *session,
                        const uint8_t *frame, size_t frame_size,
                        uint32_t now_ms, uint64_t now_us,
                        bool time_trusted) {
  zs_bg95_mqtt_receive_frame_t received;
  zs_bg95_mqtt_receive_parse_result_t parsed;
  parsed = zs_bg95_mqtt_parse_receive_frame(frame, frame_size, &received);
  if (parsed != ZS_BG95_MQTT_RECEIVE_FRAME_OK) {
    protocol_error(session);
    return false;
  }
  if (topic_equal(received.topic, received.topic_size,
                  session->command->transport->down_topic,
                  session->command->transport->down_topic_size)) {
    if (!command_subscription_active(session->command)) {
      run_command(session, frame, frame_size, now_ms, now_us, time_trusted);
    } else if (session->owner == ZS_BG95_MQTT_OWNER_NONE) {
      run_command(session, frame, frame_size, now_ms, now_us, time_trusted);
    } else if (session->pending_command_size == 0u &&
               frame_size <= sizeof(session->pending_command)) {
      memcpy(session->pending_command, frame, frame_size);
      session->pending_command_size = frame_size;
      if (session->queued_command_count != UINT32_MAX)
        ++session->queued_command_count;
      session->last_input_outcome = ZS_BG95_MQTT_INPUT_COMMAND_QUEUED;
    } else {
      if (session->retry_required_count != UINT32_MAX)
        ++session->retry_required_count;
      session->last_input_outcome =
          ZS_BG95_MQTT_INPUT_COMMAND_RETRY_REQUIRED;
    }
    return true;
  }
  if (topic_equal(received.topic, received.topic_size,
                  session->receipt->transport->receipt.topic,
                  session->receipt->transport->receipt.topic_size)) {
    session->last_receipt_result = zs_bg95_event_receipt_on_frame(
        session->receipt, frame, frame_size, &session->last_receipt_status);
    session->last_input_outcome = ZS_BG95_MQTT_INPUT_RECEIPT;
    return true;
  }
  protocol_error(session);
  return false;
}

static frame_length_result_t parse_decimal(
    const uint8_t *data, size_t size, size_t *offset, size_t *value) {
  size_t parsed = 0u;
  size_t digits = 0u;
  if (!data || !offset || !value) return FRAME_LENGTH_MALFORMED;
  while (*offset < size) {
    uint8_t byte = data[*offset];
    size_t digit;
    if (byte < (uint8_t)'0' || byte > (uint8_t)'9') break;
    digit = (size_t)(byte - (uint8_t)'0');
    if (parsed > (SIZE_MAX - digit) / 10u)
      return FRAME_LENGTH_MALFORMED;
    parsed = parsed * 10u + digit;
    ++*offset;
    ++digits;
  }
  if (digits == 0u)
    return *offset == size
               ? FRAME_LENGTH_NEED_MORE
               : FRAME_LENGTH_MALFORMED;
  if (*offset == size) return FRAME_LENGTH_NEED_MORE;
  *value = parsed;
  return FRAME_LENGTH_READY;
}

static frame_length_result_t expect_byte(
    const uint8_t *data, size_t size, size_t *offset, uint8_t expected) {
  if (*offset == size) return FRAME_LENGTH_NEED_MORE;
  if (data[*offset] != expected) return FRAME_LENGTH_MALFORMED;
  ++*offset;
  return FRAME_LENGTH_READY;
}

static frame_length_result_t qmt_frame_length(
    const uint8_t *data, size_t size, size_t *frame_size) {
  static const uint8_t prefix[] = "+QMTRECV: ";
  frame_length_result_t result;
  size_t offset = sizeof(prefix) - 1u;
  size_t ignored;
  size_t payload_size;
  if (!data || !frame_size)
    return FRAME_LENGTH_MALFORMED;
  if (size < sizeof(prefix) - 1u)
    return memcmp(data, prefix, size) == 0
               ? FRAME_LENGTH_NEED_MORE
               : FRAME_LENGTH_MALFORMED;
  if (memcmp(data, prefix, sizeof(prefix) - 1u) != 0)
    return FRAME_LENGTH_MALFORMED;
  result = parse_decimal(data, size, &offset, &ignored);
  if (result != FRAME_LENGTH_READY) return result;
  result = expect_byte(data, size, &offset, (uint8_t)',');
  if (result != FRAME_LENGTH_READY) return result;
  result = parse_decimal(data, size, &offset, &ignored);
  if (result != FRAME_LENGTH_READY) return result;
  result = expect_byte(data, size, &offset, (uint8_t)',');
  if (result != FRAME_LENGTH_READY) return result;
  result = expect_byte(data, size, &offset, (uint8_t)'"');
  if (result != FRAME_LENGTH_READY) return result;
  while (offset < size && data[offset] != (uint8_t)'"') ++offset;
  if (offset == size) return FRAME_LENGTH_NEED_MORE;
  ++offset;
  result = expect_byte(data, size, &offset, (uint8_t)',');
  if (result != FRAME_LENGTH_READY) return result;
  result = parse_decimal(data, size, &offset, &payload_size);
  if (result != FRAME_LENGTH_READY) return result;
  result = expect_byte(data, size, &offset, (uint8_t)',');
  if (result != FRAME_LENGTH_READY) return result;
  result = expect_byte(data, size, &offset, (uint8_t)'"');
  if (result != FRAME_LENGTH_READY) return result;
  if (offset >= ZS_BG95_MQTT_SESSION_RX_BYTES ||
      payload_size > ZS_BG95_MQTT_SESSION_RX_BYTES - offset - 1u)
    return FRAME_LENGTH_MALFORMED;
  *frame_size = offset + payload_size + 1u;
  if (size < *frame_size) return FRAME_LENGTH_NEED_MORE;
  if (data[*frame_size - 1u] != (uint8_t)'"')
    return FRAME_LENGTH_MALFORMED;
  return FRAME_LENGTH_READY;
}

static bool process_rx(zs_bg95_mqtt_session_t *session,
                       uint32_t now_ms, uint64_t now_us,
                       bool time_trusted, bool *progressed) {
  static const uint8_t marker[] = "+QMTRECV:";
  size_t line_end;
  size_t frame_size;
  frame_length_result_t length_result;
  *progressed = false;
  if (session->rx_size >= 2u && session->rx[0] == (uint8_t)'\r' &&
      session->rx[1] == (uint8_t)'\n') {
    consume(session, 2u);
    *progressed = true;
    return true;
  }
  if (session->rx_size == 0u) return true;
  if (session->rx[0] == (uint8_t)'>') {
    consume(session, 1u);
    session->skip_prompt_space = true;
    *progressed = true;
    return route_prompt(session, now_ms);
  }
  if (session->rx_size < sizeof(marker) - 1u &&
      memcmp(session->rx, marker, session->rx_size) == 0)
    return true;
  if (session->rx_size >= sizeof(marker) - 1u &&
      memcmp(session->rx, marker, sizeof(marker) - 1u) == 0) {
    length_result = qmt_frame_length(
        session->rx, session->rx_size, &frame_size);
    if (length_result == FRAME_LENGTH_NEED_MORE) return true;
    if (length_result != FRAME_LENGTH_READY) {
      protocol_error(session);
      return false;
    }
    if (!route_frame(session, session->rx, frame_size,
                     now_ms, now_us, time_trusted))
      return false;
    consume(session, frame_size);
    *progressed = true;
    return true;
  }
  for (line_end = 0u; line_end + 1u < session->rx_size; ++line_end) {
    if (session->rx[line_end] == (uint8_t)'\0') {
      protocol_error(session);
      return false;
    }
    if (session->rx[line_end] == (uint8_t)'\r' &&
        session->rx[line_end + 1u] == (uint8_t)'\n') {
      session->rx[line_end] = (uint8_t)'\0';
      if (line_end != 0u)
        route_line(session, (const char *)session->rx, now_ms);
      consume(session, line_end + 2u);
      *progressed = true;
      return true;
    }
  }
  return true;
}

bool zs_bg95_mqtt_session_init(
    zs_bg95_mqtt_session_t *session,
    zs_bg95_t *modem,
    zs_bg95_command_transport_t *command,
    zs_bg95_event_receipt_t *receipt,
    zs_bg95_event_uplink_t *uplink,
    uint16_t first_message_id) {
  if (!session) return false;
  memset(session, 0, sizeof(*session));
  if (!modem || !command || !receipt || !uplink || first_message_id == 0u ||
      command->modem != modem || receipt->modem != modem ||
      uplink->modem != modem || !command->transport || !receipt->transport ||
      !uplink->transport || receipt->transport != uplink->transport)
    return false;
  session->modem = modem;
  session->command = command;
  session->receipt = receipt;
  session->uplink = uplink;
  session->next_message_id = first_message_id;
  session->last_command_result = ZS_BG95_COMMAND_INVALID_ARGUMENT;
  session->last_command_status = ZS_COMMAND_STATUS_INVALID_ARGUMENT;
  session->last_receipt_result = ZS_BG95_EVENT_RECEIPT_INVALID_ARGUMENT;
  session->last_receipt_status = ZS_EVENT_RECEIPT_STATUS_INVALID_ARGUMENT;
  return true;
}

bool zs_bg95_mqtt_session_ready(const zs_bg95_mqtt_session_t *session) {
  return session && session->modem && zs_bg95_online(session->modem) &&
         command_subscription_active(session->command) &&
         session->receipt &&
         session->receipt->state == ZS_BG95_EVENT_RECEIPT_SUBSCRIBED;
}

void zs_bg95_mqtt_session_tick(zs_bg95_mqtt_session_t *session,
                               uint32_t now_ms,
                               uint64_t now_us,
                               bool time_trusted) {
  zs_bg95_command_subscribe_result_t command_result;
  zs_bg95_event_receipt_subscribe_result_t receipt_result;
  if (!session || !session->modem || !session->command ||
      !session->receipt || !session->uplink)
    return;
  zs_bg95_command_transport_tick(session->command, now_ms);
  zs_bg95_event_receipt_tick(session->receipt, now_ms);
  zs_bg95_event_uplink_tick(session->uplink, now_ms);
  sync_owner(session);
  if (!zs_bg95_online(session->modem)) {
    session->owner = ZS_BG95_MQTT_OWNER_NONE;
    session->rx_size = 0u;
    session->pending_command_size = 0u;
    session->skip_prompt_space = false;
    return;
  }
  if (session->owner != ZS_BG95_MQTT_OWNER_NONE) return;
  if (!command_subscription_active(session->command)) {
    command_result = zs_bg95_command_transport_subscribe(
        session->command, take_message_id(session), now_ms);
    if (command_result == ZS_BG95_COMMAND_SUBSCRIBE_STARTED)
      session->owner = ZS_BG95_MQTT_OWNER_COMMAND_SUBSCRIBE;
    else if (command_result != ZS_BG95_COMMAND_ALREADY_SUBSCRIBED)
      zs_bg95_mqtt_invalidate(session->modem);
    return;
  }
  if (session->receipt->state != ZS_BG95_EVENT_RECEIPT_SUBSCRIBED) {
    receipt_result = zs_bg95_event_receipt_subscribe(
        session->receipt, take_message_id(session), now_ms);
    if (receipt_result == ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_STARTED)
      session->owner = ZS_BG95_MQTT_OWNER_RECEIPT_SUBSCRIBE;
    else if (receipt_result != ZS_BG95_EVENT_RECEIPT_ALREADY_SUBSCRIBED)
      zs_bg95_mqtt_invalidate(session->modem);
    return;
  }
  if (session->pending_command_size != 0u) {
    size_t pending_size = session->pending_command_size;
    session->pending_command_size = 0u;
    run_command(session, session->pending_command, pending_size,
                now_ms, now_us, time_trusted);
  }
}

bool zs_bg95_mqtt_session_feed_uart(zs_bg95_mqtt_session_t *session,
                                    const uint8_t *data,
                                    size_t size,
                                    uint32_t now_ms,
                                    uint64_t now_us,
                                    bool time_trusted) {
  bool progressed;
  if (!session || (!data && size != 0u) || !session->modem ||
      !session->command || !session->receipt || !session->uplink)
    return false;
  for (size_t i = 0u; i < size; ++i) {
    if (session->skip_prompt_space) {
      session->skip_prompt_space = false;
      if (data[i] == (uint8_t)' ') continue;
    }
    if (session->rx_size == sizeof(session->rx)) {
      protocol_error(session);
      return false;
    }
    session->rx[session->rx_size++] = data[i];
    do {
      if (!process_rx(session, now_ms, now_us, time_trusted, &progressed))
        return false;
    } while (progressed);
  }
  return true;
}

zs_bg95_event_uplink_start_result_t zs_bg95_mqtt_session_start_event(
    zs_bg95_mqtt_session_t *session,
    uint32_t now_ms) {
  zs_bg95_event_uplink_start_result_t result;
  if (!session || !session->uplink)
    return ZS_BG95_EVENT_UPLINK_INVALID_ARGUMENT;
  if (!zs_bg95_mqtt_session_ready(session) ||
      session->owner != ZS_BG95_MQTT_OWNER_NONE ||
      session->pending_command_size != 0u)
    return ZS_BG95_EVENT_UPLINK_BUSY;
  result = zs_bg95_event_uplink_start(
      session->uplink, take_message_id(session), now_ms);
  if (result == ZS_BG95_EVENT_UPLINK_STARTED)
    session->owner = ZS_BG95_MQTT_OWNER_EVENT_UPLINK;
  return result;
}

zs_bg95_event_uplink_start_result_t zs_bg95_mqtt_session_start_message(
    zs_bg95_mqtt_session_t *session,
    const zs_mqtt_event_message_t *message,
    uint32_t now_ms) {
  zs_bg95_event_uplink_start_result_t result;
  if (!session || !session->uplink || !message)
    return ZS_BG95_EVENT_UPLINK_INVALID_ARGUMENT;
  if (!zs_bg95_mqtt_session_ready(session) ||
      session->owner != ZS_BG95_MQTT_OWNER_NONE ||
      session->pending_command_size != 0u)
    return ZS_BG95_EVENT_UPLINK_BUSY;
  result = zs_bg95_event_uplink_start_message(
      session->uplink, take_message_id(session), message, now_ms);
  if (result == ZS_BG95_EVENT_UPLINK_STARTED)
    session->owner = ZS_BG95_MQTT_OWNER_EVENT_UPLINK;
  return result;
}

#include "zs_bg95_topic_subscription.h"
#include "zs_bg95_mqtt_binary.h"

#include <stdio.h>
#include <string.h>

#define SUBSCRIBE_COMMAND_MAX_BYTES 160u

static void finish(zs_bg95_topic_subscription_t *sub, bool ok, bool invalidate) {
  if (invalidate) zs_bg95_mqtt_invalidate(sub->modem);
  sub->state = ok ? ZS_BG95_TOPIC_SUBSCRIBED : ZS_BG95_TOPIC_IDLE;
  sub->failed = !ok;
  sub->subscribe_message_id = 0u;
  sub->deadline_ms = 0u;
}

bool zs_bg95_topic_subscription_init(zs_bg95_topic_subscription_t *sub, zs_bg95_t *modem, const uint8_t *topic,
                                     size_t topic_size, zs_bg95_topic_message_fn on_message, void *ctx) {
  if (!sub) return false;
  memset(sub, 0, sizeof(*sub));
  if (!modem || !topic || topic_size == 0u || topic_size > sizeof(sub->topic) || !on_message ||
      modem->mqtt_client > 5u || !modem->io.uart_write ||
      !zs_bg95_mqtt_topic_is_at_safe(topic, topic_size, ZS_MQTT_EVENT_TOPIC_MAX_BYTES))
    return false;
  sub->modem = modem;
  memcpy(sub->topic, topic, topic_size);
  sub->topic_size = topic_size;
  sub->on_message = on_message;
  sub->ctx = ctx;
  return true;
}

void zs_bg95_topic_subscription_want(zs_bg95_topic_subscription_t *sub, bool wanted) {
  if (!sub) return;
  if (wanted && !sub->wanted) sub->failed = false;      /* a fresh request retries a refused subscription */
  sub->wanted = wanted;
}

bool zs_bg95_topic_subscription_ready(const zs_bg95_topic_subscription_t *sub) {
  return sub && sub->modem && sub->state == ZS_BG95_TOPIC_SUBSCRIBED && zs_bg95_online(sub->modem);
}

bool zs_bg95_topic_subscription_start(zs_bg95_topic_subscription_t *sub, uint16_t message_id, uint32_t now_ms) {
  static const uint8_t suffix[] = {'"', ',', '1', '\r', '\n'};
  uint8_t command[SUBSCRIBE_COMMAND_MAX_BYTES];
  char prefix[48];
  int prefix_size;
  size_t used;
  if (!sub || !sub->modem || sub->state != ZS_BG95_TOPIC_IDLE || message_id == 0u ||
      !zs_bg95_online(sub->modem) || !sub->modem->mqtt_receive_length_enabled)
    return false;
  prefix_size = snprintf(prefix, sizeof(prefix), "AT+QMTSUB=%u,%u,\"", sub->modem->mqtt_client, message_id);
  if (prefix_size <= 0 || (size_t)prefix_size >= sizeof(prefix) ||
      (size_t)prefix_size + sub->topic_size + sizeof(suffix) > sizeof(command))
    return false;
  memcpy(command, prefix, (size_t)prefix_size);
  used = (size_t)prefix_size;
  memcpy(&command[used], sub->topic, sub->topic_size);
  used += sub->topic_size;
  memcpy(&command[used], suffix, sizeof(suffix));
  used += sizeof(suffix);
  sub->subscribe_message_id = message_id;
  if (!zs_bg95_mqtt_uart_write_all(sub->modem, command, used)) {
    finish(sub, false, true);
    return false;
  }
  sub->state = ZS_BG95_TOPIC_WAIT_SUBSCRIBE_RESULT;
  sub->deadline_ms = now_ms + ZS_BG95_TOPIC_SUBSCRIPTION_TIMEOUT_MS;
  return true;
}

bool zs_bg95_topic_subscription_on_line(zs_bg95_topic_subscription_t *sub, const char *line, uint32_t now_ms) {
  unsigned client = 0u, message_id = 0u, result = 0u, granted_qos = 0u;
  if (!sub || !line || sub->state != ZS_BG95_TOPIC_WAIT_SUBSCRIBE_RESULT) return false;
  if (!zs_bg95_online(sub->modem)) { finish(sub, false, false); return false; }
  if ((int32_t)(now_ms - sub->deadline_ms) >= 0) { finish(sub, false, true); return false; }
  if (strcmp(line, "ERROR") == 0) { finish(sub, false, false); return true; }
  if (strcmp(line, "OK") == 0) return true;
  if (!zs_bg95_mqtt_parse_subscribe_result(line, &client, &message_id, &result, &granted_qos)) {
    if (strncmp(line, "+QMTSUB:", 8u) == 0) { finish(sub, false, true); return true; }
    return false;
  }
  if (client != sub->modem->mqtt_client || message_id != sub->subscribe_message_id) { finish(sub, false, true); return true; }
  /* the server publishes the chunks at QoS 0 (addendum F §2); any granted QoS delivers them */
  finish(sub, result == 0u && granted_qos <= 1u, false);
  return true;
}

bool zs_bg95_topic_subscription_matches(const zs_bg95_topic_subscription_t *sub, const uint8_t *topic, size_t topic_size) {
  return sub && sub->modem && topic && topic_size == sub->topic_size && memcmp(topic, sub->topic, topic_size) == 0;
}

bool zs_bg95_topic_subscription_on_frame(zs_bg95_topic_subscription_t *sub, const uint8_t *frame, size_t frame_size) {
  zs_bg95_mqtt_receive_frame_t received;
  if (!sub || !frame ||
      zs_bg95_mqtt_parse_receive_frame(frame, frame_size, &received) != ZS_BG95_MQTT_RECEIVE_FRAME_OK ||
      !zs_bg95_topic_subscription_matches(sub, received.topic, received.topic_size))
    return false;
  if (received.client != sub->modem->mqtt_client) return true;      /* not our client: dropped */
  sub->messages++;
  sub->on_message(sub->ctx, received.payload, received.payload_size);
  return true;
}

void zs_bg95_topic_subscription_tick(zs_bg95_topic_subscription_t *sub, uint32_t now_ms) {
  if (!sub || !sub->modem || sub->state == ZS_BG95_TOPIC_IDLE) return;
  if (!zs_bg95_online(sub->modem)) {           /* a new connection subscribes again when still wanted */
    finish(sub, false, false);
    sub->failed = false;
  } else if (sub->state == ZS_BG95_TOPIC_WAIT_SUBSCRIBE_RESULT && (int32_t)(now_ms - sub->deadline_ms) >= 0) finish(sub, false, true);
}

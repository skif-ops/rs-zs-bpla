#ifndef ZS_BG95_TOPIC_SUBSCRIPTION_H
#define ZS_BG95_TOPIC_SUBSCRIPTION_H
/*
 * An extra server->station topic of the BG95 MQTT session (addendum F: the firmware chunks on
 * zs/v1/{tenant}/{station_id}/fw).  Attached to the session it is always routed (a late message after the
 * download finished is handed over and dropped by the owner, never a protocol error), but subscribed only on
 * request: AT+QMTSUB=<client>,<msgid>,"<topic>",1 when the session is otherwise idle.  The payload goes to the
 * owner's callback from the comms task, bounded by the session receive buffer.
 */
#include "zs_bg95.h"
#include "zs_mqtt_event_transport.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_BG95_TOPIC_SUBSCRIPTION_TIMEOUT_MS 120000u

typedef enum {
  ZS_BG95_TOPIC_IDLE = 0,
  ZS_BG95_TOPIC_WAIT_SUBSCRIBE_RESULT,
  ZS_BG95_TOPIC_SUBSCRIBED
} zs_bg95_topic_state_t;

typedef void (*zs_bg95_topic_message_fn)(void *ctx, const uint8_t *payload, size_t size);

typedef struct {
  zs_bg95_t *modem;
  uint8_t topic[ZS_MQTT_EVENT_TOPIC_MAX_BYTES];
  size_t topic_size;
  zs_bg95_topic_state_t state;
  bool wanted;                 /* the owner asked for the subscription */
  bool failed;                 /* the last attempt was refused or timed out */
  uint16_t subscribe_message_id;
  uint32_t deadline_ms;
  uint32_t messages;
  zs_bg95_topic_message_fn on_message;
  void *ctx;
} zs_bg95_topic_subscription_t;

bool zs_bg95_topic_subscription_init(zs_bg95_topic_subscription_t *sub, zs_bg95_t *modem, const uint8_t *topic,
                                     size_t topic_size, zs_bg95_topic_message_fn on_message, void *ctx);
/* The owner wants (or no longer needs) the subscription; the session subscribes when it is idle. */
void zs_bg95_topic_subscription_want(zs_bg95_topic_subscription_t *sub, bool wanted);
bool zs_bg95_topic_subscription_ready(const zs_bg95_topic_subscription_t *sub);
/* Session side. */
bool zs_bg95_topic_subscription_start(zs_bg95_topic_subscription_t *sub, uint16_t message_id, uint32_t now_ms);
bool zs_bg95_topic_subscription_on_line(zs_bg95_topic_subscription_t *sub, const char *line, uint32_t now_ms);
bool zs_bg95_topic_subscription_matches(const zs_bg95_topic_subscription_t *sub, const uint8_t *topic, size_t topic_size);
/* A complete +QMTRECV frame on our topic: hands the payload to the owner; false on a framing error. */
bool zs_bg95_topic_subscription_on_frame(zs_bg95_topic_subscription_t *sub, const uint8_t *frame, size_t frame_size);
void zs_bg95_topic_subscription_tick(zs_bg95_topic_subscription_t *sub, uint32_t now_ms);

#endif

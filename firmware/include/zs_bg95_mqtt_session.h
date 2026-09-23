#ifndef ZS_BG95_MQTT_SESSION_H
#define ZS_BG95_MQTT_SESSION_H

#include "zs_bg95_command_transport.h"
#include "zs_bg95_event_receipt.h"
#include "zs_bg95_event_uplink.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_BG95_MQTT_SESSION_RX_BYTES 2304u

typedef enum {
  ZS_BG95_MQTT_OWNER_NONE = 0,
  ZS_BG95_MQTT_OWNER_COMMAND_SUBSCRIBE,
  ZS_BG95_MQTT_OWNER_RECEIPT_SUBSCRIBE,
  ZS_BG95_MQTT_OWNER_EVENT_UPLINK,
  ZS_BG95_MQTT_OWNER_COMMAND_ACK
} zs_bg95_mqtt_owner_t;

typedef enum {
  ZS_BG95_MQTT_INPUT_NONE = 0,
  ZS_BG95_MQTT_INPUT_LINE,
  ZS_BG95_MQTT_INPUT_PROMPT,
  ZS_BG95_MQTT_INPUT_COMMAND,
  ZS_BG95_MQTT_INPUT_COMMAND_QUEUED,
  ZS_BG95_MQTT_INPUT_COMMAND_RETRY_REQUIRED,
  ZS_BG95_MQTT_INPUT_RECEIPT,
  ZS_BG95_MQTT_INPUT_PROTOCOL_ERROR
} zs_bg95_mqtt_input_outcome_t;

typedef struct {
  zs_bg95_t *modem;
  zs_bg95_command_transport_t *command;
  zs_bg95_event_receipt_t *receipt;
  zs_bg95_event_uplink_t *uplink;
  zs_bg95_mqtt_owner_t owner;
  zs_bg95_mqtt_input_outcome_t last_input_outcome;
  zs_bg95_command_receive_result_t last_command_result;
  zs_command_status_t last_command_status;
  zs_bg95_event_receipt_receive_result_t last_receipt_result;
  zs_event_receipt_status_t last_receipt_status;
  uint16_t next_message_id;
  uint32_t queued_command_count;
  uint32_t retry_required_count;
  size_t rx_size;
  size_t pending_command_size;
  uint8_t rx[ZS_BG95_MQTT_SESSION_RX_BYTES];
  uint8_t pending_command[ZS_BG95_MQTT_SESSION_RX_BYTES];
  bool skip_prompt_space;
} zs_bg95_mqtt_session_t;

/*
 * The session is the sole caller of the three child BG95 MQTT bindings. It
 * serializes their AT transactions and consumes raw UART bytes in task context.
 * Target USART/DMA/ISR ownership and cache coherency remain platform concerns.
 */
bool zs_bg95_mqtt_session_init(
    zs_bg95_mqtt_session_t *session,
    zs_bg95_t *modem,
    zs_bg95_command_transport_t *command,
    zs_bg95_event_receipt_t *receipt,
    zs_bg95_event_uplink_t *uplink,
    uint16_t first_message_id);

/*
 * Drive timeouts, subscribe command then receipt without overlap, and service
 * one bounded command deferred while another MQTT transaction owned the UART.
 */
void zs_bg95_mqtt_session_tick(zs_bg95_mqtt_session_t *session,
                               uint32_t now_ms,
                               uint64_t now_us,
                               bool time_trusted);

/*
 * Feed arbitrary UART chunks. The bounded framer preserves binary QMTRECV
 * payloads using their declared byte count and routes lines/prompts by owner.
 */
bool zs_bg95_mqtt_session_feed_uart(zs_bg95_mqtt_session_t *session,
                                    const uint8_t *data,
                                    size_t size,
                                    uint32_t now_ms,
                                    uint64_t now_us,
                                    bool time_trusted);

/* Start one event publication only after both subscriptions are established. */
zs_bg95_event_uplink_start_result_t zs_bg95_mqtt_session_start_event(
    zs_bg95_mqtt_session_t *session,
    uint32_t now_ms);

/* Publish a caller-owned message (heartbeat) under the same serialization as events. */
zs_bg95_event_uplink_start_result_t zs_bg95_mqtt_session_start_message(
    zs_bg95_mqtt_session_t *session,
    const zs_mqtt_event_message_t *message,
    uint32_t now_ms);

bool zs_bg95_mqtt_session_ready(const zs_bg95_mqtt_session_t *session);

#endif

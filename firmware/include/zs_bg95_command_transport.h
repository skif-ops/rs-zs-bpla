#ifndef ZS_BG95_COMMAND_TRANSPORT_H
#define ZS_BG95_COMMAND_TRANSPORT_H

#include "zs_bg95.h"
#include "zs_mqtt_command_transport.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_BG95_COMMAND_TRANSPORT_TIMEOUT_MS 120000u

typedef enum {
  ZS_BG95_COMMAND_TRANSPORT_IDLE = 0,
  ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT,
  ZS_BG95_COMMAND_TRANSPORT_SUBSCRIBED,
  ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_PROMPT,
  ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_RESULT
} zs_bg95_command_transport_state_t;

typedef enum {
  ZS_BG95_COMMAND_TRANSPORT_OUTCOME_NONE = 0,
  ZS_BG95_COMMAND_TRANSPORT_OUTCOME_READY,
  ZS_BG95_COMMAND_TRANSPORT_OUTCOME_ACK_BROKER_ACK,
  ZS_BG95_COMMAND_TRANSPORT_OUTCOME_MODEM_REJECTED,
  ZS_BG95_COMMAND_TRANSPORT_OUTCOME_TIMEOUT,
  ZS_BG95_COMMAND_TRANSPORT_OUTCOME_IO_ERROR,
  ZS_BG95_COMMAND_TRANSPORT_OUTCOME_PROTOCOL_ERROR,
  ZS_BG95_COMMAND_TRANSPORT_OUTCOME_OFFLINE
} zs_bg95_command_transport_outcome_t;

typedef enum {
  ZS_BG95_COMMAND_SUBSCRIBE_STARTED = 0,
  ZS_BG95_COMMAND_ALREADY_SUBSCRIBED,
  ZS_BG95_COMMAND_SUBSCRIBE_BUSY,
  ZS_BG95_COMMAND_SUBSCRIBE_OFFLINE,
  ZS_BG95_COMMAND_RECEIVE_MODE_REQUIRED,
  ZS_BG95_COMMAND_SUBSCRIBE_IO_ERROR,
  ZS_BG95_COMMAND_SUBSCRIBE_INVALID_ARGUMENT
} zs_bg95_command_subscribe_result_t;

typedef enum {
  ZS_BG95_COMMAND_ACK_PUBLISH_STARTED = 0,
  ZS_BG95_COMMAND_REJECTED_TOPIC,
  ZS_BG95_COMMAND_REJECTED_DELIVERY,
  ZS_BG95_COMMAND_REJECTED_COMMAND,
  ZS_BG95_COMMAND_STORAGE_ERROR,
  ZS_BG95_COMMAND_EXECUTION_RETRY,
  ZS_BG95_COMMAND_NOT_SUBSCRIBED,
  ZS_BG95_COMMAND_BUSY,
  ZS_BG95_COMMAND_RECEIVE_OFFLINE,
  ZS_BG95_COMMAND_NOT_COMMAND_FRAME,
  ZS_BG95_COMMAND_FRAMING_ERROR,
  ZS_BG95_COMMAND_CLIENT_MISMATCH,
  ZS_BG95_COMMAND_ACK_IO_ERROR,
  ZS_BG95_COMMAND_INVALID_ARGUMENT
} zs_bg95_command_receive_result_t;

typedef struct {
  zs_bg95_t *modem;
  zs_mqtt_command_transport_t *transport;
  zs_mqtt_command_message_t ack_publication;
  zs_bg95_command_transport_state_t state;
  zs_bg95_command_transport_outcome_t last_outcome;
  uint16_t subscribe_message_id;
  uint16_t ack_message_id;
  uint32_t deadline_ms;
  uint8_t ack_buffer[ZS_COMMAND_ACK_MAX_BYTES];
  bool authenticated_server_only_nonretained_down_route;
} zs_bg95_command_transport_t;

/*
 * BG95 +QMTRECV does not expose MQTT retain. The policy boolean asserts that
 * the exact station down route is authenticated, server-only and non-retained.
 */
bool zs_bg95_command_transport_init(
    zs_bg95_command_transport_t *binding,
    zs_bg95_t *modem,
    zs_mqtt_command_transport_t *transport,
    bool authenticated_server_only_nonretained_down_route);

zs_bg95_command_subscribe_result_t zs_bg95_command_transport_subscribe(
    zs_bg95_command_transport_t *binding,
    uint16_t message_id,
    uint32_t now_ms);

/* Consume exact subscription and ACK-publication result lines. */
bool zs_bg95_command_transport_on_line(zs_bg95_command_transport_t *binding,
                                      const char *line,
                                      uint32_t now_ms);

/*
 * Verify, durably execute and start fixed-length ACK publication for one full
 * binary +QMTRECV frame. ack_message_id must be nonzero for QoS 1.
 */
zs_bg95_command_receive_result_t zs_bg95_command_transport_on_frame(
    zs_bg95_command_transport_t *binding,
    const uint8_t *frame,
    size_t frame_size,
    uint16_t ack_message_id,
    uint64_t now_us,
    bool time_trusted,
    uint32_t now_ms,
    zs_command_status_t *decode_status);

/* Send exactly the durable ACK bytes after the modem's `>` prompt. */
bool zs_bg95_command_transport_on_prompt(zs_bg95_command_transport_t *binding,
                                        uint32_t now_ms);

void zs_bg95_command_transport_tick(zs_bg95_command_transport_t *binding,
                                    uint32_t now_ms);

#endif

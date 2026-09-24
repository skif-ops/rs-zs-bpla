#ifndef ZS_BG95_EVENT_UPLINK_H
#define ZS_BG95_EVENT_UPLINK_H

#include "zs_bg95.h"
#include "zs_mqtt_event_transport.h"

#include <stdbool.h>
#include <stdint.h>

#define ZS_BG95_EVENT_UPLINK_TIMEOUT_MS 120000u

typedef enum {
  ZS_BG95_EVENT_UPLINK_IDLE = 0,
  ZS_BG95_EVENT_UPLINK_WAIT_PROMPT,
  ZS_BG95_EVENT_UPLINK_WAIT_RESULT
} zs_bg95_event_uplink_state_t;

typedef enum {
  ZS_BG95_EVENT_UPLINK_OUTCOME_NONE = 0,
  ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK,
  ZS_BG95_EVENT_UPLINK_OUTCOME_MODEM_REJECTED,
  ZS_BG95_EVENT_UPLINK_OUTCOME_TIMEOUT,
  ZS_BG95_EVENT_UPLINK_OUTCOME_IO_ERROR,
  ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR,
  ZS_BG95_EVENT_UPLINK_OUTCOME_OFFLINE
} zs_bg95_event_uplink_outcome_t;

typedef enum {
  ZS_BG95_EVENT_UPLINK_STARTED = 0,
  ZS_BG95_EVENT_UPLINK_EMPTY,
  ZS_BG95_EVENT_UPLINK_RETRY_EXHAUSTED,
  ZS_BG95_EVENT_UPLINK_STORAGE_ERROR,
  ZS_BG95_EVENT_UPLINK_STATION_MISMATCH,
  ZS_BG95_EVENT_UPLINK_BUSY,
  ZS_BG95_EVENT_UPLINK_OFFLINE,
  ZS_BG95_EVENT_UPLINK_IO_ERROR,
  ZS_BG95_EVENT_UPLINK_INVALID_ARGUMENT
} zs_bg95_event_uplink_start_result_t;

typedef struct {
  zs_bg95_t *modem;
  zs_mqtt_event_transport_t *transport;
  zs_mqtt_event_message_t publication;
  zs_bg95_event_uplink_state_t state;
  zs_bg95_event_uplink_outcome_t last_outcome;
  uint16_t message_id;
  uint32_t deadline_ms;
  bool from_outbox;                 /* the publication in flight is an outbox event (not a heartbeat message) */
} zs_bg95_event_uplink_t;

bool zs_bg95_event_uplink_init(zs_bg95_event_uplink_t *uplink,
                               zs_bg95_t *modem,
                               zs_mqtt_event_transport_t *transport);

/*
 * Persist an outbox retry and send fixed-length binary QMTPUB command framing.
 * message_id must be nonzero for QoS 1. No outbox item is reclaimed here.
 */
zs_bg95_event_uplink_start_result_t zs_bg95_event_uplink_start(
    zs_bg95_event_uplink_t *uplink,
    uint16_t message_id,
    uint32_t now_ms);

/*
 * Publish a caller-owned message (heartbeat on the status topic) through the same
 * QMTPUB flow; nothing is persisted. The message and its buffers must stay valid
 * until the uplink returns to IDLE.
 */
zs_bg95_event_uplink_start_result_t zs_bg95_event_uplink_start_message(
    zs_bg95_event_uplink_t *uplink,
    uint16_t message_id,
    const zs_mqtt_event_message_t *message,
    uint32_t now_ms);

/* Send exactly msglen payload bytes after the modem's `>` prompt. */
bool zs_bg95_event_uplink_on_prompt(zs_bg95_event_uplink_t *uplink,
                                    uint32_t now_ms);

/* Consume only exact OK/ERROR/+QMTPUB lines for the active publication. */
bool zs_bg95_event_uplink_on_line(zs_bg95_event_uplink_t *uplink,
                                  const char *line);

void zs_bg95_event_uplink_tick(zs_bg95_event_uplink_t *uplink,
                               uint32_t now_ms);

#endif

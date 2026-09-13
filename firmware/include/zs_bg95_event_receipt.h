#ifndef ZS_BG95_EVENT_RECEIPT_H
#define ZS_BG95_EVENT_RECEIPT_H

#include "zs_bg95.h"
#include "zs_mqtt_event_transport.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_BG95_EVENT_RECEIPT_TIMEOUT_MS 120000u

typedef enum {
  ZS_BG95_EVENT_RECEIPT_IDLE = 0,
  ZS_BG95_EVENT_RECEIPT_WAIT_SUBSCRIBE_RESULT,
  ZS_BG95_EVENT_RECEIPT_SUBSCRIBED
} zs_bg95_event_receipt_state_t;

typedef enum {
  ZS_BG95_EVENT_RECEIPT_OUTCOME_NONE = 0,
  ZS_BG95_EVENT_RECEIPT_OUTCOME_READY,
  ZS_BG95_EVENT_RECEIPT_OUTCOME_MODEM_REJECTED,
  ZS_BG95_EVENT_RECEIPT_OUTCOME_TIMEOUT,
  ZS_BG95_EVENT_RECEIPT_OUTCOME_IO_ERROR,
  ZS_BG95_EVENT_RECEIPT_OUTCOME_PROTOCOL_ERROR,
  ZS_BG95_EVENT_RECEIPT_OUTCOME_OFFLINE
} zs_bg95_event_receipt_outcome_t;

typedef enum {
  ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_STARTED = 0,
  ZS_BG95_EVENT_RECEIPT_ALREADY_SUBSCRIBED,
  ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_BUSY,
  ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_OFFLINE,
  ZS_BG95_EVENT_RECEIPT_RECEIVE_MODE_REQUIRED,
  ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_IO_ERROR,
  ZS_BG95_EVENT_RECEIPT_SUBSCRIBE_INVALID_ARGUMENT
} zs_bg95_event_receipt_subscribe_result_t;

typedef enum {
  ZS_BG95_EVENT_RECEIPT_APPLIED = 0,
  ZS_BG95_EVENT_RECEIPT_ALREADY_APPLIED,
  ZS_BG95_EVENT_RECEIPT_REJECTED_TOPIC,
  ZS_BG95_EVENT_RECEIPT_REJECTED_DELIVERY,
  ZS_BG95_EVENT_RECEIPT_REJECTED_RECEIPT,
  ZS_BG95_EVENT_RECEIPT_STORAGE_ERROR,
  ZS_BG95_EVENT_RECEIPT_NOT_SUBSCRIBED,
  ZS_BG95_EVENT_RECEIPT_RECEIVE_OFFLINE,
  ZS_BG95_EVENT_RECEIPT_NOT_RECEIPT_FRAME,
  ZS_BG95_EVENT_RECEIPT_FRAMING_ERROR,
  ZS_BG95_EVENT_RECEIPT_CLIENT_MISMATCH,
  ZS_BG95_EVENT_RECEIPT_INVALID_ARGUMENT
} zs_bg95_event_receipt_receive_result_t;

typedef struct {
  zs_bg95_t *modem;
  zs_mqtt_event_transport_t *transport;
  zs_bg95_event_receipt_state_t state;
  zs_bg95_event_receipt_outcome_t last_outcome;
  uint16_t subscribe_message_id;
  uint32_t deadline_ms;
  bool authenticated_server_only_nonretained_route;
} zs_bg95_event_receipt_t;

/*
 * BG95 +QMTRECV does not expose MQTT retain. The final boolean is an external
 * broker-policy assertion: the station route is authenticated, server-only,
 * and rejects retained receipt publications. Initialization fails otherwise.
 */
bool zs_bg95_event_receipt_init(
    zs_bg95_event_receipt_t *receiver,
    zs_bg95_t *modem,
    zs_mqtt_event_transport_t *transport,
    bool authenticated_server_only_nonretained_route);

/* Subscribe exact topic/QoS 1 after pre-connect length mode is confirmed. */
zs_bg95_event_receipt_subscribe_result_t zs_bg95_event_receipt_subscribe(
    zs_bg95_event_receipt_t *receiver,
    uint16_t message_id,
    uint32_t now_ms);

/* Consume exact OK/ERROR/+QMTSUB lines while subscription setup is active. */
bool zs_bg95_event_receipt_on_line(zs_bg95_event_receipt_t *receiver,
                                   const char *line,
                                   uint32_t now_ms);

/*
 * Parse one complete binary-safe +QMTRECV frame. The caller must preserve the
 * complete length-delimited URC even when its payload contains NUL/quote/CRLF.
 */
zs_bg95_event_receipt_receive_result_t zs_bg95_event_receipt_on_frame(
    zs_bg95_event_receipt_t *receiver,
    const uint8_t *frame,
    size_t frame_size,
    zs_event_receipt_status_t *decode_status);

void zs_bg95_event_receipt_tick(zs_bg95_event_receipt_t *receiver,
                                uint32_t now_ms);

#endif

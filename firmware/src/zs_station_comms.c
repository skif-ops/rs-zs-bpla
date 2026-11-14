#include "zs_station_comms.h"
#include <string.h>

static uint32_t period_ms(const zs_station_comms_t *c) { return c->port->heartbeat_period_ms ? c->port->heartbeat_period_ms : ZS_STATION_COMMS_HEARTBEAT_PERIOD_MS; }
static uint32_t retry_ms(const zs_station_comms_t *c) { return c->port->retry_ms ? c->port->retry_ms : ZS_STATION_COMMS_RETRY_MS; }
static bool due(uint32_t now_ms, uint32_t at_ms) { return (int32_t)(now_ms - at_ms) >= 0; }

bool zs_station_comms_init(zs_station_comms_t *c, const zs_station_comms_port_t *port,
                           zs_bg95_mqtt_session_t *session, zs_mqtt_event_transport_t *transport, uint32_t now_ms) {
  if (!c || !port || !port->fill_heartbeat || !session || !transport) return false;
  memset(c, 0, sizeof(*c));
  c->port = port;
  c->session = session;
  c->transport = transport;
  c->next_heartbeat_ms = now_ms;
  c->heartbeat_pending = true;
  return true;
}

void zs_station_comms_request_heartbeat(zs_station_comms_t *c) { if (c) c->heartbeat_pending = true; }

/* The uplink returned to IDLE: account the publication we started. */
static void account(zs_station_comms_t *c, uint32_t now_ms) {
  const zs_bg95_event_uplink_outcome_t outcome = c->session->uplink->last_outcome;
  const bool ok = outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK;
  if (c->activity == ZS_STATION_COMMS_EVENT_IN_FLIGHT) {
    c->last_event_outcome = outcome;
    if (ok) c->events_published++; else { c->events_failed++; c->retry_at_ms = now_ms + retry_ms(c); }
  } else if (c->activity == ZS_STATION_COMMS_HEARTBEAT_IN_FLIGHT) {
    c->last_heartbeat_outcome = outcome;
    if (ok) c->heartbeats_published++; else { c->heartbeats_failed++; c->retry_at_ms = now_ms + retry_ms(c); c->heartbeat_pending = true; }
  }
  c->activity = ZS_STATION_COMMS_IDLE;
}

static bool start_heartbeat(zs_station_comms_t *c, uint32_t now_ms) {
  zs_heartbeat_t hb;
  size_t n;
  memset(&hb, 0, sizeof(hb));
  hb.schema_ver = 1u;
  hb.station_id = c->transport->station_id;
  /* the modem's own view of the network (required by the schema); the port fills the rest */
  (void)zs_bg95_export_cellular_telemetry(c->session->modem, &hb.cellular);
  if (!c->port->fill_heartbeat(c->port->ctx, &hb)) return false;
  n = zs_protocol_encode_heartbeat(&hb, c->heartbeat_payload, sizeof(c->heartbeat_payload));
  if (n == 0u) { c->heartbeats_failed++; c->heartbeat_pending = false; c->next_heartbeat_ms = now_ms + period_ms(c); return false; }   /* not encodable (no network settings yet) */
  c->heartbeat_message.topic = c->transport->status_topic;
  c->heartbeat_message.topic_size = c->transport->status_topic_size;
  c->heartbeat_message.payload = c->heartbeat_payload;
  c->heartbeat_message.payload_size = n;
  c->heartbeat_message.qos = ZS_MQTT_EVENT_QOS;
  c->heartbeat_message.retained = false;
  if (zs_bg95_mqtt_session_start_message(c->session, &c->heartbeat_message, now_ms) != ZS_BG95_EVENT_UPLINK_STARTED) return false;
  c->activity = ZS_STATION_COMMS_HEARTBEAT_IN_FLIGHT;
  c->heartbeat_pending = false;
  c->next_heartbeat_ms = now_ms + period_ms(c);
  return true;
}

void zs_station_comms_tick(zs_station_comms_t *c, uint32_t now_ms) {
  bool ready;
  if (!c || !c->session || !c->session->uplink) return;
  ready = zs_bg95_mqtt_session_ready(c->session);
  if (!ready) {
    if (c->activity != ZS_STATION_COMMS_IDLE) account(c, now_ms);   /* the session dropped under us */
    c->session_was_ready = false;
    return;
  }
  if (!c->session_was_ready) { c->session_was_ready = true; c->heartbeat_pending = true; }   /* announce on (re)connect */
  if (c->activity != ZS_STATION_COMMS_IDLE) {
    if (c->session->uplink->state != ZS_BG95_EVENT_UPLINK_IDLE) return;          /* still in flight */
    account(c, now_ms);
  }
  if (c->session->owner != ZS_BG95_MQTT_OWNER_NONE) return;                      /* command / receipt / ack owns the UART */
  if (!due(now_ms, c->retry_at_ms)) return;
  /* events first: the outbox is the durable evidence; the heartbeat waits a tick */
  switch (zs_bg95_mqtt_session_start_event(c->session, now_ms)) {
    case ZS_BG95_EVENT_UPLINK_STARTED: c->activity = ZS_STATION_COMMS_EVENT_IN_FLIGHT; return;
    case ZS_BG95_EVENT_UPLINK_EMPTY: break;
    case ZS_BG95_EVENT_UPLINK_RETRY_EXHAUSTED: c->events_exhausted++; break;      /* left for the operator (no reclaim here) */
    case ZS_BG95_EVENT_UPLINK_BUSY: return;
    default: c->events_failed++; c->retry_at_ms = now_ms + retry_ms(c); return;
  }
  if (c->heartbeat_pending || due(now_ms, c->next_heartbeat_ms)) (void)start_heartbeat(c, now_ms);
}

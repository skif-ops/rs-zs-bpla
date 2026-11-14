#ifndef ZS_STATION_COMMS_H
#define ZS_STATION_COMMS_H
/*
 * Station comms duty on top of the BG95 MQTT session: once the modem is ONLINE and both subscriptions
 * are established, this module
 *   - drains the durable event outbox one publication at a time (zs_bg95_mqtt_session_start_event), with a
 *     backoff after a failed attempt; slots are reclaimed only by the server receipt (zs_bg95_event_receipt);
 *   - publishes the heartbeat (compact CBOR schema 1, zs_protocol_encode_heartbeat) on the station
 *     `status` topic every `heartbeat_period_ms` (default 60 s), the first one as soon as the session is
 *     ready; the payload comes from the port's `fill_heartbeat`;
 *   - counts outcomes for the console and the next heartbeat.
 * Events go first when both are due (the heartbeat is re-tried on the next tick). Portable; the STM32
 * comms task calls zs_station_comms_tick() after zs_bg95_tick / zs_bg95_mqtt_session_tick.
 */
#include "zs_bg95_mqtt_session.h"
#include "zs_protocol.h"

#define ZS_STATION_COMMS_HEARTBEAT_PERIOD_MS 60000u
#define ZS_STATION_COMMS_RETRY_MS 5000u
#define ZS_STATION_COMMS_HEARTBEAT_BYTES 512u

typedef struct {
  void *ctx;
  /* Completes the heartbeat: schema_ver, station_id and the modem's cellular telemetry are pre-filled; the port
     supplies time_us, position, gnss, power, route, versions and self-test. */
  bool (*fill_heartbeat)(void *ctx, zs_heartbeat_t *heartbeat);
  uint32_t heartbeat_period_ms;   /* 0 = ZS_STATION_COMMS_HEARTBEAT_PERIOD_MS */
  uint32_t retry_ms;              /* 0 = ZS_STATION_COMMS_RETRY_MS */
} zs_station_comms_port_t;

typedef enum {
  ZS_STATION_COMMS_IDLE = 0,
  ZS_STATION_COMMS_EVENT_IN_FLIGHT,
  ZS_STATION_COMMS_HEARTBEAT_IN_FLIGHT
} zs_station_comms_activity_t;

typedef struct {
  const zs_station_comms_port_t *port;
  zs_bg95_mqtt_session_t *session;
  zs_mqtt_event_transport_t *transport;
  zs_mqtt_event_message_t heartbeat_message;
  uint8_t heartbeat_payload[ZS_STATION_COMMS_HEARTBEAT_BYTES];
  zs_station_comms_activity_t activity;
  uint32_t next_heartbeat_ms;
  uint32_t retry_at_ms;
  bool heartbeat_pending;         /* the first heartbeat after the session became ready */
  bool session_was_ready;
  uint32_t events_published, events_failed, events_exhausted;
  uint32_t heartbeats_published, heartbeats_failed;
  zs_bg95_event_uplink_outcome_t last_event_outcome, last_heartbeat_outcome;
} zs_station_comms_t;

bool zs_station_comms_init(zs_station_comms_t *c, const zs_station_comms_port_t *port,
                           zs_bg95_mqtt_session_t *session, zs_mqtt_event_transport_t *transport, uint32_t now_ms);
/* Drives one step: accounts the outcome of a finished publication, then starts the next due one. */
void zs_station_comms_tick(zs_station_comms_t *c, uint32_t now_ms);
/* Requests a heartbeat on the next opportunity (e.g. after a self-test). */
void zs_station_comms_request_heartbeat(zs_station_comms_t *c);

#endif

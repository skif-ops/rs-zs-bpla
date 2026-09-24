/* Station comms duty: heartbeat on the status topic, outbox drain through the BG95 MQTT session, retry backoff,
   re-announcement after a session drop. The modem is the session-test fixture: ONLINE, subscriptions fed as modem lines. */
#include "zs_station_comms.h"
#include "zs_command_vector.h"
#include "zs_event_receipt_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define COMMAND_SLOTS 4u
#define EVENT_SLOTS 2u

typedef struct {
  uint8_t command_slots[COMMAND_SLOTS][ZS_COMMAND_JOURNAL_SLOT_BYTES];
  uint8_t event_slots[EVENT_SLOTS][ZS_EVENT_OUTBOX_SLOT_BYTES];
  uint8_t command_workspace[256];
  uint8_t uart[16384];
  size_t uart_size;
  unsigned heartbeats_filled;
} fixture_t;

typedef struct {
  fixture_t fixture;
  zs_command_trust_t trust;
  zs_command_journal_io_t journal;
  zs_command_channel_t channel;
  zs_mqtt_command_transport_t command_transport;
  zs_event_outbox_io_t event_outbox;
  zs_mqtt_event_transport_t event_transport;
  zs_bg95_t modem;
  zs_bg95_command_transport_t command;
  zs_bg95_event_receipt_t receipt;
  zs_bg95_event_uplink_t uplink;
  zs_bg95_mqtt_session_t session;
  zs_station_comms_port_t port;
  zs_station_comms_t comms;
} ctx_t;

static bool slot_read(uint8_t *slots, size_t slot_bytes, uint16_t count, uint16_t slot, uint32_t off, uint8_t *d, size_t n) {
  if (slot >= count || off + n > slot_bytes) return false;
  memcpy(d, slots + (size_t)slot * slot_bytes + off, n); return true;
}
static bool slot_erase(uint8_t *slots, size_t slot_bytes, uint16_t count, uint16_t slot) {
  if (slot >= count) return false;
  memset(slots + (size_t)slot * slot_bytes, 0xff, slot_bytes); return true;
}
static bool slot_write(uint8_t *slots, size_t slot_bytes, uint16_t count, uint16_t slot, uint32_t off, const uint8_t *d, size_t n) {
  uint8_t *p = slots + (size_t)slot * slot_bytes + off;
  if (slot >= count || off + n > slot_bytes) return false;
  for (size_t i = 0u; i < n; i++) { if ((p[i] & d[i]) != d[i]) return false; p[i] = d[i]; }
  return true;
}
static bool command_read(void *c, uint16_t s, uint32_t o, uint8_t *d, size_t n) { return slot_read(&((fixture_t *)c)->command_slots[0][0], ZS_COMMAND_JOURNAL_SLOT_BYTES, COMMAND_SLOTS, s, o, d, n); }
static bool command_erase(void *c, uint16_t s) { return slot_erase(&((fixture_t *)c)->command_slots[0][0], ZS_COMMAND_JOURNAL_SLOT_BYTES, COMMAND_SLOTS, s); }
static bool command_write(void *c, uint16_t s, uint32_t o, const uint8_t *d, size_t n) { return slot_write(&((fixture_t *)c)->command_slots[0][0], ZS_COMMAND_JOURNAL_SLOT_BYTES, COMMAND_SLOTS, s, o, d, n); }
static bool event_read(void *c, uint16_t s, uint32_t o, uint8_t *d, size_t n) { return slot_read(&((fixture_t *)c)->event_slots[0][0], ZS_EVENT_OUTBOX_SLOT_BYTES, EVENT_SLOTS, s, o, d, n); }
static bool event_erase(void *c, uint16_t s) { return slot_erase(&((fixture_t *)c)->event_slots[0][0], ZS_EVENT_OUTBOX_SLOT_BYTES, EVENT_SLOTS, s); }
static bool event_write(void *c, uint16_t s, uint32_t o, const uint8_t *d, size_t n) { return slot_write(&((fixture_t *)c)->event_slots[0][0], ZS_EVENT_OUTBOX_SLOT_BYTES, EVENT_SLOTS, s, o, d, n); }

static int uart_write(void *ctx, unsigned channel, const uint8_t *data, size_t size) {
  fixture_t *f = ctx; (void)channel;
  if (!data || f->uart_size + size > sizeof(f->uart)) return -1;
  memcpy(&f->uart[f->uart_size], data, size); f->uart_size += size; return 0;
}
static bool verify_backend(void *ctx, const uint8_t pk[ZS_COMMAND_PUBLIC_KEY_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx; (void)pk; (void)m; (void)n; (void)sig; return false;   /* no commands in this test */
}
static bool execute(void *ctx, const zs_command_t *cmd, zs_command_ack_result_t *r, uint16_t *d) { (void)ctx; (void)cmd; *r = ZS_COMMAND_ACK_OK; *d = 0u; return true; }

static bool fill_heartbeat(void *ctx, zs_heartbeat_t *hb) {
  fixture_t *f = ctx;
  f->heartbeats_filled++;
  assert(hb->schema_ver == 1u && hb->station_id == ZS_EVENT_RECEIPT_VECTOR_STATION_ID && hb->cellular.settings_valid && strcmp(hb->cellular.apn, "internet") == 0);
  hb->time_us = 1800000000000000LL + (int64_t)f->heartbeats_filled * 60000000LL;
  hb->power.battery_pct = 87u; hb->power.battery_mv = 12600u;
  hb->route.transport = ZS_ROUTE_LTE;
  strcpy(hb->firmware_ver, "0.1.0-b1"); strcpy(hb->model_ver, "c46"); strcpy(hb->hardware_rev, "Rev.A");
  hb->self_test_ok = true;
  return true;
}

static void feed_line(ctx_t *C, const char *line, uint32_t now_ms) {
  uint8_t framed[192]; size_t n = strlen(line);
  memcpy(framed, line, n); framed[n] = '\r'; framed[n + 1u] = '\n';
  assert(zs_bg95_mqtt_session_feed_uart(&C->session, framed, n + 2u, now_ms, UINT64_C(1750000), true));
}
static void feed_prompt(ctx_t *C, uint32_t now_ms) { assert(zs_bg95_mqtt_session_feed_uart(&C->session, (const uint8_t *)">", 1u, now_ms, UINT64_C(1750000), true)); }

/* the modem accepts the publication: prompt, payload echo, OK, +QMTPUB result for the active message id */
static void ack_publish(ctx_t *C, uint32_t t) {
  char line[32];
  const unsigned id = C->uplink.message_id;
  feed_prompt(C, t); feed_line(C, "OK", t + 1u);
  snprintf(line, sizeof(line), "+QMTPUB: 0,%u,0", id);
  feed_line(C, line, t + 2u);
}

/* the last QMTPUB command the session wrote, as text */
static const char *last_command(ctx_t *C, size_t from) { static char buf[256]; size_t n = C->fixture.uart_size - from; if (n >= sizeof(buf)) n = sizeof(buf) - 1u; memcpy(buf, &C->fixture.uart[from], n); buf[n] = 0; return buf; }

static void setup(ctx_t *C) {
  static const uint8_t tenant[] = {'e', 'v', 't'};
  const zs_event_outbox_event_t event = {ZS_EVENT_RECEIPT_VECTOR_STATION_ID, ZS_EVENT_RECEIPT_VECTOR_BOOT_ID, ZS_EVENT_RECEIPT_VECTOR_SEQ_NO,
                                         ZS_EVENT_RECEIPT_VECTOR_EVENT_ID, ZS_EVENT_RECEIPT_VECTOR_EVENT_TIME_US, 2u,
                                         zs_event_receipt_vector_event_payload, sizeof(zs_event_receipt_vector_event_payload)};
  zs_command_trust_key_t key = {0};
  zs_hal_port_t hal = {0};
  memset(C, 0, sizeof(*C));
  memset(C->fixture.command_slots, 0xff, sizeof(C->fixture.command_slots));
  memset(C->fixture.event_slots, 0xff, sizeof(C->fixture.event_slots));
  memcpy(key.public_key, zs_command_vector_public_key, sizeof(key.public_key)); key.enabled = true;
  C->journal = (zs_command_journal_io_t){&C->fixture, COMMAND_SLOTS, command_read, command_erase, command_write};
  assert(zs_command_trust_init(&C->trust, &key, 1u, verify_backend, &C->fixture));
  C->channel = (zs_command_channel_t){ZS_COMMAND_VECTOR_STATION_ID, &C->trust, &C->journal, execute, &C->fixture, C->fixture.command_workspace, sizeof(C->fixture.command_workspace)};
  assert(zs_mqtt_command_transport_init(&C->command_transport, &C->channel, tenant, sizeof(tenant)));
  C->event_outbox = (zs_event_outbox_io_t){&C->fixture, EVENT_SLOTS, event_read, event_erase, event_write};
  assert(zs_event_outbox_enqueue(&C->event_outbox, &event) == ZS_EVENT_OUTBOX_OK);
  assert(zs_mqtt_event_transport_init(&C->event_transport, &C->event_outbox, ZS_EVENT_RECEIPT_VECTOR_STATION_ID, tenant, sizeof(tenant)));
  assert(C->event_transport.status_topic_size == 19u && memcmp(C->event_transport.status_topic, "zs/v1/evt/17/status", 19u) == 0);
  hal.ctx = &C->fixture; hal.uart_write = uart_write;
  zs_bg95_init(&C->modem, &hal, 1u, 2u, "internet");
  C->modem.state = ZS_BG95_ONLINE; C->modem.mqtt_connected = true; C->modem.mqtt_receive_length_enabled = true; C->modem.mqtt_client = 0u;
  /* what the modem learned during bring-up (schema 1 heartbeat carries it) */
  strcpy(C->modem.network_settings.imsi, "250017777777777"); strcpy(C->modem.network_settings.iccid, "8970199999999999999");
  strcpy(C->modem.network_settings.home_plmn, "25001"); strcpy(C->modem.network_settings.registered_operator, "MTS RUS");
  strcpy(C->modem.network_settings.apn, "internet"); strcpy(C->modem.network_settings.local_address, "10.64.3.7");
  strcpy(C->modem.network_settings.gateway, "10.64.3.1"); strcpy(C->modem.network_settings.primary_dns, "8.8.8.8");
  C->modem.network_settings.access_technology = 7u; C->modem.network_settings.apn_source = ZS_BG95_APN_EXPLICIT; C->modem.network_settings.valid = true;
  assert(zs_bg95_command_transport_init(&C->command, &C->modem, &C->command_transport, true));
  assert(zs_bg95_event_receipt_init(&C->receipt, &C->modem, &C->event_transport, true));
  assert(zs_bg95_event_uplink_init(&C->uplink, &C->modem, &C->event_transport));
  assert(zs_bg95_mqtt_session_init(&C->session, &C->modem, &C->command, &C->receipt, &C->uplink, 30u));
  C->port = (zs_station_comms_port_t){&C->fixture, fill_heartbeat, 60000u, 5000u};
  assert(zs_station_comms_init(&C->comms, &C->port, &C->session, &C->event_transport, 0u));
}

static void establish(ctx_t *C, uint32_t t) {
  char line[32];
  zs_bg95_mqtt_session_tick(&C->session, t, UINT64_C(1750000), true);
  snprintf(line, sizeof(line), "+QMTSUB: 0,%u,0,1", C->command.subscribe_message_id);
  feed_line(C, "OK", t + 1u); feed_line(C, line, t + 2u);
  zs_bg95_mqtt_session_tick(&C->session, t + 3u, UINT64_C(1750001), true);
  snprintf(line, sizeof(line), "+QMTSUB: 0,%u,0,1", C->receipt.subscribe_message_id);
  feed_line(C, "OK", t + 4u); feed_line(C, line, t + 5u);
  assert(zs_bg95_mqtt_session_ready(&C->session));
}

int main(void) {
  static ctx_t C;
  size_t mark;
  setup(&C);
  /* nothing happens before the session is ready */
  zs_station_comms_tick(&C.comms, 50u);
  assert(C.comms.activity == ZS_STATION_COMMS_IDLE && C.fixture.uart_size == 0u);
  establish(&C, 100u);

  /* ready: the outbox item goes first (event before heartbeat) */
  mark = C.fixture.uart_size;
  zs_station_comms_tick(&C.comms, 200u);
  assert(C.comms.activity == ZS_STATION_COMMS_EVENT_IN_FLIGHT && C.session.owner == ZS_BG95_MQTT_OWNER_EVENT_UPLINK);
  assert(strncmp(last_command(&C, mark), "AT+QMTPUB=0,", 12) == 0 && strstr(last_command(&C, mark), ",1,0,\"zs/v1/evt/17/up\",") != NULL);
  zs_station_comms_tick(&C.comms, 201u);                                   /* in flight: nothing new */
  assert(C.comms.activity == ZS_STATION_COMMS_EVENT_IN_FLIGHT);
  ack_publish(&C, 202u);
  assert(C.session.owner == ZS_BG95_MQTT_OWNER_NONE);

  /* accounted; the item stays pending until the server receipt but is NOT re-offered meanwhile (receipt hold,
     ZS_MQTT_EVENT_RECEIPT_WAIT_MS): the heartbeat goes out instead of a duplicate publish */
  mark = C.fixture.uart_size;
  zs_station_comms_tick(&C.comms, 300u);
  assert(C.comms.events_published == 1u && C.comms.last_event_outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK);
  assert(C.comms.activity == ZS_STATION_COMMS_HEARTBEAT_IN_FLIGHT);
  assert(strstr(last_command(&C, mark), ",1,0,\"zs/v1/evt/17/status\",") != NULL);
  feed_prompt(&C, 301u);
  { char line[32]; snprintf(line, sizeof(line), "+QMTPUB: 0,%u,0", C.uplink.message_id); feed_line(&C, "OK", 302u); feed_line(&C, line, 303u); }
  zs_station_comms_tick(&C.comms, 303u);
  assert(C.comms.heartbeats_published == 1u && C.comms.activity == ZS_STATION_COMMS_IDLE);
  /* deliver the server receipt: the slot is reclaimed */
  {
    uint8_t frame[256]; int n = snprintf((char *)frame, sizeof(frame), "+QMTRECV: 0,10,\"%.*s\",%zu,\"",
                                         (int)C.event_transport.receipt.topic_size, (const char *)C.event_transport.receipt.topic, sizeof(zs_event_receipt_vector_payload));
    assert(n > 0);
    memcpy(frame + n, zs_event_receipt_vector_payload, sizeof(zs_event_receipt_vector_payload));
    n += (int)sizeof(zs_event_receipt_vector_payload);
    memcpy(frame + n, "\"\r\n", 3); n += 3;
    assert(zs_bg95_mqtt_session_feed_uart(&C.session, frame, (size_t)n, 304u, UINT64_C(1750002), true));
    zs_event_outbox_item_t pending;
    assert(zs_event_outbox_peek(&C.event_outbox, &pending) == ZS_EVENT_OUTBOX_EMPTY);
  }
  /* the receipt arrived: nothing to publish, the next heartbeat is due one period after the first */
  zs_station_comms_tick(&C.comms, 400u);
  assert(C.comms.events_published == 1u && C.comms.activity == ZS_STATION_COMMS_IDLE);
  assert(C.fixture.heartbeats_filled == 1u && C.comms.heartbeat_message.payload_size > 100u && C.comms.heartbeat_payload[0] == 0xadu);   /* map(13) */
  zs_station_comms_tick(&C.comms, 500u);
  assert(C.comms.heartbeats_published == 1u && C.comms.activity == ZS_STATION_COMMS_IDLE && C.comms.next_heartbeat_ms == 60300u);
  /* nothing due before the period */
  zs_station_comms_tick(&C.comms, 30000u);
  assert(C.comms.activity == ZS_STATION_COMMS_IDLE && C.fixture.heartbeats_filled == 1u);

  /* period elapsed: heartbeat; the modem rejects -> counted, retried after the backoff */
  zs_station_comms_tick(&C.comms, 60300u);
  assert(C.comms.activity == ZS_STATION_COMMS_HEARTBEAT_IN_FLIGHT && C.fixture.heartbeats_filled == 2u);
  feed_line(&C, "ERROR", 60301u);
  zs_station_comms_tick(&C.comms, 60302u);
  assert(C.comms.heartbeats_failed == 1u && C.comms.last_heartbeat_outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_MODEM_REJECTED && C.comms.activity == ZS_STATION_COMMS_IDLE);
  zs_station_comms_tick(&C.comms, 62000u);                                 /* inside the 5 s backoff */
  assert(C.comms.activity == ZS_STATION_COMMS_IDLE);
  zs_station_comms_tick(&C.comms, 65500u);
  assert(C.comms.activity == ZS_STATION_COMMS_HEARTBEAT_IN_FLIGHT && C.fixture.heartbeats_filled == 3u);
  ack_publish(&C, 65501u);
  zs_station_comms_tick(&C.comms, 65600u);
  assert(C.comms.heartbeats_published == 2u);

  /* explicit request (after a self-test) goes out before the period */
  zs_station_comms_request_heartbeat(&C.comms);
  zs_station_comms_tick(&C.comms, 70000u);
  assert(C.comms.activity == ZS_STATION_COMMS_HEARTBEAT_IN_FLIGHT);
  ack_publish(&C, 70001u);
  zs_station_comms_tick(&C.comms, 70100u);
  assert(C.comms.heartbeats_published == 3u);

  /* session drop: nothing is started while not ready; on re-establishment a heartbeat announces the station */
  C.modem.mqtt_connected = false; C.modem.state = ZS_BG95_MQTT_CONNECTING;
  zs_bg95_mqtt_session_tick(&C.session, 80000u, UINT64_C(1750003), true);
  zs_station_comms_tick(&C.comms, 80001u);
  assert(!C.comms.session_was_ready && C.comms.activity == ZS_STATION_COMMS_IDLE);
  C.modem.mqtt_connected = true; C.modem.state = ZS_BG95_ONLINE;
  establish(&C, 90000u);
  zs_station_comms_tick(&C.comms, 90100u);
  assert(C.comms.activity == ZS_STATION_COMMS_HEARTBEAT_IN_FLIGHT && C.fixture.heartbeats_filled == 5u);

  printf("station comms: events %u heartbeats %u (failed %u)\n", C.comms.events_published, C.comms.heartbeats_published, C.comms.heartbeats_failed);
  printf("station comms tests passed\n");
  return 0;
}

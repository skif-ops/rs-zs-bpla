#include "zs_lora_uplink.h"
#include <string.h>

bool zs_lora_uplink_init(zs_lora_uplink_t *u, const zs_lora_uplink_port_t *port, const zs_event_outbox_io_t *outbox,
                         uint32_t station_id, uint16_t profile_id, const uint8_t engineer_key[32], uint8_t sf, uint32_t bandwidth_hz, uint32_t now_ms) {
  if (!u || !port || !port->tx || !outbox || station_id == 0u || !engineer_key || sf < 7u || sf > 12u || bandwidth_hz == 0u) return false;
  memset(u, 0, sizeof(*u));
  u->port = port; u->outbox = outbox; u->station_id = station_id; u->profile_id = profile_id; u->sf = sf; u->bandwidth_hz = bandwidth_hz;
  zs_lora_derive_key(engineer_key, u->key);
  u->budget_ms = ZS_LORA_UPLINK_DUTY_BUDGET_MS; u->last_refill_ms = now_ms;
  return true;
}

static void refill(zs_lora_uplink_t *u, uint32_t now_ms) {
  const uint32_t dt = now_ms - u->last_refill_ms;                 /* 36 s per hour = 10 ms of airtime per second */
  if (dt < 1000u) return;
  u->budget_ms += (dt / 1000u) * 10u;
  if (u->budget_ms > ZS_LORA_UPLINK_DUTY_BUDGET_MS) u->budget_ms = ZS_LORA_UPLINK_DUTY_BUDGET_MS;
  u->last_refill_ms += (dt / 1000u) * 1000u;
}

static int retry_slot(const zs_lora_uplink_t *u, uint64_t event_id) {
  for (unsigned i = 0u; i < ZS_LORA_UPLINK_RETRY_SLOTS; i++) if (u->retry[i].used && u->retry[i].event_id == event_id) return (int)i;
  return -1;
}

static bool held(void *ctx, const zs_event_outbox_item_t *c) {
  const zs_lora_uplink_t *u = ctx;
  const int i = retry_slot(u, c->event_id);
  return i >= 0 && (int32_t)(u->retry[i].next_at_ms - u->now_ms) > 0;
}

static void note_attempt_backoff(zs_lora_uplink_t *u, uint64_t event_id, uint32_t now_ms) {
  int i = retry_slot(u, event_id);
  if (i < 0) {
    for (unsigned k = 0u; k < ZS_LORA_UPLINK_RETRY_SLOTS; k++) if (!u->retry[k].used) { i = (int)k; break; }
    if (i < 0) { i = 0; }                                             /* table full: reuse slot 0 */
    u->retry[i].used = true; u->retry[i].event_id = event_id; u->retry[i].backoff_ms = ZS_LORA_UPLINK_BACKOFF_MIN_MS;
  } else if (u->retry[i].backoff_ms < ZS_LORA_UPLINK_BACKOFF_MAX_MS) {
    u->retry[i].backoff_ms *= 2u;
  }
  u->retry[i].next_at_ms = now_ms + u->retry[i].backoff_ms;
}

static void clear_retry(zs_lora_uplink_t *u, uint64_t event_id) { const int i = retry_slot(u, event_id); if (i >= 0) u->retry[i].used = false; }

zs_lora_uplink_result_t zs_lora_uplink_tick(zs_lora_uplink_t *u, uint32_t now_ms, bool gsm_degraded) {
  zs_lora_event_t e;
  uint8_t frame[ZS_LORA_EVENT_FRAME_BYTES];
  uint32_t airtime;
  if (!u) return ZS_LORA_UPLINK_ERROR;
  u->now_ms = now_ms;
  refill(u, now_ms);
  if (u->in_flight) {
    if ((int32_t)(now_ms - u->ack_deadline_ms) < 0) return ZS_LORA_UPLINK_WAITING_ACK;
    u->ack_timeouts++;
    note_attempt_backoff(u, u->item.event_id, now_ms);
    u->in_flight = false;
  }
  if (!gsm_degraded) return ZS_LORA_UPLINK_IDLE;                   /* LoRa only while the route hint says so */
  {
    const zs_event_outbox_result_t r = zs_event_outbox_peek_filtered(u->outbox, &u->item, held, u);
    if (r == ZS_EVENT_OUTBOX_EMPTY) return ZS_LORA_UPLINK_EMPTY;
    if (r != ZS_EVENT_OUTBOX_OK || u->item.station_id != u->station_id) return ZS_LORA_UPLINK_ERROR;
  }
  airtime = zs_lora_airtime_ms(ZS_LORA_EVENT_FRAME_BYTES, u->sf, u->bandwidth_hz, 5u);
  if (airtime == 0u) return ZS_LORA_UPLINK_ERROR;
  if (u->budget_ms < airtime) { u->budget_waits++; return ZS_LORA_UPLINK_NO_BUDGET; }
  memset(&e, 0, sizeof(e));
  if (u->port->summarize) (void)u->port->summarize(u->port->ctx, &u->item, &e);
  e.profile_id = u->profile_id; e.station_id = u->item.station_id; e.boot_id = u->item.boot_id; e.seq_no = u->item.seq_no;
  e.time_s = (uint32_t)(u->item.event_time_us / 1000000LL); e.time_ms = (uint16_t)((u->item.event_time_us / 1000LL) % 1000LL);
  e.flags = (uint8_t)((retry_slot(u, u->item.event_id) >= 0 ? ZS_LORA_EVENT_FLAG_RETRY : 0u) | ZS_LORA_EVENT_FLAG_GSM_DEGRADED);
  if (!zs_lora_encode_event(&e, u->key, frame)) return ZS_LORA_UPLINK_ERROR;
  if (zs_event_outbox_note_attempt(u->outbox, &u->item) != ZS_EVENT_OUTBOX_OK) return ZS_LORA_UPLINK_ERROR;
  if (!u->port->tx(u->port->ctx, frame, sizeof(frame))) { note_attempt_backoff(u, u->item.event_id, now_ms); return ZS_LORA_UPLINK_ERROR; }
  u->budget_ms -= airtime; u->airtime_ms_total += airtime; u->frames_sent++;
  u->in_flight = true; u->ack_deadline_ms = now_ms + airtime + ZS_LORA_UPLINK_ACK_WINDOW_MS;
  return ZS_LORA_UPLINK_SENT;
}

bool zs_lora_uplink_on_rx(zs_lora_uplink_t *u, const uint8_t *frame, size_t n, uint32_t now_ms) {
  uint32_t station_id, boot_id, seq_no;
  uint64_t event_id;
  zs_event_outbox_item_t item;
  bool delivered = false;
  (void)now_ms;
  if (!u || !zs_lora_decode_ack(frame, n, u->key, &station_id, &boot_id, &seq_no) || station_id != u->station_id) return false;
  event_id = ((uint64_t)boot_id << 32) | seq_no;
  if (u->in_flight && u->item.event_id == event_id) {
    if (zs_event_outbox_mark_application_acked(u->outbox, &u->item) != ZS_EVENT_OUTBOX_OK) return false;
    u->in_flight = false; u->acks++; clear_retry(u, event_id);
    return true;
  }
  /* a late ACK for an event that timed out (or a duplicate): still a valid delivery */
  if (zs_event_outbox_lookup(u->outbox, station_id, event_id, &item, &delivered) != ZS_EVENT_OUTBOX_OK) return false;
  if (delivered) return true;
  if (zs_event_outbox_mark_application_acked(u->outbox, &item) != ZS_EVENT_OUTBOX_OK) return false;
  u->acks++; clear_retry(u, event_id);
  return true;
}

bool zs_lora_uplink_busy(const zs_lora_uplink_t *u) { return u && u->in_flight; }

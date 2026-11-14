/* LoRa uplink: send/ack lifecycle, ack timeout with per-event backoff, late ack, duty-cycle budget, route hint gate. */
#include "zs_lora_uplink.h"
#include "zs_event_receipt_vector.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define SLOTS 4u
static uint8_t slots[SLOTS][ZS_EVENT_OUTBOX_SLOT_BYTES];
static bool rd(void *c, uint16_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s >= SLOTS || o + n > ZS_EVENT_OUTBOX_SLOT_BYTES) return false; memcpy(d, &slots[s][o], n); return true; }
static bool er(void *c, uint16_t s) { (void)c; if (s >= SLOTS) return false; memset(slots[s], 0xff, ZS_EVENT_OUTBOX_SLOT_BYTES); return true; }
static bool wr(void *c, uint16_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s >= SLOTS || o + n > ZS_EVENT_OUTBOX_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((slots[s][o + i] & d[i]) != d[i]) return false; slots[s][o + i] = d[i]; } return true; }
static const zs_event_outbox_io_t io = {NULL, SLOTS, rd, er, wr};

static uint8_t last_tx[64]; static size_t last_tx_n; static unsigned tx_count; static bool tx_fail;
static bool tx(void *c, const uint8_t *f, size_t n) { (void)c; if (tx_fail) return false; memcpy(last_tx, f, n); last_tx_n = n; tx_count++; return true; }
static bool summarize(void *c, const zs_event_outbox_item_t *it, zs_lora_event_t *e) { (void)c; (void)it; e->class_id = 3u; e->confidence_u8 = 190u; e->presence_level = 3u; e->f0_hz = 185u; e->battery_mv = 13100u; e->battery_pct = 78u; return true; }
static const zs_lora_uplink_port_t port = {NULL, tx, summarize};

static void enqueue(uint32_t seq) {
  const zs_event_outbox_event_t ev = {17u, 5u, seq, ((uint64_t)5u << 32) | seq, 1800000123456000LL + (int64_t)seq * 1000000LL, 2u,
                                      zs_event_receipt_vector_event_payload, sizeof(zs_event_receipt_vector_event_payload)};
  assert(zs_event_outbox_enqueue(&io, &ev) == ZS_EVENT_OUTBOX_OK);
}
static void ack_for(const uint8_t key[32], uint32_t seq, uint8_t out[ZS_LORA_ACK_FRAME_BYTES]) { assert(zs_lora_encode_ack(17u, 5u, seq, key, out)); }

int main(void) {
  static zs_lora_uplink_t u;
  uint8_t ek[32], ack[ZS_LORA_ACK_FRAME_BYTES];
  zs_lora_event_t e;
  uint16_t pending;
  for (unsigned i = 0u; i < 32u; i++) ek[i] = (uint8_t)(0xa0u + i);
  memset(slots, 0xff, sizeof(slots));
  enqueue(1u);
  assert(zs_lora_uplink_init(&u, &port, &io, 17u, 1u, ek, 9u, 125000u, 1000u));

  /* no route hint: nothing happens */
  assert(zs_lora_uplink_tick(&u, 1000u, false) == ZS_LORA_UPLINK_IDLE && tx_count == 0u);
  /* degraded: the event goes out as a 38-byte frame with the summary fields, then the ACK marks it delivered */
  assert(zs_lora_uplink_tick(&u, 2000u, true) == ZS_LORA_UPLINK_SENT && tx_count == 1u && last_tx_n == ZS_LORA_EVENT_FRAME_BYTES);
  assert(zs_lora_decode_event(last_tx, last_tx_n, u.key, &e) && e.station_id == 17u && e.seq_no == 1u && e.class_id == 3u && e.f0_hz == 185u && e.time_s == 1800000124u && e.time_ms == 456u && e.flags == ZS_LORA_EVENT_FLAG_GSM_DEGRADED);
  assert(zs_lora_uplink_tick(&u, 2500u, true) == ZS_LORA_UPLINK_WAITING_ACK && zs_lora_uplink_busy(&u));
  ack_for(u.key, 1u, ack);
  assert(zs_lora_uplink_on_rx(&u, ack, sizeof(ack), 2600u) && u.acks == 1u && !zs_lora_uplink_busy(&u));
  assert(zs_event_outbox_pending_count(&io, &pending) == ZS_EVENT_OUTBOX_OK && pending == 0u);
  assert(zs_lora_uplink_tick(&u, 2700u, true) == ZS_LORA_UPLINK_EMPTY);
  assert(!zs_lora_uplink_on_rx(&u, ack, sizeof(ack) - 1u, 2800u));            /* garbage is ignored */

  /* ack timeout -> backoff 30 s, the retry carries the RETRY flag, the second timeout doubles the backoff */
  enqueue(2u);
  assert(zs_lora_uplink_tick(&u, 3000u, true) == ZS_LORA_UPLINK_SENT && tx_count == 2u);
  assert(zs_lora_uplink_tick(&u, 3000u + 268u + ZS_LORA_UPLINK_ACK_WINDOW_MS + 1u, true) == ZS_LORA_UPLINK_EMPTY && u.ack_timeouts == 1u);   /* timed out, now held */
  assert(zs_lora_uplink_tick(&u, 3000u + 29000u, true) == ZS_LORA_UPLINK_EMPTY);
  assert(zs_lora_uplink_tick(&u, 36300u, true) == ZS_LORA_UPLINK_SENT && tx_count == 3u);           /* 6269 + 30 s backoff */
  assert(zs_lora_decode_event(last_tx, last_tx_n, u.key, &e) && (e.flags & ZS_LORA_EVENT_FLAG_RETRY));
  assert(zs_lora_uplink_tick(&u, 36300u + 268u + 3001u, true) == ZS_LORA_UPLINK_EMPTY && u.ack_timeouts == 2u);
  assert(u.retry[0].backoff_ms == 60000u);
  /* a late ACK (after the timeout) still delivers the event and clears its backoff */
  ack_for(u.key, 2u, ack);
  assert(zs_lora_uplink_on_rx(&u, ack, sizeof(ack), 40000u) && u.acks == 2u && !u.retry[0].used);
  assert(zs_event_outbox_pending_count(&io, &pending) == ZS_EVENT_OUTBOX_OK && pending == 0u);
  assert(zs_lora_uplink_on_rx(&u, ack, sizeof(ack), 40001u));                 /* duplicate ACK: fine */

  /* duty cycle: the budget is 36 s; ~134 frames of 268 ms exhaust it, then NO_BUDGET until the refill (10 ms/s) */
  {
    unsigned sent = 0u; uint32_t t = 100000u;
    u.budget_ms = 1000u; u.last_refill_ms = t;                             /* budget for three frames */
    for (unsigned i = 0u; i < 5u; i++) {
      enqueue(10u + i);
      const zs_lora_uplink_result_t r = zs_lora_uplink_tick(&u, t, true);
      if (r == ZS_LORA_UPLINK_SENT) { sent++; ack_for(u.key, 10u + i, ack); assert(zs_lora_uplink_on_rx(&u, ack, sizeof(ack), t + 1u)); }
      else assert(r == ZS_LORA_UPLINK_NO_BUDGET);
      t += 10u;
    }
    assert(sent == 3u && u.budget_waits == 2u);
    t += 30000u;                                                            /* +300 ms of budget: one more frame */
    assert(zs_lora_uplink_tick(&u, t, true) == ZS_LORA_UPLINK_SENT);
    ack_for(u.key, 13u, ack); assert(zs_lora_uplink_on_rx(&u, ack, sizeof(ack), t + 1u));
    assert(zs_lora_uplink_tick(&u, t + 1u, true) == ZS_LORA_UPLINK_NO_BUDGET);
  }
  /* radio failure: backoff, no budget spent */
  { const uint32_t b = u.budget_ms; tx_fail = true; u.budget_ms = 36000u; assert(zs_lora_uplink_tick(&u, 300000u, true) == ZS_LORA_UPLINK_ERROR && u.budget_ms == 36000u); tx_fail = false; (void)b; }
  printf("lora uplink: frames %u acks %u timeouts %u budget waits %u airtime %u ms\n", u.frames_sent, u.acks, u.ack_timeouts, u.budget_waits, u.airtime_ms_total);
  printf("lora uplink tests passed\n");
  return 0;
}

#ifndef ZS_LORA_UPLINK_H
#define ZS_LORA_UPLINK_H
/*
 * LoRa event uplink (LORA_BACKUP_ICD_v0_1 addendum A): drains the outbox over LoRa when the GSM link is degraded.
 * One event in flight at a time: frame -> TX -> ACK window (class-A style) -> delivered on a valid ACK, otherwise a
 * per-event backoff.  A 1 % duty-cycle token bucket (36 s of airtime per hour) gates every transmission.  The radio
 * is behind a port (the twin's channel model, the SX1262 driver on the target); the detection fields that are not
 * in the outbox item come from a summary callback (RAM cache of recent detections; zeros after a reboot).
 */
#include "zs_event_outbox.h"
#include "zs_lora_frame.h"
#include <stdbool.h>
#include <stdint.h>

#define ZS_LORA_UPLINK_ACK_WINDOW_MS 3000u
#define ZS_LORA_UPLINK_BACKOFF_MIN_MS 30000u
#define ZS_LORA_UPLINK_BACKOFF_MAX_MS 600000u
#define ZS_LORA_UPLINK_DUTY_BUDGET_MS 36000u   /* 1 % of an hour */
#define ZS_LORA_UPLINK_RETRY_SLOTS 8u

typedef struct {
  void *ctx;
  bool (*tx)(void *ctx, const uint8_t *frame, size_t n);                              /* start a transmission */
  bool (*summarize)(void *ctx, const zs_event_outbox_item_t *item, zs_lora_event_t *e); /* class/conf/level/f0/battery */
} zs_lora_uplink_port_t;

typedef struct {
  const zs_lora_uplink_port_t *port;
  const zs_event_outbox_io_t *outbox;
  uint8_t key[ZS_LORA_KEY_BYTES];
  uint32_t station_id;
  uint16_t profile_id;
  uint8_t sf; uint32_t bandwidth_hz;
  uint32_t now_ms;                       /* clock of the last tick (the hold predicate reads it) */
  /* duty cycle */
  uint32_t budget_ms, last_refill_ms;
  /* in flight */
  bool in_flight;
  zs_event_outbox_item_t item;
  uint32_t ack_deadline_ms;
  /* per-event retry backoff (RAM) */
  struct { uint64_t event_id; uint32_t next_at_ms, backoff_ms; bool used; } retry[ZS_LORA_UPLINK_RETRY_SLOTS];
  /* stats */
  uint32_t frames_sent, acks, ack_timeouts, budget_waits, airtime_ms_total;
} zs_lora_uplink_t;

typedef enum { ZS_LORA_UPLINK_IDLE = 0, ZS_LORA_UPLINK_SENT, ZS_LORA_UPLINK_WAITING_ACK, ZS_LORA_UPLINK_NO_BUDGET, ZS_LORA_UPLINK_EMPTY, ZS_LORA_UPLINK_ERROR } zs_lora_uplink_result_t;

bool zs_lora_uplink_init(zs_lora_uplink_t *u, const zs_lora_uplink_port_t *port, const zs_event_outbox_io_t *outbox,
                         uint32_t station_id, uint16_t profile_id, const uint8_t engineer_key[32], uint8_t sf, uint32_t bandwidth_hz, uint32_t now_ms);
/* Drives the uplink: refills the duty budget, times out the ACK window, sends the next eligible event. */
zs_lora_uplink_result_t zs_lora_uplink_tick(zs_lora_uplink_t *u, uint32_t now_ms, bool gsm_degraded);
/* A frame received from the radio: a valid ACK for the event in flight (or any pending event) marks it delivered. */
bool zs_lora_uplink_on_rx(zs_lora_uplink_t *u, const uint8_t *frame, size_t n, uint32_t now_ms);
bool zs_lora_uplink_busy(const zs_lora_uplink_t *u);

#endif

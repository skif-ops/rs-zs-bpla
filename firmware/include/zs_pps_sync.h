#ifndef ZS_PPS_SYNC_H
#define ZS_PPS_SYNC_H

/*
 * Binds GNSS PPS (TIM2 input capture, free-running 32-bit counter) to the MDF
 * sample counter and feeds zs_time.
 *
 * Two ISR sources deliver timestamps in timer ticks:
 *   - PPS edge:  zs_pps_sync_on_pps(ticks)
 *   - DMA block: zs_pps_sync_on_block(ticks, samples_total_at_block_end)
 * The UART task delivers the UTC label for a PPS (RMC/ZDA sentence that
 * follows the edge): zs_pps_sync_on_utc(epoch_us).
 *
 * The sample index at the PPS instant is interpolated between the two DMA
 * block marks that bracket it (tick -> sample is linear at the ADC rate), and
 * (epoch_us, sample_index) is handed to zs_time_on_pps.  Wrap of the 32-bit
 * timer is handled by unsigned arithmetic; a PPS without a UTC label within
 * `label_timeout_ticks`, or a label without a PPS, is dropped and counted.
 *
 * Portable/host only.
 */

#include <stdbool.h>
#include <stdint.h>

#include "zs_time.h"

typedef struct {
  uint32_t ticks;
  uint64_t samples;
} zs_pps_mark_t;

typedef struct {
  zs_time_sync_t *time;
  uint32_t timer_hz;
  double nominal_fs;           /* nominal sample rate captured at init (zs_time adapts its own estimate) */
  uint32_t label_timeout_ticks;
  zs_pps_mark_t marks[2];      /* last two DMA block marks (older, newer) */
  uint8_t mark_count;
  volatile bool pps_armed;     /* PPS edge captured, waiting for block bracket and label */
  volatile uint32_t pps_ticks;
  bool label_pending;
  int64_t label_epoch_us;
  uint64_t pps_sample;         /* interpolated sample index at the PPS edge */
  bool pps_sample_valid;
  uint32_t pps_count;
  uint32_t bound_count;        /* PPS successfully delivered to zs_time */
  uint32_t dropped_no_label;
  uint32_t dropped_no_pps;
  uint32_t dropped_no_bracket;
  int32_t last_interval_ppm;   /* measured sample rate error vs nominal, ppm, from consecutive PPS */
  uint64_t prev_pps_sample;
  bool prev_pps_valid;
} zs_pps_sync_t;

void zs_pps_sync_init(zs_pps_sync_t *p, zs_time_sync_t *time, uint32_t timer_hz, uint32_t label_timeout_ms);

/* ISR: TIM2 capture of the PPS rising edge. */
void zs_pps_sync_on_pps(zs_pps_sync_t *p, uint32_t ticks);

/* ISR or task: DMA block boundary, `samples_total` = sample counter at that boundary. */
void zs_pps_sync_on_block(zs_pps_sync_t *p, uint32_t ticks, uint64_t samples_total);

/* Task: UTC for the most recent PPS edge (seconds boundary), microseconds since epoch. */
void zs_pps_sync_on_utc(zs_pps_sync_t *p, int64_t epoch_us);

/* Task: run after ISR events; performs the binding when both sides are available. Returns true when zs_time was updated. */
bool zs_pps_sync_poll(zs_pps_sync_t *p, uint32_t now_ticks);

/* Expected sample-rate error from the last two bound PPS edges, in ppm (0 when unknown). */
int32_t zs_pps_sync_rate_error_ppm(const zs_pps_sync_t *p);

#endif

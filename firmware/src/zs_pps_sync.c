#include "zs_pps_sync.h"

#include <string.h>

void zs_pps_sync_init(zs_pps_sync_t *p, zs_time_sync_t *time, uint32_t timer_hz, uint32_t label_timeout_ms) {
  if (!p) return;
  memset(p, 0, sizeof(*p));
  p->time = time;
  p->nominal_fs = time ? time->samples_per_second : 0.0;
  p->timer_hz = timer_hz ? timer_hz : 1u;
  p->label_timeout_ticks = (uint32_t)(((uint64_t)label_timeout_ms * p->timer_hz) / 1000u);
}

void zs_pps_sync_on_pps(zs_pps_sync_t *p, uint32_t ticks) {
  if (!p) return;
  if (p->pps_armed) p->dropped_no_label++; /* previous edge never got its label */
  p->pps_ticks = ticks;
  p->pps_sample_valid = false;
  p->pps_armed = true;
  p->pps_count++;
}

void zs_pps_sync_on_block(zs_pps_sync_t *p, uint32_t ticks, uint64_t samples_total) {
  if (!p) return;
  if (p->mark_count == 2u) p->marks[0] = p->marks[1];
  p->marks[p->mark_count == 2u ? 1u : p->mark_count] = (zs_pps_mark_t){ticks, samples_total};
  if (p->mark_count < 2u) p->mark_count++;
}

void zs_pps_sync_on_utc(zs_pps_sync_t *p, int64_t epoch_us) {
  if (!p) return;
  if (p->label_pending) p->dropped_no_pps++;
  p->label_epoch_us = epoch_us;
  p->label_pending = true;
}

/* Interpolates the sample index at pps_ticks using the two most recent block marks. */
static bool bracket(zs_pps_sync_t *p) {
  uint32_t span_ticks, off_ticks;
  uint64_t span_samples;
  if (p->mark_count < 2u) return false;
  span_ticks = p->marks[1].ticks - p->marks[0].ticks;
  if (span_ticks == 0u) return false;
  off_ticks = p->pps_ticks - p->marks[0].ticks;
  /* PPS must fall inside [older, newer] (or slightly after newer within one span, extrapolated). */
  if (off_ticks > 2u * span_ticks) return false;
  span_samples = p->marks[1].samples - p->marks[0].samples;
  p->pps_sample = p->marks[0].samples + (span_samples * off_ticks) / span_ticks;
  p->pps_sample_valid = true;
  return true;
}

bool zs_pps_sync_poll(zs_pps_sync_t *p, uint32_t now_ticks) {
  if (!p) return false;
  if (!p->pps_armed) {
    if (p->label_pending && p->mark_count == 2u && (uint32_t)(now_ticks - p->marks[1].ticks) > p->label_timeout_ticks) {
      p->label_pending = false;
      p->dropped_no_pps++;
    }
    return false;
  }
  if (!p->pps_sample_valid && !bracket(p)) {
    /* wait for the block after the edge; give up if the marks never catch up */
    if ((uint32_t)(now_ticks - p->pps_ticks) > p->label_timeout_ticks) {
      p->pps_armed = false;
      p->dropped_no_bracket++;
      if (p->label_pending) { p->label_pending = false; }
    }
    return false;
  }
  if (!p->label_pending) {
    if ((uint32_t)(now_ticks - p->pps_ticks) > p->label_timeout_ticks) {
      p->pps_armed = false;
      p->dropped_no_label++;
    }
    return false;
  }
  /* both sides present: bind */
  if (p->prev_pps_valid) {
    uint64_t d = p->pps_sample - p->prev_pps_sample;
    double nominal = p->nominal_fs;
    if (nominal > 0.0 && d > 0u) {
      double ppm = ((double)d - nominal) / nominal * 1e6;
      if (ppm > 1e6) ppm = 1e6;
      if (ppm < -1e6) ppm = -1e6;
      p->last_interval_ppm = (int32_t)ppm;
    }
  }
  if (p->time) zs_time_on_pps(p->time, p->label_epoch_us, p->pps_sample);
  p->prev_pps_sample = p->pps_sample;
  p->prev_pps_valid = true;
  p->bound_count++;
  p->pps_armed = false;
  p->label_pending = false;
  return true;
}

int32_t zs_pps_sync_rate_error_ppm(const zs_pps_sync_t *p) { return p ? p->last_interval_ppm : 0; }

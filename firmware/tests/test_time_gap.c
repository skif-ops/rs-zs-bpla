/* Capture pauses (S3/S0 stop the PDM clock, the sample counter stops, time does not): zs_time keeps the mapping in
   step with real time, ages the holdover by the pause and does not update the rate across it; zs_pps_sync never
   brackets a PPS edge with block marks from both sides of a pause. */
#include "zs_pps_sync.h"
#include "zs_time.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>

#define FS 32000.0
#define S 1000000LL

static void test_time(void) {
  zs_time_sync_t t;
  zs_time_init(&t, FS);
  zs_time_on_pps(&t, 1 * S, 32000u);
  zs_time_on_pps(&t, 2 * S, 64000u);
  assert(t.trust == ZS_TIME_TRUST_GNSS_TRUSTED && fabs(t.samples_per_second - FS) < 1e-6);
  assert(zs_time_for_sample(&t, 96000u) == 3 * S);
  /* 30 s pause at sample 96000: the next samples belong 30 s later */
  zs_time_on_capture_gap(&t, 30 * S);
  assert(zs_time_for_sample(&t, 96000u) == 33 * S && zs_time_for_sample(&t, 128000u) == 34 * S);
  /* the holdover age counts the pause: 2 s of samples + 30 s paused */
  assert(zs_time_update(&t, 128000u) == ZS_TIME_TRUST_HOLDOVER && t.expected_error_us > 30000u);
  /* the first PPS after the pause re-anchors but does not feed the rate (samples and seconds are not comparable) */
  zs_time_on_pps(&t, 35 * S, 160500u);
  assert(t.trust == ZS_TIME_TRUST_GNSS_TRUSTED && fabs(t.samples_per_second - FS) < 1e-6 && t.gap_us == 0);
  assert(zs_time_for_sample(&t, 192500u) == 36 * S);
  /* the next one does again */
  zs_time_on_pps(&t, 36 * S, 192510u);
  assert(t.samples_per_second > FS);
  /* a long sleep without GNSS: the time is no longer trusted until the next PPS */
  zs_time_on_capture_gap(&t, 200 * S);
  assert(zs_time_update(&t, 193000u) == ZS_TIME_TRUST_UNSYNCED && zs_time_for_sample(&t, 193000u) == 0);
  /* nothing to shift before the first fix */
  zs_time_init(&t, FS);
  zs_time_on_capture_gap(&t, 5 * S);
  assert(zs_time_update(&t, 1000u) == ZS_TIME_TRUST_UNSYNCED);
}

static void test_pps(void) {
  zs_time_sync_t t;
  zs_pps_sync_t p;
  const uint32_t TICK = 160000u;                /* 10 ms blocks of 320 samples on a 16 MHz timer */
  uint32_t ticks = 1000u;
  uint64_t samples = 0u;
  zs_time_init(&t, FS);
  zs_pps_sync_init(&p, &t, 16000000u, 900u);
  for (int i = 0; i < 5; i++) { ticks += TICK; samples += 320u; zs_pps_sync_on_block(&p, ticks, samples); }
  /* pause: 3 s of timer, no blocks; a PPS edge and its label arrive meanwhile */
  const uint32_t stop_ticks = ticks;
  zs_pps_sync_on_pps(&p, stop_ticks + 1000000u);
  zs_pps_sync_on_utc(&p, 100 * S);
  zs_pps_sync_on_capture_gap(&p);
  assert(!p.pps_armed && !p.label_pending && p.mark_count == 0u);
  ticks = stop_ticks + 48000000u;                 /* restart 3 s later */
  ticks += TICK; samples += 320u; zs_pps_sync_on_block(&p, ticks, samples);
  assert(!zs_pps_sync_poll(&p, ticks) && p.bound_count == 0u);
  /* without the reset this edge would have been interpolated between a pre-pause and a post-pause block */
  ticks += TICK; samples += 320u; zs_pps_sync_on_block(&p, ticks, samples);
  zs_pps_sync_on_pps(&p, ticks + TICK / 2u);      /* half a block after the newest mark */
  ticks += TICK; samples += 320u; zs_pps_sync_on_block(&p, ticks, samples);
  zs_pps_sync_on_utc(&p, 104 * S);
  assert(zs_pps_sync_poll(&p, ticks) && p.bound_count == 1u);
  assert(t.pps_sample_counter == samples - 160u && t.pps_epoch_us == 104 * S);   /* the edge's own sample */
}

int main(void) {
  test_time();
  test_pps();
  puts("zs_time_gap_tests: OK");
  return 0;
}

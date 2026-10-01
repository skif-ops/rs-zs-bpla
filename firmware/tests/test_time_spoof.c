/* Protection of the station time against a wrong GNSS time (zs_time.h): a jump of the PPS label is refused and the
   station stays on its own timeline (holdover) with the time flagged suspect; labels agreeing again clear the flag;
   a jump that outlives the holdover is taken as an unverified timeline (GNSS_SUSPECT) until verified; the
   receiver's own spoofing report keeps PPS out the same way. */
#include "zs_time.h"

#include <assert.h>
#include <stdio.h>

#define FS 32000.0
#define S 1000000LL
#define T0 (1800000000LL * S)

/* the PPS of second k on the true timeline (sample = k * FS), labelled with `offset_us` */
static void pps(zs_time_sync_t *t, int k, int64_t offset_us) { zs_time_on_pps(t, T0 + k * S + offset_us, (uint64_t)k * 32000u); }

static void test_jitter_is_accepted(void) {
  zs_time_sync_t t;
  zs_time_init(&t, FS);
  for (int k = 1; k <= 30; k++) pps(&t, k, (k % 3 - 1) * 200);              /* +-200 us of label jitter */
  assert(t.trust == ZS_TIME_TRUST_GNSS_TRUSTED && t.verified && !zs_time_suspect(&t) && t.jumps == 0u);
}

static void test_a_jump_is_refused_and_held_over(void) {
  zs_time_sync_t t;
  zs_time_init(&t, FS);
  for (int k = 1; k <= 20; k++) pps(&t, k, 0);
  for (int k = 21; k <= 40; k++) {                                          /* the GNSS time jumps 5 s ahead */
    pps(&t, k, 5 * S);
    (void)zs_time_update(&t, (uint64_t)k * 32000u + 16000u);
  }
  assert(t.jumps == 20u && t.last_jump_us == 5 * S && t.suspect && zs_time_suspect(&t));
  assert(t.trust == ZS_TIME_TRUST_HOLDOVER && t.verified);                   /* its own timeline, ageing */
  assert(zs_time_for_sample(&t, 40u * 32000u) == T0 + 40 * S);               /* not the spoofed one */
  /* the GNSS time agrees again: taken at once, the flag clears after ZS_TIME_CLEAR_PPS of them */
  for (int k = 41; k < 41 + (int)ZS_TIME_CLEAR_PPS - 1; k++) pps(&t, k, 0);
  assert(t.trust == ZS_TIME_TRUST_GNSS_TRUSTED && t.suspect);
  pps(&t, 41 + (int)ZS_TIME_CLEAR_PPS - 1, 0);
  assert(!t.suspect && !zs_time_suspect(&t) && t.trust == ZS_TIME_TRUST_GNSS_TRUSTED);
}

static void test_small_and_whole_second_jumps(void) {
  zs_time_sync_t t;
  zs_time_init(&t, FS);
  for (int k = 1; k <= 10; k++) pps(&t, k, 0);
  pps(&t, 11, 3000);                                                        /* 3 ms: beyond 1 ms + 200 ppm */
  assert(t.jumps == 1u && t.suspect);
  zs_time_init(&t, FS);
  for (int k = 1; k <= 10; k++) pps(&t, k, 0);
  pps(&t, 11, -1 * S);                                                      /* a second behind */
  assert(t.jumps == 1u && t.last_jump_us == -1 * S);
}

static void test_a_persistent_jump_becomes_an_unverified_timeline(void) {
  zs_time_sync_t t;
  zs_time_init(&t, FS);
  for (int k = 1; k <= 10; k++) pps(&t, k, 0);
  int k = 11;
  for (; k <= 10 + 125; k++) { pps(&t, k, 3600 * S); (void)zs_time_update(&t, (uint64_t)k * 32000u + 100u); }
  /* the holdover (120 s) ran out during a jump the GNSS kept: its timeline, but GNSS_SUSPECT */
  assert(t.reanchors == 1u && !t.verified && t.trust == ZS_TIME_TRUST_GNSS_SUSPECT && zs_time_suspect(&t));
  assert(zs_time_for_sample(&t, (uint64_t)(k - 1) * 32000u) == T0 + (k - 1) * S + 3600 * S);
  /* verified after ZS_TIME_VERIFY_S of PPS without a jump */
  while (t.verify_s < ZS_TIME_VERIFY_S - 1u) pps(&t, k++, 3600 * S);
  assert(t.trust == ZS_TIME_TRUST_GNSS_SUSPECT && !t.verified);
  pps(&t, k++, 3600 * S);
  assert(t.verified && t.trust == ZS_TIME_TRUST_GNSS_TRUSTED && !zs_time_suspect(&t) && t.reanchors == 1u);
}

static void test_erratic_labels_end_unsynced_then_unverified(void) {
  zs_time_sync_t t;
  zs_time_init(&t, FS);
  for (int k = 1; k <= 10; k++) pps(&t, k, 0);
  int k = 11;
  for (; k <= 10 + 125; k++) { pps(&t, k, (k % 7 + 1) * 10 * S); (void)zs_time_update(&t, (uint64_t)k * 32000u + 100u); }
  /* no consistent GNSS timeline to take: the holdover ran out, and the next label starts an unverified one */
  assert(t.trust == ZS_TIME_TRUST_GNSS_SUSPECT && !t.verified && t.reanchors == 1u && zs_time_suspect(&t));
}

static void test_the_receiver_spoofing_report(void) {
  zs_time_sync_t t;
  zs_time_init(&t, FS);
  for (int k = 1; k <= 10; k++) pps(&t, k, 0);
  zs_time_set_receiver_spoof(&t, true);
  for (int k = 11; k <= 15; k++) pps(&t, k, 0);                             /* agreeing labels are not taken either */
  (void)zs_time_update(&t, 15u * 32000u);
  assert(t.trust == ZS_TIME_TRUST_HOLDOVER && zs_time_suspect(&t) && t.jumps == 0u && t.pps_epoch_us == T0 + 10 * S);
  zs_time_set_receiver_spoof(&t, false);
  for (int k = 16; k < 16 + (int)ZS_TIME_CLEAR_PPS; k++) pps(&t, k, 0);
  assert(t.trust == ZS_TIME_TRUST_GNSS_TRUSTED && !zs_time_suspect(&t));
  /* spoofing reported before the first fix: the time is taken, unverified */
  zs_time_init(&t, FS);
  zs_time_set_receiver_spoof(&t, true);
  pps(&t, 1, 0);
  assert(t.trust == ZS_TIME_TRUST_GNSS_SUSPECT && !t.verified && zs_time_suspect(&t));
}

static void test_after_a_capture_pause_only_whole_seconds_are_checked(void) {
  zs_time_sync_t t;
  zs_time_init(&t, FS);
  for (int k = 1; k <= 10; k++) pps(&t, k, 0);
  zs_time_on_capture_gap(&t, 30 * S + 40000);                               /* the tick measured the pause 40 ms long */
  zs_time_on_pps(&t, T0 + 41 * S, 11u * 32000u);                            /* sample 11 s is 41 s now */
  assert(t.jumps == 0u && t.trust == ZS_TIME_TRUST_GNSS_TRUSTED);
  zs_time_on_capture_gap(&t, 30 * S);
  zs_time_on_pps(&t, T0 + 73 * S, 12u * 32000u);                            /* 72 s expected: a whole second off */
  assert(t.jumps == 1u && t.suspect);
}

int main(void) {
  test_jitter_is_accepted();
  test_a_jump_is_refused_and_held_over();
  test_small_and_whole_second_jumps();
  test_a_persistent_jump_becomes_an_unverified_timeline();
  test_erratic_labels_end_unsynced_then_unverified();
  test_the_receiver_spoofing_report();
  test_after_a_capture_pause_only_whole_seconds_are_checked();
  puts("zs_time_spoof_tests: OK");
  return 0;
}

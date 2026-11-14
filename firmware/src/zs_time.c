#include "zs_time.h"

#include <math.h>
#include <string.h>

void zs_time_init(zs_time_sync_t *t, double nominal_fs) {
  memset(t, 0, sizeof(*t));
  t->samples_per_second = nominal_fs;
  t->expected_error_us = 1000000u;
  t->trust = ZS_TIME_TRUST_UNSYNCED;
}

static bool has_timeline(const zs_time_sync_t *t) {
  return t->trust == ZS_TIME_TRUST_GNSS_TRUSTED || t->trust == ZS_TIME_TRUST_HOLDOVER || t->trust == ZS_TIME_TRUST_GNSS_SUSPECT;
}

/* seconds of samples (and capture pauses) since the last accepted PPS */
static double elapsed_s(const zs_time_sync_t *t, uint64_t sc) {
  const double ds = (double)(int64_t)(sc - t->pps_sample_counter);
  return ds / t->samples_per_second + (double)t->gap_us / 1000000.0;
}

/* a refused label: does it continue the GNSS timeline of the refused labels before it? */
static void follow_candidate(zs_time_sync_t *t, int64_t epoch_us, uint64_t sc) {
  if (t->candidate) {
    const double dt = (double)(int64_t)(sc - t->candidate_sample) / t->samples_per_second;
    const double predicted = (double)t->candidate_epoch_us + dt * 1e6;
    const bool agrees = dt > 0.0 && fabs((double)epoch_us - predicted) <= ZS_TIME_JUMP_MIN_US + ZS_TIME_RATE_TOL_PPM * dt;
    t->candidate_run = agrees ? (uint16_t)(t->candidate_run < UINT16_MAX ? t->candidate_run + 1u : UINT16_MAX) : 1u;
  } else {
    t->candidate_run = 1u;
  }
  t->candidate = true;
  t->candidate_epoch_us = epoch_us;
  t->candidate_sample = sc;
}

void zs_time_on_pps(zs_time_sync_t *t, int64_t epoch_us, uint64_t sc) {
  if (!t || t->samples_per_second <= 0.0) return;
  (void)zs_time_update(t, sc);                             /* a holdover that ran out ends here, not at the check */
  double since_s = 0.0;
  if (has_timeline(t)) {
    since_s = elapsed_s(t, sc);
    const double error_us = (double)epoch_us - (double)zs_time_for_sample(t, sc);
    double tol_us = ZS_TIME_JUMP_MIN_US + ZS_TIME_RATE_TOL_PPM * fabs(since_s);
    if (t->gap_us > 0 && tol_us < ZS_TIME_GAP_TOL_US) tol_us = ZS_TIME_GAP_TOL_US;
    const bool jump = fabs(error_us) > tol_us;
    if (jump || t->receiver_spoof) {                       /* not taken: the station keeps its timeline */
      if (jump) { t->jumps++; t->last_jump_us = (int64_t)error_us; follow_candidate(t, epoch_us, sc); }
      t->suspect = true;
      t->agree_run = 0u;
      t->verify_s = 0u;
      return;
    }
    if (t->suspect && ++t->agree_run >= ZS_TIME_CLEAR_PPS) { t->suspect = false; t->candidate = false; t->agree_run = 0u; }
    if (!t->verified) {
      t->verify_s += since_s >= 1.0 ? (uint32_t)(since_s + 0.5) : 1u;
      if (t->verify_s >= ZS_TIME_VERIFY_S && !t->suspect) t->verified = true;
    }
  } else {
    /* no timeline to check against: the first PPS, or the first after the holdover ran out */
    t->verified = !t->suspect && !t->receiver_spoof;
    if (!t->verified && t->suspect && !t->receiver_spoof) t->reanchors++;
    t->suspect = false;
    t->candidate = false;
    t->agree_run = 0u;
    t->verify_s = 0u;
    t->rate_ref = false;
  }
  if (t->verified && t->trust == ZS_TIME_TRUST_GNSS_TRUSTED && t->rate_ref) {
    const uint64_t ds = sc - t->pps_sample_counter;
    const int64_t dt = epoch_us - t->pps_epoch_us;
    if (dt > 500000 && dt < 1500000) t->samples_per_second = 0.9 * t->samples_per_second + 0.1 * ((double)ds * 1000000.0 / (double)dt);
  }
  t->pps_epoch_us = epoch_us;
  t->pps_sample_counter = sc;
  t->pps_ok = true;
  t->expected_error_us = 100u;
  t->trust = t->verified ? ZS_TIME_TRUST_GNSS_TRUSTED : ZS_TIME_TRUST_GNSS_SUSPECT;
  t->gap_us = 0;
  t->rate_ref = true;
}

zs_time_trust_t zs_time_update(zs_time_sync_t *t, uint64_t sc) {
  if (!t || !has_timeline(t) || t->samples_per_second <= 0.0) return ZS_TIME_TRUST_UNSYNCED;
  double age_s = elapsed_s(t, sc);
  if (age_s < 0.0) age_s = 0.0;
  if (age_s <= 1.5) return t->trust;
  t->pps_ok = false;
  if (age_s > ZS_TIME_HOLDOVER_MAX_S) {
    if (t->suspect && t->candidate && t->candidate_run >= ZS_TIME_REANCHOR_PPS) {
      /* the holdover ran out during a jump the GNSS kept consistently: its timeline, unverified */
      t->pps_epoch_us = t->candidate_epoch_us;
      t->pps_sample_counter = t->candidate_sample;
      t->gap_us = 0;
      t->rate_ref = false;
      t->verified = false;
      t->suspect = false;
      t->candidate = false;
      t->agree_run = 0u;
      t->verify_s = 0u;
      t->reanchors++;
      t->trust = ZS_TIME_TRUST_GNSS_SUSPECT;
      age_s = elapsed_s(t, sc);
      const double error = 100.0 + (age_s > 0.0 ? age_s : 0.0) * 1000.0;
      t->expected_error_us = error >= 1000000.0 ? 1000000u : (uint32_t)error;
      return t->trust;
    }
    t->trust = ZS_TIME_TRUST_UNSYNCED;
    t->expected_error_us = 1000000u;
    return t->trust;
  }
  t->trust = t->verified ? ZS_TIME_TRUST_HOLDOVER : ZS_TIME_TRUST_GNSS_SUSPECT;
  const double error = 100.0 + age_s * 1000.0;
  t->expected_error_us = error >= 1000000.0 ? 1000000u : (uint32_t)error;
  return t->trust;
}

int64_t zs_time_for_sample(const zs_time_sync_t *t, uint64_t sc) {
  if (!t || !has_timeline(t) || t->samples_per_second <= 0.0) return 0;
  const double ds = (double)(int64_t)(sc - t->pps_sample_counter);
  return t->pps_epoch_us + (int64_t)(ds * 1000000.0 / t->samples_per_second);
}

void zs_time_on_capture_gap(zs_time_sync_t *t, int64_t gap_us) {
  if (!t || gap_us <= 0) return;
  t->pps_epoch_us += gap_us;
  t->gap_us += gap_us;
  t->rate_ref = false;
  t->candidate = false;      /* the refused labels before the pause cannot be followed across it */
}

void zs_time_set_receiver_spoof(zs_time_sync_t *t, bool spoof) {
  if (!t) return;
  t->receiver_spoof = spoof;
  if (spoof) { t->suspect = true; t->agree_run = 0u; t->verify_s = 0u; }
}

bool zs_time_suspect(const zs_time_sync_t *t) {
  return t && (t->suspect || t->receiver_spoof || (has_timeline(t) && !t->verified));
}

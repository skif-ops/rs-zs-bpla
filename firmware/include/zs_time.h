#ifndef ZS_TIME_H
#define ZS_TIME_H
#include <stdint.h>
#include <stdbool.h>
#include "zs_types.h"
/* Time of a capture sample = the last PPS epoch + samples since it / rate.  The sample counter only runs while the
   PDM capture runs: zs_time_on_capture_gap() accounts a stop (S3/S0) so the mapping does not fall behind by the
   pause, the holdover age includes it, and the next PPS does not update the rate across it.

   Protection against a wrong GNSS time (spoofing, meaconing, a receiver fault).  Once the station keeps a timeline
   (trusted, holdover or unverified), every PPS label is checked against the time that timeline predicts for the
   PPS sample: within ZS_TIME_JUMP_MIN_US + ZS_TIME_RATE_TOL_PPM of the time since the last accepted PPS, or within
   ZS_TIME_GAP_TOL_US right after a capture pause (whose length the MCU tick measures only to a few ms).  A label
   outside that is a time jump: the PPS is not taken, the station stays on its own timeline (holdover with its
   growing expected error) and flags the GNSS time as suspect (`suspect`, telemetry time_suspect).  The same happens
   while the receiver itself reports spoofing (zs_time_set_receiver_spoof).  The flag clears after
   ZS_TIME_CLEAR_PPS consecutive PPS that agree with the station's timeline again.
   A jump that persists outlives the holdover (ZS_TIME_HOLDOVER_MAX_S): the station then has no timeline of its own
   and takes the GNSS one - unverified: the trust is GNSS_SUSPECT (the server keeps such bearings out of fusion, and
   commands are checked against network time), right away if ZS_TIME_REANCHOR_PPS consecutive refused labels agreed
   with each other on it, otherwise with the next PPS.  An unverified timeline becomes GNSS_TRUSTED after
   ZS_TIME_VERIFY_S of PPS without another jump or a receiver spoofing report.  The very first PPS after power-up
   has nothing to be checked against and is taken as it is (unverified while the receiver reports spoofing).  A
   slow drift of the PPS within the oscillator tolerance is not detectable from inside the station. */
#define ZS_TIME_JUMP_MIN_US 1000.0          /* PPS jitter, interpolation between DMA blocks: tens of us */
#define ZS_TIME_RATE_TOL_PPM 200.0          /* the HSE crystal (+-50 ppm) and the rate estimate, with margin */
#define ZS_TIME_GAP_TOL_US 250000.0         /* after a capture pause the sub-second phase is not checked */
#define ZS_TIME_HOLDOVER_MAX_S 120.0
#define ZS_TIME_CLEAR_PPS 10u
#define ZS_TIME_REANCHOR_PPS 10u
#define ZS_TIME_VERIFY_S 600u
typedef struct { bool pps_ok; int64_t pps_epoch_us; uint64_t pps_sample_counter; double samples_per_second; uint32_t expected_error_us; zs_time_trust_t trust;
                 int64_t gap_us;       /* capture pauses since the last PPS */
                 bool rate_ref;        /* the last PPS is a valid reference for the rate estimate (no pause since) */
                 bool verified;        /* the timeline is trusted (false: taken from a GNSS time that had jumped) */
                 bool suspect;         /* the GNSS time disagrees with the station's timeline, or the receiver reports spoofing */
                 bool receiver_spoof;  /* the receiver's own spoofing indication */
                 uint16_t agree_run;   /* consecutive PPS agreeing with the timeline while suspect */
                 uint32_t verify_s;    /* unverified timeline: seconds of PPS without a jump so far */
                 uint32_t jumps;       /* PPS labels refused as time jumps */
                 int64_t last_jump_us; /* the last refused label minus the predicted time */
                 uint32_t reanchors;   /* unverified timelines taken after a jump */
                 bool candidate;       /* refused labels: a GNSS timeline other than the station's */
                 uint16_t candidate_run;
                 int64_t candidate_epoch_us;
                 uint64_t candidate_sample;
} zs_time_sync_t;
void zs_time_init(zs_time_sync_t*t,double nominal_fs);
void zs_time_on_pps(zs_time_sync_t*t,int64_t epoch_us,uint64_t sample_counter);
zs_time_trust_t zs_time_update(zs_time_sync_t*t,uint64_t sample_counter);
int64_t zs_time_for_sample(const zs_time_sync_t*t,uint64_t sample_counter);
/* The capture was stopped for gap_us (measured by a free-running clock) and restarts now at the same sample count. */
void zs_time_on_capture_gap(zs_time_sync_t*t,int64_t gap_us);
/* The receiver's spoofing indication (true: spoofing indicated).  While set no PPS is taken into a timeline the
   station already keeps, and the time is flagged suspect. */
void zs_time_set_receiver_spoof(zs_time_sync_t*t,bool spoof);
/* time_suspect for the telemetry: a jump or a receiver report now, or a timeline not verified since one. */
bool zs_time_suspect(const zs_time_sync_t*t);
#endif

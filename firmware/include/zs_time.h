#ifndef ZS_TIME_H
#define ZS_TIME_H
#include <stdint.h>
#include <stdbool.h>
#include "zs_types.h"
/* Time of a capture sample = the last PPS epoch + samples since it / rate.  The sample counter only runs while the
   PDM capture runs: zs_time_on_capture_gap() accounts a stop (S3/S0) so the mapping does not fall behind by the
   pause, the holdover age includes it, and the next PPS does not update the rate across it. */
typedef struct { bool pps_ok; int64_t pps_epoch_us; uint64_t pps_sample_counter; double samples_per_second; uint32_t expected_error_us; zs_time_trust_t trust;
                 int64_t gap_us;       /* capture pauses since the last PPS */
                 bool rate_ref;        /* the last PPS is a valid reference for the rate estimate (no pause since) */
} zs_time_sync_t;
void zs_time_init(zs_time_sync_t*t,double nominal_fs);
void zs_time_on_pps(zs_time_sync_t*t,int64_t epoch_us,uint64_t sample_counter);
zs_time_trust_t zs_time_update(zs_time_sync_t*t,uint64_t sample_counter);
int64_t zs_time_for_sample(const zs_time_sync_t*t,uint64_t sample_counter);
/* The capture was stopped for gap_us (measured by a free-running clock) and restarts now at the same sample count. */
void zs_time_on_capture_gap(zs_time_sync_t*t,int64_t gap_us);
#endif

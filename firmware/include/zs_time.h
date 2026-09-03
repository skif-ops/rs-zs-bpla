#ifndef ZS_TIME_H
#define ZS_TIME_H
#include <stdint.h>
#include <stdbool.h>
typedef struct { bool pps_ok; int64_t pps_epoch_us; uint64_t pps_sample_counter; double samples_per_second; uint32_t expected_error_us; } zs_time_sync_t;
void zs_time_init(zs_time_sync_t*t,double nominal_fs);
void zs_time_on_pps(zs_time_sync_t*t,int64_t epoch_us,uint64_t sample_counter);
int64_t zs_time_for_sample(const zs_time_sync_t*t,uint64_t sample_counter);
#endif

#include "zs_time.h"
void zs_time_init(zs_time_sync_t*t,double nominal_fs){t->pps_ok=false;t->pps_epoch_us=0;t->pps_sample_counter=0;t->samples_per_second=nominal_fs;t->expected_error_us=1000000;}
void zs_time_on_pps(zs_time_sync_t*t,int64_t epoch_us,uint64_t sc){if(t->pps_ok){uint64_t ds=sc-t->pps_sample_counter;int64_t dt=epoch_us-t->pps_epoch_us;if(dt>500000&&dt<1500000)t->samples_per_second=0.9*t->samples_per_second+0.1*((double)ds*1000000.0/(double)dt);}t->pps_epoch_us=epoch_us;t->pps_sample_counter=sc;t->pps_ok=true;t->expected_error_us=100;}
int64_t zs_time_for_sample(const zs_time_sync_t*t,uint64_t sc){if(!t->pps_ok)return 0;double ds=(double)((int64_t)(sc-t->pps_sample_counter));return t->pps_epoch_us+(int64_t)(ds*1000000.0/t->samples_per_second);}

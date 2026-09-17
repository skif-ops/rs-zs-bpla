#include "zs_protocol.h"
#include "zs_mesh.h"
#include "zs_time.h"
#include "zs_classifier.h"
#include <assert.h>
#include <stdio.h>
int main(void){zs_detection_t d={0};d.schema_ver=4;d.station_id=1;d.seq_no=2;d.event_id=3;d.event_time_us=4;d.classification.class_id=1;d.classification.confidence_u8=220;uint8_t buf[512];size_t n=zs_protocol_encode_detection(&d,buf,sizeof(buf));assert(n>0&&n<sizeof(buf));zs_mesh_sm_t m;zs_mesh_init(&m);zs_mesh_set_cellular(&m,false,0);zs_mesh_set_pending_p0(&m,true,0);assert(zs_mesh_step(&m,0)==ZS_LORA_DISCOVERY);m.route_hops=2;assert(zs_mesh_step(&m,10)==ZS_LORA_MESH_ACTIVE);zs_time_sync_t t;zs_time_init(&t,32000);assert(t.trust==ZS_TIME_TRUST_UNSYNCED);zs_time_on_pps(&t,1000000,32000);assert(t.trust==ZS_TIME_TRUST_GNSS_TRUSTED);assert(zs_time_for_sample(&t,48000)>1499000);assert(zs_time_update(&t,96000)==ZS_TIME_TRUST_HOLDOVER);assert(!t.pps_ok&&t.expected_error_us>100);assert(zs_time_for_sample(&t,96000)>2999000);assert(zs_time_update(&t,4000000)==ZS_TIME_TRUST_UNSYNCED);assert(zs_time_for_sample(&t,4000000)==0);float f[43]={0};zs_classifier_result_t r=zs_classifier_predict_centroid(f);assert(r.confidence_u8<=255);puts("zs_core_tests: OK");return 0;}

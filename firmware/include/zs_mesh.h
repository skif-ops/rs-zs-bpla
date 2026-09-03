#ifndef ZS_MESH_H
#define ZS_MESH_H
#include <stdint.h>
#include <stdbool.h>
typedef enum { ZS_LORA_SLEEP=0, ZS_LORA_GATEWAY_BEACON, ZS_LORA_GATEWAY_RX, ZS_LORA_DISCOVERY, ZS_LORA_MESH_ACTIVE, ZS_LORA_STORE_FORWARD } zs_lora_state_t;
typedef struct { zs_lora_state_t state; bool cellular_ok; bool pending_p0; uint32_t now_ms, deadline_ms, beacon_interval_ms, rx_window_ms, active_window_ms; uint8_t route_hops; } zs_mesh_sm_t;
void zs_mesh_init(zs_mesh_sm_t *s);
void zs_mesh_set_cellular(zs_mesh_sm_t*s,bool ok,uint32_t now_ms);
void zs_mesh_set_pending_p0(zs_mesh_sm_t*s,bool p0,uint32_t now_ms);
zs_lora_state_t zs_mesh_step(zs_mesh_sm_t*s,uint32_t now_ms);
#endif

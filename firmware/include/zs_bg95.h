#ifndef ZS_BG95_H
#define ZS_BG95_H
#include "zs_hal_port.h"
#include <stdbool.h>
#include <stdint.h>

typedef enum { ZS_BG95_OFF=0, ZS_BG95_POWERING, ZS_BG95_AT_SYNC, ZS_BG95_SIM_CHECK, ZS_BG95_CONFIGURE, ZS_BG95_REGISTERING, ZS_BG95_READY, ZS_BG95_ERROR } zs_bg95_state_t;
typedef enum { ZS_BG95_NET_NONE=0, ZS_BG95_NET_LTE=1, ZS_BG95_NET_NBIOT=2, ZS_BG95_NET_2G=3 } zs_bg95_net_t;
typedef struct { zs_hal_port_t io; unsigned uart_channel; unsigned pwrkey_gpio; zs_bg95_state_t state; zs_bg95_net_t network; char apn[64]; uint32_t deadline_ms; uint32_t retry_at_ms; uint8_t retries; bool sim_ready; bool registered_eps; bool registered_cs; bool command_pending; char last_command[96]; } zs_bg95_t;
void zs_bg95_init(zs_bg95_t *m, const zs_hal_port_t *io, unsigned uart_channel, unsigned pwrkey_gpio, const char *apn);
void zs_bg95_power_on(zs_bg95_t *m, uint32_t now_ms);
void zs_bg95_tick(zs_bg95_t *m, uint32_t now_ms);
void zs_bg95_on_line(zs_bg95_t *m, const char *line, uint32_t now_ms);
bool zs_bg95_ready(const zs_bg95_t *m);
const char *zs_bg95_state_name(zs_bg95_state_t s);
#endif

#ifndef ZS_DUAL_SIM_BG95_H
#define ZS_DUAL_SIM_BG95_H

#include "zs_bg95.h"
#include "zs_dual_sim.h"

#include <stdbool.h>
#include <stdint.h>

/*
 * Portable bridge for modem-dependent actions only. Traffic/session closure,
 * board GPIO/rail control, audit persistence and CELL_STATUS sampling remain
 * caller responsibilities.
 */
bool zs_dual_sim_bg95_begin_graceful_shutdown(zs_dual_sim_t *controller,
                                               zs_bg95_t *modem,
                                               uint32_t now_ms);
bool zs_dual_sim_bg95_confirm_shutdown(zs_dual_sim_t *controller,
                                       zs_bg95_t *modem,
                                       bool cell_status_low,
                                       uint32_t now_ms);
bool zs_dual_sim_bg95_begin_power_on(zs_dual_sim_t *controller,
                                     zs_bg95_t *modem,
                                     uint32_t now_ms);
bool zs_dual_sim_bg95_confirm_modem_on(zs_dual_sim_t *controller,
                                       const zs_bg95_t *modem,
                                       bool cell_status_high,
                                       uint32_t now_ms);
bool zs_dual_sim_bg95_verify_iccid(zs_dual_sim_t *controller,
                                   const zs_bg95_t *modem);
bool zs_dual_sim_bg95_confirm_link(zs_dual_sim_t *controller,
                                   const zs_bg95_t *modem,
                                   uint32_t now_ms);

#endif

#ifndef BSP_TIM2_PPS_H
#define BSP_TIM2_PPS_H
#include <stdbool.h>
#include <stdint.h>
#include "zs_pps_sync.h"
/* TIM2: 32-bit free-running at 16 MHz, CH1 (PA0, GNSS TIMEPULSE) input capture on the rising edge. */
bool bsp_tim2_pps_init(zs_pps_sync_t *pps);
uint32_t bsp_tim2_pps_now(void);       /* current counter, same timebase as the capture values */
uint32_t bsp_tim2_pps_edges(void);
#endif

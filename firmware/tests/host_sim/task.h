#ifndef HOST_SIM_TASK_H
#define HOST_SIM_TASK_H
#include <stdint.h>
uint32_t xTaskGetTickCount(void);   /* simulated milliseconds (test_app_comms_sim.c) */
void vTaskDelay(uint32_t ticks);    /* advances the simulated clock */
#endif

#ifndef HOST_SIM_TASK_H
#define HOST_SIM_TASK_H
#include <stdint.h>
uint32_t xTaskGetTickCount(void);   /* simulated milliseconds (test_app_comms_sim.c) */
void vTaskDelay(uint32_t ticks);    /* advances the simulated clock */
#define taskENTER_CRITICAL() ((void)0) /* single-threaded simulation */
#define taskEXIT_CRITICAL() ((void)0)
#endif

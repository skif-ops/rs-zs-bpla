/* Host simulation stand-in for FreeRTOS.h: the app_comms state machine is compiled against this on the host
   (test_app_comms_sim.c) with a simulated clock; nothing else of the kernel is used by that module. */
#ifndef HOST_SIM_FREERTOS_H
#define HOST_SIM_FREERTOS_H
#include <stdint.h>
typedef uint32_t TickType_t;
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
#endif

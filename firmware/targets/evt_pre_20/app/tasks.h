#ifndef TASKS_H
#define TASKS_H
#include <stdbool.h>
/* Creates the B1 task set; call before vTaskStartScheduler. */
bool app_tasks_create(void);
/* True while the GSM link is marked degraded (consecutive failed sessions): the LoRa transport is preferred. */
bool app_route_hint_lora(void);
#endif

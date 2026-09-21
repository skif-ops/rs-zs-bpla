#ifndef TASKS_H
#define TASKS_H
#include <stdbool.h>
/* Creates the B1 task set; call before vTaskStartScheduler. */
bool app_tasks_create(void);
#endif

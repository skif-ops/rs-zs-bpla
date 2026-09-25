#ifndef APP_WATCHDOG_H
#define APP_WATCHDOG_H
/*
 * Hardware watchdog (IWDG, LSI 32 kHz / 256, APP_WATCHDOG_TIMEOUT_MS) fed by the supervisor only while every
 * registered task has checked in within APP_WATCHDOG_WINDOW_MS (zs_task_watch).  A stuck task stops the feeding;
 * its bit is written to a TAMP backup register before the reset and reported with the reset cause in the next
 * heartbeat (detector map keys 12/13).  The IWDG is frozen while the core is halted by a debugger.
 */
#include <stdbool.h>
#include <stdint.h>

typedef enum { APP_WD_AUDIO = 1, APP_WD_DSP, APP_WD_COMMS, APP_WD_BLE, APP_WD_POWER, APP_WD_LORA, APP_WD_GNSS } app_wd_task_t;

/* Reads and clears the reset flags and the backup-register mask; call first thing at boot. */
void app_watchdog_capture_reset_cause(void);
uint8_t app_watchdog_reset_cause(void);        /* zs_detector_health_t.reset_cause encoding */
uint16_t app_watchdog_previous_missed(void);    /* tasks that let the IWDG fire before this boot */
const char *app_watchdog_reset_cause_name(void);

void app_watchdog_register(app_wd_task_t task);
void app_watchdog_checkin(app_wd_task_t task);
void app_watchdog_hold(app_wd_task_t task, uint32_t duration_ms);   /* bounded long operation */
/* Starts the IWDG (irreversible until reset). */
void app_watchdog_start(void);
/* Supervisor: feeds the IWDG when the task watch allows it; latches a miss into the backup register. */
void app_watchdog_service(void);
void app_watchdog_status(void (*print)(const char *fmt, ...));
/* Bench: make `task` stop checking in (proves the path on the board: reset in < window + timeout). */
void app_watchdog_simulate_stall(app_wd_task_t task);
bool app_watchdog_stalled(app_wd_task_t task);
#endif

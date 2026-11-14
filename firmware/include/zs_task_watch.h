#ifndef ZS_TASK_WATCH_H
#define ZS_TASK_WATCH_H
/*
 * Task liveness for the hardware watchdog: the supervisor feeds the IWDG only while every registered task has
 * checked in within `window_ms`.  A task that blocks by design for a bounded long operation (nRF image update,
 * large NOR erase) takes a hold that exempts it until a deadline; an expired hold counts as a miss.  When the
 * window closes with a task missing, feeding stops and the IWDG resets the MCU; the missing-task mask is kept by
 * the target in a backup register and reported in the next heartbeat.  Portable, host-tested.
 */
#include <stdbool.h>
#include <stdint.h>

#define ZS_TASK_WATCH_MAX 16u

typedef struct {
  uint32_t registered;         /* bit per task id */
  uint32_t seen;               /* checked in during the current window */
  uint32_t window_ms, window_start_ms;
  uint32_t hold_until_ms[ZS_TASK_WATCH_MAX];
  uint32_t hold_mask;
  uint32_t missed;             /* tasks missing when the last window closed (0 = healthy) */
  uint32_t windows_ok, windows_missed;
} zs_task_watch_t;

void zs_task_watch_init(zs_task_watch_t *w, uint32_t window_ms, uint32_t now_ms);
void zs_task_watch_register(zs_task_watch_t *w, unsigned task_id);
void zs_task_watch_checkin(zs_task_watch_t *w, unsigned task_id);
/* Exempts `task_id` for `duration_ms` (a bounded blocking operation); a new checkin ends the hold. */
void zs_task_watch_hold(zs_task_watch_t *w, unsigned task_id, uint32_t duration_ms, uint32_t now_ms);
/* Called by the supervisor often (<< window).  Returns true when the IWDG may be fed now.  Once a window closes with
   a task missing it keeps returning false (latched) so the hardware watchdog fires. */
bool zs_task_watch_service(zs_task_watch_t *w, uint32_t now_ms);
#endif

#include "zs_task_watch.h"
#include <string.h>

void zs_task_watch_init(zs_task_watch_t *w, uint32_t window_ms, uint32_t now_ms) {
  if (!w) return;
  memset(w, 0, sizeof(*w));
  w->window_ms = window_ms ? window_ms : 1000u;
  w->window_start_ms = now_ms;
}
void zs_task_watch_register(zs_task_watch_t *w, unsigned id) { if (w && id < ZS_TASK_WATCH_MAX) { w->registered |= 1u << id; w->seen |= 1u << id; } }
void zs_task_watch_checkin(zs_task_watch_t *w, unsigned id) {
  if (!w || id >= ZS_TASK_WATCH_MAX) return;
  w->seen |= 1u << id;
  w->hold_mask &= ~(1u << id);
}
void zs_task_watch_hold(zs_task_watch_t *w, unsigned id, uint32_t duration_ms, uint32_t now_ms) {
  if (!w || id >= ZS_TASK_WATCH_MAX) return;
  w->hold_mask |= 1u << id;
  w->hold_until_ms[id] = now_ms + duration_ms;
}

bool zs_task_watch_service(zs_task_watch_t *w, uint32_t now_ms) {
  uint32_t exempt = 0u;
  if (!w) return false;
  if (w->missed) return false;                                  /* latched: let the IWDG fire */
  if ((uint32_t)(now_ms - w->window_start_ms) < w->window_ms) return true;
  for (unsigned i = 0u; i < ZS_TASK_WATCH_MAX; i++)
    if ((w->hold_mask & (1u << i)) && (int32_t)(w->hold_until_ms[i] - now_ms) > 0) exempt |= 1u << i;
  {
    const uint32_t missing = w->registered & ~w->seen & ~exempt;
    if (missing) { w->missed = missing; w->windows_missed++; return false; }
  }
  w->windows_ok++;
  w->seen = 0u;
  w->window_start_ms = now_ms;
  return true;
}

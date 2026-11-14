/* Task liveness for the IWDG: healthy windows, a stuck task latches the miss, bounded holds, expired holds. */
#include "zs_task_watch.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
  zs_task_watch_t w;
  uint32_t t = 1000u;
  zs_task_watch_init(&w, 2000u, t);
  zs_task_watch_register(&w, 0u); zs_task_watch_register(&w, 3u); zs_task_watch_register(&w, 5u);
  /* first window: registration counts as a check-in */
  t += 2000u; assert(zs_task_watch_service(&w, t) && w.windows_ok == 1u);
  /* all check in -> fed */
  for (int k = 0; k < 5; k++) {
    zs_task_watch_checkin(&w, 0u); zs_task_watch_checkin(&w, 3u); zs_task_watch_checkin(&w, 5u);
    t += 500u; assert(zs_task_watch_service(&w, t));
    t += 1500u; assert(zs_task_watch_service(&w, t));
  }
  assert(w.windows_missed == 0u);
  /* task 3 holds for 10 s (bounded long operation), others keep checking in */
  zs_task_watch_hold(&w, 3u, 10000u, t);
  for (int k = 0; k < 4; k++) { zs_task_watch_checkin(&w, 0u); zs_task_watch_checkin(&w, 5u); t += 2000u; assert(zs_task_watch_service(&w, t)); }
  /* its check-in ends the hold early */
  zs_task_watch_checkin(&w, 3u); assert(!(w.hold_mask & (1u << 3)));
  zs_task_watch_checkin(&w, 0u); zs_task_watch_checkin(&w, 5u); t += 2000u; assert(zs_task_watch_service(&w, t));
  /* an expired hold is a miss */
  zs_task_watch_hold(&w, 3u, 3000u, t);
  zs_task_watch_checkin(&w, 0u); zs_task_watch_checkin(&w, 5u); t += 2000u; assert(zs_task_watch_service(&w, t));   /* still held */
  zs_task_watch_checkin(&w, 0u); zs_task_watch_checkin(&w, 5u); t += 2000u; assert(!zs_task_watch_service(&w, t) && w.missed == (1u << 3));
  /* latched: even if everybody checks in now, feeding stays off so the IWDG fires */
  zs_task_watch_checkin(&w, 0u); zs_task_watch_checkin(&w, 3u); zs_task_watch_checkin(&w, 5u); t += 2000u; assert(!zs_task_watch_service(&w, t));
  /* a stuck task in a fresh watch */
  zs_task_watch_init(&w, 1000u, 0u); zs_task_watch_register(&w, 1u); zs_task_watch_register(&w, 2u);
  assert(zs_task_watch_service(&w, 1000u));
  zs_task_watch_checkin(&w, 1u); assert(zs_task_watch_service(&w, 1500u));                        /* inside the window */
  assert(!zs_task_watch_service(&w, 2000u) && w.missed == (1u << 2) && w.windows_missed == 1u);
  printf("task watch tests passed\n");
  return 0;
}

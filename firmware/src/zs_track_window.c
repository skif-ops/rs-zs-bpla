#include "zs_track_window.h"

#include <string.h>

void zs_track_window_init(zs_track_window_t *t, uint32_t max_ms, uint16_t lost_windows) {
  if (!t) return;
  memset(t, 0, sizeof(*t));
  t->max_ms = max_ms;
  t->lost_windows = lost_windows ? lost_windows : 1u;
}

bool zs_track_window_on_event(zs_track_window_t *t, uint64_t track_event_id, bool link_ok, uint32_t now_ms) {
  if (!t || t->max_ms == 0u || track_event_id == 0u) return false;
  if (t->track_event_id == track_event_id) return false;   /* keep-alive update of the running (or a closed) track */
  if (!link_ok) { t->refused_link++; return false; }
  t->active = true;
  t->track_event_id = track_event_id;
  t->started_ms = now_ms;
  t->lost = 0u;
  t->windows = 0u;
  t->last_end = ZS_TRACK_END_NONE;
  t->tracks++;
  return true;
}

static zs_track_end_t close_with(zs_track_window_t *t, zs_track_end_t why) {
  t->active = false;
  t->last_end = why;
  if (why == ZS_TRACK_END_LOST) t->ended_lost++;
  else if (why == ZS_TRACK_END_MAX) t->ended_max++;
  else t->ended_mode++;
  return why;
}

zs_track_end_t zs_track_window_on_window(zs_track_window_t *t, bool confirmed, uint32_t now_ms) {
  if (!t || !t->active) return ZS_TRACK_END_NONE;
  t->windows++;
  t->lost = confirmed ? 0u : (uint16_t)(t->lost + 1u);
  if (t->lost >= t->lost_windows) return close_with(t, ZS_TRACK_END_LOST);
  if ((uint32_t)(now_ms - t->started_ms) >= t->max_ms) return close_with(t, ZS_TRACK_END_MAX);
  return ZS_TRACK_END_NONE;
}

void zs_track_window_end(zs_track_window_t *t) { if (t && t->active) (void)close_with(t, ZS_TRACK_END_MODE); }
bool zs_track_window_active(const zs_track_window_t *t) { return t && t->active; }

const char *zs_track_end_name(zs_track_end_t e) {
  static const char *const names[] = {"none", "target lost", "time limit", "mode"};
  return (unsigned)e < 4u ? names[e] : "?";
}

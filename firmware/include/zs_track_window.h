#ifndef ZS_TRACK_WINDOW_H
#define ZS_TRACK_WINDOW_H
/*
 * Tracking window (MQTT ICD addendum H): after a detection event the station keeps the detector running during the
 * modem session (S3) so every CONFIRMED window adds a bearing to the live stream.  The window is the energy cap of
 * that overlap (DSP + modem at once):
 *   - it opens on a detection event of a new track (the rising edge; keep-alive updates of the same track never open
 *     it, also not after it closed on the time limit) and only while the cellular link is healthy (LTE-only stream);
 *   - it closes after `lost_windows` consecutive windows without CONFIRMED (the target left or went quiet), after
 *     `max_ms` in total, or when the caller ends it (the mode left S1/S2/S3, service, shutdown).
 * Pure state, no HAL: the DSP task feeds it after every analysed window.
 */
#include <stdbool.h>
#include <stdint.h>

typedef enum {
  ZS_TRACK_END_NONE = 0,
  ZS_TRACK_END_LOST,        /* lost_windows windows without CONFIRMED */
  ZS_TRACK_END_MAX,         /* max_ms reached */
  ZS_TRACK_END_MODE         /* ended by the caller */
} zs_track_end_t;

typedef struct {
  uint32_t max_ms;
  uint16_t lost_windows;
  bool active;
  uint64_t track_event_id;
  uint32_t started_ms;
  uint16_t lost;
  uint32_t windows;           /* of the current track */
  zs_track_end_t last_end;
  uint32_t tracks, ended_lost, ended_max, ended_mode, refused_link;
} zs_track_window_t;

/* max_ms 0 disables tracking. */
void zs_track_window_init(zs_track_window_t *t, uint32_t max_ms, uint16_t lost_windows);
/* A detection event of track `track_event_id`; true when a window opened (a new track with a healthy link). */
bool zs_track_window_on_event(zs_track_window_t *t, uint64_t track_event_id, bool link_ok, uint32_t now_ms);
/* After every analysed window while active; returns the end reason when this window closed it (NONE otherwise). */
zs_track_end_t zs_track_window_on_window(zs_track_window_t *t, bool confirmed, uint32_t now_ms);
void zs_track_window_end(zs_track_window_t *t);
bool zs_track_window_active(const zs_track_window_t *t);
const char *zs_track_end_name(zs_track_end_t e);

#endif

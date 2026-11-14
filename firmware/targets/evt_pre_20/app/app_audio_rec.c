#include "app_audio_rec.h"

#include "FreeRTOS.h"
#include "app_config.h"
#include "app_watchdog.h"
#include "task.h"

static zs_prehistory_t ring;
static zs_audio_recorder_t recorder;
static const zs_audio_ring_t *capture_ring;
static void (*log_fn)(const char *fmt, ...);
static bool bound;
static TaskHandle_t rec_task;
static volatile bool capture_request;
static volatile uint32_t capture_request_seq;
static uint32_t capture_seen_seq;
static volatile uint8_t channel_request;
static uint32_t step_max_ms;
static zs_audio_recorder_time_fn time_fn;
typedef struct { uint64_t event_id; int64_t time_us; bool trusted; } event_entry_t;
static event_entry_t events[APP_AUDIO_EVENT_TABLE];
static unsigned events_next;

bool app_audio_rec_bind(const zs_archive_storage_t *storage, uint32_t base, uint32_t ring_bytes, const zs_audio_ring_t *capture,
                        zs_audio_recorder_time_fn sample_time, void (*log)(const char *fmt, ...)) {
  log_fn = log;
  capture_ring = capture;
  time_fn = sample_time;
  if (!storage || !capture || !zs_prehistory_init(&ring, storage, base, ring_bytes, APP_AUDIO_SAMPLE_RATE_HZ) ||
      !zs_audio_recorder_init(&recorder, &ring, sample_time, NULL)) {
    if (log_fn) log_fn("rec: prehistory ring not bound\r\n");
    return false;
  }
  if (!zs_prehistory_recover(&ring) && log_fn) log_fn("rec: ring recovery failed, starting empty\r\n");
  recorder.channel = channel_request;
  bound = true;
  if (log_fn) log_fn("rec: prehistory ring %lu records (%lu min), %lu recorded, next #%lu\r\n", (unsigned long)ring.record_count,
                     (unsigned long)(ring.record_count / 60u), (unsigned long)ring.available_records, (unsigned long)ring.next_sequence);
  return true;
}

void app_audio_rec_capture(bool on) { capture_request = on; capture_request_seq++; if (rec_task) xTaskNotifyGive(rec_task); }
void app_audio_rec_set_channel(uint8_t channel) { if (channel < ZS_AUDIO_CHANNELS) channel_request = channel; }
void app_audio_rec_notify(void) { if (rec_task) xTaskNotifyGive(rec_task); }
const zs_prehistory_t *app_audio_rec_ring(void) { return bound ? &ring : NULL; }

/* The audio task writes the 64-bit counter; read it until two reads agree (no torn value across the word halves). */
static uint64_t capture_total(void) {
  uint64_t a, b;
  do { a = capture_ring->total_frames; b = capture_ring->total_frames; } while (a != b);
  return a;
}

void app_audio_rec_task(void *arg) {
  (void)arg;
  rec_task = xTaskGetCurrentTaskHandle();
  for (;;) {
    (void)ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(200));
    app_watchdog_checkin(APP_WD_REC);
    if (!bound) continue;
    if (capture_seen_seq != capture_request_seq) {
      capture_seen_seq = capture_request_seq;
      if (capture_request) zs_audio_recorder_start(&recorder, capture_total());
      else zs_audio_recorder_stop(&recorder);
    }
    if (recorder.channel != channel_request) {           /* a new channel starts a new second */
      zs_audio_recorder_stop(&recorder);
      recorder.channel = channel_request;
      if (capture_request) zs_audio_recorder_start(&recorder, capture_total());
    }
    {
      const uint32_t t0 = xTaskGetTickCount();
      while (zs_audio_recorder_step(&recorder, capture_ring, capture_total(), APP_AUDIO_SAMPLE_RATE_HZ / 4u) == APP_AUDIO_SAMPLE_RATE_HZ / 4u)
        app_watchdog_checkin(APP_WD_REC);
      if ((uint32_t)(xTaskGetTickCount() - t0) > step_max_ms) step_max_ms = xTaskGetTickCount() - t0;
    }
  }
}

void app_audio_rec_note_event(uint64_t event_id, int64_t time_us, bool time_trusted) {
  taskENTER_CRITICAL();
  events[events_next] = (event_entry_t){event_id, time_us, time_trusted};
  events_next = (events_next + 1u) % APP_AUDIO_EVENT_TABLE;
  taskEXIT_CRITICAL();
}

/* ---- the upload's view (comms task); the 64-bit fields change in the rec / dsp tasks: copy them atomically ---- */
static const zs_prehistory_t *src_ring(void) { return bound ? &ring : NULL; }
static void src_range(uint64_t *oldest, uint64_t *next) {
  taskENTER_CRITICAL();
  *next = ring.next_sequence;
  *oldest = ring.next_sequence - ring.available_records;
  taskEXIT_CRITICAL();
}
static bool src_event_time(uint64_t event_id, int64_t *time_us, bool *trusted) {
  bool found = false;
  taskENTER_CRITICAL();
  for (unsigned i = 0u; i < APP_AUDIO_EVENT_TABLE; i++)
    if (events[i].event_id == event_id && event_id != 0u) { *time_us = events[i].time_us; *trusted = events[i].trusted; found = true; }
  taskEXIT_CRITICAL();
  return found;
}
static int64_t src_now_us(void) { return time_fn && capture_ring ? time_fn(NULL, capture_total()) : 0; }
static bool src_recording(void) { return capture_request; }
static const app_comms_audio_source_t source = {src_ring, src_range, src_event_time, src_now_us, src_recording};
const app_comms_audio_source_t *app_audio_rec_source(void) { return &source; }

void app_audio_rec_status(void (*print)(const char *fmt, ...)) {
  if (!bound) { print("rec: not bound (no NOR)\r\n"); return; }
  print("rec %s ch %u | ring %lu records, %lu recorded, next #%lu | committed %lu aborted %lu overruns %lu storage errors %lu | step max %lu ms\r\n",
        recorder.capturing ? "capturing" : "idle", recorder.channel, (unsigned long)ring.record_count, (unsigned long)ring.available_records,
        (unsigned long)ring.next_sequence, (unsigned long)recorder.frames_committed, (unsigned long)recorder.frames_aborted,
        (unsigned long)recorder.overruns, (unsigned long)recorder.storage_errors, (unsigned long)step_max_ms);
}

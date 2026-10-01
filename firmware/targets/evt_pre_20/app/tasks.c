/*
 * Milestone B1 task set (bring-up on NUCLEO-U575 / Rev.A):
 *   audio       - converts MDF blocks, drives PPS binding, computes block peaks
 *   supervisor  - zs_power_modes scheduler, self-tests, rail enables, console status line
 *   console     - LPUART1 line commands for the bench: "st" (self-test), "lag", "svc", "modes", "pps"
 *   gnss        - NMEA: RMC labels the PPS seconds, GGA fixes give the station position (zs_station_position)
 *   ble         - zs_ipc_service over USART3 to the nRF52840 bridge (ICD addendum C), window with S4 SERVICE
 *   dsp         - zs_station_pipeline: 1 s windows at a 0.5 s hop -> zs_dsp_mcu -> votes + AIR gate -> level 1 ->
 *                 detection events into the NOR outbox (fetch in the audio task, analysis here); after an event of a
 *                 new track the tracking window keeps it running in S3 and streams the bearings (addendum H)
 *   comms       - app_comms: BG95 bring-up from the station configuration, MQTT session, outbox drain + heartbeat (B2)
 *   power       - app_power: INA226 on I2C2 every second -> power snapshot for heartbeat, events and the self-test
 *   lora        - app_lora: SX1262 fallback uplink of the outbox while the GSM link is degraded (DRY until the RF gate)
 *   rec         - app_audio_rec: mono audio from the capture ring into the NOR prehistory ring (addendum B)
 */
#include "tasks.h"

#include "FreeRTOS.h"
#include "app_config.h"
#include "app_comms.h"
#include "app_audio_rec.h"
#include "app_commands.h"
#include "app_fw.h"
#include "app_lora.h"
#include "app_watchdog.h"
#include "app_nrf_update.h"
#include "app_power.h"
#include "bsp_gpio.h"
#include "bsp_mdf.h"
#include "bsp_nor.h"
#include "bsp_rng.h"
#include "bsp_tim2_pps.h"
#include "bsp_uart.h"
#include "evt_pre_20_clock_policy.h"
#include "queue.h"
#include "task.h"
#include "zs_audio.h"
#include "zs_boot_counter.h"
#include "zs_command_clock.h"
#include "zs_dsp_mcu.h"
#include "zs_ipc_service.h"
#include "zs_nor_slot_store.h"
#include "zs_nor_storage_layout.h"
#include "zs_pdm_capture.h"
#include "zs_power_modes.h"
#include "zs_pps_sync.h"
#include "zs_selftest.h"
#include "zs_station_pipeline.h"
#include "zs_station_position.h"
#include "zs_gnss.h"
#include "zs_installation_store.h"
#include "zs_station_secrets.h"
#include "zs_command_keys.h"
#include "zs_time.h"
#include "zs_track_window.h"
#include "zs_event_outbox.h"
#include "zs_model_store.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "stm32u5xx_hal.h"

/* ---- shared state ---------------------------------------------------------- */
static int16_t audio_storage[APP_AUDIO_RING_FRAMES_B1 * ZS_AUDIO_CHANNELS] __attribute__((section(".bss"), aligned(4)));
static zs_audio_ring_t audio_ring;
static zs_pdm_capture_t capture;
static zs_time_sync_t time_sync;
static zs_pps_sync_t pps;
static zs_mode_scheduler_t modes;
static zs_selftest_registry_t selftests;
static int16_t dsp_pcm[APP_AUDIO_SAMPLE_RATE_HZ] __attribute__((section(".bss"), aligned(4)));   /* 1 s mono window of the pipeline */
static zs_dsp_ctx_t dsp_ctx;
static zs_station_pipeline_t pipeline;
static uint32_t pipeline_last_ms, pipeline_max_ms, pipeline_events_ram;

static TaskHandle_t audio_task, supervisor_task, console_task, gnss_task, ble_task, dsp_task, comms_task, power_task, lora_task, rec_task;

/* ---- ISR notifications ----------------------------------------------------- */
void app_audio_block_notify_from_isr(void) {
  BaseType_t woken = pdFALSE;
  if (audio_task) vTaskNotifyGiveFromISR(audio_task, &woken);
  portYIELD_FROM_ISR(woken);
}

void app_uart_rx_notify_from_isr(bsp_uart_id_t id) {
  BaseType_t woken = pdFALSE;
  TaskHandle_t t = id == BSP_UART_CONSOLE ? console_task : id == BSP_UART_GNSS ? gnss_task : id == BSP_UART_BLE ? ble_task : id == BSP_UART_CELL ? comms_task : NULL;
  if (t) vTaskNotifyGiveFromISR(t, &woken);
  portYIELD_FROM_ISR(woken);
}

void HAL_GPIO_EXTI_Rising_Callback(uint16_t pin) {
  if (pin == GPIO_PIN_8 && supervisor_task) {        /* MIC_WAKE */
    BaseType_t woken = pdFALSE;
    xTaskNotifyFromISR(supervisor_task, 1u << ZS_MODE_EV_MIC_WAKE, eSetBits, &woken);
    portYIELD_FROM_ISR(woken);
  }
}

/* Mode scheduler events raised by the tasks (the supervisor consumes them as notification bits). */
static void mode_event(zs_mode_event_t ev) { if (supervisor_task) (void)xTaskNotify(supervisor_task, 1u << ev, eSetBits); }

/* ---- console output -------------------------------------------------------- */
static void console_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void console_printf(const char *fmt, ...) {
  char line[160];
  va_list ap;
  int n;
  va_start(ap, fmt);
  n = vsnprintf(line, sizeof(line), fmt, ap);
  va_end(ap);
  if (n > 0) bsp_uart_write(BSP_UART_CONSOLE, (const uint8_t *)line, (size_t)(n < (int)sizeof(line) ? n : (int)sizeof(line) - 1));
}

/* ---- self-tests bound to the B1 hardware ----------------------------------- */
/* The capture counters grow for the whole boot; a self-test judges the window it ran in (selftest_window below),
   so one DMA overrun at boot does not fail every later retest. */
static uint32_t st_blocks_base, st_overruns_base;
static zs_selftest_code_t st_mic_capture(void *ctx, uint32_t *detail) {
  const zs_pdm_capture_t *c = ctx;
  int16_t min_peak = 32767;
  if (c->blocks_processed - st_blocks_base < 10u) return ZS_ST_SKIPPED;
  for (unsigned i = 0u; i < ZS_PDM_CHANNELS; i++) if (c->peak[i] < min_peak) min_peak = c->peak[i];
  *detail = (uint32_t)min_peak;
  return (min_peak > 8 && c->overruns == st_overruns_base) ? ZS_ST_PASS : ZS_ST_FAIL;   /* dead channel or DMA overrun */
}

static zs_selftest_code_t st_mic_alignment(void *ctx, uint32_t *detail) {
  const zs_pdm_capture_t *c = ctx;
  int worst = 0;
  for (unsigned ch = 1u; ch < ZS_PDM_CHANNELS; ch++) {
    int lag;
    if (!zs_pdm_capture_channel_lag(c, ch, 2048u, 8, &lag)) return ZS_ST_SKIPPED;   /* silence: needs the bench source */
    if (abs(lag) > worst) worst = abs(lag);
  }
  *detail = (uint32_t)worst;
  return worst == 0 ? ZS_ST_PASS : ZS_ST_FAIL;
}

static zs_selftest_code_t st_gnss_pps(void *ctx, uint32_t *detail) {
  const zs_pps_sync_t *p = ctx;
  *detail = p->bound_count;
  if (bsp_tim2_pps_edges() == 0u) return ZS_ST_SKIPPED;
  return p->bound_count > 0u ? ZS_ST_PASS : ZS_ST_FAIL;
}

/* PWR_GOOD/PWR_FAULT from PCB-PWR decide; the INA226 bus voltage is the detail (0 until the first valid sample). */
static zs_selftest_code_t st_power_good(void *ctx, uint32_t *detail) {
  (void)ctx;
  *detail = app_power_battery_mv();
  return (bsp_gpio_power_good() && !bsp_gpio_power_fault()) ? ZS_ST_PASS : ZS_ST_FAIL;
}

static zs_selftest_code_t st_rtc_lse(void *ctx, uint32_t *detail) {
  (void)ctx;
  *detail = 0u;
  return (RCC->BDCR & RCC_BDCR_LSERDY) ? ZS_ST_PASS : ZS_ST_FAIL;
}

/* Capture pauses: the sample counter stops with the PDM clock while time goes on.  The supervisor measures each
   pause (capture_set) and the audio task applies it to the time mapping and the PPS binder before it touches the
   first block after the restart (zs_time_on_capture_gap / zs_pps_sync_on_capture_gap). */
static volatile uint32_t capture_gap_pending_ms;
static void apply_capture_gap(void) {
  uint32_t gap;
  taskENTER_CRITICAL();                              /* the MDF block ISR also writes the PPS marks */
  gap = capture_gap_pending_ms;
  capture_gap_pending_ms = 0u;
  if (gap) { zs_time_on_capture_gap(&time_sync, (int64_t)gap * 1000); zs_pps_sync_on_capture_gap(&pps); }
  taskEXIT_CRITICAL();
}

/* Tracking window (addendum H): opened by the DSP task on an event of a new track, it keeps the capture and the
   detector running through S3 and the bearings flowing to the comms task; closed after APP_TRACK_LOST_WINDOWS windows
   without CONFIRMED, after track_max_s (CMD_SET_PARAMS id 7), or when the supervisor asks (the mode left S3, sleep,
   service). */
static zs_track_window_t track;
static volatile uint32_t track_max_ms = (uint32_t)ZS_PARAM_TRACK_MAX_S_DEFAULT * 1000u;   /* params_apply writes it */
static volatile bool track_open;             /* DSP task writes; audio task and supervisor read */
static volatile bool track_close_request;    /* supervisor -> DSP task */
static volatile bool track_s3_extension;     /* a window opened in this S3 episode: its watchdog is extended until S3 ends */
static bool gsm_degraded;                    /* defined with the GSM health below */

/* ---- tasks ------------------------------------------------------------------ */
static void audio_task_fn(void *arg) {
  (void)arg;
  for (;;) {
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100));
    app_watchdog_checkin(APP_WD_AUDIO);
    apply_capture_gap();
    while (zs_pdm_capture_process(&capture)) {}
    app_audio_rec_notify();                        /* the recorder follows the capture ring */
    (void)zs_pps_sync_poll(&pps, bsp_tim2_pps_now());
    (void)zs_time_update(&time_sync, zs_pdm_capture_sample_counter(&capture));
    /* listen/detection duty (S1 and S2 keep the PDM clock): copy the next complete window out of the ring while it is
       still there, hand it to the DSP task; a window that is still pending when the next one completes is skipped
       (dropped). S1 runs the same pipeline as S2 for now - the gate IS the pipeline's AIR gate + level 1; a cheaper
       listen-only gate is low-power work. */
    if ((modes.mode == ZS_MODE_S1_LISTEN || modes.mode == ZS_MODE_S2_DSP || track_open) && dsp_task && zs_station_pipeline_fetch(&pipeline, &audio_ring))
      xTaskNotifyGive(dsp_task);
  }
}

/* ---- station pipeline ports ------------------------------------------------ */
static bool pl_extract(void *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) { (void)ctx; return zs_dsp_mcu_extract_1s(&dsp_ctx, pcm, n, out); }
static int64_t pl_sample_time(void *ctx, uint64_t sample) { (void)ctx; return zs_time_for_sample(&time_sync, sample); }
static bool pl_emit(void *ctx, const zs_detection_t *d);
/* every bearing of a CONFIRMED window while the tracking window is open goes to the live stream (addendum H), under
   the window's track: a level-1 flicker inside the window (a new rising edge, a new event id) stays one track */
static void pl_bearing(void *ctx, const zs_bearing_t *b, uint64_t end_sample, uint64_t track_event_id) {
  zs_bearing_record_t r;
  (void)ctx; (void)track_event_id;
  if (!track_open) return;
  if (zs_bearing_record_from(&r, track.track_event_id, zs_time_for_sample(&time_sync, end_sample), (uint8_t)time_sync.trust, b)) app_comms_bearing_push(&r);
}
/* boot_id starts as APP_BOOT_ID and is replaced by the NOR boot counter once the stores are bound (the pipeline reads it per event) */
static zs_station_pipeline_port_t pipeline_port = {NULL, pl_extract, pl_sample_time, pl_emit, APP_STATION_ID, APP_BOOT_ID, 0u, 0u, NULL, pl_bearing};
static uint32_t boot_id = APP_BOOT_ID;

/* Capture after an event: S3 and S0 stop the PDM clock, so without this the 30 s after a detection (the post-event
   audio segment of addendum B) would never be recorded.  Set by the DSP task, read by the supervisor. */
static volatile uint32_t post_capture_until_ms;
static void post_capture_open(void) { post_capture_until_ms = xTaskGetTickCount() + APP_AUDIO_POST_EVENT_MS; }

/* The tracking window after every analysed window: an event of a new track opens it (LTE link healthy), the level
   of the window or the supervisor's request closes it. */
static void track_step(bool new_event) {
  const uint32_t now = xTaskGetTickCount();
  zs_track_end_t end = ZS_TRACK_END_NONE;
  track.max_ms = track_max_ms;                                            /* a CMD_SET_PARAMS also reaches an open window */
  if (new_event && zs_track_window_on_event(&track, pipeline.track_event_id, !gsm_degraded, now)) {
    track_open = true;
    track_s3_extension = true;
    track_close_request = false;
    app_comms_set_tracking(true);
    console_printf("track: window open for event %lu:%lu (max %lu s)\r\n", (unsigned long)(track.track_event_id >> 32),
                   (unsigned long)(track.track_event_id & 0xffffffffu), (unsigned long)(track.max_ms / 1000u));
    return;
  }
  if (!track_open) return;
  if (track_close_request) { zs_track_window_end(&track); end = ZS_TRACK_END_MODE; }
  else end = zs_track_window_on_window(&track, pipeline.presence.level == ZS_PRESENCE_CONFIRMED, now);
  if (end == ZS_TRACK_END_NONE) return;
  track_open = false;
  track_close_request = false;
  app_comms_set_tracking(false);
  console_printf("track: window closed (%s) after %lu windows\r\n", zs_track_end_name(end), (unsigned long)track.windows);
}

/* Mode events from the pipeline: level 1 SUSPECT or above in S1 opens S2 (gate positive); in S2 an emitted event
   moves to S3 (outbox has data) and APP_DSP_QUIET_WINDOWS windows of NONE end the DSP duty. */
static void dsp_mode_events(void) {
  static uint32_t seen_events;
  static unsigned quiet_windows;
  const uint8_t level = pipeline.presence.level;
  track_step(pipeline.events_emitted != seen_events && (modes.mode == ZS_MODE_S1_LISTEN || modes.mode == ZS_MODE_S2_DSP));
  if (modes.mode == ZS_MODE_S1_LISTEN) {
    quiet_windows = 0u;
    if (level >= ZS_PRESENCE_SUSPECT) mode_event(ZS_MODE_EV_GATE_POSITIVE);
    if (pipeline.events_emitted != seen_events) { seen_events = pipeline.events_emitted; post_capture_open(); mode_event(ZS_MODE_EV_OUTBOX_PENDING); }
    return;
  }
  if (modes.mode != ZS_MODE_S2_DSP) { quiet_windows = 0u; seen_events = pipeline.events_emitted; return; }
  if (pipeline.events_emitted != seen_events) { seen_events = pipeline.events_emitted; quiet_windows = 0u; post_capture_open(); mode_event(ZS_MODE_EV_DSP_DONE_EVENT); return; }
  if (level == ZS_PRESENCE_NONE) { if (++quiet_windows >= APP_DSP_QUIET_WINDOWS) { quiet_windows = 0u; mode_event(ZS_MODE_EV_DSP_DONE_NOTHING); } }
  else quiet_windows = 0u;
}

static void dsp_task_fn(void *arg) {
  (void)arg;
  for (;;) {
    (void)ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));          /* timed wait: the watchdog sees an idle DSP as alive */
    app_watchdog_checkin(APP_WD_DSP);
    while (pipeline.pending) {
      const uint32_t t0 = xTaskGetTickCount();
      (void)zs_station_pipeline_run_pending(&pipeline);
      pipeline_last_ms = xTaskGetTickCount() - t0;
      if (pipeline_last_ms > pipeline_max_ms) pipeline_max_ms = pipeline_last_ms;
      dsp_mode_events();
    }
  }
}

/* The PDM capture: on where the mode table says so, and in any mode but SHUTDOWN during the post-event window (S3,
   and the S0 that may follow it, would otherwise cut the post-event segment short; the window costs 30 s without
   deep sleep per event).  Every start/stop is told to the recorder, which keeps only complete, continuous seconds. */
static bool capture_on, capture_was_stopped;
static uint32_t capture_stopped_ms;
static bool capture_wanted(zs_mode_t mode) {
  return zs_mode_power_for(mode).mdf_clock ||
         (mode != ZS_MODE_SHUTDOWN && ((int32_t)(xTaskGetTickCount() - post_capture_until_ms) < 0 || track_open));
}
static void capture_set(bool on) {
  if (on == capture_on) return;
  capture_on = on;
  if (on) {
    if (capture_was_stopped) {                       /* the pause, before the first block after the restart */
      taskENTER_CRITICAL();
      capture_gap_pending_ms += xTaskGetTickCount() - capture_stopped_ms;
      taskEXIT_CRITICAL();
    }
    (void)bsp_mdf_start();
  } else {
    bsp_mdf_stop();
    capture_stopped_ms = xTaskGetTickCount();
    capture_was_stopped = true;
  }
  app_audio_rec_capture(on);
}

static void apply_power(zs_mode_t mode) {
  zs_mode_power_t p = zs_mode_power_for(mode);
  bsp_gpio_mic_rail(p.mic_1v8);
  app_comms_allow_modem(p.modem);                 /* EN_MODEM belongs to the comms task (graceful off, dual-SIM sequence) */
  capture_set(capture_wanted(mode));
  /* clock profile switching (S0 STOP2 etc.) lands with the low-power work; B1 keeps 160 MHz */
  (void)zs_mode_clock_profile(mode);
}


static uint32_t tamper_events;

/* Outbox retry: events left in the NOR outbox after an S3 that did not finish (no network, S3 watchdog) are
   re-offered to the scheduler with a backoff (APP_OUTBOX_RETRY_MS, doubling up to APP_OUTBOX_RETRY_MAX_MS);
   a completed session (COMMS_DONE) resets it.  Without this an event emitted during a GSM outage waited for the
   next detection or reboot (found by the station twin). */
static uint32_t outbox_retry_at_ms, outbox_retry_backoff_ms = APP_OUTBOX_RETRY_MS, outbox_retries;
static bool outbox_has_pending(void);
static void outbox_retry_tick(uint32_t now) {
  static uint32_t last_check_ms;
  if ((uint32_t)(now - last_check_ms) < 10000u) return;
  last_check_ms = now;
  if (modes.mode == ZS_MODE_S3_COMMS || modes.mode == ZS_MODE_S4_SERVICE) return;
  if (!outbox_has_pending()) { outbox_retry_at_ms = 0u; return; }
  if (outbox_retry_at_ms == 0u) { outbox_retry_at_ms = now + outbox_retry_backoff_ms; return; }
  if ((int32_t)(now - outbox_retry_at_ms) < 0) return;
  outbox_retries++;
  console_printf("outbox: events still pending, retry S3 (backoff %lu s)\r\n", (unsigned long)(outbox_retry_backoff_ms / 1000u));
  mode_event(ZS_MODE_EV_OUTBOX_PENDING);
  if (outbox_retry_backoff_ms < APP_OUTBOX_RETRY_MAX_MS) outbox_retry_backoff_ms *= 2u;
  outbox_retry_at_ms = now + outbox_retry_backoff_ms;
}

/* GSM health: consecutive S3 sessions that end without COMMS_DONE (watchdog) mark the link degraded after
   APP_COMMS_DEGRADED_AFTER: the S3 watchdog drops to APP_COMMS_MAX_DEGRADED_MS so a dead network costs less
   modem time per retry, and the route hint (app_route_hint_lora) is set for the LoRa transport; a completed
   session restores the defaults. */
static unsigned comms_fail_streak;
/* S3 watchdog = this base (default, or APP_COMMS_MAX_DEGRADED_MS while degraded) + APP_AUDIO_UPLOAD_MAX_MS while an
   audio upload runs (the supervisor applies it every tick). */
static uint32_t comms_max_base_ms;
/* runtime parameters (CMD_SET_PARAMS, zs_station_params); compile-time values until the record is applied */
static unsigned comms_degraded_after = APP_COMMS_DEGRADED_AFTER;
static uint32_t gsm_probe_ms = APP_GSM_PROBE_MS;
static uint32_t last_s3_exit_ms;
bool app_route_hint_lora(void) { return gsm_degraded; }
/* While degraded, probe GSM every APP_GSM_PROBE_MS with a capped S3: a completed session restores the link. */
static void gsm_probe_tick(uint32_t now) {
  if (!gsm_degraded || modes.mode == ZS_MODE_S3_COMMS || modes.mode == ZS_MODE_S4_SERVICE) return;
  if ((uint32_t)(now - last_s3_exit_ms) < gsm_probe_ms) return;
  last_s3_exit_ms = now;
  console_printf("comms: gsm probe\r\n");
  mode_event(ZS_MODE_EV_OUTBOX_PENDING);
}
static void comms_health_on_s3_exit(bool done) {
  last_s3_exit_ms = xTaskGetTickCount();
  if (done) { comms_fail_streak = 0u; if (gsm_degraded) { gsm_degraded = false; comms_max_base_ms = zs_mode_policy_default().comms_max_ms; app_lora_set_route_hint(false); console_printf("comms: link healthy again\r\n"); } return; }
  comms_fail_streak++;
  if (!gsm_degraded && comms_fail_streak >= comms_degraded_after) {
    gsm_degraded = true;
    comms_max_base_ms = APP_COMMS_MAX_DEGRADED_MS;
    app_lora_set_route_hint(true);
    console_printf("comms: DEGRADED after %u failed sessions, S3 watchdog %lu s, route hint lora\r\n", comms_fail_streak, (unsigned long)(APP_COMMS_MAX_DEGRADED_MS / 1000u));
  }
}

/* CMD_SET_PARAMS (addendum D): the stored or commanded parameter set takes effect here.  Called from the ble task
   at bind time, from the comms task by the executor and from the supervisor after the scheduler init; every target
   is a single aligned word or byte. */
static void params_apply(const zs_station_params_t *p) {
  modes.policy.heartbeat_period_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_HEARTBEAT_PERIOD_S) * 1000u;
  modes.policy.listen_dwell_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_LISTEN_DWELL_S) * 1000u;
  pipeline_port.channel = (uint8_t)zs_station_params_get(p, ZS_PARAM_MIC_CHANNEL);
  app_audio_rec_set_channel(pipeline_port.channel);                       /* the prehistory records the analysed channel */
  pipeline_port.update_period_windows = (uint8_t)zs_station_params_get(p, ZS_PARAM_EVENT_UPDATE_WINDOWS);
  comms_degraded_after = (unsigned)zs_station_params_get(p, ZS_PARAM_COMMS_DEGRADED_AFTER);
  gsm_probe_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_GSM_PROBE_S) * 1000u;
  track_max_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_TRACK_MAX_S) * 1000u;
}

/* The self-test window: capture on for 300 ms (the microphone tests need blocks), every registered test, capture
   back to what the mode wants.  At boot and, while a required test is failed, after every session: a transient
   failure (a slow LSE start, a DMA overrun at boot) recovers without a site visit or a remote reboot.  At boot the
   capture stays on (the first mode change applies the mode's power); a retest hands it back to the mode. */
static bool selftest_window(bool restore) {
  bool ok;
  st_blocks_base = capture.blocks_processed;
  st_overruns_base = capture.overruns;
  bsp_gpio_mic_rail(true);
  vTaskDelay(pdMS_TO_TICKS(50));                 /* 1V8_MIC settle before the PDM clock */
  capture_set(true);
  vTaskDelay(pdMS_TO_TICKS(300));                /* let the capture stabilise for the self-tests */
  ok = zs_selftest_run_all(&selftests, xTaskGetTickCount());
  console_printf("selftest: %s (failed mask 0x%04x)\r\n", ok ? "PASS" : "required test FAILED", (unsigned)zs_selftest_failed_mask(&selftests));
  if (restore) {
    bsp_gpio_mic_rail(zs_mode_power_for(modes.mode).mic_1v8);
    capture_set(capture_wanted(modes.mode));
  }
  return ok;
}

static void supervisor_task_fn(void *arg) {
  zs_mode_t last = ZS_MODE_SHUTDOWN;
  uint32_t tamper_since = 0u;
  bool tamper_fired = false;
  (void)arg;
  zs_mode_init(&modes, NULL, xTaskGetTickCount());
  comms_max_base_ms = modes.policy.comms_max_ms;
  params_apply(app_commands_params());             /* the init reset the policy: re-apply the stored parameters */
  /* a failed required test does not silence the station: BOOT_FAILED reports it in a session at once and keeps it
     reachable (heartbeat, commands, service) with the detector off; the test is repeated after every session */
  (void)zs_mode_on_event(&modes, selftest_window(false) ? ZS_MODE_EV_BOOT_DONE : ZS_MODE_EV_BOOT_FAILED, xTaskGetTickCount());
  app_watchdog_start();
  console_printf("boot: reset cause %s%s, watchdog running (%lu s)\r\n", app_watchdog_reset_cause_name(),
                 app_watchdog_previous_missed() ? " - a supervised task had stopped" : "", (unsigned long)(APP_WATCHDOG_TIMEOUT_MS / 1000u));
  for (;;) {
    uint32_t bits = 0u;
    uint32_t now;
    (void)xTaskNotifyWait(0u, UINT32_MAX, &bits, pdMS_TO_TICKS(100));
    now = xTaskGetTickCount();
    for (unsigned ev = 1u; ev < 32u; ev++) if (bits & (1u << ev)) (void)zs_mode_on_event(&modes, (zs_mode_event_t)ev, now);
    modes.policy.comms_max_ms = comms_max_base_ms + (app_comms_audio_busy() ? APP_AUDIO_UPLOAD_MAX_MS : 0u) +
                                (app_comms_fw_busy() ? APP_FW_UPDATE_MAX_MS : 0u) + (app_comms_net_busy() ? APP_NET_TRIAL_MAX_MS : 0u) +
                                (track_s3_extension ? track_max_ms : 0u);
    (void)zs_mode_tick(&modes, now);
    app_watchdog_service();
    app_commands_tick(now);
    app_fw_tick(now);
    if (capture_on && !capture_wanted(modes.mode)) capture_set(false);   /* the post-event window closed */
    outbox_retry_tick(now);
    gsm_probe_tick(now);
    if (bsp_gpio_power_fault()) (void)zs_mode_on_event(&modes, ZS_MODE_EV_FAULT, now);
    /* TAMPER_IN as service trigger: 5 s continuous activation requests service mode (once per activation);
       shorter activations are counted as tamper events for the security log. */
    if (bsp_gpio_service_button()) {
      if (tamper_since == 0u) tamper_since = now ? now : 1u;
      else if (!tamper_fired && (uint32_t)(now - tamper_since) >= APP_SERVICE_HOLD_MS) {
        tamper_fired = true;
        (void)zs_mode_on_event(&modes, ZS_MODE_EV_SERVICE_BUTTON, now);
      }
    } else if (tamper_since != 0u) {
      if (!tamper_fired) tamper_events++;
      tamper_since = 0u;
      tamper_fired = false;
    }
    if (modes.mode != last) {
      console_printf("mode %s -> %s\r\n", zs_mode_name(last), zs_mode_name(modes.mode));
      if (last == ZS_MODE_S3_COMMS) comms_health_on_s3_exit(modes.journal[(modes.journal_head + ZS_MODE_JOURNAL_DEPTH - 1u) % ZS_MODE_JOURNAL_DEPTH].event == ZS_MODE_EV_COMMS_DONE);
      /* the tracking window lives in S2/S3 only: the session is gone, or sleep / service / shutdown */
      if (last == ZS_MODE_S3_COMMS) track_s3_extension = false;
      if (track_open && (last == ZS_MODE_S3_COMMS || modes.mode == ZS_MODE_S0_SLEEP || modes.mode == ZS_MODE_S4_SERVICE || modes.mode == ZS_MODE_SHUTDOWN))
        track_close_request = true;
      apply_power(modes.mode);
      last = modes.mode;
      /* retest after a session while failed: a pass resumes the normal boot path (detection, a session saying so) */
      if (modes.selftest_failed && modes.mode == ZS_MODE_S0_SLEEP && selftest_window(true)) {
        console_printf("selftest: recovered, detection resumes\r\n");
        (void)zs_mode_on_event(&modes, ZS_MODE_EV_BOOT_DONE, xTaskGetTickCount());
      }
    }
  }
}

/* Minimal RMC parser: "$GNRMC,hhmmss.ss,A,...,ddmmyy,..." -> epoch microseconds of the second boundary. */
static bool rmc_epoch_us(const char *line, int64_t *epoch_us) {
  const char *f[13];
  unsigned n = 0u;
  int hh, mm, ss, dd, mo, yy;
  int64_t days;
  static const int cum[12] = {0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334};
  if (strncmp(line, "$GNRMC,", 7) != 0 && strncmp(line, "$GPRMC,", 7) != 0) return false;
  f[n++] = line;
  for (const char *p = line; *p && n < 13u; p++) if (*p == ',') f[n++] = p + 1;
  if (n < 10u || f[2][0] != 'A') return false;
  if (sscanf(f[1], "%2d%2d%2d", &hh, &mm, &ss) != 3 || sscanf(f[9], "%2d%2d%2d", &dd, &mo, &yy) != 3) return false;
  yy += 2000;
  days = (int64_t)(yy - 1970) * 365 + (yy - 1969) / 4 + cum[mo - 1] + (dd - 1) + ((mo > 2 && yy % 4 == 0) ? 1 : 0);
  *epoch_us = ((days * 86400 + hh * 3600 + mm * 60 + ss) * 1000000LL);
  return true;
}

/* ---- station position (zs_station_position): the GNSS task owns `station_pos` (its GGA fixes, the installation
   record) and publishes a copy after every change; pl_emit (DSP task) and the heartbeat (comms task) fill the station
   map from that copy.  The BLE task loads the installation record at boot and after every commissioning attempt
   and hands it over through `installation_pending`. ---- */
static zs_station_position_t station_pos, station_pos_shared;
static zs_position_trust_config_t installation_pending;
static volatile bool installation_pending_set;
static volatile bool installation_reload_pending;             /* ble_audit -> BLE task: a commissioning attempt ended */

static void station_pos_publish(void) {
  taskENTER_CRITICAL();
  station_pos_shared = station_pos;
  taskEXIT_CRITICAL();
}
static bool station_pos_fill(zs_position_t *station, zs_gnss_t *gnss) {
  zs_station_position_t snap;
  taskENTER_CRITICAL();
  snap = station_pos_shared;
  taskEXIT_CRITICAL();
  return zs_station_position_fill(&snap, xTaskGetTickCount(), station, gnss);
}
static void gnss_task_fn(void *arg) {
  static char line[96];
  static zs_gnss_nmea_t nmea;
  size_t len = 0u;
  (void)arg;
  zs_gnss_nmea_init(&nmea);
  zs_station_position_init(&station_pos);
  for (;;) {
    uint8_t buf[32];
    size_t n;
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(500));
    app_watchdog_checkin(APP_WD_GNSS);
    if (installation_pending_set) {
      zs_position_trust_config_t cfg;
      taskENTER_CRITICAL();
      cfg = installation_pending;
      installation_pending_set = false;
      taskEXIT_CRITICAL();
      zs_station_position_set_installation(&station_pos, &cfg);
      station_pos_publish();
    }
    while ((n = bsp_uart_read(BSP_UART_GNSS, buf, sizeof(buf))) > 0u) {
      for (size_t i = 0u; i < n; i++) {
        char c = (char)buf[i];
        if (c == '\n') {
          int64_t epoch;
          line[len] = '\0';
          if (rmc_epoch_us(line, &epoch)) zs_pps_sync_on_utc(&pps, epoch);   /* the RMC follows the PPS edge it labels */
          /* the GGA fixes: the station position of uncommissioned stations, a check of the installation otherwise */
          zs_station_position_set_gnss_suspect(&station_pos, zs_time_suspect(&time_sync));   /* a GNSS time jump: its fixes neither */
          if (zs_gnss_parse_line(&nmea, line) && zs_station_position_on_gnss(&station_pos, &nmea, xTaskGetTickCount())) station_pos_publish();
          len = 0u;
        } else if (c != '\r' && len + 1u < sizeof(line)) {
          line[len++] = c;
        } else if (c != '\r') {
          len = 0u;
        }
      }
    }
  }
}


/* ---- BLE service window: STM32 side of the GATT contract over the nRF52840 bridge (USART3) ------------
   B3: configuration and installation records live in the NOR record stores (zs_nor_storage_layout_make_stores:
   the last four 4 KiB blocks of the W25Q512JV); if the NOR probe fails on the bench the task falls back to
   RAM-backed slots so BLE bring-up still works.  The role is the installer and "secure" follows the link
   state reported by the nRF (LESC passkey from the label secret, B.7).  The advertising window opens with
   S4 SERVICE and closes when the mode leaves it. */
static zs_ipc_service_t ipc;
static uint8_t cfg_slots[ZS_STATION_CONFIG_SLOT_COUNT][ZS_STATION_CONFIG_SLOT_BYTES];
static uint8_t pos_slots[ZS_INSTALLATION_STORE_SLOT_COUNT][ZS_INSTALLATION_STORE_SLOT_BYTES];
static uint32_t service_started_ms, ble_audit_events;
static zs_nor_t nor;
static zs_nor_storage_bindings_t nor_bindings;
static zs_archive_storage_t nor_archive_storage;      /* the audio prehistory ring (app_audio_rec) */
static zs_command_journal_io_t nor_command_io;
static zs_event_outbox_io_t nor_outbox_io;
static zs_boot_counter_t boot_counter;
static bool stores_on_nor;

static bool ram_read(void *ctx, uint8_t slot, uint32_t off, uint8_t *d, size_t n) {
  const size_t bytes = ctx == cfg_slots ? ZS_STATION_CONFIG_SLOT_BYTES : ZS_INSTALLATION_STORE_SLOT_BYTES;
  if (slot >= 2u || off + n > bytes) return false;
  memcpy(d, (uint8_t *)ctx + slot * bytes + off, n);
  return true;
}
static bool ram_erase(void *ctx, uint8_t slot) {
  const size_t bytes = ctx == cfg_slots ? ZS_STATION_CONFIG_SLOT_BYTES : ZS_INSTALLATION_STORE_SLOT_BYTES;
  if (slot >= 2u) return false;
  memset((uint8_t *)ctx + slot * bytes, 0xff, bytes);
  return true;
}
static bool ram_write(void *ctx, uint8_t slot, uint32_t off, const uint8_t *d, size_t n) {
  const size_t bytes = ctx == cfg_slots ? ZS_STATION_CONFIG_SLOT_BYTES : ZS_INSTALLATION_STORE_SLOT_BYTES;
  uint8_t *p = (uint8_t *)ctx + slot * bytes + off;
  if (slot >= 2u || off + n > bytes) return false;
  for (size_t i = 0u; i < n; i++) { if ((p[i] & d[i]) != d[i]) return false; p[i] = d[i]; }
  return true;
}
static bool ble_audit(void *ctx, const zs_commissioning_audit_event_t *e) {
  (void)ctx;
  ble_audit_events++;
  /* after every commissioning attempt the BLE task re-reads the record: it can be stored even when the final audit
     entry fails (AUDIT_FINALIZE_FAILED, READBACK_FAILED), and re-reading an unchanged record changes nothing */
  if (e->operation == ZS_COMMISSIONING_OPERATION_INITIAL || e->operation == ZS_COMMISSIONING_OPERATION_RECOMMISSION)
    installation_reload_pending = true;
  console_printf("install audit phase %u op %u role %u result %u v%lu\r\n", e->phase, e->operation, e->role, e->result, (unsigned long)e->version);
  return true;
}
static bool ble_uart_send(void *ctx, const uint8_t *w, size_t n) { (void)ctx; return bsp_uart_write(BSP_UART_BLE, w, n) == (int)n; }
static uint32_t ble_now_ms(void *ctx) { (void)ctx; return xTaskGetTickCount(); }
static bool ble_service_mode(void *ctx, uint32_t *started) { (void)ctx; *started = service_started_ms; return modes.mode == ZS_MODE_S4_SERVICE; }
static zs_commissioning_role_t ble_peer_role(void *ctx) { (void)ctx; return ZS_COMMISSIONING_ROLE_INSTALLER; }   /* base role by pairing (B.7) */
static bool ble_peer_secure(void *ctx) { (void)ctx; return ipc.link_state == 2u; }
static bool ble_random(void *ctx, uint8_t *out, size_t n) { (void)ctx; return bsp_rng_fill(out, n); }
/* Station secrets (B3 NOR record, zs_station_secrets): the B.9 engineer key and the expected ICCIDs of both SIM
   slots.  Loaded at boot and applied to the BLE service (engineer role) and the comms task (dual SIM); the bench
   provisions them with "engkey <64 hex>" / "simiccid <1|2> <iccid>", which commit to NOR.  Without a valid record
   ipc_port.engineer_key stays NULL (elevation refused) and comms keeps the single-SIM path. */
static uint8_t engineer_key[32];
static zs_station_secrets_io_t secrets_io;
static zs_station_secrets_t secrets;
static bool secrets_on_nor, secrets_loaded;

static zs_station_config_io_t cfg_io = {cfg_slots, ram_read, ram_erase, ram_write};
static zs_installation_store_io_t pos_io = {pos_slots, ram_read, ram_erase, ram_write};
static const zs_commissioning_audit_io_t audit_io = {NULL, ble_audit};
static const zs_ipc_identity_t identity = {APP_STATION_SERIAL, APP_STATION_HW_REV, APP_STATION_FW_VERSION, APP_STATION_BL_VERSION, APP_STATION_ID, ZS_STATION_CONFIG_REGION_RU868};
/* v0.3 station_secrets over BLE: the service commits to the NOR record and hands the new record here to apply. */
static void ble_secrets_changed(void *ctx, const zs_station_secrets_t *rec);
static zs_ipc_service_port_t ipc_port = {NULL, ble_uart_send, ble_now_ms, ble_service_mode, ble_peer_role, ble_peer_secure,
                                         &cfg_io, &pos_io, &audit_io, &selftests, &identity, NULL, ble_random, &secrets_io, ble_secrets_changed};

/* BLE task: the installation record from its store (none: GNSS position only); a read error keeps the current one. */
static void installation_reload(void) {
  static zs_installation_record_t rec;
  zs_position_trust_config_t cfg;
  const zs_installation_store_result_t r = zs_installation_store_load(&pos_io, &rec, NULL);
  memset(&cfg, 0, sizeof(cfg));
  if (r == ZS_INSTALLATION_STORE_OK) cfg = rec.trust;
  else if (r != ZS_INSTALLATION_STORE_NOT_FOUND) { console_printf("position: installation record unreadable (%d), kept\r\n", (int)r); return; }
  taskENTER_CRITICAL();
  installation_pending = cfg;
  installation_pending_set = true;
  taskEXIT_CRITICAL();
  if (cfg.configured) console_printf("position: installation v%lu %ld.%07ld %ld.%07ld alt %ld dm\r\n", (unsigned long)rec.version,
                                     (long)(cfg.installation.lat_e7 / 10000000), (long)labs(cfg.installation.lat_e7 % 10000000),
                                     (long)(cfg.installation.lon_e7 / 10000000), (long)labs(cfg.installation.lon_e7 % 10000000), (long)cfg.installation.alt_dm);
  else console_printf("position: not commissioned, GNSS position\r\n");
}

/* Heartbeat (schema 2): identity, time, power/route placeholders of B1, self-test verdict, and the detector map
   (key 13): boot_id, uptime, pipeline counters, level 1, longest window, events waiting in the NOR outbox. */
static bool comms_fill_heartbeat(void *ctx, zs_heartbeat_t *hb) {
  uint16_t pending = 0u;
  (void)ctx;
  hb->schema_ver = 2u;
  hb->time_us = zs_time_for_sample(&time_sync, zs_pdm_capture_sample_counter(&capture));
  (void)app_power_snapshot(&hb->power);                                   /* INA226: last valid sample, status bits when stale */
  hb->route.transport = ZS_ROUTE_LTE;
  strncpy(hb->firmware_ver, APP_STATION_FW_VERSION, sizeof(hb->firmware_ver) - 1u);
  (void)zs_model_active_describe(hb->model_ver, sizeof(hb->model_ver));  /* "c46" built-in, "m<version>" package */
  strncpy(hb->hardware_rev, APP_STATION_HW_REV, sizeof(hb->hardware_rev) - 1u);
  hb->self_test_ok = zs_selftest_required_ok(&selftests);
  hb->gnss.time_trust = (uint8_t)time_sync.trust;
  hb->gnss.expected_time_error_us = time_sync.expected_error_us;
  (void)station_pos_fill(&hb->station, &hb->gnss);                       /* installation record or GNSS fix (zeros: unknown) */
  hb->gnss.time_suspect = zs_time_suspect(&time_sync);                    /* a GNSS time jump or an unverified timeline (zs_time.h) */
  hb->detector_present = true;
  hb->detector.boot_id = boot_id;
  hb->detector.uptime_s = xTaskGetTickCount() / 1000u;
  hb->detector.windows = pipeline.windows;
  hb->detector.windows_dropped = pipeline.windows_dropped;
  hb->detector.confirmed_windows = pipeline.confirmed_windows;
  hb->detector.suspect_windows = pipeline.suspect_windows;
  hb->detector.engine_windows = pipeline.engine_windows;
  hb->detector.events_emitted = pipeline.events_emitted;
  hb->detector.events_refused = pipeline.events_refused;
  if (stores_on_nor && zs_event_outbox_pending_count(&nor_outbox_io, &pending) == ZS_EVENT_OUTBOX_OK) hb->detector.outbox_pending = pending;
  hb->detector.window_max_ms = (uint16_t)(pipeline_max_ms > 65535u ? 65535u : pipeline_max_ms);
  hb->detector.presence_level = pipeline.presence.level;
  hb->detector.reset_cause = app_watchdog_reset_cause();
  hb->detector.watchdog_missed = app_watchdog_previous_missed();
  hb->detector.params_version = app_commands_params()->version;
  hb->detector.selftest_failed = zs_selftest_failed_mask(&selftests);
  hb->detector.command_key_id = secrets.command_key_set ? zs_command_key_id_u64(secrets.command_public_key) : 0u;
  hb->detector.command_next_key_id = secrets.command_next_key_set ? zs_command_key_id_u64(secrets.command_next_key) : 0u;
  app_fw_fill_heartbeat(&hb->detector);                                  /* addendum F: keys 18..20 */
  app_comms_net_heartbeat(&hb->detector);                                /* addendum G: keys 21..23 */
  return true;
}
/* The comms duty loop (app_comms_task's body, as the host simulation and the twin drive it) plus the watchdog
   check-in; app_comms.c stays target/host neutral. */
static void comms_task_fn(void *arg) {
  (void)arg;
  for (;;) {
    app_comms_step();
    app_watchdog_checkin(APP_WD_COMMS);
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}
/* Command validity clock: PPS-disciplined time while GNSS is trusted or in holdover, otherwise the network time
   (NITZ) for APP_COMMAND_NETWORK_TIME_MAX_MS; called from the comms task only. */
static zs_command_clock_t command_clock;
static bool command_clock_now(uint32_t now_ms, uint64_t *now_us) {
  static uint32_t network_seen_at_ms;
  int64_t network_us;
  uint32_t network_at_ms;
  const bool gnss = time_sync.trust == ZS_TIME_TRUST_GNSS_TRUSTED || time_sync.trust == ZS_TIME_TRUST_HOLDOVER;
  /* NITZ read by the modem during this bring-up (AT+QLTS=1): hand each new reading to the clock once */
  if (zs_bg95_network_time(app_comms_modem(), &network_us, &network_at_ms) && network_at_ms != network_seen_at_ms) {
    network_seen_at_ms = network_at_ms;
    (void)zs_command_clock_set_network(&command_clock, network_us, network_at_ms);
  }
  const int64_t gnss_us = gnss ? zs_time_for_sample(&time_sync, zs_pdm_capture_sample_counter(&capture)) : 0;
  return zs_command_clock_now(&command_clock, gnss_us, gnss, now_ms, now_us);
}
static void comms_session_done(void *ctx) {
  (void)ctx; outbox_retry_backoff_ms = APP_OUTBOX_RETRY_MS; outbox_retry_at_ms = 0u; mode_event(ZS_MODE_EV_COMMS_DONE);
  app_fw_confirm(zs_selftest_required_ok(&selftests));                   /* addendum F: a trial image proved itself */
}
static bool outbox_has_pending(void) { uint16_t pending = 0u; return stores_on_nor && zs_event_outbox_pending_count(&nor_outbox_io, &pending) == ZS_EVENT_OUTBOX_OK && pending > 0u; }
static const app_comms_hooks_t comms_hooks = {comms_fill_heartbeat, NULL, console_printf, comms_session_done};

static void secrets_apply(void);   /* defined after ipc_port */

/* Pushes the loaded/edited secrets into their consumers; values are never printed. */
static void secrets_apply(void) {
  if (secrets.engineer_key_set) { memcpy(engineer_key, secrets.engineer_key, sizeof(engineer_key)); ipc_port.engineer_key = engineer_key; }
  else ipc_port.engineer_key = NULL;
  for (unsigned i = 0u; i < 2u; i++) if (secrets.iccid[i][0]) (void)app_comms_set_sim_iccid(i + 1u, secrets.iccid[i]);
  { zs_command_trust_key_t keys[2]; const size_t n = zs_command_keys_trust_set(&secrets, keys); app_comms_set_command_keys(keys, n); }
  if (stores_on_nor) app_lora_bind(&nor_outbox_io, APP_STATION_ID, secrets.engineer_key_set ? secrets.engineer_key : NULL, console_printf);
}

static void ble_secrets_changed(void *ctx, const zs_station_secrets_t *rec) {
  (void)ctx;
  secrets = *rec;
  secrets_loaded = rec->engineer_key_set || rec->iccid[0][0] || rec->iccid[1][0] || rec->command_key_set;
  if (!rec->engineer_key_set) memset(engineer_key, 0, sizeof(engineer_key));
  secrets_apply();
  console_printf("secrets: provisioned over ble (v%lu) engineer key %s, iccid1 %s, iccid2 %s, command key %s\r\n", (unsigned long)rec->version,
                 rec->engineer_key_set ? "set" : "-", rec->iccid[0][0] ? "set" : "-", rec->iccid[1][0] ? "set" : "-", rec->command_key_set ? "set" : "-");
}

/* Command key rotation (addendum E, app_commands in the comms task): the NOR record changed, keep the RAM copy in
   step (the console commits it) and reload the trust set. */
static void command_keys_changed(const zs_station_secrets_t *rec) {
  secrets = *rec;
  secrets_loaded = true;
  secrets_apply();
}

/* Commits the current secrets to NOR; false on the RAM fallback or a storage error (the RAM copy still applies). */
static bool secrets_persist(void) {
  if (!secrets_on_nor) return false;
  if (zs_station_secrets_commit(&secrets_io, &secrets) != ZS_STATION_SECRETS_OK) return false;
  secrets_loaded = true;
  return true;
}

/* Remote network configuration (addendum G): the comms task committed a confirmed record to the config store; the ble
   task reloads its service copy (config_read, the base of the next BLE patch) on its next turn. */
static volatile bool config_reload_pending;
static void net_config_committed(const zs_station_config_t *cfg) {
  (void)cfg;
  config_reload_pending = true;
}

/* Model packages (MQTT ICD addendum I): two slots in the NOR model region; the active one is loaded at boot. */
static zs_model_store_t model_store;
static app_comms_model_port_t model_port;
static bool model_nor_erase(void *ctx, uint32_t address, uint32_t size) { return zs_nor_erase((zs_nor_t *)ctx, address, size); }
static bool model_nor_program(void *ctx, uint32_t address, const uint8_t *data, size_t size) { return zs_nor_program((zs_nor_t *)ctx, address, data, size); }
static bool model_nor_read(void *ctx, uint32_t address, uint8_t *data, size_t size) { return zs_nor_read((zs_nor_t *)ctx, address, data, size); }
static const zs_model_flash_t model_flash = {&nor, model_nor_erase, model_nor_program, model_nor_read};

static void bind_model_store(void) {
  const app_comms_fw_port_t *fw = app_fw_port();
  uint32_t size = 0u, version = 0u;
  char text[ZS_MODEL_DESCRIBE_MAX];
  if (!zs_model_store_init(&model_store, &model_flash, nor_bindings.layout.model_base_address, nor_bindings.layout.model_slot_bytes,
                           nor_bindings.layout.erase_block_bytes)) {
    console_printf("model: store not bound, built-in model\r\n");
    return;
  }
  model_port = (app_comms_model_port_t){&model_store, fw ? fw->keys : NULL, fw ? fw->key_count : 0u};
  app_comms_set_model_port(&model_port);                                 /* CMD_UPDATE_FIRMWARE target 3 (addendum I) */
  if (zs_model_store_active(&model_store, &size, &version)) {
    const zs_model_status_t st = zs_model_activate(zs_model_store_read_active, &model_store, size, version);
    if (st != ZS_MODEL_OK) console_printf("model: stored m%lu not loaded (status %d)\r\n", (unsigned long)version, (int)st);
  }
  (void)zs_model_active_describe(text, sizeof(text));
  console_printf("model: %s active (store @0x%08lx)\r\n", text, (unsigned long)nor_bindings.layout.model_base_address);
}

static void bind_record_stores(void) {
  memset(cfg_slots, 0xff, sizeof(cfg_slots));
  memset(pos_slots, 0xff, sizeof(pos_slots));
  if (bsp_nor_init(&nor) &&
      zs_nor_storage_bind_stores(&nor_bindings, &nor, APP_NOR_COMMAND_SLOTS, APP_NOR_OUTBOX_SLOTS, &nor_archive_storage,
                                 &nor_command_io, &nor_outbox_io, &cfg_io, &pos_io)) {
    stores_on_nor = true;
    {
      /* runtime parameters: the last APP_PARAMS_NOR_BLOCKS blocks of the nRF image partition (addendum D) */
      static zs_nor_storage_layout_t nrf_layout;
      static zs_nor_slot_store_t params_slots;
      static zs_station_params_io_t params_io;
      zs_station_config_io_t slot_io;
      const uint32_t params_bytes = APP_PARAMS_NOR_BLOCKS * nor_bindings.layout.erase_block_bytes;
      nrf_layout = nor_bindings.layout;
      nrf_layout.nrf_image_partition_bytes -= params_bytes;
      app_nrf_update_bind(&nor, &nrf_layout, console_printf);
      if (zs_nor_slot_store_init(&params_slots, &nor, nrf_layout.nrf_image_base_address + nrf_layout.nrf_image_partition_bytes, 2u, ZS_STATION_PARAMS_RECORD_BYTES) &&
          zs_nor_slot_store_config_io(&params_slots, &slot_io)) {
        params_io = (zs_station_params_io_t){slot_io.ctx, slot_io.read, slot_io.erase, slot_io.write};
        app_commands_bind(&params_io, params_apply, console_printf);
      } else {
        app_commands_bind(NULL, params_apply, console_printf);
      }
    }
    app_comms_bind(&nor_outbox_io, &nor_command_io, &comms_hooks);        /* comms needs the durable stores */
    app_comms_bind_config_store(&cfg_io, net_config_committed);           /* CMD_SET_NETWORK_CONFIG (addendum G) */
    /* audio prehistory: the archive region at the start of the NOR map (event slots after it stay unused for now) */
    if (app_audio_rec_bind(&nor_archive_storage, nor_bindings.layout.archive.base_address, nor_bindings.layout.archive.prehistory_ring_bytes,
                           &audio_ring, pl_sample_time, console_printf))
      app_comms_set_audio_source(app_audio_rec_source());                 /* CMD_REQUEST_AUDIO can now be served */
    app_lora_bind(&nor_outbox_io, APP_STATION_ID, secrets.engineer_key_set ? secrets.engineer_key : NULL, console_printf);
    { uint16_t pending = 0u; if (zs_event_outbox_pending_count(&nor_outbox_io, &pending) == ZS_EVENT_OUTBOX_OK && pending > 0u) { console_printf("outbox: %u events pending from before the reboot\r\n", pending); mode_event(ZS_MODE_EV_OUTBOX_PENDING); } }
    /* B3 boot counter: one erase block before the nRF image; every power cycle gets a new boot_id so event ids never repeat */
    if (zs_boot_counter_open(&boot_counter, &nor, nor_bindings.layout.boot_counter_base_address, nor_bindings.layout.erase_block_bytes) &&
        zs_boot_counter_increment(&boot_counter, &boot_id)) {
      pipeline_port.boot_id = boot_id;
    } else {
      console_printf("nor: boot counter unavailable, boot_id stays %lu\r\n", (unsigned long)boot_id);
    }
    console_printf("nor: W25Q512JV bound, boot %lu, nrf image @0x%08lx config @0x%08lx installation @0x%08lx\r\n",
                   (unsigned long)boot_id, (unsigned long)nor_bindings.layout.nrf_image_base_address, (unsigned long)nor_bindings.layout.config_base_address,
                   (unsigned long)nor_bindings.layout.installation_base_address);
    bind_model_store();
    /* station secrets: two blocks before the boot counter */
    if (zs_nor_storage_bind_secrets(&nor_bindings, &nor, &secrets_io)) {
      const zs_station_secrets_result_t r = zs_station_secrets_load(&secrets_io, &secrets, NULL);
      secrets_on_nor = true;
      app_commands_bind_keys(&secrets_io, command_keys_changed);
      if (r == ZS_STATION_SECRETS_OK) { secrets_loaded = true; secrets_apply(); }
      else if (r != ZS_STATION_SECRETS_NOT_FOUND) console_printf("secrets: read error %d\r\n", (int)r);
      console_printf("secrets: %s (v%lu) engineer key %s, iccid1 %s, iccid2 %s\r\n", secrets_loaded ? "loaded" : "none",
                     (unsigned long)secrets.version, secrets.engineer_key_set ? "set" : "-", secrets.iccid[0][0] ? "set" : "-", secrets.iccid[1][0] ? "set" : "-");
    } else {
      console_printf("secrets: store not bound\r\n");
    }
  } else {
    cfg_io = (zs_station_config_io_t){cfg_slots, ram_read, ram_erase, ram_write};
    pos_io = (zs_installation_store_io_t){pos_slots, ram_read, ram_erase, ram_write};
    console_printf("nor: bind/probe failed, record stores in RAM for this session\r\n");
    app_commands_bind(NULL, params_apply, console_printf);
  }
}

/* Detection events go to the NOR outbox (B3 map) when it is bound; on the RAM fallback they are only counted. */
static bool pl_emit(void *ctx, const zs_detection_t *d) {
  static uint8_t workspace[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES + 64u];
  static zs_detection_t with_power;                                       /* dsp task only: the pipeline is not re-entrant */
  (void)ctx;
  with_power = *d;
  (void)app_power_snapshot(&with_power.power);                            /* battery bus/current/power of the moment */
  with_power.route.transport = ZS_ROUTE_LTE;
  /* the quality of the event time (fusion weights it; the server skips audio requests it knows would be refused) */
  with_power.gnss.time_trust = (uint8_t)time_sync.trust;
  with_power.gnss.expected_time_error_us = time_sync.expected_error_us;
  with_power.gnss.pps_ok = time_sync.pps_ok;
  with_power.gnss.time_holdover = time_sync.trust == ZS_TIME_TRUST_HOLDOVER;
  (void)station_pos_fill(&with_power.station, &with_power.gnss);          /* the server fuses bearings by it (zeros: unknown) */
  with_power.gnss.time_suspect = zs_time_suspect(&time_sync);
  app_audio_rec_note_event(d->event_id, d->event_time_us,                 /* CMD_REQUEST_AUDIO finds its audio by this */
                           time_sync.trust == ZS_TIME_TRUST_GNSS_TRUSTED || time_sync.trust == ZS_TIME_TRUST_HOLDOVER);
  if (!stores_on_nor) { pipeline_events_ram++; return true; }
  app_lora_remember_event(d->event_id, d->classification.class_id, d->classification.confidence_u8, pipeline.presence.level, (uint16_t)pipeline.last_gate.f0_hz);
  return zs_event_outbox_enqueue_detection(&nor_outbox_io, &with_power, 2u, workspace, sizeof(workspace)) == ZS_EVENT_OUTBOX_OK;
}

static volatile bool ble_recovery_request;   /* console "bledfu": restart the nRF with BLE_DFU_REQ asserted */

/* Controlled nRF recovery entry (pin authority: P0.15 sampled by the bootloader at reset release):
   hold reset via BLE_EN, assert DFU_REQ, release reset, keep the request during boot, then release it. */
static void ble_enter_recovery(void) {
  bsp_gpio_ble_enable(false);
  bsp_gpio_ble_dfu_request(true);
  vTaskDelay(pdMS_TO_TICKS(20));
  bsp_gpio_ble_enable(true);
  vTaskDelay(pdMS_TO_TICKS(500));
  bsp_gpio_ble_dfu_request(false);
  console_printf("ble: recovery requested (BLE_DFU_REQ held through reset release)\r\n");
}

static void ble_task_fn(void *arg) {
  bool window_open = false;
  uint32_t last_ping = 0u;
  (void)arg;
  bind_record_stores();
  installation_reload();                                                  /* the station position of a commissioned station */
  (void)bsp_uart_init(BSP_UART_BLE, APP_UART_BLE_BAUD);
  if (!bsp_rng_init()) console_printf("rng: init failed, engineer role elevation disabled\r\n");
  bsp_gpio_ble_enable(true);
  vTaskDelay(pdMS_TO_TICKS(200));                  /* nRF boot */
  (void)zs_ipc_service_init(&ipc, &ipc_port);
  (void)zs_ipc_service_ping(&ipc);
  if (ipc.config_loaded) app_comms_set_config(&ipc.config, boot_id);
  for (;;) {
    uint8_t buf[64];
    size_t n;
    (void)ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(250));
    app_watchdog_checkin(APP_WD_BLE);
    if (installation_reload_pending) { installation_reload_pending = false; installation_reload(); }
    if (config_reload_pending) {                                          /* a remote configuration was confirmed (addendum G) */
      config_reload_pending = false;
      if (zs_station_config_store_load(&cfg_io, &ipc.config, NULL) == ZS_STATION_CONFIG_OK) ipc.config_loaded = true;
    }
    { static uint32_t seen_version; if (ipc.config_loaded && ipc.config.version != seen_version) { seen_version = ipc.config.version; app_comms_set_config(&ipc.config, boot_id); } }
    while ((n = bsp_uart_read(BSP_UART_BLE, buf, sizeof(buf))) > 0u) zs_ipc_service_on_uart_rx(&ipc, buf, n);
    if (ble_recovery_request) { ble_recovery_request = false; ble_enter_recovery(); (void)zs_ipc_service_init(&ipc, &ipc_port); }
    if (app_nrf_update_pending()) { app_watchdog_hold(APP_WD_BLE, APP_NRF_UPDATE_HOLD_MS); app_nrf_update_run(); (void)zs_ipc_service_init(&ipc, &ipc_port); (void)zs_ipc_service_ping(&ipc); }
    /* until the bridge has answered once, repeat the link check every 2 s (nRF boot / re-flash on the bench) */
    if (ipc.pongs_seen == 0u && (uint32_t)(xTaskGetTickCount() - last_ping) >= 2000u) { last_ping = xTaskGetTickCount(); (void)zs_ipc_service_ping(&ipc); }
    const bool want = modes.mode == ZS_MODE_S4_SERVICE;
    if (want && !window_open) { service_started_ms = xTaskGetTickCount(); (void)zs_ipc_service_set_window(&ipc, true, APP_BLE_SERVICE_WINDOW_S); }
    else if (!want && window_open) (void)zs_ipc_service_set_window(&ipc, false, 0u);
    window_open = want;
  }
}

static void console_exec(const char *cmd) {
  if (app_nrf_console(cmd)) return;                     /* nrfimg ... / nrfupd (addendum C.6) */
  if (strcmp(cmd, "st") == 0) {
    uint8_t rep[64];
    size_t n;
    bool ok = zs_selftest_run_all(&selftests, xTaskGetTickCount());
    n = zs_selftest_encode(&selftests, rep, sizeof(rep));
    console_printf("selftest %s, cbor %u bytes:", ok ? "PASS" : "FAIL", (unsigned)n);
    for (size_t i = 0u; i < n; i++) console_printf("%02x", rep[i]);
    console_printf("\r\n");
    for (uint8_t i = 0u; i < selftests.count; i++) {
      uint8_t id = selftests.entries[i].id;
      console_printf("  %-14s %-8s %lu\r\n", selftests.entries[i].name, zs_selftest_code_name(selftests.result[id]), (unsigned long)selftests.detail[id]);
    }
  } else if (strcmp(cmd, "lag") == 0) {
    for (unsigned ch = 1u; ch < ZS_PDM_CHANNELS; ch++) {
      int lag;
      bool ok = zs_pdm_capture_channel_lag(&capture, ch, 2048u, 8, &lag);
      console_printf("ch%u lag %s %d\r\n", ch, ok ? "=" : "n/a", ok ? lag : 0);
    }
  } else if (strcmp(cmd, "pos") == 0) {
    zs_position_t st;
    zs_gnss_t g;
    memset(&st, 0, sizeof(st));
    memset(&g, 0, sizeof(g));
    if (!station_pos_fill(&st, &g)) console_printf("position: unknown (no installation record, no GNSS fix yet)\r\n");
    else console_printf("position: %s %ld.%07ld %ld.%07ld alt %ld dm acc %u m | fix %u sats %u hdop %u.%02u | trust %u delta %u m | fixes %lu\r\n",
                        st.position_source == ZS_POSITION_SOURCE_CONFIGURED_INSTALL ? "installation" : "gnss",
                        (long)(st.lat_e7 / 10000000), (long)labs(st.lat_e7 % 10000000), (long)(st.lon_e7 / 10000000), (long)labs(st.lon_e7 % 10000000),
                        (long)st.alt_dm, (unsigned)st.pos_accuracy_m, (unsigned)g.fix_type, (unsigned)g.satellites,
                        (unsigned)(g.hdop_x100 / 100u), (unsigned)(g.hdop_x100 % 100u), (unsigned)g.position_trust, (unsigned)g.position_delta_m,
                        (unsigned long)station_pos_shared.fixes);
  } else if (strcmp(cmd, "pps") == 0) {
    console_printf("pps edges %lu bound %lu drop(label %lu pps %lu bracket %lu) ppm %ld trust %d err_us %lu\r\n",
                   (unsigned long)bsp_tim2_pps_edges(), (unsigned long)pps.bound_count, (unsigned long)pps.dropped_no_label,
                   (unsigned long)pps.dropped_no_pps, (unsigned long)pps.dropped_no_bracket, (long)zs_pps_sync_rate_error_ppm(&pps),
                   (int)time_sync.trust, (unsigned long)time_sync.expected_error_us);
    console_printf("time suspect %d verified %d jumps %lu last_jump_ms %ld reanchors %lu\r\n", (int)zs_time_suspect(&time_sync),   /* ms: long is 32 bit */
                   (int)time_sync.verified, (unsigned long)time_sync.jumps, (long)(time_sync.last_jump_us / 1000), (unsigned long)time_sync.reanchors);
  } else if (strcmp(cmd, "audio") == 0) {
    console_printf("blocks %lu samples %lu overruns %lu seq %lu dma_err %lu peaks %d %d %d %d\r\n",
                   (unsigned long)capture.blocks_processed, (unsigned long)zs_pdm_capture_sample_counter(&capture),
                   (unsigned long)capture.overruns, (unsigned long)capture.sequence_errors, (unsigned long)bsp_mdf_dma_errors(),
                   capture.peak[0], capture.peak[1], capture.peak[2], capture.peak[3]);
  } else if (strcmp(cmd, "svc") == 0) {
    xTaskNotify(supervisor_task, 1u << ZS_MODE_EV_SERVICE_BUTTON, eSetBits);   /* console shortcut for the bench */
  } else if (strcmp(cmd, "modes") == 0) {
    zs_mode_transition_t j[ZS_MODE_JOURNAL_DEPTH];
    uint8_t n = zs_mode_journal(&modes, j, ZS_MODE_JOURNAL_DEPTH);
    console_printf("mode %s, tamper events %lu, outbox retries %lu (backoff %lu s), gsm %s (fail streak %u)\r\n", zs_mode_name(modes.mode), (unsigned long)tamper_events, (unsigned long)outbox_retries, (unsigned long)(outbox_retry_backoff_ms / 1000u), gsm_degraded ? "degraded" : "ok", comms_fail_streak);
    for (uint8_t i = 0u; i < n; i++)
      console_printf("  %8lu %s -> %s (ev %u)\r\n", (unsigned long)j[i].at_ms, zs_mode_name((zs_mode_t)j[i].from), zs_mode_name((zs_mode_t)j[i].to), j[i].event);
  } else if (strcmp(cmd, "ble") == 0) {
    console_printf("ble bridge %s (v%u, ping %lu/pong %lu) link %u role %d (elev %lu rej %lu) window %s config v%lu%s (%s) writes ok %lu rejected %lu audits %lu uart overruns %lu\r\n",
                   ipc.pongs_seen ? "alive" : "silent", ipc.peer_protocol_version, (unsigned long)ipc.pings_sent, (unsigned long)ipc.pongs_seen,
                   ipc.link_state, (int)zs_ipc_service_role(&ipc), (unsigned long)ipc.role_elevations, (unsigned long)ipc.role_rejections,
                   modes.mode == ZS_MODE_S4_SERVICE ? "open" : "closed", (unsigned long)ipc.config.version,
                   ipc.config_loaded ? "" : " (none)", stores_on_nor ? "nor" : "ram", (unsigned long)ipc.writes_ok,
                   (unsigned long)ipc.writes_rejected, (unsigned long)ble_audit_events, (unsigned long)bsp_uart_rx_overruns(BSP_UART_BLE));
  } else if (strcmp(cmd, "ping") == 0) {
    (void)zs_ipc_service_ping(&ipc);
  } else if (strcmp(cmd, "bledfu") == 0) {
    ble_recovery_request = true;
  } else if (strncmp(cmd, "engkey", 6u) == 0) {
    const char *h = cmd + 6;
    while (*h == ' ') h++;
    if (strlen(h) != 64u) { console_printf("engkey <64 hex>: B.9 engineer key for this bench session (%s)\r\n", ipc_port.engineer_key ? "set" : "not set"); }
    else {
      bool ok = true;
      for (unsigned i = 0u; i < 32u && ok; i++) {
        unsigned v; char b[3] = {h[2u * i], h[2u * i + 1u], 0};
        ok = sscanf(b, "%2x", &v) == 1;
        engineer_key[i] = (uint8_t)v;
      }
      if (ok) {
        memcpy(secrets.engineer_key, engineer_key, sizeof(engineer_key));
        secrets.engineer_key_set = true;
        secrets_apply();
        console_printf(secrets_persist() ? "engkey: set, stored in nor (v%lu)\r\n" : "engkey: set for this session only (nor v%lu)\r\n", (unsigned long)secrets.version);
      } else console_printf("engkey: bad hex\r\n");
    }
  } else if (strcmp(cmd, "dsp") == 0) {
    const zs_presence_t *pr = &pipeline.presence;
    console_printf("pipeline windows %lu dropped %lu last %lu ms max %lu ms | level %u conf %u uav %u/%u weak %u ground %u comb %d f0 %d Hz | class %u conf %u | events %lu refused %lu (ram %lu)\r\n",
                   (unsigned long)pipeline.windows, (unsigned long)pipeline.windows_dropped, (unsigned long)pipeline_last_ms, (unsigned long)pipeline_max_ms,
                   pr->level, pr->confidence_u8, pr->uav_votes, pr->windows, pr->uav_weak_votes, pr->ground_votes, pr->comb, (int)pipeline.last_gate.f0_hz,
                   pipeline.last_window.class_id, pipeline.last_window.confidence_u8, (unsigned long)pipeline.events_emitted, (unsigned long)pipeline.events_refused,
                   (unsigned long)pipeline_events_ram);
    console_printf("  sources: mixture windows %lu, one target %lu, confirmed by a source %lu | comb bearings %lu of %lu (few bins %lu weak %lu)\r\n",
                   (unsigned long)pipeline.separated_windows, (unsigned long)pipeline.merged_windows, (unsigned long)pipeline.source_confirmed_windows,
                   (unsigned long)pipeline.comb_stats.computed, (unsigned long)pipeline.comb_stats.attempts, (unsigned long)pipeline.comb_stats.few_bins,
                   (unsigned long)pipeline.comb_stats.weak);
    console_printf("  directions: windows %lu, several %lu, classified %lu, confirmed by one %lu, bearings %lu, mask failed %lu\r\n",
                   (unsigned long)pipeline.doa_windows, (unsigned long)pipeline.doa_mixture_windows, (unsigned long)pipeline.doa_classified_windows,
                   (unsigned long)pipeline.doa_confirmed_windows, (unsigned long)pipeline.doa_bearings, (unsigned long)pipeline.doa_mask_failed);
    console_printf("  track %s (event %lu:%lu, %lu windows) | tracks %lu ended lost %lu max %lu mode %lu, refused (link) %lu\r\n",
                   track_open ? "OPEN" : "closed", (unsigned long)(track.track_event_id >> 32), (unsigned long)(track.track_event_id & 0xffffffffu),
                   (unsigned long)track.windows, (unsigned long)track.tracks, (unsigned long)track.ended_lost, (unsigned long)track.ended_max,
                   (unsigned long)track.ended_mode, (unsigned long)track.refused_link);
    console_printf("  features f0 %d Hz harmonics %d step %d Hz stab %d%% centroid %d Hz flat %d%% noise %d%% rough %d%%\r\n",
                   (int)pipeline.features[0], (int)pipeline.features[1], (int)pipeline.features[2], (int)(pipeline.features[3] * 100.0f),
                   (int)pipeline.features[7], (int)(pipeline.features[8] * 100.0f), (int)(pipeline.features[10] * 100.0f), (int)(pipeline.features[15] * 100.0f));
  } else if (strcmp(cmd, "comms") == 0) {
    app_comms_status(console_printf);
    app_fw_status(console_printf);
  } else if (strcmp(cmd, "comms on") == 0 || strcmp(cmd, "comms off") == 0) {
    app_comms_request(cmd[6] == 'o' && cmd[7] == 'n');
    if (cmd[7] == 'n') mode_event(ZS_MODE_EV_OUTBOX_PENDING);           /* bench: pull the scheduler into S3 */
  } else if (strncmp(cmd, "simiccid ", 9u) == 0) {
    const unsigned slot = (unsigned)(cmd[9] - '0');
    const char *iccid = cmd[10] == ' ' ? cmd + 11 : "";
    if (slot >= 1u && slot <= 2u && app_comms_set_sim_iccid(slot, iccid)) {
      strcpy(secrets.iccid[slot - 1u], iccid);
      console_printf(secrets_persist() ? "simiccid: slot %u set, stored in nor (v%lu)\r\n" : "simiccid: slot %u set for this session only (nor v%lu)\r\n", slot, (unsigned long)secrets.version);
    } else console_printf("simiccid <1|2> <18..22 digits>: slot %u not set\r\n", slot);
  } else if (strcmp(cmd, "secrets") == 0) {
    console_printf("secrets %s (%s, v%lu): engineer key %s, iccid1 %s, iccid2 %s, command key %s%s\r\n", secrets_loaded ? "loaded" : "none",
                   secrets_on_nor ? "nor" : "ram", (unsigned long)secrets.version, secrets.engineer_key_set ? "set" : "-",
                   secrets.iccid[0][0] ? "set" : "-", secrets.iccid[1][0] ? "set" : "-", secrets.command_key_set ? "set" : "-",
                   secrets.command_next_key_set ? " + next (rotation in flight)" : "");
  } else if (strcmp(cmd, "secrets clear") == 0) {
    memset(&secrets, 0, sizeof(secrets));
    memset(engineer_key, 0, sizeof(engineer_key));
    secrets_loaded = false;
    secrets_apply();
    console_printf((!secrets_on_nor || zs_station_secrets_clear(&secrets_io) == ZS_STATION_SECRETS_OK) ? "secrets: cleared (sim iccids apply after reboot)\r\n" : "secrets: nor clear failed\r\n");
  } else if (strcmp(cmd, "power") == 0) {
    app_power_status(console_printf);
  } else if (strcmp(cmd, "rec") == 0) {
    app_audio_rec_status(console_printf);
  } else if (strcmp(cmd, "cmds") == 0) {
    app_commands_status(console_printf);
  } else if (strcmp(cmd, "clock") == 0) {
    static const char *const src[] = {"none", "gnss", "network"};
    console_printf("command clock: last source %s | reads gnss %lu network %lu untrusted %lu | network sets %lu rejected %lu | time trust %d\r\n",
                   src[command_clock.last_source % 3u], (unsigned long)command_clock.gnss_reads, (unsigned long)command_clock.network_reads,
                   (unsigned long)command_clock.untrusted_reads, (unsigned long)command_clock.network_sets, (unsigned long)command_clock.network_rejected, (int)time_sync.trust);
  } else if (strcmp(cmd, "wd") == 0) {
    app_watchdog_status(console_printf);
  } else if (strncmp(cmd, "wdtest ", 7u) == 0) {
    const int t = atoi(cmd + 7);
    if (t >= (int)APP_WD_AUDIO && t <= (int)APP_WD_REC) { app_watchdog_simulate_stall((app_wd_task_t)t); console_printf("wdtest: task %d stops checking in, reset expected within %lu s\r\n", t, (unsigned long)((APP_WATCHDOG_WINDOW_MS * 2u + APP_WATCHDOG_TIMEOUT_MS) / 1000u)); }
    else console_printf("wdtest <1..8>: 1 audio 2 dsp 3 comms 4 ble 5 power 6 lora 7 gnss 8 rec\r\n");
  } else if (strcmp(cmd, "lora") == 0) {
    app_lora_status(console_printf);
  } else if (strcmp(cmd, "lora on") == 0 || strcmp(cmd, "lora off") == 0) {
    app_lora_set_route_hint(cmd[5] == 'o' && cmd[6] == 'n');            /* bench: force the route hint */
  } else if (strcmp(cmd, "heap") == 0) {
    console_printf("heap free %u min %u\r\n", (unsigned)xPortGetFreeHeapSize(), (unsigned)xPortGetMinimumEverFreeHeapSize());
  } else if (cmd[0] != '\0') {
    console_printf("commands: st lag pos pps audio dsp svc modes ble ping bledfu engkey simiccid secrets [clear]\r\n");   /* one line: 160 B */
    console_printf("          nrfimg nrfupd comms [on|off] power lora [on|off] clock cmds rec wd wdtest heap\r\n");
  }
}

static void console_task_fn(void *arg) {
  static char line[192];                               /* nrfimg put <off> <base64 of 96 bytes> is ~150 chars */
  size_t len = 0u;
  (void)arg;
  console_printf("\r\nDioneya EVT-PRE-20 B1 bring-up, clock policy %s, %lu Hz\r\n", EVT_PRE_20_CLOCK_POLICY_ID, (unsigned long)SystemCoreClock);
  for (;;) {
    uint8_t buf[16];
    size_t n;
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    while ((n = bsp_uart_read(BSP_UART_CONSOLE, buf, sizeof(buf))) > 0u) {
      for (size_t i = 0u; i < n; i++) {
        char c = (char)buf[i];
        if (c == '\r' || c == '\n') {
          line[len] = '\0';
          if (len) console_exec(line);
          len = 0u;
          console_printf("> ");
        } else if (len + 1u < sizeof(line)) {
          line[len++] = c;
        }
      }
    }
  }
}

/* Every task stack comes from the FreeRTOS heap (nothing else allocates): a new task that does not fit must fail
   the build, not xTaskCreate at boot.  128 B per task covers the TCB and the heap_4 block header. */
#define APP_TASK_STACK_WORDS (APP_STACK_AUDIO + APP_STACK_SUPERVISOR + APP_STACK_SERVICE + APP_STACK_CONSOLE + APP_STACK_BLE + APP_STACK_DSP + \
                              APP_STACK_COMMS + APP_STACK_POWER + APP_STACK_LORA + APP_STACK_REC)
_Static_assert(APP_TASK_STACK_WORDS * 4u + 10u * 128u + 2048u <= configTOTAL_HEAP_SIZE, "task stacks exceed the FreeRTOS heap (keep 2 KB spare)");

bool app_tasks_create(void) {
  zs_pdm_config_t cfg = zs_pdm_config_default();
  cfg.block_samples = APP_AUDIO_BLOCK_SAMPLES;
  zs_audio_ring_init(&audio_ring, audio_storage, APP_AUDIO_RING_FRAMES_B1, APP_AUDIO_SAMPLE_RATE_HZ);
  if (!zs_pdm_capture_init(&capture, &cfg, bsp_mdf_dma_buffers(), &audio_ring)) return false;
  zs_time_init(&time_sync, (double)APP_AUDIO_SAMPLE_RATE_HZ);
  zs_pps_sync_init(&pps, &time_sync, APP_TIM2_CLOCK_HZ, APP_PPS_LABEL_TIMEOUT_MS);
  if (!bsp_mdf_init(&capture, &pps)) return false;
  if (!bsp_tim2_pps_init(&pps)) return false;

  zs_dsp_mcu_init(&dsp_ctx);
  zs_track_window_init(&track, track_max_ms, APP_TRACK_LOST_WINDOWS);
  {
    size_t work;
    zs_complex_t *scratch = zs_dsp_mcu_borrow_work(&work);        /* the AIR gate scratch overlays the DSP work buffer */
    if (work < ZS_AIR_SCRATCH_COMPLEX || !zs_station_pipeline_init(&pipeline, &pipeline_port, scratch, dsp_pcm)) return false;
    {
      size_t stash_samples;
      int16_t *stash = zs_dsp_mcu_borrow_stash(&stash_samples);   /* idle between two feature extractions */
      if (stash_samples < ZS_PIPELINE_HOP_SAMPLES) return false;
      zs_station_pipeline_set_stash(&pipeline, stash);
    }
  }
  zs_selftest_init(&selftests);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_POWER_INA226, "power_good", st_power_good, NULL, true);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_MIC_CAPTURE, "mic_capture", st_mic_capture, &capture, true);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_MIC_ALIGNMENT, "mic_align", st_mic_alignment, &capture, false);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_GNSS_PPS, "gnss_pps", st_gnss_pps, &pps, false);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_RTC_LSE, "rtc_lse", st_rtc_lse, NULL, true);

  zs_command_clock_init(&command_clock, APP_COMMAND_NETWORK_TIME_MAX_MS);
  app_comms_set_clock(command_clock_now);
  app_comms_set_executor(app_commands_execute, NULL);
  app_comms_set_fw_port(app_fw_port());                                  /* CMD_UPDATE_FIRMWARE (addendum F) */
  app_watchdog_capture_reset_cause();
  for (unsigned t = APP_WD_AUDIO; t <= APP_WD_REC; t++) app_watchdog_register((app_wd_task_t)t);
  if (xTaskCreate(audio_task_fn, "audio", APP_STACK_AUDIO, NULL, APP_PRIO_AUDIO, &audio_task) != pdPASS) return false;
  if (xTaskCreate(supervisor_task_fn, "superv", APP_STACK_SUPERVISOR, NULL, APP_PRIO_SUPERVISOR, &supervisor_task) != pdPASS) return false;
  if (xTaskCreate(gnss_task_fn, "gnss", APP_STACK_SERVICE, NULL, APP_PRIO_SERVICE, &gnss_task) != pdPASS) return false;
  if (xTaskCreate(console_task_fn, "console", APP_STACK_CONSOLE, NULL, APP_PRIO_CONSOLE, &console_task) != pdPASS) return false;
  if (xTaskCreate(ble_task_fn, "ble", APP_STACK_BLE, NULL, APP_PRIO_BLE, &ble_task) != pdPASS) return false;
  if (xTaskCreate(dsp_task_fn, "dsp", APP_STACK_DSP, NULL, APP_PRIO_DSP, &dsp_task) != pdPASS) return false;
  if (xTaskCreate(comms_task_fn, "comms", APP_STACK_COMMS, NULL, APP_PRIO_COMMS, &comms_task) != pdPASS) return false;
  if (xTaskCreate(app_power_task, "power", APP_STACK_POWER, NULL, APP_PRIO_POWER, &power_task) != pdPASS) return false;
  if (xTaskCreate(app_lora_task, "lora", APP_STACK_LORA, NULL, APP_PRIO_LORA, &lora_task) != pdPASS) return false;
  if (xTaskCreate(app_audio_rec_task, "rec", APP_STACK_REC, NULL, APP_PRIO_REC, &rec_task) != pdPASS) return false;
  return true;
}

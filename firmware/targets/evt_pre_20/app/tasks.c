/*
 * Milestone B1 task set (bring-up on NUCLEO-U575 / Rev.A):
 *   audio       - converts MDF blocks, drives PPS binding, computes block peaks
 *   supervisor  - zs_power_modes scheduler, self-tests, rail enables, console status line
 *   console     - LPUART1 line commands for the bench: "st" (self-test), "lag", "svc", "modes", "pps"
 *   gnss        - NMEA RMC parser stub: extracts UTC seconds for PPS labelling
 *   ble         - zs_ipc_service over USART3 to the nRF52840 bridge (ICD addendum C), window with S4 SERVICE
 *   dsp         - zs_station_pipeline: 1 s windows at a 0.5 s hop -> zs_dsp_mcu -> votes + AIR gate -> level 1 ->
 *                 detection events into the NOR outbox (fetch in the audio task, analysis here)
 *   comms       - app_comms: BG95 bring-up from the station configuration, MQTT session, outbox drain + heartbeat (B2)
 *   power       - app_power: INA226 on I2C2 every second -> power snapshot for heartbeat, events and the self-test
 */
#include "tasks.h"

#include "FreeRTOS.h"
#include "app_config.h"
#include "app_comms.h"
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
#include "zs_dsp_mcu.h"
#include "zs_ipc_service.h"
#include "zs_nor_storage_layout.h"
#include "zs_pdm_capture.h"
#include "zs_power_modes.h"
#include "zs_pps_sync.h"
#include "zs_selftest.h"
#include "zs_station_pipeline.h"
#include "zs_station_secrets.h"
#include "zs_time.h"
#include "zs_event_outbox.h"

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

static TaskHandle_t audio_task, supervisor_task, console_task, gnss_task, ble_task, dsp_task, comms_task, power_task;

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
static zs_selftest_code_t st_mic_capture(void *ctx, uint32_t *detail) {
  const zs_pdm_capture_t *c = ctx;
  int16_t min_peak = 32767;
  if (c->blocks_processed < 10u) return ZS_ST_SKIPPED;
  for (unsigned i = 0u; i < ZS_PDM_CHANNELS; i++) if (c->peak[i] < min_peak) min_peak = c->peak[i];
  *detail = (uint32_t)min_peak;
  return (min_peak > 8 && c->overruns == 0u) ? ZS_ST_PASS : ZS_ST_FAIL;   /* dead channel or DMA overrun */
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

/* ---- tasks ------------------------------------------------------------------ */
static void audio_task_fn(void *arg) {
  (void)arg;
  for (;;) {
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100));
    while (zs_pdm_capture_process(&capture)) {}
    (void)zs_pps_sync_poll(&pps, bsp_tim2_pps_now());
    (void)zs_time_update(&time_sync, zs_pdm_capture_sample_counter(&capture));
    /* listen/detection duty (S1 and S2 keep the PDM clock): copy the next complete window out of the ring while it is
       still there, hand it to the DSP task; a window that is still pending when the next one completes is skipped
       (dropped). S1 runs the same pipeline as S2 for now - the gate IS the pipeline's AIR gate + level 1; a cheaper
       listen-only gate is low-power work. */
    if ((modes.mode == ZS_MODE_S1_LISTEN || modes.mode == ZS_MODE_S2_DSP) && dsp_task && zs_station_pipeline_fetch(&pipeline, &audio_ring))
      xTaskNotifyGive(dsp_task);
  }
}

/* ---- station pipeline ports ------------------------------------------------ */
static bool pl_extract(void *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) { (void)ctx; return zs_dsp_mcu_extract_1s(&dsp_ctx, pcm, n, out); }
static int64_t pl_sample_time(void *ctx, uint64_t sample) { (void)ctx; return zs_time_for_sample(&time_sync, sample); }
static bool pl_emit(void *ctx, const zs_detection_t *d);
/* boot_id starts as APP_BOOT_ID and is replaced by the NOR boot counter once the stores are bound (the pipeline reads it per event) */
static zs_station_pipeline_port_t pipeline_port = {NULL, pl_extract, pl_sample_time, pl_emit, APP_STATION_ID, APP_BOOT_ID, 0u, 0u};
static uint32_t boot_id = APP_BOOT_ID;

/* Mode events from the pipeline: level 1 SUSPECT or above in S1 opens S2 (gate positive); in S2 an emitted event
   moves to S3 (outbox has data) and APP_DSP_QUIET_WINDOWS windows of NONE end the DSP duty. */
static void dsp_mode_events(void) {
  static uint32_t seen_events;
  static unsigned quiet_windows;
  const uint8_t level = pipeline.presence.level;
  if (modes.mode == ZS_MODE_S1_LISTEN) {
    quiet_windows = 0u;
    if (level >= ZS_PRESENCE_SUSPECT) mode_event(ZS_MODE_EV_GATE_POSITIVE);
    if (pipeline.events_emitted != seen_events) { seen_events = pipeline.events_emitted; mode_event(ZS_MODE_EV_OUTBOX_PENDING); }
    return;
  }
  if (modes.mode != ZS_MODE_S2_DSP) { quiet_windows = 0u; seen_events = pipeline.events_emitted; return; }
  if (pipeline.events_emitted != seen_events) { seen_events = pipeline.events_emitted; quiet_windows = 0u; mode_event(ZS_MODE_EV_DSP_DONE_EVENT); return; }
  if (level == ZS_PRESENCE_NONE) { if (++quiet_windows >= APP_DSP_QUIET_WINDOWS) { quiet_windows = 0u; mode_event(ZS_MODE_EV_DSP_DONE_NOTHING); } }
  else quiet_windows = 0u;
}

static void dsp_task_fn(void *arg) {
  (void)arg;
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    while (pipeline.pending) {
      const uint32_t t0 = xTaskGetTickCount();
      (void)zs_station_pipeline_run_pending(&pipeline);
      pipeline_last_ms = xTaskGetTickCount() - t0;
      if (pipeline_last_ms > pipeline_max_ms) pipeline_max_ms = pipeline_last_ms;
      dsp_mode_events();
    }
  }
}

static void apply_power(zs_mode_t mode) {
  zs_mode_power_t p = zs_mode_power_for(mode);
  bsp_gpio_mic_rail(p.mic_1v8);
  app_comms_allow_modem(p.modem);                 /* EN_MODEM belongs to the comms task (graceful off, dual-SIM sequence) */
  if (p.mdf_clock) (void)bsp_mdf_start(); else bsp_mdf_stop();
  /* clock profile switching (S0 STOP2 etc.) lands with the low-power work; B1 keeps 160 MHz */
  (void)zs_mode_clock_profile(mode);
}


static uint32_t tamper_events;

static void supervisor_task_fn(void *arg) {
  zs_mode_t last = ZS_MODE_SHUTDOWN;
  uint32_t tamper_since = 0u;
  bool tamper_fired = false;
  (void)arg;
  zs_mode_init(&modes, NULL, xTaskGetTickCount());
  bsp_gpio_mic_rail(true);
  vTaskDelay(pdMS_TO_TICKS(50));                 /* 1V8_MIC settle before the PDM clock */
  (void)bsp_mdf_start();
  vTaskDelay(pdMS_TO_TICKS(300));                /* let the capture stabilise for the self-tests */
  if (zs_selftest_run_all(&selftests, xTaskGetTickCount())) {
    (void)zs_mode_on_event(&modes, ZS_MODE_EV_BOOT_DONE, xTaskGetTickCount());
  } else {
    console_printf("selftest: required test failed, staying in S0\r\n");
  }
  for (;;) {
    uint32_t bits = 0u;
    uint32_t now;
    (void)xTaskNotifyWait(0u, UINT32_MAX, &bits, pdMS_TO_TICKS(100));
    now = xTaskGetTickCount();
    for (unsigned ev = 1u; ev < 32u; ev++) if (bits & (1u << ev)) (void)zs_mode_on_event(&modes, (zs_mode_event_t)ev, now);
    (void)zs_mode_tick(&modes, now);
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
      apply_power(modes.mode);
      last = modes.mode;
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

static void gnss_task_fn(void *arg) {
  static char line[96];
  size_t len = 0u;
  (void)arg;
  for (;;) {
    uint8_t buf[32];
    size_t n;
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(500));
    while ((n = bsp_uart_read(BSP_UART_GNSS, buf, sizeof(buf))) > 0u) {
      for (size_t i = 0u; i < n; i++) {
        char c = (char)buf[i];
        if (c == '\n') {
          int64_t epoch;
          line[len] = '\0';
          if (rmc_epoch_us(line, &epoch)) zs_pps_sync_on_utc(&pps, epoch);   /* the RMC follows the PPS edge it labels */
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
static zs_archive_storage_t nor_archive_storage;      /* handed to the prehistory archive with the rest of B3 */
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
  strncpy(hb->model_ver, "c46", sizeof(hb->model_ver) - 1u);
  strncpy(hb->hardware_rev, APP_STATION_HW_REV, sizeof(hb->hardware_rev) - 1u);
  hb->self_test_ok = zs_selftest_required_ok(&selftests);
  hb->gnss.time_trust = (uint8_t)time_sync.trust;
  hb->gnss.expected_time_error_us = time_sync.expected_error_us;
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
  return true;
}
static void comms_session_done(void *ctx) { (void)ctx; mode_event(ZS_MODE_EV_COMMS_DONE); }
static const app_comms_hooks_t comms_hooks = {comms_fill_heartbeat, NULL, console_printf, comms_session_done};

static void secrets_apply(void);   /* defined after ipc_port */

/* Pushes the loaded/edited secrets into their consumers; values are never printed. */
static void secrets_apply(void) {
  if (secrets.engineer_key_set) { memcpy(engineer_key, secrets.engineer_key, sizeof(engineer_key)); ipc_port.engineer_key = engineer_key; }
  else ipc_port.engineer_key = NULL;
  for (unsigned i = 0u; i < 2u; i++) if (secrets.iccid[i][0]) (void)app_comms_set_sim_iccid(i + 1u, secrets.iccid[i]);
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

/* Commits the current secrets to NOR; false on the RAM fallback or a storage error (the RAM copy still applies). */
static bool secrets_persist(void) {
  if (!secrets_on_nor) return false;
  if (zs_station_secrets_commit(&secrets_io, &secrets) != ZS_STATION_SECRETS_OK) return false;
  secrets_loaded = true;
  return true;
}

static void bind_record_stores(void) {
  memset(cfg_slots, 0xff, sizeof(cfg_slots));
  memset(pos_slots, 0xff, sizeof(pos_slots));
  if (bsp_nor_init(&nor) &&
      zs_nor_storage_bind_stores(&nor_bindings, &nor, APP_NOR_COMMAND_SLOTS, APP_NOR_OUTBOX_SLOTS, &nor_archive_storage,
                                 &nor_command_io, &nor_outbox_io, &cfg_io, &pos_io)) {
    stores_on_nor = true;
    app_nrf_update_bind(&nor, &nor_bindings.layout, console_printf);
    app_comms_bind(&nor_outbox_io, &nor_command_io, &comms_hooks);        /* comms needs the durable stores */
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
    /* station secrets: two blocks before the boot counter */
    if (zs_nor_storage_bind_secrets(&nor_bindings, &nor, &secrets_io)) {
      const zs_station_secrets_result_t r = zs_station_secrets_load(&secrets_io, &secrets, NULL);
      secrets_on_nor = true;
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
  if (!stores_on_nor) { pipeline_events_ram++; return true; }
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
    { static uint32_t seen_version; if (ipc.config_loaded && ipc.config.version != seen_version) { seen_version = ipc.config.version; app_comms_set_config(&ipc.config, boot_id); } }
    while ((n = bsp_uart_read(BSP_UART_BLE, buf, sizeof(buf))) > 0u) zs_ipc_service_on_uart_rx(&ipc, buf, n);
    if (ble_recovery_request) { ble_recovery_request = false; ble_enter_recovery(); (void)zs_ipc_service_init(&ipc, &ipc_port); }
    if (app_nrf_update_pending()) { app_nrf_update_run(); (void)zs_ipc_service_init(&ipc, &ipc_port); (void)zs_ipc_service_ping(&ipc); }
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
  } else if (strcmp(cmd, "pps") == 0) {
    console_printf("pps edges %lu bound %lu drop(label %lu pps %lu bracket %lu) ppm %ld trust %d err_us %lu\r\n",
                   (unsigned long)bsp_tim2_pps_edges(), (unsigned long)pps.bound_count, (unsigned long)pps.dropped_no_label,
                   (unsigned long)pps.dropped_no_pps, (unsigned long)pps.dropped_no_bracket, (long)zs_pps_sync_rate_error_ppm(&pps),
                   (int)time_sync.trust, (unsigned long)time_sync.expected_error_us);
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
    console_printf("mode %s, tamper events %lu\r\n", zs_mode_name(modes.mode), (unsigned long)tamper_events);
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
    console_printf("  features f0 %d Hz harmonics %d step %d Hz stab %d%% centroid %d Hz flat %d%% noise %d%% rough %d%%\r\n",
                   (int)pipeline.features[0], (int)pipeline.features[1], (int)pipeline.features[2], (int)(pipeline.features[3] * 100.0f),
                   (int)pipeline.features[7], (int)(pipeline.features[8] * 100.0f), (int)(pipeline.features[10] * 100.0f), (int)(pipeline.features[15] * 100.0f));
  } else if (strcmp(cmd, "comms") == 0) {
    app_comms_status(console_printf);
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
    console_printf("secrets %s (%s, v%lu): engineer key %s, iccid1 %s, iccid2 %s, command key %s\r\n", secrets_loaded ? "loaded" : "none",
                   secrets_on_nor ? "nor" : "ram", (unsigned long)secrets.version, secrets.engineer_key_set ? "set" : "-",
                   secrets.iccid[0][0] ? "set" : "-", secrets.iccid[1][0] ? "set" : "-", secrets.command_key_set ? "set" : "-");
  } else if (strcmp(cmd, "secrets clear") == 0) {
    memset(&secrets, 0, sizeof(secrets));
    memset(engineer_key, 0, sizeof(engineer_key));
    secrets_loaded = false;
    secrets_apply();
    console_printf((!secrets_on_nor || zs_station_secrets_clear(&secrets_io) == ZS_STATION_SECRETS_OK) ? "secrets: cleared (sim iccids apply after reboot)\r\n" : "secrets: nor clear failed\r\n");
  } else if (strcmp(cmd, "power") == 0) {
    app_power_status(console_printf);
  } else if (strcmp(cmd, "heap") == 0) {
    console_printf("heap free %u min %u\r\n", (unsigned)xPortGetFreeHeapSize(), (unsigned)xPortGetMinimumEverFreeHeapSize());
  } else if (cmd[0] != '\0') {
    console_printf("commands: st lag pps audio dsp svc modes ble ping bledfu engkey simiccid secrets [clear] nrfimg nrfupd comms [on|off] power heap\r\n");
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
  {
    size_t work;
    zs_complex_t *scratch = zs_dsp_mcu_borrow_work(&work);        /* the AIR gate scratch overlays the DSP work buffer */
    if (work < ZS_AIR_SCRATCH_COMPLEX || !zs_station_pipeline_init(&pipeline, &pipeline_port, scratch, dsp_pcm)) return false;
  }
  zs_selftest_init(&selftests);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_POWER_INA226, "power_good", st_power_good, NULL, true);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_MIC_CAPTURE, "mic_capture", st_mic_capture, &capture, true);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_MIC_ALIGNMENT, "mic_align", st_mic_alignment, &capture, false);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_GNSS_PPS, "gnss_pps", st_gnss_pps, &pps, false);
  (void)zs_selftest_register(&selftests, ZS_ST_ID_RTC_LSE, "rtc_lse", st_rtc_lse, NULL, true);

  if (xTaskCreate(audio_task_fn, "audio", APP_STACK_AUDIO, NULL, APP_PRIO_AUDIO, &audio_task) != pdPASS) return false;
  if (xTaskCreate(supervisor_task_fn, "superv", APP_STACK_SUPERVISOR, NULL, APP_PRIO_SUPERVISOR, &supervisor_task) != pdPASS) return false;
  if (xTaskCreate(gnss_task_fn, "gnss", APP_STACK_SERVICE, NULL, APP_PRIO_SERVICE, &gnss_task) != pdPASS) return false;
  if (xTaskCreate(console_task_fn, "console", APP_STACK_CONSOLE, NULL, APP_PRIO_CONSOLE, &console_task) != pdPASS) return false;
  if (xTaskCreate(ble_task_fn, "ble", APP_STACK_BLE, NULL, APP_PRIO_BLE, &ble_task) != pdPASS) return false;
  if (xTaskCreate(dsp_task_fn, "dsp", APP_STACK_DSP, NULL, APP_PRIO_DSP, &dsp_task) != pdPASS) return false;
  if (xTaskCreate(app_comms_task, "comms", APP_STACK_COMMS, NULL, APP_PRIO_COMMS, &comms_task) != pdPASS) return false;
  if (xTaskCreate(app_power_task, "power", APP_STACK_POWER, NULL, APP_PRIO_POWER, &power_task) != pdPASS) return false;
  return true;
}

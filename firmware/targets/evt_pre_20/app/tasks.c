/*
 * Milestone B1 task set (bring-up on NUCLEO-U575 / Rev.A):
 *   audio       - converts MDF blocks, drives PPS binding, computes block peaks
 *   supervisor  - zs_power_modes scheduler, self-tests, rail enables, console status line
 *   console     - LPUART1 line commands for the bench: "st" (self-test), "lag", "svc", "modes", "pps"
 *   gnss        - NMEA RMC parser stub: extracts UTC seconds for PPS labelling
 *   ble         - zs_ipc_service over USART3 to the nRF52840 bridge (ICD addendum C), window with S4 SERVICE
 * The comms task (BG95) is created in B2 on top of zs_bg95 / zs_bg95_provision.
 */
#include "tasks.h"

#include "FreeRTOS.h"
#include "app_config.h"
#include "bsp_gpio.h"
#include "bsp_mdf.h"
#include "bsp_tim2_pps.h"
#include "bsp_uart.h"
#include "evt_pre_20_clock_policy.h"
#include "queue.h"
#include "task.h"
#include "zs_audio.h"
#include "zs_ipc_service.h"
#include "zs_pdm_capture.h"
#include "zs_power_modes.h"
#include "zs_pps_sync.h"
#include "zs_selftest.h"
#include "zs_time.h"

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

static TaskHandle_t audio_task, supervisor_task, console_task, gnss_task, ble_task;

/* ---- ISR notifications ----------------------------------------------------- */
void app_audio_block_notify_from_isr(void) {
  BaseType_t woken = pdFALSE;
  if (audio_task) vTaskNotifyGiveFromISR(audio_task, &woken);
  portYIELD_FROM_ISR(woken);
}

void app_uart_rx_notify_from_isr(bsp_uart_id_t id) {
  BaseType_t woken = pdFALSE;
  TaskHandle_t t = id == BSP_UART_CONSOLE ? console_task : id == BSP_UART_GNSS ? gnss_task : id == BSP_UART_BLE ? ble_task : NULL;
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

static zs_selftest_code_t st_power_good(void *ctx, uint32_t *detail) {
  (void)ctx;
  *detail = bsp_gpio_power_fault() ? 1u : 0u;
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
  }
}

static void apply_power(zs_mode_t mode) {
  zs_mode_power_t p = zs_mode_power_for(mode);
  bsp_gpio_mic_rail(p.mic_1v8);
  bsp_gpio_modem_power(p.modem);
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
   B1: configuration and installation records live in RAM-backed slots (NOR binding is B3); the role is
   the installer and "secure" follows the link state reported by the nRF (LESC + label secret on the
   prototype).  The advertising window opens with S4 SERVICE and closes when the mode leaves it. */
static zs_ipc_service_t ipc;
static uint8_t cfg_slots[ZS_STATION_CONFIG_SLOT_COUNT][ZS_STATION_CONFIG_SLOT_BYTES];
static uint8_t pos_slots[ZS_INSTALLATION_STORE_SLOT_COUNT][ZS_INSTALLATION_STORE_SLOT_BYTES];
static uint32_t service_started_ms, ble_audit_events;

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
static zs_commissioning_role_t ble_peer_role(void *ctx) { (void)ctx; return ZS_COMMISSIONING_ROLE_INSTALLER; }
static bool ble_peer_secure(void *ctx) { (void)ctx; return ipc.link_state == 2u; }

static const zs_station_config_io_t cfg_io = {cfg_slots, ram_read, ram_erase, ram_write};
static const zs_installation_store_io_t pos_io = {pos_slots, ram_read, ram_erase, ram_write};
static const zs_commissioning_audit_io_t audit_io = {NULL, ble_audit};
static const zs_ipc_identity_t identity = {APP_STATION_SERIAL, APP_STATION_HW_REV, APP_STATION_FW_VERSION, APP_STATION_BL_VERSION, APP_STATION_ID, ZS_STATION_CONFIG_REGION_RU868};
static const zs_ipc_service_port_t ipc_port = {NULL, ble_uart_send, ble_now_ms, ble_service_mode, ble_peer_role, ble_peer_secure,
                                               &cfg_io, &pos_io, &audit_io, &selftests, &identity};

static void ble_task_fn(void *arg) {
  bool window_open = false;
  (void)arg;
  memset(cfg_slots, 0xff, sizeof(cfg_slots));
  memset(pos_slots, 0xff, sizeof(pos_slots));
  (void)bsp_uart_init(BSP_UART_BLE, APP_UART_BLE_BAUD);
  bsp_gpio_ble_enable(true);
  vTaskDelay(pdMS_TO_TICKS(200));                  /* nRF boot */
  (void)zs_ipc_service_init(&ipc, &ipc_port);
  for (;;) {
    uint8_t buf[64];
    size_t n;
    (void)ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(250));
    while ((n = bsp_uart_read(BSP_UART_BLE, buf, sizeof(buf))) > 0u) zs_ipc_service_on_uart_rx(&ipc, buf, n);
    const bool want = modes.mode == ZS_MODE_S4_SERVICE;
    if (want && !window_open) { service_started_ms = xTaskGetTickCount(); (void)zs_ipc_service_set_window(&ipc, true, APP_BLE_SERVICE_WINDOW_S); }
    else if (!want && window_open) (void)zs_ipc_service_set_window(&ipc, false, 0u);
    window_open = want;
  }
}

static void console_exec(const char *cmd) {
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
    console_printf("ble link %u window %s config v%lu%s writes ok %lu rejected %lu audits %lu uart overruns %lu\r\n",
                   ipc.link_state, modes.mode == ZS_MODE_S4_SERVICE ? "open" : "closed", (unsigned long)ipc.config.version,
                   ipc.config_loaded ? "" : " (none)", (unsigned long)ipc.writes_ok, (unsigned long)ipc.writes_rejected,
                   (unsigned long)ble_audit_events, (unsigned long)bsp_uart_rx_overruns(BSP_UART_BLE));
  } else if (strcmp(cmd, "heap") == 0) {
    console_printf("heap free %u min %u\r\n", (unsigned)xPortGetFreeHeapSize(), (unsigned)xPortGetMinimumEverFreeHeapSize());
  } else if (cmd[0] != '\0') {
    console_printf("commands: st lag pps audio svc modes ble heap\r\n");
  }
}

static void console_task_fn(void *arg) {
  static char line[64];
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
  return true;
}

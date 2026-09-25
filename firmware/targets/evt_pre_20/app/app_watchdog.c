#include "app_watchdog.h"
#include "app_config.h"
#include "FreeRTOS.h"
#include "task.h"
#include "zs_task_watch.h"
#include "stm32u5xx_hal.h"

#define BKP_MAGIC 0x57440000u          /* "WD" in the upper half, missed mask in the lower half */

static zs_task_watch_t watch;
static uint8_t reset_cause;
static uint16_t previous_missed;
static bool started;
static volatile uint32_t stall_mask;
static uint32_t feeds;

void app_watchdog_capture_reset_cause(void) {
  const uint32_t csr = RCC->CSR;
  if (csr & RCC_CSR_IWDGRSTF) reset_cause = 4u;
  else if (csr & RCC_CSR_WWDGRSTF) reset_cause = 5u;
  else if (csr & RCC_CSR_LPWRRSTF) reset_cause = 6u;
  else if (csr & RCC_CSR_OBLRSTF) reset_cause = 7u;
  else if (csr & RCC_CSR_SFTRSTF) reset_cause = 3u;
  else if (csr & RCC_CSR_BORRSTF) reset_cause = 1u;
  else if (csr & RCC_CSR_PINRSTF) reset_cause = 2u;
  else reset_cause = 0u;
  RCC->CSR |= RCC_CSR_RMVF;
  __HAL_RCC_PWR_CLK_ENABLE();
  PWR->DBPR |= PWR_DBPR_DBP;                              /* backup domain writable (TAMP backup registers) */
  __HAL_RCC_RTCAPB_CLK_ENABLE();                          /* TAMP registers sit behind the RTC APB clock */
  if ((TAMP->BKP1R & 0xFFFF0000u) == BKP_MAGIC && reset_cause == 4u) previous_missed = (uint16_t)(TAMP->BKP1R & 0xFFFFu);
  TAMP->BKP1R = 0u;
  zs_task_watch_init(&watch, APP_WATCHDOG_WINDOW_MS, 0u);
}
uint8_t app_watchdog_reset_cause(void) { return reset_cause; }
uint16_t app_watchdog_previous_missed(void) { return previous_missed; }
const char *app_watchdog_reset_cause_name(void) {
  static const char *const n[] = {"unknown", "power/BOR", "pin", "software", "IWDG", "WWDG", "low-power", "option bytes"};
  return reset_cause < 8u ? n[reset_cause] : "?";
}

void app_watchdog_register(app_wd_task_t t) { taskENTER_CRITICAL(); zs_task_watch_register(&watch, (unsigned)t); taskEXIT_CRITICAL(); }
void app_watchdog_checkin(app_wd_task_t t) {
  if (stall_mask & (1u << t)) return;                     /* bench stall */
  taskENTER_CRITICAL(); zs_task_watch_checkin(&watch, (unsigned)t); taskEXIT_CRITICAL();
}
void app_watchdog_hold(app_wd_task_t t, uint32_t ms) { taskENTER_CRITICAL(); zs_task_watch_hold(&watch, (unsigned)t, ms, xTaskGetTickCount()); taskEXIT_CRITICAL(); }
void app_watchdog_simulate_stall(app_wd_task_t t) { stall_mask |= 1u << t; }
bool app_watchdog_stalled(app_wd_task_t t) { return (stall_mask & (1u << t)) != 0u; }

void app_watchdog_start(void) {
  const uint32_t reload = (APP_WATCHDOG_TIMEOUT_MS * (32000u / 256u)) / 1000u;   /* LSI 32 kHz / 256 */
  DBGMCU->APB1FZR1 |= DBGMCU_APB1FZR1_DBG_IWDG_STOP;
  IWDG->KR = 0xCCCCu;                                      /* start (LSI switched on by hardware) */
  IWDG->KR = 0x5555u;                                      /* unlock PR/RLR */
  IWDG->PR = 6u;                                           /* /256 */
  IWDG->RLR = reload > 0xFFFu ? 0xFFFu : reload;
  for (unsigned i = 0u; i < 100000u && (IWDG->SR & (IWDG_SR_PVU | IWDG_SR_RVU)); i++) {}
  IWDG->KR = 0xAAAAu;
  taskENTER_CRITICAL(); watch.window_start_ms = xTaskGetTickCount(); watch.seen = watch.registered; taskEXIT_CRITICAL();
  started = true;
}

void app_watchdog_service(void) {
  bool feed;
  if (!started) return;
  taskENTER_CRITICAL(); feed = zs_task_watch_service(&watch, xTaskGetTickCount()); taskEXIT_CRITICAL();
  if (feed) { IWDG->KR = 0xAAAAu; feeds++; return; }
  TAMP->BKP1R = BKP_MAGIC | (watch.missed & 0xFFFFu);     /* culprit for the next boot's heartbeat */
}

void app_watchdog_status(void (*print)(const char *fmt, ...)) {
  print("watchdog %s timeout %lu ms window %lu ms | windows ok %lu missed %lu (mask 0x%04lx) feeds %lu | boot: %s%s previous stuck mask 0x%04x\r\n",
        started ? "running" : "off", (unsigned long)APP_WATCHDOG_TIMEOUT_MS, (unsigned long)APP_WATCHDOG_WINDOW_MS,
        (unsigned long)watch.windows_ok, (unsigned long)watch.windows_missed, (unsigned long)watch.missed, (unsigned long)feeds,
        app_watchdog_reset_cause_name(), stall_mask ? " (bench stall active)" : "", previous_missed);
}

#include "app_power.h"
#include "app_config.h"
#include "bsp_i2c.h"
#include "FreeRTOS.h"
#include "task.h"
#include "zs_ina226.h"

#include <string.h>

static zs_ina226_t ina;
static zs_power_t snapshot;
static bool snapshot_valid, probed;
static uint32_t samples, failures, reprobes, last_ok_ms;
static uint8_t last_status = ZS_INA226_STATUS_IO;

static int hal_i2c_read(void *ctx, unsigned bus, uint8_t a, uint8_t reg, uint8_t *d, size_t n) { (void)ctx; (void)bus; return bsp_i2c_mem_read(a, reg, d, n); }
static int hal_i2c_write(void *ctx, unsigned bus, uint8_t a, uint8_t reg, const uint8_t *d, size_t n) { (void)ctx; (void)bus; return bsp_i2c_mem_write(a, reg, d, n); }
static uint32_t hal_millis(void *ctx) { (void)ctx; return xTaskGetTickCount(); }
static void hal_delay(void *ctx, uint32_t ms) { (void)ctx; vTaskDelay(pdMS_TO_TICKS(ms)); }
static const zs_hal_port_t hal = {NULL, hal_millis, hal_delay, NULL, NULL, hal_i2c_read, hal_i2c_write, NULL, NULL};

/* Battery level from the bus voltage (linear between the empty/full points of app_config; chemistry to confirm). */
static uint8_t battery_pct(uint32_t mv) {
  if (mv <= APP_BATTERY_EMPTY_MV) return 0u;
  if (mv >= APP_BATTERY_FULL_MV) return 100u;
  return (uint8_t)(((mv - APP_BATTERY_EMPTY_MV) * 100u) / (APP_BATTERY_FULL_MV - APP_BATTERY_EMPTY_MV));
}

static void apply(const zs_ina226_measurement_t *m) {
  zs_power_t p = snapshot;
  p.battery_bus_mv = (uint16_t)(m->bus_mv > 65535u ? 65535u : m->bus_mv);
  p.battery_mv = p.battery_bus_mv;
  p.battery_current_ma = (int16_t)(m->current_ua / 1000);
  p.battery_power_mw = m->power_mw;
  p.battery_pct = battery_pct(m->bus_mv);
  p.monitor_status = 0u;
  taskENTER_CRITICAL();
  snapshot = p;
  snapshot_valid = true;
  taskEXIT_CRITICAL();
}

bool app_power_snapshot(zs_power_t *out) {
  bool valid;
  if (!out) return false;
  taskENTER_CRITICAL();
  *out = snapshot;
  valid = snapshot_valid;
  taskEXIT_CRITICAL();
  if (!valid) { memset(out, 0, sizeof(*out)); out->monitor_status = last_status ? last_status : ZS_INA226_STATUS_IO; return false; }
  out->monitor_status = last_status;          /* nonzero: the latest read failed, values are the last good sample */
  return true;
}

uint32_t app_power_battery_mv(void) { return snapshot_valid ? snapshot.battery_bus_mv : 0u; }

void app_power_task(void *arg) {
  (void)arg;
  zs_ina226_init(&ina, &hal, 2u, ZS_INA226_ADDR_REV_A);
  if (!bsp_i2c_init()) last_status = ZS_INA226_STATUS_IO;
  for (;;) {
    zs_ina226_measurement_t m;
    if (!probed) {
      last_status = zs_ina226_probe_and_configure(&ina);
      probed = last_status == ZS_INA226_STATUS_OK;
      if (!probed) { reprobes++; (void)bsp_i2c_reset(); vTaskDelay(pdMS_TO_TICKS(APP_POWER_PERIOD_MS * 5u)); continue; }
    }
    last_status = zs_ina226_read(&ina, &m);
    if (last_status == ZS_INA226_STATUS_OK && m.valid) { apply(&m); samples++; last_ok_ms = xTaskGetTickCount(); }
    else { failures++; if (failures % 5u == 0u) probed = false; }   /* five misses in a row: probe again */
    vTaskDelay(pdMS_TO_TICKS(APP_POWER_PERIOD_MS));
  }
}

void app_power_status(void (*print)(const char *fmt, ...)) {
  zs_power_t p;
  const bool valid = app_power_snapshot(&p);
  print("power %s status 0x%02x: bus %u mV current %d mA power %lu mW battery %u%% | samples %lu failures %lu reprobes %lu i2c errors %lu last ok %lu s ago\r\n",
        valid ? "ok" : "no sample", p.monitor_status, p.battery_bus_mv, (int)p.battery_current_ma, (unsigned long)p.battery_power_mw, p.battery_pct,
        (unsigned long)samples, (unsigned long)failures, (unsigned long)reprobes, (unsigned long)bsp_i2c_errors(),
        (unsigned long)((xTaskGetTickCount() - last_ok_ms) / 1000u));
}

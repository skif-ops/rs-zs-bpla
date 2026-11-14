#ifndef APP_POWER_H
#define APP_POWER_H
/*
 * Power task: the INA226 on I2C2 (Rev.A battery monitor, zs_ina226) sampled every APP_POWER_PERIOD_MS, folded into
 * one zs_power_t snapshot that the heartbeat, the detection events and the self-test read.  monitor_status = 0 only
 * while the last read was valid; a failed read keeps the last good values and raises the driver status bits, and a
 * repeated failure re-probes the device (and recovers the bus) instead of spinning on a dead sensor.
 */
#include "zs_types.h"
#include <stdbool.h>
#include <stdint.h>

void app_power_task(void *arg);              /* never returns */
/* Latest snapshot (copied under a critical section); false when no valid sample has ever been taken. */
bool app_power_snapshot(zs_power_t *out);
/* Battery bus voltage of the last valid sample in mV (0 when none): the self-test detail. */
uint32_t app_power_battery_mv(void);
void app_power_status(void (*print)(const char *fmt, ...));
#endif

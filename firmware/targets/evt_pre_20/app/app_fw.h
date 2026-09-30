#ifndef APP_FW_H
#define APP_FW_H
/*
 * A/B banks of the STM32U585 for the firmware update over MQTT (MQTT_TLS_ICD_v0_1 addendum F).
 *
 *   0x08000000  running bank (whichever physical bank SWAP_BANK maps there): image 1016 KiB + boot record page
 *   0x08100000  other bank: the download target (app_comms through app_fw_port()), armed for trial before the swap
 *
 * app_fw_boot_guard() runs in main() right after the clock: it counts the trial attempts on the running bank's
 * record, starts the IWDG early while on trial (a hang before the supervisor starts it resets the station) and swaps
 * back after ZS_FW_BOOT_MAX_ATTEMPTS unconfirmed boots.  The supervisor confirms a trial once the self-test passed
 * and a session completed, and resets an unconfirmed trial after ZS_FW_BOOT_TRIAL_TIMEOUT_MS.
 */
#include "app_comms.h"
#include <stdbool.h>
#include <stdint.h>

void app_fw_boot_guard(void);
const app_comms_fw_port_t *app_fw_port(void);
uint32_t app_fw_running_version(void);
bool app_fw_on_trial(void);
/* The trial proved itself (self-test passed, a session completed): the CONFIRM mark. */
void app_fw_confirm(bool selftest_ok);
/* Supervisor: a due install (swap + reset) or an expired trial (reset = the next attempt). */
void app_fw_tick(uint32_t now_ms);
/* Heartbeat keys 18..20. */
void app_fw_fill_heartbeat(zs_detector_health_t *d);
void app_fw_status(void (*print)(const char *fmt, ...));
#endif

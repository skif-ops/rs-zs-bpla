#ifndef APP_COMMANDS_H
#define APP_COMMANDS_H
/*
 * Executor of verified remote commands (MQTT_TLS_ICD_v0_1 §2.1 and addendum D), installed with
 * app_comms_set_executor.  The command channel has already checked the signature, the validity window and the
 * journal (ACCEPTED is durable before this runs; COMPLETED and the ACK follow):
 *   CMD_SET_PARAMS    whole-command validation -> NOR commit -> apply -> OK; REJECTED 0x0100|id; FAILED 1 (NOR)
 *   CMD_REBOOT        OK now, NVIC reset max(delay_s, APP_REBOOT_MIN_DELAY_S) later (app_commands_tick), so the
 *                     ACK leaves first; a redelivery after the reset finds COMPLETED in the journal (no second reset)
 *   CMD_REQUEST_AUDIO REJECTED detail 1 until the event audio archive lands (addendum B)
 */
#include "zs_command.h"
#include "zs_station_params.h"
#include <stdbool.h>
#include <stdint.h>

/* Loads the stored parameters (defaults when none) and applies them once; `io` may be NULL (RAM-only session). */
void app_commands_bind(const zs_station_params_io_t *io, void (*apply)(const zs_station_params_t *p), void (*log)(const char *fmt, ...));
bool app_commands_execute(void *ctx, const zs_command_t *cmd, zs_command_ack_result_t *result, uint16_t *detail);
/* Supervisor: performs a scheduled reboot when it is due. */
void app_commands_tick(uint32_t now_ms);
const zs_station_params_t *app_commands_params(void);
void app_commands_status(void (*print)(const char *fmt, ...));
#endif

#include "app_commands.h"
#include "app_comms.h"
#include "app_config.h"
#include "zs_command_keys.h"
#include <string.h>
#include "FreeRTOS.h"
#include "task.h"
#include "stm32u5xx_hal.h"

static const zs_station_params_io_t *params_io;
static zs_station_params_t params;
static bool params_ready;                             /* defaults until the stores are bound */
static void (*apply_fn)(const zs_station_params_t *p);
static void (*log_fn)(const char *fmt, ...);
static volatile bool reboot_pending;
static volatile uint32_t reboot_at_ms;
static uint32_t executed, rejected, failed, last_detail;
static uint8_t last_code;
static const zs_station_secrets_io_t *keys_io;
static void (*keys_changed_fn)(const zs_station_secrets_t *rec);
static uint32_t key_rotations, key_promotions;

void app_commands_bind(const zs_station_params_io_t *io, void (*apply)(const zs_station_params_t *p), void (*log)(const char *fmt, ...)) {
  zs_station_params_result_t r;
  params_io = io; apply_fn = apply; log_fn = log;
  r = io ? zs_station_params_load(io, &params) : ZS_STATION_PARAMS_NOT_FOUND;
  if (!io) zs_station_params_defaults(&params);
  params_ready = true;
  if (log_fn) log_fn("params: %s (v%lu)\r\n", r == ZS_STATION_PARAMS_OK ? "loaded" : r == ZS_STATION_PARAMS_NOT_FOUND ? "defaults" : "read error, defaults",
                     (unsigned long)params.version);
  if (apply_fn) apply_fn(&params);
}

void app_commands_bind_keys(const zs_station_secrets_io_t *io, void (*changed)(const zs_station_secrets_t *rec)) {
  keys_io = io; keys_changed_fn = changed;
}

/* the record changed on NOR: its owner reloads the trust set and its RAM copy */
static void keys_reload(const char *what) {
  zs_station_secrets_t rec;
  if (keys_io && zs_station_secrets_load(keys_io, &rec, NULL) == ZS_STATION_SECRETS_OK) {
    if (keys_changed_fn) keys_changed_fn(&rec);
    if (log_fn) log_fn("command key: %s (secrets v%lu)\r\n", what, (unsigned long)rec.version);
  }
  memset(&rec, 0, sizeof(rec));
}

bool app_commands_execute(void *ctx, const zs_command_t *cmd, zs_command_ack_result_t *result, uint16_t *detail) {
  (void)ctx;
  *result = ZS_COMMAND_ACK_OK;
  *detail = 0u;
  last_code = (uint8_t)cmd->code;
  /* addendum E: the first command signed by the next key proves the server has it - it becomes the current key */
  if (keys_io && zs_command_keys_on_verified(keys_io, cmd->key_id)) { key_promotions++; keys_reload("next key promoted, old key dropped"); }
  switch (cmd->code) {
    case ZS_COMMAND_SET_PARAMS: {
      zs_station_params_t next;
      const uint16_t reject = zs_station_params_apply_command(&params, &cmd->params, &next);
      if (reject) { *result = ZS_COMMAND_ACK_REJECTED; *detail = reject; break; }
      if (params_io && zs_station_params_commit(params_io, &next) != ZS_STATION_PARAMS_OK) { *result = ZS_COMMAND_ACK_FAILED; *detail = 1u; break; }
      params = next;
      if (apply_fn) apply_fn(&params);
      if (log_fn) log_fn("params: v%lu applied by command\r\n", (unsigned long)params.version);
      break;
    }
    case ZS_COMMAND_REBOOT: {
      const uint32_t delay_s = cmd->reboot.delay_s > APP_REBOOT_MIN_DELAY_S ? cmd->reboot.delay_s : APP_REBOOT_MIN_DELAY_S;
      reboot_at_ms = xTaskGetTickCount() + delay_s * 1000u;
      reboot_pending = true;
      if (log_fn) log_fn("reboot: by command in %lu s\r\n", (unsigned long)delay_s);
      break;
    }
    case ZS_COMMAND_REQUEST_AUDIO:
      /* addendum B: answered now (refusal) or accepted: the upload runs in the session, the ACK follows it */
      if (!app_comms_request_audio(cmd, result, detail)) return false;
      break;
    case ZS_COMMAND_UPDATE_FIRMWARE:
      /* addendum F: refused now, or accepted: the download runs in the sessions, the ACK follows the image check */
      if (!app_comms_update_firmware(cmd, result, detail)) return false;
      break;
    case ZS_COMMAND_SET_NETWORK:
      /* addendum G: accepted for trial (the next bring-up uses it, the first session online stores it) or refused */
      (void)app_comms_set_network(cmd, result, detail);
      break;
    case ZS_COMMAND_ROTATE_KEY:
      if (!keys_io) { *result = ZS_COMMAND_ACK_REJECTED; *detail = ZS_COMMAND_KEYS_REJECT_NO_RECORD; break; }
      zs_command_keys_rotate(keys_io, cmd->rotate.public_key, result, detail);
      if (*result == ZS_COMMAND_ACK_OK) { key_rotations++; keys_reload("next key installed, both trusted"); }
      break;
    default:
      *result = ZS_COMMAND_ACK_REJECTED;
      *detail = 1u;                                   /* not implemented on this station yet */
      break;
  }
  if (*result == ZS_COMMAND_ACK_OK) executed++;
  else if (*result == ZS_COMMAND_ACK_REJECTED) rejected++;
  else failed++;
  last_detail = *detail;
  return true;
}

void app_commands_tick(uint32_t now_ms) {
  if (!reboot_pending || (int32_t)(now_ms - reboot_at_ms) < 0) return;
  if (log_fn) log_fn("reboot: now\r\n");
  vTaskDelay(pdMS_TO_TICKS(50));                      /* let the console line out */
  NVIC_SystemReset();
}

const zs_station_params_t *app_commands_params(void) {
  if (!params_ready) { zs_station_params_defaults(&params); params_ready = true; }
  return &params;
}

void app_commands_status(void (*print)(const char *fmt, ...)) {
  print("commands executed %lu rejected %lu failed %lu (last code %u detail 0x%04lx)%s | key rotations %lu promotions %lu | params v%lu: heartbeat %ld s mic %ld update %ld win degraded-after %ld gsm-probe %ld s dwell %ld s (%s)\r\n",
        (unsigned long)executed, (unsigned long)rejected, (unsigned long)failed, last_code, (unsigned long)last_detail,
        reboot_pending ? " | REBOOT PENDING" : "", (unsigned long)key_rotations, (unsigned long)key_promotions, (unsigned long)params.version,
        (long)params.value[0], (long)params.value[1], (long)params.value[2], (long)params.value[3], (long)params.value[4], (long)params.value[5],
        params_io ? "nor" : "ram");
}

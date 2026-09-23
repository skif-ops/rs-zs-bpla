#ifndef APP_COMMS_H
#define APP_COMMS_H
/*
 * B2 comms task: BG95 on USART1 -> zs_bg95 bring-up (auto network from the station configuration) -> TLS/MQTT
 * endpoint from the configuration record -> zs_bg95_mqtt_session (command down / receipt / event uplink) ->
 * zs_station_comms (outbox drain + heartbeat on the status topic).  Command trust keys are not provisioned in
 * B1/B2: the down channel subscribes but every command is rejected as unverified until key provisioning lands.
 */
#include "zs_bg95.h"
#include "zs_event_outbox.h"
#include "zs_command_journal.h"
#include "zs_station_config.h"
#include "zs_station_comms.h"
#include <stdbool.h>
#include <stdint.h>

typedef struct {
  bool (*fill_heartbeat)(void *ctx, zs_heartbeat_t *hb);
  void *ctx;
  void (*log)(const char *fmt, ...);
} app_comms_hooks_t;

/* Stores are the NOR bindings (B3 map) or their RAM fallback; config is the record the ble task loaded. */
void app_comms_bind(const zs_event_outbox_io_t *outbox, const zs_command_journal_io_t *journal, const app_comms_hooks_t *hooks);
/* Runs the comms state machine; call from its own task. Never returns. */
void app_comms_task(void *arg);
/* Console: one status line; "comms on|off" requests. */
void app_comms_status(void (*print)(const char *fmt, ...));
void app_comms_request(bool on);
/* Latest station config for the endpoint (from the ble task's zs_ipc_service). */
void app_comms_set_config(const zs_station_config_t *cfg, uint32_t boot_id);
const zs_bg95_t *app_comms_modem(void);
const zs_station_comms_t *app_comms_state(void);
#endif

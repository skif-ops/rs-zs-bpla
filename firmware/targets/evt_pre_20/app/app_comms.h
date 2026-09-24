#ifndef APP_COMMS_H
#define APP_COMMS_H
/*
 * B2 comms task: BG95 on USART1 -> zs_bg95 bring-up (auto network from the station configuration) -> TLS/MQTT
 * endpoint from the configuration record -> zs_bg95_mqtt_session (command down / receipt / event uplink) ->
 * zs_station_comms (outbox drain + heartbeat on the status topic).  Command trust keys are not provisioned in
 * B1/B2: the down channel subscribes but every command is rejected as unverified until key provisioning lands.
 *
 * Dual SIM: when both expected ICCIDs are known (`simiccid` on the bench until provisioning lands them), the
 * modem is brought up through evt_pre_20_sim_orchestrator (slot select, rail, mux, PWRKEY, ICCID check,
 * graceful switch after repeated link failures); otherwise the single-SIM path powers the modem directly.
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
  /* The session did its work (outbox drained, heartbeat published): the mode scheduler may leave S3. May be NULL. */
  void (*session_done)(void *ctx);
} app_comms_hooks_t;

/* Stores are the NOR bindings (B3 map) or their RAM fallback; config is the record the ble task loaded. */
void app_comms_bind(const zs_event_outbox_io_t *outbox, const zs_command_journal_io_t *journal, const app_comms_hooks_t *hooks);
/* Runs the comms state machine; call from its own task. Never returns. */
void app_comms_task(void *arg);
/* Console: one status line; "comms on|off" requests (operator enable). */
void app_comms_status(void (*print)(const char *fmt, ...));
void app_comms_request(bool on);
/* Power policy from the mode scheduler (S3/S4 allow the modem): the comms task owns EN_MODEM and brings the modem
   down gracefully (AT+QPOWD, then the rail) when the policy withdraws it; a later allow restarts it. */
void app_comms_allow_modem(bool allowed);
/* Latest station config for the endpoint (from the ble task's zs_ipc_service). */
void app_comms_set_config(const zs_station_config_t *cfg, uint32_t boot_id);
/* Ed25519 public key of the server's command signer (station secrets key 4); NULL clears it. Takes effect on the
   next session: verified commands are acknowledged (execution lands with the command executor). */
void app_comms_set_command_key(const uint8_t public_key[32]);
/* Expected ICCID of slot 1/2 (18..22 digits); the dual-SIM path engages once both are set. */
bool app_comms_set_sim_iccid(unsigned slot, const char *iccid);
const zs_bg95_t *app_comms_modem(void);
const zs_station_comms_t *app_comms_state(void);
#endif

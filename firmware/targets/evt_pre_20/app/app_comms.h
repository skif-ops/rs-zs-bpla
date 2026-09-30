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
#include "zs_command_channel.h"
#include "zs_command_journal.h"
#include "zs_command_trust.h"
#include "zs_station_config.h"
#include "zs_station_comms.h"
#include "zs_prehistory.h"
#include "zs_fw_boot.h"
#include "zs_fw_update.h"
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
/* Wall-time source for command validity (true = trusted, *now_us set); NULL keeps commands rejected as untrusted. */
void app_comms_set_clock(bool (*now)(uint32_t now_ms, uint64_t *now_us));
/* Command executor for verified commands (takes effect with the next session); NULL restores the default, which
   acknowledges every verified command as REJECTED / detail 1 (not implemented). */
void app_comms_set_executor(zs_command_execute_fn exec, void *ctx);
/* Runs the comms state machine; call from its own task. Never returns. */
void app_comms_task(void *arg);
/* One iteration of the state machine (the task calls it every 20 ms; the host simulation drives it directly). */
void app_comms_step(void);
/* Console: one status line; "comms on|off" requests (operator enable). */
void app_comms_status(void (*print)(const char *fmt, ...));
void app_comms_request(bool on);
/* Power policy from the mode scheduler (S3/S4 allow the modem): the comms task owns EN_MODEM and brings the modem
   down gracefully (AT+QPOWD, then the rail) when the policy withdraws it; a later allow restarts it. */
void app_comms_allow_modem(bool allowed);
/* Latest station config for the endpoint (from the ble task's zs_ipc_service). */
void app_comms_set_config(const zs_station_config_t *cfg, uint32_t boot_id);
/* Ed25519 public keys of the server's command signer (station secrets key 4): the current key and, while a
   rotation is in flight, the next one (MQTT ICD addendum E, zs_command_keys_trust_set); count 0 clears them.
   Called from the executor inside a session, the running channel uses the new set from the next command on. */
void app_comms_set_command_keys(const zs_command_trust_key_t *keys, size_t count);
/* One key (NULL clears): app_comms_set_command_keys with a single entry. */
void app_comms_set_command_key(const uint8_t public_key[32]);
size_t app_comms_command_key_count(void);
/* Expected ICCID of slot 1/2 (18..22 digits); the dual-SIM path engages once both are set. */
bool app_comms_set_sim_iccid(unsigned slot, const char *iccid);
/* Audio for CMD_REQUEST_AUDIO (MQTT ICD addendum B): the prehistory ring and the event times live with the
   recorder; the comms task reads them through this port while it uploads. */
typedef struct {
  const zs_prehistory_t *(*ring)(void);                               /* NULL until the ring is bound */
  void (*range)(uint64_t *oldest_seq, uint64_t *next_seq);            /* consistent snapshot of the records held */
  bool (*event_time)(uint64_t event_id, int64_t *time_us, bool *trusted);
  int64_t (*now_us)(void);                                            /* the station's current sample time */
  bool (*recording)(void);                                            /* the capture still runs */
} app_comms_audio_source_t;
void app_comms_set_audio_source(const app_comms_audio_source_t *src);
/* Executor part for CMD_REQUEST_AUDIO: true = answered now (*result, *detail); false = accepted: the upload runs in
   the session and the ACK (OK, detail = chunks) follows its last chunk.  A redelivery of the running command
   returns false again; a different request while one runs is REJECTED / detail 4 (busy). */
bool app_comms_request_audio(const zs_command_t *cmd, zs_command_ack_result_t *result, uint16_t *detail);
/* An upload runs or its ACK waits: the session must stay (the scheduler extends S3). */
bool app_comms_audio_busy(void);
/* Firmware update (MQTT ICD addendum F): the other flash bank, its boot record and the running image as the station
   knows them; install() is called once the OK ACK of a verified image is at the broker and the new bank is armed
   (the target swaps the banks and resets, the twin simulates it).  No port (or no release key) = REJECTED 1. */
typedef struct {
  const zs_fw_image_io_t *io;                 /* image area of the other bank */
  const zs_fw_boot_port_t *other_record;      /* boot record page of the other bank */
  const zs_fw_release_key_t *keys;            /* compiled-in release keys */
  size_t key_count;
  uint32_t target;                            /* ZS_FW_TARGET_STM32_APP */
  uint32_t (*running_version)(void);
  bool (*trial)(void);                        /* the running image is not confirmed yet */
  void (*install)(uint32_t version);
} app_comms_fw_port_t;
void app_comms_set_fw_port(const app_comms_fw_port_t *port);
/* Executor part for CMD_UPDATE_FIRMWARE: true = answered now (REJECTED detail, addendum F §3); false = accepted:
   the download runs in the sessions, the ACK (OK, detail = chunks; FAILED detail) follows the image check.  A
   redelivery of the running command returns false again; another one while a download runs is REJECTED 6. */
bool app_comms_update_firmware(const zs_command_t *cmd, zs_command_ack_result_t *result, uint16_t *detail);
/* A download runs (not paused) or its ACK / the install waits: the session must stay (the scheduler extends S3). */
bool app_comms_fw_busy(void);
/* 0 idle, 1 downloading, 2 install pending (heartbeat key 19 before the boot-record states 3/4 are added). */
uint8_t app_comms_fw_state(void);
/* The twin's simulated reset: drop the session and every RAM job (audio upload, firmware download) as a real reset
   would; the stores (journal, outbox) stay. */
void app_comms_reset(void);
const zs_bg95_t *app_comms_modem(void);
const zs_station_comms_t *app_comms_state(void);
#endif

#include "app_comms.h"
#include "app_config.h"
#include "bsp_gpio.h"
#include "bsp_uart.h"
#include "evt_pre_20_sim_orchestrator.h"
#include "FreeRTOS.h"
#include "task.h"
#include "zs_audio_upload.h"
#include "zs_bg95_provision.h"
#include "zs_bg95_mqtt_session.h"
#include "zs_command_trust.h"
#include "zs_ed25519.h"
#include "zs_mqtt_command_transport.h"
#include "zs_bg95_topic_subscription.h"
#include <string.h>

typedef enum { COMMS_OFF = 0, COMMS_BRINGUP, COMMS_ENDPOINT, COMMS_SESSION, COMMS_ONLINE, COMMS_FAULT, COMMS_SIM, COMMS_STOPPING } comms_phase_t;

static zs_bg95_t modem;
static zs_command_trust_t trust;
static zs_command_channel_t channel;
static zs_mqtt_command_transport_t command_transport;
static zs_mqtt_event_transport_t event_transport;
static zs_bg95_command_transport_t command_binding;
static zs_bg95_event_receipt_t receipt_binding;
static zs_bg95_event_uplink_t uplink_binding;
static zs_bg95_mqtt_session_t session;
static zs_station_comms_t comms;
static zs_station_comms_port_t comms_port;
static uint8_t verify_workspace[256];
static const zs_event_outbox_io_t *outbox_io;
static const zs_command_journal_io_t *journal_io;
static app_comms_hooks_t hooks;
static zs_station_config_t config;
static bool config_valid, want_on = true, modem_allowed, bound, session_reported;
static uint32_t boot_id, phase_since_ms, faults, online_count, sessions_done, last_outbox_check_ms, stop_requested_ms;
static comms_phase_t phase;
static char line[256];
static size_t line_len;

/* ---- dual SIM ---- */
static zs_dual_sim_t sim_controller;
static evt_pre_20_dual_sim_gpio_t sim_gpio;
static evt_pre_20_sim_orchestrator_t sim;
static char sim_iccid[2][ZS_DUAL_SIM_ICCID_CAPACITY];
static bool sim_enabled, sim_provisioned, safe_off_logged;
static uint32_t safe_off_since_ms, sim_faults;

static bool sim_gpio_write(void *ctx, evt_pre_20_pin_id_t pin, bool high) {
  (void)ctx;
  switch (pin) {
    case EVT_PRE_20_PIN_SIM_MUX_SEL: bsp_gpio_sim_mux_select(high); return true;
    case EVT_PRE_20_PIN_SIM_MUX_EN: bsp_gpio_sim_mux_enable(high); return true;
    case EVT_PRE_20_PIN_EN_MODEM: bsp_gpio_modem_power(high); return true;
    case EVT_PRE_20_PIN_CELL_PWRKEY_CMD: bsp_gpio_modem_pwrkey(high); return true;
    default: return false;
  }
}
static bool sim_gpio_read(void *ctx, evt_pre_20_pin_id_t pin, bool *high) {
  (void)ctx;
  switch (pin) {
    case EVT_PRE_20_PIN_SIM_MUX_SEL: *high = bsp_gpio_sim_mux_select_level(); return true;
    case EVT_PRE_20_PIN_SIM_MUX_EN: *high = bsp_gpio_sim_mux_enable_level(); return true;
    case EVT_PRE_20_PIN_EN_MODEM: *high = bsp_gpio_modem_power_level(); return true;
    case EVT_PRE_20_PIN_PWR_GOOD: *high = bsp_gpio_power_good(); return true;
    case EVT_PRE_20_PIN_CELL_STATUS: *high = bsp_gpio_cell_status(); return true;
    case EVT_PRE_20_PIN_SIM1_DET: *high = bsp_gpio_sim_present(1u); return true;
    case EVT_PRE_20_PIN_SIM2_DET: *high = bsp_gpio_sim_present(2u); return true;
    default: return false;
  }
}

bool app_comms_set_sim_iccid(unsigned slot, const char *iccid) {
  size_t n;
  if (slot < 1u || slot > 2u || !iccid) return false;
  n = strlen(iccid);
  if (n < 18u || n > 22u) return false;
  for (size_t i = 0u; i < n; i++) if (iccid[i] < '0' || iccid[i] > '9') return false;
  strcpy(sim_iccid[slot - 1u], iccid);
  sim_enabled = sim_iccid[0][0] != '\0' && sim_iccid[1][0] != '\0' && strcmp(sim_iccid[0], sim_iccid[1]) != 0;
  return true;
}

/* ---- HAL port for zs_bg95 ---- */
static uint32_t hal_millis(void *ctx) { (void)ctx; return xTaskGetTickCount(); }
static void hal_delay(void *ctx, uint32_t ms) { (void)ctx; vTaskDelay(pdMS_TO_TICKS(ms)); }
static int hal_uart_write(void *ctx, unsigned ch, const uint8_t *d, size_t n) { (void)ctx; (void)ch; return bsp_uart_write(BSP_UART_CELL, d, n) == (int)n ? 0 : -1; }
static void hal_gpio_write(void *ctx, unsigned id, bool level) { (void)ctx; (void)id; bsp_gpio_modem_pwrkey(level); }
static const zs_hal_port_t hal = {NULL, hal_millis, hal_delay, hal_uart_write, NULL, NULL, NULL, hal_gpio_write, NULL};

/* Command trust (MQTT ICD §2.1): the Ed25519 public keys of the server's command signer come from the station
   secrets record (ICD BLE v0.3, key 4): the current key and, while a rotation is in flight, the next one (addendum
   E).  Until a key is provisioned the trust set holds a placeholder key whose backend rejects everything, so the
   down channel subscribes but every command is refused as unverified (zs_command_trust_init needs at least one
   enabled, non-zero key). */
static zs_command_trust_key_t command_keys[2];
static size_t command_key_count;
static volatile bool trust_dirty;          /* a new set waits for the comms task (never swapped under a verification) */
static bool trust_ready;
static bool trust_load(void);
static uint32_t commands_verified, commands_rejected;
static bool verify_none(void *ctx, const uint8_t pk[ZS_COMMAND_PUBLIC_KEY_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx; (void)pk; (void)m; (void)n; (void)sig; commands_rejected++; return false;
}
static bool verify_ed25519(void *ctx, const uint8_t pk[ZS_COMMAND_PUBLIC_KEY_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx;
  const bool ok = zs_ed25519_verify(pk, m, n, sig);
  if (ok) commands_verified++; else commands_rejected++;
  return ok;
}
/* Verified commands are acknowledged but not executed yet: the command set (config push, service, reboot) lands
   with the command executor; REJECTED/detail 1 = "not implemented on this station". */
static bool execute_none(void *ctx, const zs_command_t *cmd, zs_command_ack_result_t *r, uint16_t *detail) {
  (void)ctx; (void)cmd; *r = ZS_COMMAND_ACK_REJECTED; *detail = 1u; return true;
}

/* The command executor (app_commands on the target) replaces execute_none from the next session on. */
static zs_command_execute_fn executor = execute_none;
static void *executor_ctx;
void app_comms_set_executor(zs_command_execute_fn exec, void *ctx) { executor = exec ? exec : execute_none; executor_ctx = exec ? ctx : NULL; }

void app_comms_set_command_keys(const zs_command_trust_key_t *keys, size_t count) {
  /* callers: the ble task (secrets over BLE), the comms task (the executor: rotation, promotion) and boot; the comms
     task swaps the running trust set between two commands (trust_refresh), so a verification never sees half a set */
  taskENTER_CRITICAL();
  memset(command_keys, 0, sizeof(command_keys));
  command_key_count = keys && count ? (count > 2u ? 2u : count) : 0u;
  if (command_key_count) memcpy(command_keys, keys, command_key_count * sizeof(keys[0]));
  trust_dirty = true;
  taskEXIT_CRITICAL();
}
void app_comms_set_command_key(const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES]) {
  zs_command_trust_key_t key;
  memset(&key, 0, sizeof(key));
  if (!public_key) { app_comms_set_command_keys(NULL, 0u); return; }
  memcpy(key.public_key, public_key, sizeof(key.public_key)); key.enabled = true;
  app_comms_set_command_keys(&key, 1u);
}
size_t app_comms_command_key_count(void) { return command_key_count; }
static bool trust_load(void) {
  zs_command_trust_key_t keys[2];
  size_t count;
  taskENTER_CRITICAL();
  count = command_key_count;
  memcpy(keys, command_keys, sizeof(keys));
  trust_dirty = false;
  taskEXIT_CRITICAL();
  if (count) { trust_ready = zs_command_trust_init(&trust, keys, count, verify_ed25519, NULL); memset(keys, 0, sizeof(keys)); return trust_ready; }
  memset(&keys[0], 0, sizeof(keys[0]));
  keys[0].enabled = true;
  memset(keys[0].public_key, 0xff, sizeof(keys[0].public_key));          /* placeholder: never matches a real key id, backend rejects anyway */
  return trust_ready = zs_command_trust_init(&trust, keys, 1u, verify_none, NULL);
}
/* comms task, between commands: a rotation or promotion by the executor verifies the next command with the new set
   in the same session; a set from the ble task takes effect the same way */
static void trust_refresh(void) { if (trust_ready && trust_dirty) (void)trust_load(); }
static bool fill_heartbeat(void *ctx, zs_heartbeat_t *hb) { return hooks.fill_heartbeat ? hooks.fill_heartbeat(hooks.ctx ? hooks.ctx : ctx, hb) : false; }

void app_comms_bind(const zs_event_outbox_io_t *outbox, const zs_command_journal_io_t *journal, const app_comms_hooks_t *h) {
  outbox_io = outbox; journal_io = journal; if (h) hooks = *h; bound = outbox && journal;
}
void app_comms_set_config(const zs_station_config_t *cfg, uint32_t id) { if (cfg) { config = *cfg; config_valid = true; boot_id = id; } }
void app_comms_request(bool on) { want_on = on; }
void app_comms_allow_modem(bool allowed) { modem_allowed = allowed; }
static bool wanted(void) { return want_on && modem_allowed; }
const zs_bg95_t *app_comms_modem(void) { return &modem; }
const zs_station_comms_t *app_comms_state(void) { return &comms; }

static void audio_abort(const char *why);
static bool build_audio_topic(void);
static bool fw_session_start(void);
static void set_phase(comms_phase_t p) {
  if ((phase == COMMS_SESSION || phase == COMMS_ONLINE) && p != COMMS_SESSION && p != COMMS_ONLINE) audio_abort("session ended");
  phase = p; phase_since_ms = xTaskGetTickCount();
}

static bool start_session(const char *tenant) {
  if (!trust_load()) return false;
  channel = (zs_command_channel_t){config.station_id, &trust, journal_io, executor, executor_ctx, verify_workspace, sizeof(verify_workspace)};
  if (!zs_mqtt_command_transport_init(&command_transport, &channel, (const uint8_t *)tenant, strlen(tenant))) return false;
  if (!zs_mqtt_event_transport_init(&event_transport, outbox_io, config.station_id, (const uint8_t *)tenant, strlen(tenant))) return false;
  if (!zs_bg95_command_transport_init(&command_binding, &modem, &command_transport, true)) return false;
  if (!zs_bg95_event_receipt_init(&receipt_binding, &modem, &event_transport, true)) return false;
  if (!zs_bg95_event_uplink_init(&uplink_binding, &modem, &event_transport)) return false;
  if (!zs_bg95_mqtt_session_init(&session, &modem, &command_binding, &receipt_binding, &uplink_binding, (uint16_t)(1u + (xTaskGetTickCount() & 0x7fffu)))) return false;
  if (!build_audio_topic()) return false;
  audio_abort("new session");
  if (!fw_session_start()) return false;
  comms_port = (zs_station_comms_port_t){NULL, fill_heartbeat, APP_COMMS_HEARTBEAT_MS, 0u};
  return zs_station_comms_init(&comms, &comms_port, &session, &event_transport, xTaskGetTickCount());
}

/* ---- audio upload (addendum B): CMD_REQUEST_AUDIO answered chunk by chunk on the audio topic ----
   The job (zs_audio_upload) shares the uplink with zs_station_comms: every step first collects the outcome of our
   own chunk, then lets the outbox/heartbeat go (detections keep priority), then starts the next chunk when the
   session is free.  The last chunk completes the command in the journal and the ACK is published from it. */
static const app_comms_audio_source_t *audio_src;
static zs_audio_upload_t upload;
static bool chunk_in_flight, ack_pending;
static unsigned chunk_failures;
static uint8_t chunk_buf[ZS_AUDIO_CHUNK_MAX_BYTES], ack_buf[ZS_COMMAND_ACK_MAX_BYTES];
static uint8_t audio_topic[ZS_MQTT_EVENT_TOPIC_MAX_BYTES];
static size_t audio_topic_size;
static zs_mqtt_event_message_t chunk_msg, ack_msg;
static uint32_t audio_uploads, audio_chunks, audio_rejected, audio_failed, audio_aborted, audio_by_server_time;
void app_comms_set_audio_source(const app_comms_audio_source_t *src) { audio_src = src; }
bool app_comms_audio_busy(void) { return zs_audio_upload_active(&upload) || upload.state == ZS_AUDIO_UPLOAD_FINISHED || ack_pending || chunk_in_flight; }

bool app_comms_request_audio(const zs_command_t *cmd, zs_command_ack_result_t *result, uint16_t *detail) {
  int64_t event_us;
  bool trusted, by_server = false;
  const zs_prehistory_t *ring = audio_src && audio_src->ring ? audio_src->ring() : NULL;
  *result = ZS_COMMAND_ACK_REJECTED;
  if (!ring) { *detail = 1u; audio_rejected++; return true; }                       /* no recorder on this station */
  if (app_comms_audio_busy()) {
    if (memcmp(upload.command_id, cmd->command_id, ZS_COMMAND_UUID_BYTES) == 0) return false;   /* redelivery: still running */
    *detail = ZS_AUDIO_UPLOAD_DETAIL_BUSY; audio_rejected++; return true;
  }
  /* the station's own table of this boot first; for older events the time the server signed into the request */
  if (!audio_src->event_time(cmd->audio.event_id, &event_us, &trusted)) {
    if (!cmd->audio.has_event_time) { *detail = ZS_AUDIO_UPLOAD_DETAIL_NO_AUDIO; audio_rejected++; return true; }
    event_us = cmd->audio.event_time_us;
    trusted = true;                                      /* the server requests only events whose time it trusts */
    by_server = true;
  }
  if (!trusted) { *detail = ZS_AUDIO_UPLOAD_DETAIL_TIME; audio_rejected++; return true; }
  if (!zs_audio_upload_start(&upload, ring, config.station_id, cmd->command_id, &cmd->audio, event_us, detail)) { audio_rejected++; return true; }
  chunk_failures = 0u;
  audio_uploads++;
  audio_by_server_time += by_server;
  if (hooks.log) hooks.log("audio: request for event %lu:%lu accepted (segment %u, %s time), upload follows\r\n",
                           (unsigned long)(cmd->audio.event_id >> 32), (unsigned long)(cmd->audio.event_id & 0xffffffffu), (unsigned)cmd->audio.segment,
                           by_server ? "server" : "station");
  return false;                                                                    /* ACCEPTED stays; the ACK comes later */
}

/* audio topic = the ack topic with "audio" in place of "ack" (same tenant/station prefix) */
static bool build_audio_topic(void) {
  const size_t base = command_transport.ack_topic_size;
  if (base < 3u || base - 3u + 5u > sizeof(audio_topic) || memcmp(command_transport.ack_topic + base - 3u, "ack", 3u) != 0) return false;
  memcpy(audio_topic, command_transport.ack_topic, base - 3u);
  memcpy(audio_topic + base - 3u, "audio", 5u);
  audio_topic_size = base + 2u;                             /* "ack" (3) -> "audio" (5) */
  return true;
}

static void audio_abort(const char *why) {
  if (zs_audio_upload_active(&upload) || upload.state == ZS_AUDIO_UPLOAD_FINISHED) {
    audio_aborted++;
    if (hooks.log) hooks.log("audio: upload abandoned (%s), the command stays accepted\r\n", why);
  }
  zs_audio_upload_abort(&upload);
  chunk_in_flight = false;
  ack_pending = false;
}

static bool command_time(uint32_t now_ms, uint64_t *now_us);

/* 1: the outcome of our chunk, read before anyone else starts a publication on the uplink */
static void audio_collect(void) {
  if (!chunk_in_flight || uplink_binding.state != ZS_BG95_EVENT_UPLINK_IDLE) return;
  chunk_in_flight = false;
  if (uplink_binding.last_outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK) { zs_audio_upload_chunk_sent(&upload); audio_chunks++; chunk_failures = 0u; }
  else if (++chunk_failures >= 5u) audio_abort("chunk refused 5 times");
}

/* 3: the next piece of work when the session is free */
static void audio_drive(uint32_t now) {
  uint64_t oldest = 0u, next = 0u;
  if (chunk_in_flight || session.owner != ZS_BG95_MQTT_OWNER_NONE || !zs_bg95_mqtt_session_ready(&session)) return;
  if (ack_pending) {
    if (zs_bg95_mqtt_session_start_message(&session, &ack_msg, now) == ZS_BG95_EVENT_UPLINK_STARTED) ack_pending = false;
    return;
  }
  if (!zs_audio_upload_active(&upload) && upload.state != ZS_AUDIO_UPLOAD_FINISHED) return;
  for (unsigned i = 0u; i < 4u; i++) {                   /* a few bounded steps (header scan / one record hash) */
    zs_audio_upload_step_t st;
    audio_src->range(&oldest, &next);
    st = zs_audio_upload_step(&upload, audio_src->now_us(), audio_src->recording(), oldest, next);
    if (st == ZS_AUDIO_UPLOAD_STEP_BUSY) continue;
    if (st == ZS_AUDIO_UPLOAD_STEP_CHUNK_READY) {
      const size_t n = zs_audio_upload_chunk(&upload, chunk_buf, sizeof(chunk_buf));
      if (n == 0u) continue;                               /* storage failure: the job finished FAILED */
      chunk_msg = (zs_mqtt_event_message_t){audio_topic, audio_topic_size, chunk_buf, n, 1u, false};
      if (zs_bg95_mqtt_session_start_message(&session, &chunk_msg, now) == ZS_BG95_EVENT_UPLINK_STARTED) chunk_in_flight = true;
      return;
    }
    if (st == ZS_AUDIO_UPLOAD_STEP_FINISHED) {
      uint64_t now_us;
      size_t n;
      (void)command_time(now, &now_us);
      if (upload.result != ZS_COMMAND_ACK_OK) audio_failed++;
      if (hooks.log) hooks.log("audio: upload finished, result %u detail %u (%lu chunks)\r\n", (unsigned)upload.result, (unsigned)upload.detail, (unsigned long)upload.chunks_sent);
      if (zs_command_journal_complete(journal_io, upload.command_id, upload.result, upload.detail, now_us) == ZS_COMMAND_JOURNAL_OK &&
          (n = zs_command_journal_encode_ack(journal_io, upload.command_id, ack_buf, sizeof(ack_buf))) > 0u) {
        ack_msg = (zs_mqtt_event_message_t){command_transport.ack_topic, command_transport.ack_topic_size, ack_buf, n, 1u, false};
        ack_pending = true;
      }
      upload.state = ZS_AUDIO_UPLOAD_IDLE;
      return;
    }
    return;                                                /* IDLE: waiting for the window to be recorded */
  }
}

/* ---- firmware update (addendum F): CMD_UPDATE_FIRMWARE fetched chunk by chunk (fwreq -> fw), stop-and-wait ----
   The image goes into the other flash bank through the port; the download lives in RAM for this boot and survives
   the end of a session (it pauses and resumes in the next one).  Verified -> journal COMPLETED -> ACK OK at the
   broker -> the new bank is armed for trial -> port install (swap + reset). */
#define FW_REQUEST_TIMEOUT_MS 15000u
#define FW_TIMEOUTS_PAUSE 8u
#define FW_STALLED_SESSIONS_FAIL 3u
typedef enum { FW_IDLE = 0, FW_DOWNLOADING, FW_ACK, FW_INSTALLING } fw_phase_t;
static const app_comms_fw_port_t *fw_port;
static fw_phase_t fw_phase;
static zs_fw_download_t fw_dl;
static zs_bg95_topic_subscription_t fw_sub;
static uint8_t fw_topic[ZS_MQTT_EVENT_TOPIC_MAX_BYTES], fwreq_topic[ZS_MQTT_EVENT_TOPIC_MAX_BYTES];
static size_t fw_topic_size, fwreq_topic_size;
static uint8_t fw_req_buf[ZS_FW_REQUEST_MAX_BYTES], fw_ack_buf[ZS_COMMAND_ACK_MAX_BYTES];
static zs_mqtt_event_message_t fw_req_msg, fw_ack_msg;
static bool fw_req_in_flight, fw_waiting, fw_paused, fw_ack_in_flight;
static uint32_t fw_req_offset, fw_req_sent_ms, fw_session_chunks;
static unsigned fw_timeouts, fw_stalled_sessions;
static uint32_t fw_updates, fw_rejected, fw_failed, fw_chunks, fw_chunks_ignored, fw_timeouts_total, fw_installs;
void app_comms_set_fw_port(const app_comms_fw_port_t *port) { fw_port = port; }
bool app_comms_fw_busy(void) { return (fw_phase == FW_DOWNLOADING && !fw_paused) || fw_phase == FW_ACK || fw_phase == FW_INSTALLING; }
uint8_t app_comms_fw_state(void) {
  if (fw_phase == FW_DOWNLOADING) return 1u;
  if ((fw_phase == FW_ACK && fw_dl.result == ZS_COMMAND_ACK_OK) || fw_phase == FW_INSTALLING) return 2u;
  return 0u;
}

/* the topic next to the ack topic: ".../ack" -> ".../<suffix>" (same tenant/station prefix) */
static bool derive_topic(const char *suffix, uint8_t *out, size_t cap, size_t *size) {
  const size_t base = command_transport.ack_topic_size, n = strlen(suffix);
  if (base < 3u || base - 3u + n > cap || memcmp(command_transport.ack_topic + base - 3u, "ack", 3u) != 0) return false;
  memcpy(out, command_transport.ack_topic, base - 3u);
  memcpy(out + base - 3u, suffix, n);
  *size = base - 3u + n;
  return true;
}

static void fw_on_message(void *ctx, const uint8_t *payload, size_t size) {
  zs_fw_chunk_t chunk;
  zs_fw_chunk_result_t r;
  (void)ctx;
  if (fw_phase != FW_DOWNLOADING || !zs_fw_chunk_decode(payload, size, &chunk)) { fw_chunks_ignored++; return; }
  r = zs_fw_download_on_chunk(&fw_dl, &chunk);
  if (r == ZS_FW_CHUNK_IGNORED) { fw_chunks_ignored++; return; }
  fw_waiting = false;
  fw_timeouts = 0u;
  if (r == ZS_FW_CHUNK_ACCEPTED) { fw_chunks++; fw_session_chunks++; }
}

static bool fw_session_start(void) {
  if (!derive_topic("fw", fw_topic, sizeof(fw_topic), &fw_topic_size) ||
      !derive_topic("fwreq", fwreq_topic, sizeof(fwreq_topic), &fwreq_topic_size) ||
      !zs_bg95_topic_subscription_init(&fw_sub, &modem, fw_topic, fw_topic_size, fw_on_message, NULL) ||
      !zs_bg95_mqtt_session_attach(&session, &fw_sub))
    return false;
  fw_req_in_flight = fw_waiting = fw_paused = fw_ack_in_flight = false;
  fw_timeouts = 0u;
  if (fw_phase == FW_DOWNLOADING) {
    /* a session that ended without a single chunk counts; three in a row end the download (addendum F §2) */
    if (fw_session_chunks == 0u && ++fw_stalled_sessions >= FW_STALLED_SESSIONS_FAIL) {
      zs_fw_download_fail(&fw_dl, ZS_FW_FAIL_STALLED);
      if (hooks.log) hooks.log("fw: no progress in %u sessions, download failed\r\n", fw_stalled_sessions);
    } else if (fw_session_chunks) {
      fw_stalled_sessions = 0u;
    }
    if (fw_dl.state != ZS_FW_DOWNLOAD_FINISHED) zs_bg95_topic_subscription_want(&fw_sub, true);
  }
  fw_session_chunks = 0u;
  return true;
}

bool app_comms_update_firmware(const zs_command_t *cmd, zs_command_ack_result_t *result, uint16_t *detail) {
  zs_fw_manifest_t manifest;
  zs_fw_station_t station;
  *result = ZS_COMMAND_ACK_REJECTED;
  if (!fw_port || !fw_port->io || !fw_port->other_record || !fw_port->install) { *detail = ZS_FW_REJECT_UNSUPPORTED; fw_rejected++; return true; }
  if (fw_phase != FW_IDLE) {
    if (fw_phase == FW_DOWNLOADING && memcmp(fw_dl.command_id, cmd->command_id, ZS_COMMAND_UUID_BYTES) == 0) return false;   /* redelivery */
    *detail = ZS_FW_REJECT_BUSY; fw_rejected++; return true;
  }
  station = (zs_fw_station_t){fw_port->keys, fw_port->key_count, fw_port->target,
                              fw_port->running_version ? fw_port->running_version() : 0u, fw_port->io->capacity,
                              fw_port->trial ? fw_port->trial() : false};
  *detail = zs_fw_update_check(&cmd->firmware, &station, &manifest);
  if (*detail) {
    fw_rejected++;
    if (hooks.log) hooks.log("fw: update refused, detail %u (running v%lu)\r\n", (unsigned)*detail, (unsigned long)station.running_version);
    return true;
  }
  if (!zs_fw_download_start(&fw_dl, fw_port->io, config.station_id, cmd->command_id, &manifest)) { *detail = ZS_FW_REJECT_UNSUPPORTED; fw_rejected++; return true; }
  fw_phase = FW_DOWNLOADING;
  fw_updates++;
  fw_req_in_flight = fw_waiting = fw_paused = false;
  fw_timeouts = fw_stalled_sessions = 0u;
  fw_session_chunks = 0u;
  zs_bg95_topic_subscription_want(&fw_sub, true);
  if (hooks.log) hooks.log("fw: update to v%lu accepted (%lu bytes, running v%lu), download follows\r\n",
                           (unsigned long)manifest.version, (unsigned long)manifest.size, (unsigned long)station.running_version);
  return false;
}

/* 1: the outcome of our request or ACK, read before anyone else starts a publication on the uplink */
static void fw_collect(uint32_t now) {
  if ((!fw_req_in_flight && !fw_ack_in_flight) || uplink_binding.state != ZS_BG95_EVENT_UPLINK_IDLE) return;
  if (fw_req_in_flight) {
    fw_req_in_flight = false;
    if (uplink_binding.last_outcome == ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK) {
      /* the chunk may already be here (it can overtake the +QMTPUB line) */
      fw_waiting = fw_phase == FW_DOWNLOADING && fw_dl.offset == fw_req_offset && zs_fw_download_want(&fw_dl) != 0u;
      fw_req_sent_ms = now;
    } else if (++fw_timeouts >= FW_TIMEOUTS_PAUSE) {
      fw_paused = true;
    }
    return;
  }
  fw_ack_in_flight = false;
  if (uplink_binding.last_outcome != ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK) return;   /* published again next time */
  if (fw_dl.result != ZS_COMMAND_ACK_OK) { fw_phase = FW_IDLE; return; }
  fw_phase = FW_INSTALLING;
}

static void fw_finish(uint32_t now) {
  uint64_t now_us;
  size_t n;
  (void)command_time(now, &now_us);
  zs_bg95_topic_subscription_want(&fw_sub, false);
  if (fw_dl.result != ZS_COMMAND_ACK_OK) fw_failed++;
  if (hooks.log) hooks.log("fw: download finished, result %u detail %u (%lu chunks)\r\n", (unsigned)fw_dl.result, (unsigned)fw_dl.detail, (unsigned long)fw_dl.chunks);
  if (zs_command_journal_complete(journal_io, fw_dl.command_id, fw_dl.result, fw_dl.detail, now_us) == ZS_COMMAND_JOURNAL_OK &&
      (n = zs_command_journal_encode_ack(journal_io, fw_dl.command_id, fw_ack_buf, sizeof(fw_ack_buf))) > 0u) {
    fw_ack_msg = (zs_mqtt_event_message_t){command_transport.ack_topic, command_transport.ack_topic_size, fw_ack_buf, n, 1u, false};
    fw_phase = FW_ACK;
  } else {
    if (hooks.log) hooks.log("fw: journal completion failed, the command stays accepted\r\n");
    fw_phase = FW_IDLE;
  }
}

/* 3: local work (erase / verify) and the next publication when the session is free */
static void fw_drive(uint32_t now) {
  if (!fw_port || fw_phase == FW_IDLE) return;
  if (fw_phase == FW_INSTALLING) {
    fw_phase = FW_IDLE;
    if (!zs_fw_boot_arm(fw_port->other_record, fw_dl.manifest.version, fw_port->running_version ? fw_port->running_version() : 0u)) {
      fw_failed++;
      if (hooks.log) hooks.log("fw: arming the new bank failed, staying on the running image\r\n");
      return;
    }
    fw_installs++;
    if (hooks.log) hooks.log("fw: v%lu armed for trial, installing\r\n", (unsigned long)fw_dl.manifest.version);
    fw_port->install(fw_dl.manifest.version);
    return;
  }
  if (fw_phase == FW_DOWNLOADING) {
    const zs_fw_step_t st = zs_fw_download_step(&fw_dl, 16384u);
    if (st == ZS_FW_STEP_FINISHED) { fw_finish(now); return; }
    if (st != ZS_FW_STEP_NEED_CHUNK || fw_paused) return;
    if (!zs_bg95_topic_subscription_ready(&fw_sub)) {
      zs_bg95_topic_subscription_want(&fw_sub, true);
      if (fw_sub.failed) { fw_paused = true; if (hooks.log) hooks.log("fw: chunk topic refused, download paused\r\n"); }
      return;
    }
    if (fw_waiting) {
      if ((uint32_t)(now - fw_req_sent_ms) < FW_REQUEST_TIMEOUT_MS) return;
      fw_waiting = false;
      fw_timeouts_total++;
      if (++fw_timeouts >= FW_TIMEOUTS_PAUSE) {
        fw_paused = true;
        if (hooks.log) hooks.log("fw: %u requests unanswered at offset %lu, download paused until the next session\r\n", fw_timeouts, (unsigned long)fw_dl.offset);
        return;
      }
    }
  }
  if (fw_req_in_flight || fw_ack_in_flight || session.owner != ZS_BG95_MQTT_OWNER_NONE || !zs_bg95_mqtt_session_ready(&session)) return;
  if (fw_phase == FW_ACK) {
    if (zs_bg95_mqtt_session_start_message(&session, &fw_ack_msg, now) == ZS_BG95_EVENT_UPLINK_STARTED) fw_ack_in_flight = true;
    return;
  }
  if (fw_phase == FW_DOWNLOADING && !fw_waiting) {
    const size_t n = zs_fw_download_request(&fw_dl, fw_req_buf, sizeof(fw_req_buf));
    if (n == 0u) return;
    fw_req_msg = (zs_mqtt_event_message_t){fwreq_topic, fwreq_topic_size, fw_req_buf, n, 1u, false};
    if (zs_bg95_mqtt_session_start_message(&session, &fw_req_msg, now) == ZS_BG95_EVENT_UPLINK_STARTED) {
      fw_req_in_flight = true;
      fw_req_offset = fw_dl.offset;
    }
  }
}

void app_comms_reset(void) {
  audio_abort("reset");
  zs_fw_download_abort(&fw_dl);
  fw_phase = FW_IDLE;
  fw_req_in_flight = fw_waiting = fw_paused = fw_ack_in_flight = false;
  if (phase != COMMS_OFF) { bsp_gpio_modem_power(false); modem.state = ZS_BG95_OFF; }
  session_reported = false;
  stop_requested_ms = 0u;
  set_phase(COMMS_OFF);
}

/* zs_bg95 instance for the station configuration (APN profiles of the config, pilot APN policy). */
static void modem_prepare(void) {
  zs_bg95_apn_profile_t profiles[2];
  unsigned n = 0u;
  memset(profiles, 0, sizeof(profiles));
  for (unsigned i = 0u; i < ZS_STATION_CONFIG_APN_COUNT && n < 2u; i++) {
    if (config.apn[i][0] == '\0') continue;
    strncpy(profiles[n].apn, config.apn[i], sizeof(profiles[n].apn) - 1u);
    profiles[n].public_apn = APP_COMMS_PUBLIC_APN != 0;
    n++;
  }
  zs_bg95_init(&modem, &hal, BSP_UART_CELL, 0u, config.apn[0]);
  (void)zs_bg95_configure_auto_network(&modem, profiles, n);
  sim_provisioned = false;
}

static char tenant[ZS_STATION_CONFIG_TENANT_MAX + 1u];

/* Endpoint from the configuration record, then the MQTT bring-up (both paths). */
static bool modem_provision(uint32_t now) {
  if (!zs_bg95_provision_apply_station_config(&modem, &config, boot_id, APP_COMMS_PUBLIC_APN != 0, tenant, sizeof(tenant)) || !zs_bg95_start_mqtt(&modem, now)) return false;
  if (hooks.log) hooks.log("comms: endpoint %s:%u tenant %s\r\n", config.server_host, config.mqtt_port, tenant);
  sim_provisioned = true;
  return true;
}

/* Linger (ICD addendum D): the broker delivers queued commands after the subscription and the server may answer
   the heartbeat with one, so the session stays up APP_COMMS_LINGER_MS after the last activity (online, heartbeat,
   any command in or out) and never ends with a publish in flight.  Without it the second command of a queue, or a
   command sent in reply to the heartbeat, landed in a closing session (found by the station twin). */
static uint32_t activity_ms, activity_seen;
static void note_session_activity(uint32_t now) {
  const uint32_t seen = comms.heartbeats_published + commands_verified + commands_rejected +
                        session.queued_command_count + session.retry_required_count + audio_chunks + audio_uploads +
                        fw_chunks + fw_updates + fw_timeouts_total;
  if (seen != activity_seen) { activity_seen = seen; activity_ms = now; }
}

/* S3 exit criterion: the session is up, at least one heartbeat went out, nothing waits in the outbox and the
   linger since the last activity has passed (the outbox is checked at most every 5 s: it walks the NOR slots). */
static void check_session_done(uint32_t now) {
  uint16_t pending = 1u;
  if (session_reported || !hooks.session_done || comms.heartbeats_published == 0u || app_comms_audio_busy() || app_comms_fw_busy()) return;
  if ((uint32_t)(now - activity_ms) < APP_COMMS_LINGER_MS || session.owner != ZS_BG95_MQTT_OWNER_NONE) return;
  if ((uint32_t)(now - last_outbox_check_ms) < 5000u) return;
  last_outbox_check_ms = now;
  if (zs_event_outbox_pending_count(outbox_io, &pending) == ZS_EVENT_OUTBOX_OK && pending == 0u) {
    session_reported = true;
    sessions_done++;
    hooks.session_done(hooks.ctx);
  }
}

/* Wall time for the validity window of signed commands (zs_command_clock on the target).  Without a clock source
   the uptime stands in and every command is rejected as TIME_UNTRUSTED, which is the safe default. */
static bool (*clock_fn)(uint32_t now_ms, uint64_t *now_us);
void app_comms_set_clock(bool (*now)(uint32_t now_ms, uint64_t *now_us)) { clock_fn = now; }
static bool command_time(uint32_t now_ms, uint64_t *now_us) {
  if (clock_fn && clock_fn(now_ms, now_us)) return true;
  *now_us = (uint64_t)now_ms * 1000u;
  return false;
}

/* Bring-up lines go to the modem driver; once the session exists it owns the byte stream. */
static void feed_uart(uint32_t now_ms) {
  uint8_t buf[64];
  size_t n;
  while ((n = bsp_uart_read(BSP_UART_CELL, buf, sizeof(buf))) > 0u) {
    if (phase == COMMS_SESSION || phase == COMMS_ONLINE) {
      uint64_t now_us;
      const bool trusted = command_time(now_ms, &now_us);
      trust_refresh();
      (void)zs_bg95_mqtt_session_feed_uart(&session, buf, n, now_ms, now_us, trusted);
      continue;
    }
    for (size_t i = 0u; i < n; i++) {
      const char c = (char)buf[i];
      if (c == '\n') { line[line_len] = '\0'; if (line_len) zs_bg95_on_line(&modem, line, now_ms); line_len = 0u; }
      else if (c != '\r' && line_len + 1u < sizeof(line)) line[line_len++] = c;
      else if (c != '\r') line_len = 0u;
    }
  }
}

/* Dual-SIM phase: the orchestrator owns rail/mux/PWRKEY; this task feeds it the modem side. */
static void sim_phase(uint32_t now) {
  evt_pre_20_sim_phase_t ph;
  if (modem.state != ZS_BG95_OFF) zs_bg95_tick(&modem, now);
  ph = evt_pre_20_sim_orchestrator_step(&sim, now);
  switch (ph) {
    case EVT_PRE_20_SIM_PHASE_MODEM_BOOT:
    case EVT_PRE_20_SIM_PHASE_NEED_LINK:
      if (modem.state == ZS_BG95_READY && !sim_provisioned) { if (!modem_provision(now)) { sim_faults++; evt_pre_20_sim_orchestrator_fail(&sim, ZS_DUAL_SIM_FAILURE_PDP, now); } }
      else if (modem.state == ZS_BG95_ERROR) { sim_faults++; evt_pre_20_sim_orchestrator_fail(&sim, ZS_DUAL_SIM_FAILURE_ATTACH_TIMEOUT, now); }
      else if ((uint32_t)(now - phase_since_ms) > 180000u) { sim_faults++; evt_pre_20_sim_orchestrator_fail(&sim, ZS_DUAL_SIM_FAILURE_ATTACH_TIMEOUT, now); phase_since_ms = now; }
      safe_off_logged = false;
      break;
    case EVT_PRE_20_SIM_PHASE_ACTIVE:
      if (start_session(tenant)) { set_phase(COMMS_SESSION); if (hooks.log) hooks.log("comms: sim slot %d active, mqtt online, session starting\r\n", (int)zs_dual_sim_active_slot(&sim_controller)); }
      else { faults++; sim_faults++; evt_pre_20_sim_orchestrator_fail(&sim, ZS_DUAL_SIM_FAILURE_TLS, now); }
      safe_off_logged = false;
      break;
    case EVT_PRE_20_SIM_PHASE_CLOSE_TRANSPORT:
      evt_pre_20_sim_orchestrator_transport_closed(&sim);         /* no session in this phase: nothing to close */
      break;
    case EVT_PRE_20_SIM_PHASE_SAFE_OFF:
      if (!safe_off_logged) { safe_off_since_ms = now; safe_off_logged = true; if (hooks.log) hooks.log("comms: sim safe-off (no usable SIM); retry in %lu s\r\n", (unsigned long)(APP_SIM_SAFE_OFF_RETRY_MS / 1000u)); }
      else if ((uint32_t)(now - safe_off_since_ms) >= APP_SIM_SAFE_OFF_RETRY_MS) { evt_pre_20_sim_orchestrator_reset_failures(&sim); evt_pre_20_sim_orchestrator_start(&sim); safe_off_logged = false; phase_since_ms = now; }
      break;
    case EVT_PRE_20_SIM_PHASE_BUSY:
    default:
      break;
  }
}

void app_comms_step(void) {
  const uint32_t now = xTaskGetTickCount();
  feed_uart(now);
  {
    switch (phase) {
      case COMMS_OFF:
        if (wanted() && bound && config_valid && config.apn[0][0] != '\0') {
          session_reported = false;
          modem_prepare();
          if (sim_enabled) {
            /* dual SIM: the orchestrator recovers the board to safe-off first, then brings the preferred slot up */
            const zs_dual_sim_slot_t preferred = config.preferred_sim == 2u ? ZS_DUAL_SIM_SLOT_2 : ZS_DUAL_SIM_SLOT_1;
            if (zs_dual_sim_init(&sim_controller, sim_iccid[0], sim_iccid[1]) &&
                evt_pre_20_dual_sim_gpio_init(&sim_gpio, NULL, sim_gpio_write, sim_gpio_read, NULL) &&
                evt_pre_20_sim_orchestrator_init(&sim, &sim_controller, &sim_gpio, &modem, preferred, 0u)) {
              evt_pre_20_sim_orchestrator_start(&sim);
              safe_off_logged = false;
              if (hooks.log) hooks.log("comms: dual-sim bring-up, preferred slot %d, apn %s\r\n", (int)preferred, config.apn[0]);
              set_phase(COMMS_SIM);
              break;
            }
            if (hooks.log) hooks.log("comms: dual-sim init failed, single-sim path\r\n");
          }
          bsp_gpio_modem_power(true);
          vTaskDelay(pdMS_TO_TICKS(100));
          zs_bg95_power_on(&modem, now);
          if (hooks.log) hooks.log("comms: modem power on, apn %s\r\n", config.apn[0]);
          set_phase(COMMS_BRINGUP);
        }
        break;
      case COMMS_SIM:
        if (!wanted()) { if (modem.state >= ZS_BG95_AT_SYNC && modem.state < ZS_BG95_POWERING_OFF) (void)zs_bg95_request_graceful_power_off(&modem, now); set_phase(COMMS_STOPPING); break; }
        sim_phase(now);
        break;
      case COMMS_BRINGUP:
        zs_bg95_tick(&modem, now);
        if (!wanted()) { (void)zs_bg95_request_graceful_power_off(&modem, now); set_phase(COMMS_STOPPING); break; }
        if (modem.state == ZS_BG95_READY) {
          if (modem_provision(now)) set_phase(COMMS_ENDPOINT);
          else { if (hooks.log) hooks.log("comms: endpoint rejected\r\n"); faults++; set_phase(COMMS_FAULT); }
        } else if (modem.state == ZS_BG95_ERROR || (uint32_t)(now - phase_since_ms) > 180000u) { faults++; set_phase(COMMS_FAULT); }
        break;
      case COMMS_ENDPOINT:
        zs_bg95_tick(&modem, now);
        if (!wanted()) { (void)zs_bg95_request_graceful_power_off(&modem, now); set_phase(COMMS_STOPPING); break; }
        if (modem.state == ZS_BG95_ONLINE) {
          if (start_session(tenant)) { set_phase(COMMS_SESSION); if (hooks.log) hooks.log("comms: mqtt online, session starting\r\n"); }
          else { faults++; set_phase(COMMS_FAULT); }
        } else if (modem.state == ZS_BG95_ERROR || (uint32_t)(now - phase_since_ms) > 120000u) { faults++; set_phase(COMMS_FAULT); }
        break;
      case COMMS_SESSION:
      case COMMS_ONLINE:
        zs_bg95_tick(&modem, now);
        { uint64_t now_us; const bool trusted = command_time(now, &now_us); trust_refresh(); zs_bg95_mqtt_session_tick(&session, now, now_us, trusted); }
        audio_collect();                                   /* our chunk's outcome before anyone reuses the uplink */
        fw_collect(now);
        zs_station_comms_tick(&comms, now);
        if (phase == COMMS_ONLINE) { audio_drive(now); fw_drive(now); }
        if (phase == COMMS_SESSION && zs_bg95_mqtt_session_ready(&session)) { online_count++; set_phase(COMMS_ONLINE); activity_ms = now; }
        if (phase == COMMS_ONLINE) { note_session_activity(now); check_session_done(now); }
        if (!wanted()) {
          /* let a publish in flight finish (the modem would otherwise take the QPOWD text as payload bytes);
             after 3 s the power-down goes ahead regardless */
          if (stop_requested_ms == 0u) stop_requested_ms = now ? now : 1u;
          if (session.owner != ZS_BG95_MQTT_OWNER_NONE && (uint32_t)(now - stop_requested_ms) < 3000u) break;
          stop_requested_ms = 0u;
          (void)zs_bg95_request_graceful_power_off(&modem, now); set_phase(COMMS_STOPPING); break;
        }
        if (sim_enabled) {
          /* the orchestrator watches presence; a pulled card or a pending switch takes the modem down under us */
          const evt_pre_20_sim_phase_t ph = evt_pre_20_sim_orchestrator_step(&sim, now);
          if (ph == EVT_PRE_20_SIM_PHASE_CLOSE_TRANSPORT) { evt_pre_20_sim_orchestrator_transport_closed(&sim); set_phase(COMMS_SIM); break; }
          if (ph != EVT_PRE_20_SIM_PHASE_ACTIVE) { set_phase(COMMS_SIM); break; }
          if (modem.state == ZS_BG95_ERROR || !zs_bg95_online(&modem)) { faults++; sim_faults++; evt_pre_20_sim_orchestrator_fail(&sim, ZS_DUAL_SIM_FAILURE_SUSTAINED_LINK_LOSS, now); set_phase(COMMS_SIM); break; }
          break;
        }
        if (modem.state == ZS_BG95_ERROR || !zs_bg95_online(&modem)) { faults++; set_phase(COMMS_FAULT); }
        break;
      case COMMS_STOPPING:
        /* graceful power-down: QPOWD was requested; confirm on STATUS low (or give up after 5 s), then the rail */
        zs_bg95_tick(&modem, now);
        if (modem.state == ZS_BG95_POWERING_OFF) (void)zs_bg95_confirm_power_off(&modem, !bsp_gpio_cell_status());
        if (sim_enabled) {
          if (modem.state == ZS_BG95_OFF || (uint32_t)(now - phase_since_ms) > 5000u) {
            evt_pre_20_sim_orchestrator_shutdown(&sim);                  /* safe-off recovery drops mux and rail */
            if (evt_pre_20_sim_orchestrator_step(&sim, now) == EVT_PRE_20_SIM_PHASE_SAFE_OFF) { if (hooks.log) hooks.log("comms: modem off (policy)\r\n"); set_phase(COMMS_OFF); }
          }
          break;
        }
        if (modem.state == ZS_BG95_OFF || (uint32_t)(now - phase_since_ms) > 5000u) {
          bsp_gpio_modem_power(false);
          modem.state = ZS_BG95_OFF;
          if (hooks.log) hooks.log("comms: modem off (policy)\r\n");
          set_phase(COMMS_OFF);
        }
        break;
      case COMMS_FAULT:
        zs_bg95_tick(&modem, now);
        if ((uint32_t)(now - phase_since_ms) > 30000u) {           /* back off, then a clean restart of the modem */
          bsp_gpio_modem_power(false);
          vTaskDelay(pdMS_TO_TICKS(2000));
          set_phase(COMMS_OFF);
        }
        break;
    }
  }
}

void app_comms_task(void *arg) {
  (void)arg;
  set_phase(COMMS_OFF);
  for (;;) {
    app_comms_step();
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

void app_comms_status(void (*print)(const char *fmt, ...)) {
  static const char *const names[] = {"off", "bringup", "endpoint", "session", "online", "fault", "sim", "stopping"};
  print("comms %s (%s) policy %s%s faults %lu online %lu done %lu | events pub %lu fail %lu exhausted %lu | heartbeats %lu fail %lu | commands key %s verified %lu rejected %lu\r\n",
        names[phase], zs_bg95_state_name(modem.state), modem_allowed ? "modem-on" : "modem-off", want_on ? "" : " (operator off)",
        (unsigned long)faults, (unsigned long)online_count, (unsigned long)sessions_done,
        (unsigned long)comms.events_published, (unsigned long)comms.events_failed, (unsigned long)comms.events_exhausted,
        (unsigned long)comms.heartbeats_published, (unsigned long)comms.heartbeats_failed,
        command_key_count == 2u ? "set+next" : command_key_count ? "set" : "none", (unsigned long)commands_verified, (unsigned long)commands_rejected);
  print("  audio uploads %lu (by server time %lu) chunks %lu rejected %lu failed %lu abandoned %lu%s\r\n", (unsigned long)audio_uploads,
        (unsigned long)audio_by_server_time, (unsigned long)audio_chunks, (unsigned long)audio_rejected, (unsigned long)audio_failed,
        (unsigned long)audio_aborted, app_comms_audio_busy() ? " (upload running)" : "");
  print("  firmware updates %lu rejected %lu failed %lu installs %lu | chunks %lu ignored %lu timeouts %lu%s%s\r\n", (unsigned long)fw_updates,
        (unsigned long)fw_rejected, (unsigned long)fw_failed, (unsigned long)fw_installs, (unsigned long)fw_chunks, (unsigned long)fw_chunks_ignored,
        (unsigned long)fw_timeouts_total, fw_phase == FW_DOWNLOADING ? " (downloading)" : fw_phase != FW_IDLE ? " (finishing)" : "",
        fw_paused ? " (paused)" : "");
  if (sim_enabled)
    print("  dual-sim %s slot %d (sim1 %s, sim2 %s, status %s) starts %lu switches %lu retries %lu recoveries %lu faults %lu bringup-fail %u/%u link-fail %u/%u\r\n",
          zs_dual_sim_state_name(zs_dual_sim_state(&sim_controller)), (int)zs_dual_sim_active_slot(&sim_controller),
          bsp_gpio_sim_present(1u) ? "in" : "out", bsp_gpio_sim_present(2u) ? "in" : "out", bsp_gpio_cell_status() ? "on" : "off",
          (unsigned long)sim.starts, (unsigned long)sim.switches, (unsigned long)sim.retries, (unsigned long)sim.recoveries, (unsigned long)sim_faults,
          sim.bringup_failures[0], sim.bringup_failures[1], sim.link_failures[0], sim.link_failures[1]);
  else
    print("  single-sim path (simiccid 1/2 <iccid> enables dual-sim); sim1 %s sim2 %s status %s\r\n",
          bsp_gpio_sim_present(1u) ? "in" : "out", bsp_gpio_sim_present(2u) ? "in" : "out", bsp_gpio_cell_status() ? "on" : "off");
}

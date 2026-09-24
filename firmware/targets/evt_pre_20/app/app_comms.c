#include "app_comms.h"
#include "app_config.h"
#include "bsp_gpio.h"
#include "bsp_uart.h"
#include "evt_pre_20_sim_orchestrator.h"
#include "FreeRTOS.h"
#include "task.h"
#include "zs_bg95_provision.h"
#include "zs_bg95_mqtt_session.h"
#include "zs_command_trust.h"
#include "zs_mqtt_command_transport.h"
#include <string.h>

typedef enum { COMMS_OFF = 0, COMMS_BRINGUP, COMMS_ENDPOINT, COMMS_SESSION, COMMS_ONLINE, COMMS_FAULT, COMMS_SIM } comms_phase_t;

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
static bool config_valid, want_on = true, bound;
static uint32_t boot_id, phase_since_ms, faults, online_count;
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

/* No provisioned command key on the station yet: nothing verifies. */
static bool verify_none(void *ctx, const uint8_t pk[ZS_COMMAND_PUBLIC_KEY_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx; (void)pk; (void)m; (void)n; (void)sig; return false;
}
static bool execute_none(void *ctx, const zs_command_t *cmd, zs_command_ack_result_t *r, uint16_t *detail) {
  (void)ctx; (void)cmd; *r = ZS_COMMAND_ACK_REJECTED; *detail = 1u; return true;
}
static bool fill_heartbeat(void *ctx, zs_heartbeat_t *hb) { return hooks.fill_heartbeat ? hooks.fill_heartbeat(hooks.ctx ? hooks.ctx : ctx, hb) : false; }

void app_comms_bind(const zs_event_outbox_io_t *outbox, const zs_command_journal_io_t *journal, const app_comms_hooks_t *h) {
  outbox_io = outbox; journal_io = journal; if (h) hooks = *h; bound = outbox && journal;
}
void app_comms_set_config(const zs_station_config_t *cfg, uint32_t id) { if (cfg) { config = *cfg; config_valid = true; boot_id = id; } }
void app_comms_request(bool on) { want_on = on; }
const zs_bg95_t *app_comms_modem(void) { return &modem; }
const zs_station_comms_t *app_comms_state(void) { return &comms; }

static void set_phase(comms_phase_t p) { phase = p; phase_since_ms = xTaskGetTickCount(); }

static bool start_session(const char *tenant) {
  zs_command_trust_key_t no_key; memset(&no_key, 0, sizeof(no_key));
  if (!zs_command_trust_init(&trust, &no_key, 1u, verify_none, NULL)) return false;
  channel = (zs_command_channel_t){config.station_id, &trust, journal_io, execute_none, NULL, verify_workspace, sizeof(verify_workspace)};
  if (!zs_mqtt_command_transport_init(&command_transport, &channel, (const uint8_t *)tenant, strlen(tenant))) return false;
  if (!zs_mqtt_event_transport_init(&event_transport, outbox_io, config.station_id, (const uint8_t *)tenant, strlen(tenant))) return false;
  if (!zs_bg95_command_transport_init(&command_binding, &modem, &command_transport, true)) return false;
  if (!zs_bg95_event_receipt_init(&receipt_binding, &modem, &event_transport, true)) return false;
  if (!zs_bg95_event_uplink_init(&uplink_binding, &modem, &event_transport)) return false;
  if (!zs_bg95_mqtt_session_init(&session, &modem, &command_binding, &receipt_binding, &uplink_binding, (uint16_t)(1u + (xTaskGetTickCount() & 0x7fffu)))) return false;
  comms_port = (zs_station_comms_port_t){NULL, fill_heartbeat, APP_COMMS_HEARTBEAT_MS, 0u};
  return zs_station_comms_init(&comms, &comms_port, &session, &event_transport, xTaskGetTickCount());
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

/* Bring-up lines go to the modem driver; once the session exists it owns the byte stream. */
static void feed_uart(uint32_t now_ms) {
  uint8_t buf[64];
  size_t n;
  while ((n = bsp_uart_read(BSP_UART_CELL, buf, sizeof(buf))) > 0u) {
    if (phase == COMMS_SESSION || phase == COMMS_ONLINE) {
      (void)zs_bg95_mqtt_session_feed_uart(&session, buf, n, now_ms, (uint64_t)now_ms * 1000u, false);
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

void app_comms_task(void *arg) {
  (void)arg;
  set_phase(COMMS_OFF);
  for (;;) {
    const uint32_t now = xTaskGetTickCount();
    feed_uart(now);
    switch (phase) {
      case COMMS_OFF:
        if (want_on && bound && config_valid && config.apn[0][0] != '\0') {
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
        sim_phase(now);
        break;
      case COMMS_BRINGUP:
        zs_bg95_tick(&modem, now);
        if (modem.state == ZS_BG95_READY) {
          if (modem_provision(now)) set_phase(COMMS_ENDPOINT);
          else { if (hooks.log) hooks.log("comms: endpoint rejected\r\n"); faults++; set_phase(COMMS_FAULT); }
        } else if (modem.state == ZS_BG95_ERROR || (uint32_t)(now - phase_since_ms) > 180000u) { faults++; set_phase(COMMS_FAULT); }
        break;
      case COMMS_ENDPOINT:
        zs_bg95_tick(&modem, now);
        if (modem.state == ZS_BG95_ONLINE) {
          if (start_session(tenant)) { set_phase(COMMS_SESSION); if (hooks.log) hooks.log("comms: mqtt online, session starting\r\n"); }
          else { faults++; set_phase(COMMS_FAULT); }
        } else if (modem.state == ZS_BG95_ERROR || (uint32_t)(now - phase_since_ms) > 120000u) { faults++; set_phase(COMMS_FAULT); }
        break;
      case COMMS_SESSION:
      case COMMS_ONLINE:
        zs_bg95_tick(&modem, now);
        zs_bg95_mqtt_session_tick(&session, now, (uint64_t)now * 1000u, false);
        zs_station_comms_tick(&comms, now);
        if (phase == COMMS_SESSION && zs_bg95_mqtt_session_ready(&session)) { online_count++; set_phase(COMMS_ONLINE); }
        if (sim_enabled) {
          /* the orchestrator watches presence; a pulled card or a pending switch takes the modem down under us */
          const evt_pre_20_sim_phase_t ph = evt_pre_20_sim_orchestrator_step(&sim, now);
          if (ph == EVT_PRE_20_SIM_PHASE_CLOSE_TRANSPORT) { evt_pre_20_sim_orchestrator_transport_closed(&sim); set_phase(COMMS_SIM); break; }
          if (ph != EVT_PRE_20_SIM_PHASE_ACTIVE) { set_phase(COMMS_SIM); break; }
          if (modem.state == ZS_BG95_ERROR || !zs_bg95_online(&modem)) { faults++; sim_faults++; evt_pre_20_sim_orchestrator_fail(&sim, ZS_DUAL_SIM_FAILURE_SUSTAINED_LINK_LOSS, now); set_phase(COMMS_SIM); break; }
          if (!want_on) { (void)zs_bg95_request_graceful_power_off(&modem, now); set_phase(COMMS_FAULT); }
          break;
        }
        if (modem.state == ZS_BG95_ERROR || !zs_bg95_online(&modem)) { faults++; set_phase(COMMS_FAULT); }
        if (!want_on) { (void)zs_bg95_request_graceful_power_off(&modem, now); set_phase(COMMS_FAULT); }
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
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

void app_comms_status(void (*print)(const char *fmt, ...)) {
  static const char *const names[] = {"off", "bringup", "endpoint", "session", "online", "fault", "sim"};
  print("comms %s (%s) faults %lu online %lu | events pub %lu fail %lu exhausted %lu | heartbeats %lu fail %lu\r\n",
        names[phase], zs_bg95_state_name(modem.state), (unsigned long)faults, (unsigned long)online_count,
        (unsigned long)comms.events_published, (unsigned long)comms.events_failed, (unsigned long)comms.events_exhausted,
        (unsigned long)comms.heartbeats_published, (unsigned long)comms.heartbeats_failed);
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

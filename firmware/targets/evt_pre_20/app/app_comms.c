#include "app_comms.h"
#include "app_config.h"
#include "bsp_gpio.h"
#include "bsp_uart.h"
#include "FreeRTOS.h"
#include "task.h"
#include "zs_bg95_provision.h"
#include "zs_bg95_mqtt_session.h"
#include "zs_command_trust.h"
#include "zs_mqtt_command_transport.h"
#include <string.h>

typedef enum { COMMS_OFF = 0, COMMS_BRINGUP, COMMS_ENDPOINT, COMMS_SESSION, COMMS_ONLINE, COMMS_FAULT } comms_phase_t;

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

void app_comms_task(void *arg) {
  static char tenant[ZS_STATION_CONFIG_TENANT_MAX + 1u];
  zs_bg95_apn_profile_t profiles[2];
  (void)arg;
  set_phase(COMMS_OFF);
  for (;;) {
    const uint32_t now = xTaskGetTickCount();
    feed_uart(now);
    switch (phase) {
      case COMMS_OFF:
        if (want_on && bound && config_valid && config.apn[0][0] != '\0') {
          unsigned n = 0u;
          memset(profiles, 0, sizeof(profiles));
          for (unsigned i = 0u; i < ZS_STATION_CONFIG_APN_COUNT && n < 2u; i++) {
            if (config.apn[i][0] == '\0') continue;
            strncpy(profiles[n].apn, config.apn[i], sizeof(profiles[n].apn) - 1u);
            profiles[n].public_apn = APP_COMMS_PUBLIC_APN != 0;
            n++;
          }
          bsp_gpio_modem_power(true);
          vTaskDelay(pdMS_TO_TICKS(100));
          zs_bg95_init(&modem, &hal, BSP_UART_CELL, 0u, config.apn[0]);
          (void)zs_bg95_configure_auto_network(&modem, profiles, n);
          zs_bg95_power_on(&modem, now);
          if (hooks.log) hooks.log("comms: modem power on, apn %s\r\n", config.apn[0]);
          set_phase(COMMS_BRINGUP);
        }
        break;
      case COMMS_BRINGUP:
        zs_bg95_tick(&modem, now);
        if (modem.state == ZS_BG95_READY) {
          if (zs_bg95_provision_apply_station_config(&modem, &config, boot_id, APP_COMMS_PUBLIC_APN != 0, tenant, sizeof(tenant)) && zs_bg95_start_mqtt(&modem, now)) {
            if (hooks.log) hooks.log("comms: endpoint %s:%u tenant %s\r\n", config.server_host, config.mqtt_port, tenant);
            set_phase(COMMS_ENDPOINT);
          } else { if (hooks.log) hooks.log("comms: endpoint rejected\r\n"); faults++; set_phase(COMMS_FAULT); }
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
  static const char *const names[] = {"off", "bringup", "endpoint", "session", "online", "fault"};
  print("comms %s (%s) faults %lu online %lu | events pub %lu fail %lu exhausted %lu | heartbeats %lu fail %lu\r\n",
        names[phase], zs_bg95_state_name(modem.state), (unsigned long)faults, (unsigned long)online_count,
        (unsigned long)comms.events_published, (unsigned long)comms.events_failed, (unsigned long)comms.events_exhausted,
        (unsigned long)comms.heartbeats_published, (unsigned long)comms.heartbeats_failed);
}

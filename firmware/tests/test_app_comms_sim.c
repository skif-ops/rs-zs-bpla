/*
 * Host simulation of the STM32 comms task (targets/evt_pre_20/app/app_comms.c): the state machine runs against a
 * scripted BG95 (AT responder on the simulated cell UART), simulated GPIO and a simulated FreeRTOS clock.
 * Scenarios: single-SIM bring-up to an online session with a heartbeat and session_done; policy withdrawal with a
 * graceful power-down and a later restart; a dead modem (FAULT -> back-off -> retry); an event in the outbox that
 * is published and acknowledged before session_done.
 */
#include "app_comms.h"
#include "bsp_gpio.h"
#include "bsp_uart.h"
#include "task.h"
#include "zs_event_outbox.h"
#include "zs_command_journal.h"
#include "zs_station_config.h"

#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- simulated clock ---------------------------------------------------------------------- */
static uint32_t sim_now = 1000u;
uint32_t xTaskGetTickCount(void) { return sim_now; }
void vTaskDelay(uint32_t ticks) { sim_now += ticks; }

/* ---- simulated GPIO (bsp_gpio.h surface used by app_comms) -------------------------------- */
static bool g_modem_rail, g_pwrkey, g_mux_sel, g_mux_en, g_cell_status, g_sim_present[2] = {true, true};
static unsigned g_rail_on, g_rail_off;
void bsp_gpio_init(void) {}
void bsp_gpio_mic_rail(bool on) { (void)on; }
static void modem_reset_state(void);
void bsp_gpio_modem_power(bool on) { if (on && !g_modem_rail) g_rail_on++; if (!on && g_modem_rail) { g_rail_off++; g_cell_status = false; modem_reset_state(); } g_modem_rail = on; }
void bsp_gpio_modem_pwrkey(bool on) { g_pwrkey = on; }
void bsp_gpio_ble_enable(bool on) { (void)on; }
void bsp_gpio_ble_dfu_request(bool on) { (void)on; }
bool bsp_gpio_mic_wake(void) { return false; }
bool bsp_gpio_power_good(void) { return g_modem_rail; }
bool bsp_gpio_power_fault(void) { return false; }
bool bsp_gpio_service_button(void) { return false; }
void bsp_gpio_sim_mux_select(bool s) { g_mux_sel = s; }
void bsp_gpio_sim_mux_enable(bool e) { g_mux_en = e; }
bool bsp_gpio_sim_mux_select_level(void) { return g_mux_sel; }
bool bsp_gpio_sim_mux_enable_level(void) { return g_mux_en; }
bool bsp_gpio_modem_power_level(void) { return g_modem_rail; }
bool bsp_gpio_cell_status(void) { return g_cell_status; }
bool bsp_gpio_sim_present(unsigned slot) { return slot >= 1u && slot <= 2u && g_sim_present[slot - 1u]; }

/* ---- simulated cell UART + BG95 responder ------------------------------------------------- */
static uint8_t rx_fifo[8192]; static size_t rx_head, rx_tail;
static char cmd_line[512]; static size_t cmd_len;
static size_t binary_expected; static uint8_t binary_buf[2048]; static size_t binary_len;
static unsigned pending_pub_id; static char pending_pub_topic[128];
static char at_log[16384]; static size_t at_log_len;
static bool modem_alive = true;         /* false: the modem never answers (dead modem scenario) */
static bool powered_down;               /* after QPOWD: answers nothing until a PWRKEY pulse */
static unsigned qmtpub_count, qmtsub_count, qpowd_count;
static char last_evt_topic[128]; static uint8_t last_evt_payload[1024]; static size_t last_evt_payload_len;

/* A rail cut resets the module: whatever was half-received is gone and it stays silent until PWRKEY. */
static void modem_reset_state(void) { binary_expected = 0u; binary_len = 0u; cmd_len = 0u; rx_head = rx_tail = 0u; powered_down = true; }
static void rx_push(const void *d, size_t n) { for (size_t i = 0u; i < n; i++) { rx_fifo[rx_tail] = ((const uint8_t *)d)[i]; rx_tail = (rx_tail + 1u) % sizeof(rx_fifo); assert(rx_tail != rx_head); } }
static void reply(const char *line) { rx_push(line, strlen(line)); rx_push("\r\n", 2u); }
static void logf_at(const char *s) { const size_t n = strlen(s); if (at_log_len + n + 2u < sizeof(at_log)) { memcpy(at_log + at_log_len, s, n); at_log_len += n; at_log[at_log_len++] = '\n'; at_log[at_log_len] = 0; } }

static void on_at_command(const char *c) {
  logf_at(c);
  if (!modem_alive || powered_down) return;                             /* silence */
  if (strcmp(c, "AT") == 0) { reply("OK"); return; }
  if (strcmp(c, "AT+CPIN?") == 0) { reply("+CPIN: READY"); reply("OK"); return; }
  if (strcmp(c, "AT+QCCID") == 0) { reply("+QCCID: 89701012345678901234"); reply("OK"); return; }
  if (strcmp(c, "AT+CIMI") == 0) { reply("250011234567890"); reply("OK"); return; }
  if (strcmp(c, "AT+COPS?") == 0) { reply("+COPS: 0,0,\"Test Operator\",7"); reply("OK"); return; }
  if (strcmp(c, "AT+CGNAPN") == 0) { reply("+CGNAPN: 1,\"internet\""); reply("OK"); return; }
  if (strncmp(c, "AT+CGDCONT=", 11u) == 0) { reply("OK"); return; }
  if (strcmp(c, "AT+CEREG?") == 0) { reply("+CEREG: 2,1,\"001A\",\"00BC1234\",8"); reply("OK"); return; }
  if (strcmp(c, "AT+CREG?") == 0) { reply("+CREG: 2,1"); reply("OK"); return; }
  if (strcmp(c, "AT+CGCONTRDP=1") == 0) { reply("+CGCONTRDP: 1,5,\"internet\",\"10.10.0.2.255.255.255.0\",\"10.10.0.1\",\"1.1.1.1\",\"8.8.8.8\""); reply("OK"); return; }
  if (strncmp(c, "AT+QSSLCFG=", 11u) == 0 || strncmp(c, "AT+QMTCFG=", 10u) == 0 || strcmp(c, "AT+QIACT=1") == 0) { reply("OK"); return; }
  if (strncmp(c, "AT+QMTOPEN=", 11u) == 0) { reply("OK"); reply("+QMTOPEN: 0,0"); return; }
  if (strncmp(c, "AT+QMTCONN=", 11u) == 0) { reply("OK"); reply("+QMTCONN: 0,0,0"); return; }
  if (strncmp(c, "AT+QMTSUB=", 10u) == 0) { unsigned client, id; char r[64]; qmtsub_count++; assert(sscanf(c, "AT+QMTSUB=%u,%u", &client, &id) == 2); reply("OK"); snprintf(r, sizeof(r), "+QMTSUB: %u,%u,0,1", client, id); reply(r); return; }
  if (strncmp(c, "AT+QMTPUB=", 10u) == 0) {
    unsigned client, id, qos, retain, len; char topic[128];
    assert(sscanf(c, "AT+QMTPUB=%u,%u,%u,%u,\"%127[^\"]\",%u", &client, &id, &qos, &retain, topic, &len) == 6);
    qmtpub_count++; pending_pub_id = id; strcpy(pending_pub_topic, topic); binary_expected = len; binary_len = 0u;
    rx_push(">", 1u);
    return;
  }
  if (strcmp(c, "AT+QPOWD") == 0) { qpowd_count++; reply("OK"); reply("POWERED DOWN"); powered_down = true; g_cell_status = false; return; }
  if (strncmp(c, "AT+QMTDISC", 10u) == 0) { reply("OK"); reply("+QMTDISC: 0,0"); return; }
  reply("OK");                                                          /* anything else: accept */
}

int bsp_uart_write(bsp_uart_id_t id, const uint8_t *data, size_t len) {
  assert(id == BSP_UART_CELL);
  for (size_t i = 0u; i < len; i++) {
    if (binary_expected) {
      binary_buf[binary_len++] = data[i];
      if (binary_len == binary_expected) {
        char r[64];
        if (strstr(pending_pub_topic, "/up")) {
          strcpy(last_evt_topic, pending_pub_topic); memcpy(last_evt_payload, binary_buf, binary_len); last_evt_payload_len = binary_len;
        }
        binary_expected = 0u;
        snprintf(r, sizeof(r), "+QMTPUB: 0,%u,0", pending_pub_id);
        reply(r);
      }
      continue;
    }
    const char c = (char)data[i];
    if (c == '\n') { cmd_line[cmd_len] = 0; if (cmd_len) on_at_command(cmd_line); cmd_len = 0u; }
    else if (c != '\r' && cmd_len + 1u < sizeof(cmd_line)) cmd_line[cmd_len++] = c;
  }
  return (int)len;
}
size_t bsp_uart_read(bsp_uart_id_t id, uint8_t *out, size_t cap) {
  size_t n = 0u;
  assert(id == BSP_UART_CELL);
  while (n < cap && rx_head != rx_tail) { out[n++] = rx_fifo[rx_head]; rx_head = (rx_head + 1u) % sizeof(rx_fifo); }
  return n;
}
bool bsp_uart_init(bsp_uart_id_t id, uint32_t baud) { (void)id; (void)baud; return true; }
uint32_t bsp_uart_rx_overruns(bsp_uart_id_t id) { (void)id; return 0u; }
void app_uart_rx_notify_from_isr(bsp_uart_id_t id) { (void)id; }

/* The modem answers a PWRKEY pulse (PWRKEY high >= 500 ms) by raising STATUS and leaving power-down. */
static bool pwrkey_seen;
static void modem_physics(void) {
  if (g_pwrkey) pwrkey_seen = true;
  if (!g_pwrkey && pwrkey_seen && g_modem_rail && modem_alive) { g_cell_status = true; powered_down = false; pwrkey_seen = false; }
}

/* ---- RAM outbox / journal -------------------------------------------------------------------- */
#define OUTBOX_SLOTS 8u
static uint8_t outbox_mem[OUTBOX_SLOTS][ZS_EVENT_OUTBOX_SLOT_BYTES];
static bool ob_read(void *c, uint16_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s >= OUTBOX_SLOTS || o + n > ZS_EVENT_OUTBOX_SLOT_BYTES) return false; memcpy(d, &outbox_mem[s][o], n); return true; }
static bool ob_erase(void *c, uint16_t s) { (void)c; if (s >= OUTBOX_SLOTS) return false; memset(outbox_mem[s], 0xff, ZS_EVENT_OUTBOX_SLOT_BYTES); return true; }
static bool ob_write(void *c, uint16_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s >= OUTBOX_SLOTS || o + n > ZS_EVENT_OUTBOX_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((outbox_mem[s][o + i] & d[i]) != d[i]) return false; outbox_mem[s][o + i] = d[i]; } return true; }
static const zs_event_outbox_io_t outbox_io = {NULL, OUTBOX_SLOTS, ob_read, ob_erase, ob_write};
#define JOURNAL_SLOTS 4u
static uint8_t journal_mem[JOURNAL_SLOTS][ZS_COMMAND_JOURNAL_SLOT_BYTES];
static bool jn_read(void *c, uint16_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s >= JOURNAL_SLOTS || o + n > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false; memcpy(d, &journal_mem[s][o], n); return true; }
static bool jn_erase(void *c, uint16_t s) { (void)c; if (s >= JOURNAL_SLOTS) return false; memset(journal_mem[s], 0xff, ZS_COMMAND_JOURNAL_SLOT_BYTES); return true; }
static bool jn_write(void *c, uint16_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s >= JOURNAL_SLOTS || o + n > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((journal_mem[s][o + i] & d[i]) != d[i]) return false; journal_mem[s][o + i] = d[i]; } return true; }
static const zs_command_journal_io_t journal_io = {NULL, JOURNAL_SLOTS, jn_read, jn_erase, jn_write};

/* ---- hooks ------------------------------------------------------------------------------------ */
static unsigned heartbeats_filled, sessions_done;
static bool fill_heartbeat(void *ctx, zs_heartbeat_t *hb) { (void)ctx; hb->schema_ver = 2u; hb->time_us = (int64_t)sim_now * 1000; hb->power.battery_pct = 77u; hb->power.battery_mv = 13100u; hb->route.transport = ZS_ROUTE_LTE; strcpy(hb->firmware_ver, "0.1.0-b1"); strcpy(hb->model_ver, "c46"); strcpy(hb->hardware_rev, "Rev.A"); hb->self_test_ok = true; heartbeats_filled++; return true; }
static void session_done(void *ctx) { (void)ctx; sessions_done++; }
static char last_log[4096]; static size_t last_log_len;
static void log_line(const char *fmt, ...) { va_list ap; char b[256]; int n; va_start(ap, fmt); n = vsnprintf(b, sizeof(b), fmt, ap); va_end(ap); if (n > 0 && last_log_len + (size_t)n < sizeof(last_log)) { memcpy(last_log + last_log_len, b, (size_t)n); last_log_len += (size_t)n; last_log[last_log_len] = 0; } }
static const app_comms_hooks_t hooks = {fill_heartbeat, NULL, log_line, session_done};

/* One simulated 20 ms tick of the comms task. */
static void tick(void) { modem_physics(); app_comms_step(); sim_now += 20u; }
static void run_ms(uint32_t ms) { const uint32_t end = sim_now + ms; while (sim_now < end) tick(); }
/* Waits for a log line that appears after the current end of the log (earlier occurrences do not count). */
static bool wait_log(const char *needle, uint32_t timeout_ms) {
  const uint32_t end = sim_now + timeout_ms;
  const size_t from = last_log_len;
  while (sim_now < end) { if (strstr(last_log + from, needle)) return true; tick(); }
  return strstr(last_log + from, needle) != NULL;
}
static const char *at_after(const char *needle, const char *from) { const char *p = strstr(from, needle); return p; }

static void config_for_sim(zs_station_config_t *cfg) {
  zs_station_config_defaults(cfg, 17u, ZS_STATION_CONFIG_REGION_RU868);
  cfg->version = 1u;
  strcpy(cfg->server_host, "muhoed.example.ru"); cfg->mqtt_port = 8883u;
  strcpy(cfg->ca_reference, "dioneya-root"); strcpy(cfg->tenant, "pilot1"); strcpy(cfg->topic_prefix, "zs/v1");
  cfg->preferred_sim = 1u; strcpy(cfg->apn[0], "internet");
  assert(zs_station_config_validate(cfg) == 0u && zs_station_config_compute_hash(cfg, cfg->config_hash));
}

int main(void) {
  zs_station_config_t cfg;
  memset(outbox_mem, 0xff, sizeof(outbox_mem)); memset(journal_mem, 0xff, sizeof(journal_mem));
  config_for_sim(&cfg);
  app_comms_bind(&outbox_io, &journal_io, &hooks);
  app_comms_set_config(&cfg, 5u);

  /* --- 1. modem allowed by the mode scheduler: single-SIM bring-up to an online session --- */
  app_comms_request(true);
  app_comms_allow_modem(true);
  assert(wait_log("modem power on", 2000u));
  assert(g_modem_rail && g_rail_on == 1u);
  assert(wait_log("endpoint muhoed.example.ru:8883 tenant pilot1", 60000u));
  assert(wait_log("mqtt online, session starting", 60000u));
  /* the whole AT dialog in order: sync, SIM, operator, APN, registration, context, TLS, MQTT open/connect */
  {
    const char *p = at_log;
    const char *steps[] = {"AT\n", "AT+CPIN?", "AT+QCCID", "AT+CIMI", "AT+COPS?", "AT+CGDCONT=1,\"IP\",\"internet\"", "AT+CEREG?", "AT+QIACT=1", "AT+CGCONTRDP=1",
                           "AT+QSSLCFG=\"sslversion\"", "AT+QSSLCFG=\"cacert\"", "AT+QMTCFG=\"ssl\"", "AT+QMTOPEN=0,\"muhoed.example.ru\",8883", "AT+QMTCONN=0,\""};
    for (unsigned i = 0u; i < sizeof(steps) / sizeof(steps[0]); i++) { p = at_after(steps[i], p); if (!p) { fprintf(stderr, "missing AT step %s\nlog:\n%s", steps[i], at_log); assert(p); } }
  }
  /* session: subscriptions, then the heartbeat on the status topic, then session_done (outbox empty) */
  run_ms(20000u);
  assert(qmtsub_count >= 2u);
  assert(heartbeats_filled >= 1u && strstr(at_log, "zs/v1/pilot1/17/status") != NULL);
  assert(app_comms_state()->heartbeats_published >= 1u);
  assert(sessions_done == 1u);
  printf("sim 1: online, subs %u pubs %u heartbeats %u, session done at %u ms\n", qmtsub_count, qmtpub_count, app_comms_state()->heartbeats_published, sim_now);

  /* --- 2. the scheduler withdraws the modem (S3 -> S1): graceful QPOWD, rail down, OFF; allowed again -> restart --- */
  app_comms_allow_modem(false);
  assert(wait_log("modem off (policy)", 10000u));
  assert(qpowd_count == 1u && !g_modem_rail && g_rail_off == 1u);
  run_ms(5000u);
  assert(g_rail_on == 1u);                                                /* stays off while not allowed */
  {
    const size_t log_before = last_log_len;
    app_comms_allow_modem(true);
    assert(wait_log("modem power on", 2000u) && strstr(last_log + log_before, "modem power on"));
    assert(g_rail_on == 2u);
    if (!wait_log("mqtt online, session starting", 60000u)) { app_comms_status(log_line); fprintf(stderr, "LOG:\n%s\nAT (tail):\n%s\n", last_log + log_before, at_log + (at_log_len > 700 ? at_log_len - 700 : 0)); assert(0); }
    run_ms(20000u);
    assert(sessions_done == 2u && app_comms_state()->heartbeats_published >= 1u);
  }
  printf("sim 2: policy off -> QPOWD %u, rail off; policy on -> second session at %u ms\n", qpowd_count, sim_now);

  /* --- 3. an event in the outbox: published on the evt topic, acknowledged by a receipt, then session_done --- */
  {
    zs_detection_t d;
    uint8_t ws[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES + 64u];
    const unsigned pubs_before = qmtpub_count;
    memset(&d, 0, sizeof(d));
    d.schema_ver = 4u; d.station_id = 17u; d.boot_id = 5u; d.seq_no = 1u; d.event_id = 500u; d.event_time_us = (int64_t)sim_now * 1000;
    d.classification.class_id = 1u; d.classification.confidence_u8 = 200u; d.route.transport = ZS_ROUTE_LTE;
    assert(zs_event_outbox_enqueue_detection(&outbox_io, &d, 2u, ws, sizeof(ws)) == ZS_EVENT_OUTBOX_OK);
    /* the running session drains it within its next poll */
    run_ms(15000u);
    assert(qmtpub_count > pubs_before && strcmp(last_evt_topic, "zs/v1/pilot1/17/up") == 0 && last_evt_payload_len > 20u);
    assert(app_comms_state()->events_published >= 1u);
    /* no receipt yet: the event stays pending, the session is not "done" */
    { uint16_t pending = 0u; assert(zs_event_outbox_pending_count(&outbox_io, &pending) == ZS_EVENT_OUTBOX_OK && pending == 1u); }
    assert(sessions_done == 2u);
  }
  printf("sim 3: event published on %s (%zu bytes), pending until the receipt\n", last_evt_topic, last_evt_payload_len);

  /* --- 4. dead modem: no answers -> FAULT after the bring-up timeout, back-off, retry --- */
  {
    const unsigned rail_on_before = g_rail_on, rail_off_before = g_rail_off;
    app_comms_allow_modem(false); assert(wait_log("modem off (policy)", 10000u));
    modem_alive = false;
    app_comms_allow_modem(true);
    assert(wait_log("modem power on", 2000u));
    run_ms(130000u);                                                      /* AT sync 30 s -> ERROR -> FAULT 30 s -> rail off -> retry */
    assert(g_rail_off >= rail_off_before + 1u && g_rail_on >= rail_on_before + 2u);   /* at least one power cycle */
    modem_alive = true;
    assert(wait_log("mqtt online, session starting", 300000u));
  }
  printf("sim 4: dead modem -> fault/back-off/retry, then online after recovery at %u ms\n", sim_now);
  printf("app comms sim passed\n");
  return 0;
}

/*
 * Station digital twin (phase 1): the portable station stack running on the host with simulated time against a
 * synthetic acoustic scene, a scripted BG95 and the Muhoed twin server (server/twin/twin_server.py) over a pipe.
 *
 *   scene -> 4-channel audio ring -> zs_station_pipeline (zs_dsp_mcu, AIR gate, level 1) -> zs_event_outbox (RAM)
 *         -> zs_power_modes (the same event wiring as tasks.c) -> app_comms (real STM32 comms task, tests/host_sim)
 *         -> BG95 responder -> twin link: "PUB <topic> <hex>" lines to the server, receipts/commands back as +QMTRECV
 *
 * Remote commands (ICD addendum D): the twin tells the server when the station subscribes to its down topic
 * ("SUB <topic> <wall_us>", as a broker would deliver its QoS 1 queue); the server answers with a signed command
 * and sends the next one in reply to each ACK.  The station side runs the real command channel with the
 * repository test key, a trusted wall clock and an executor that mirrors app_commands.c over zs_station_params.
 *
 * Nothing on the target changes: the twin reuses the modules and mirrors the task wiring of tasks.c.
 *   station_twin --scene drone|quiet|ground --seconds N --server "python3 -m twin.twin_server" [--seed S]
 */
#include "app_comms.h"
#include "bsp_gpio.h"
#include "bsp_uart.h"
#include "scene.h"
#include "task.h"
#include "zs_audio.h"
#include "zs_command_journal.h"
#include "zs_command_set_vector.h"
#include "zs_dsp_mcu.h"
#include "zs_event_outbox.h"
#include "zs_lora_uplink.h"
#include "zs_power_modes.h"
#include "zs_station_config.h"
#include "zs_station_params.h"
#include "zs_station_pipeline.h"

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

/* ---- simulated clock ------------------------------------------------------------------------- */
static uint32_t sim_now = 1000u;
uint32_t xTaskGetTickCount(void) { return sim_now; }
void vTaskDelay(uint32_t ticks) { sim_now += ticks; }

/* ---- log ------------------------------------------------------------------------------------- */
static void tlog(const char *fmt, ...) {
  va_list ap; va_start(ap, fmt);
  printf("[%8.2f] ", (double)sim_now / 1000.0); vprintf(fmt, ap); printf("\n"); va_end(ap);
}
static void comms_log(const char *fmt, ...) {
  va_list ap; char b[256]; int n; va_start(ap, fmt); n = vsnprintf(b, sizeof(b), fmt, ap); va_end(ap);
  if (n > 0) { while (n > 0 && (b[n - 1] == '\n' || b[n - 1] == '\r')) b[--n] = 0; tlog("%s", b); }
}

/* ---- simulated GPIO ---------------------------------------------------------------------------- */
static bool g_modem_rail, g_pwrkey, g_mux_sel, g_mux_en, g_cell_status, g_mic_rail;
static void modem_reset_state(void);
void bsp_gpio_init(void) {}
void bsp_gpio_mic_rail(bool on) { g_mic_rail = on; }
void bsp_gpio_modem_power(bool on) { if (!on && g_modem_rail) { g_cell_status = false; modem_reset_state(); } g_modem_rail = on; }
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
bool bsp_gpio_sim_present(unsigned slot) { return slot == 1u || slot == 2u; }

/* ---- twin link to the server (pipe to the python process) -------------------------------------- */
static int link_in = -1, link_out = -1; static pid_t server_pid;
static char link_buf[65536]; static size_t link_len;
static unsigned link_pubs, link_receipts, link_commands;

static bool link_start(const char *cmd) {
  int to_srv[2], from_srv[2];
  if (pipe(to_srv) || pipe(from_srv)) return false;
  server_pid = fork();
  if (server_pid < 0) return false;
  if (server_pid == 0) {
    dup2(to_srv[0], 0); dup2(from_srv[1], 1);
    close(to_srv[1]); close(from_srv[0]);
    execl("/bin/sh", "sh", "-c", cmd, (char *)NULL);
    _exit(127);
  }
  close(to_srv[0]); close(from_srv[1]);
  link_out = to_srv[1]; link_in = from_srv[0];
  fcntl(link_in, F_SETFL, fcntl(link_in, F_GETFL) | O_NONBLOCK);
  return true;
}
static void link_await_reply(void);
static void link_send(const char *topic, const uint8_t *payload, size_t n) {
  char *line = malloc(strlen(topic) + 2u * n + 16u);
  size_t k = (size_t)sprintf(line, "PUB %s ", topic);
  for (size_t i = 0u; i < n; i++) k += (size_t)sprintf(line + k, "%02x", payload[i]);
  line[k++] = '\n';
  if (write(link_out, line, k) != (ssize_t)k) tlog("link: write failed");
  free(line);
  link_pubs++;
  link_await_reply();
}
static void link_report(void) { const char *r = "REPORT\n"; if (write(link_out, r, 7) != 7) tlog("link: report write failed"); }
/* Wall clock of the twin (station and server agree on UTC: GNSS on the station, NTP on the server). */
static uint64_t twin_wall_us(void) { return UINT64_C(1800000000000000) + (uint64_t)sim_now * 1000u; }
/* The station subscribed to its down topic: the broker delivers its queue now (the server twin answers with a
   command or OK). */
static void link_subscribed(const char *topic) {
  char line[192];
  const int k = snprintf(line, sizeof(line), "SUB %s %llu\n", topic, (unsigned long long)twin_wall_us());
  if (link_out < 0 || k <= 0) return;
  if (write(link_out, line, (size_t)k) != (ssize_t)k) tlog("link: write failed");
  link_await_reply();
}
/* The server answers every line (a message or OK); waiting for that reply keeps the simulation deterministic. */
static bool link_handle_line(char *line);
static void link_await_reply(void) {
  for (unsigned tries = 0u; tries < 10000u; tries++) {
    char *nl = memchr(link_buf, '\n', link_len);
    if (nl) {
      *nl = 0;
      (void)link_handle_line(link_buf);
      memmove(link_buf, nl + 1, link_len - (size_t)(nl + 1 - link_buf));
      link_len -= (size_t)(nl + 1 - link_buf);
      return;
    }
    const ssize_t r = read(link_in, link_buf + link_len, sizeof(link_buf) - 1u - link_len);
    if (r > 0) link_len += (size_t)r; else usleep(1000);
  }
  tlog("link: no reply from the server");
}

/* ---- BG95 responder (as in test_app_comms_sim.c) + downlink injection ------------------------- */
static uint8_t rx_fifo[65536]; static size_t rx_head, rx_tail;
static char cmd_line[512]; static size_t cmd_len;
static size_t binary_expected; static uint8_t binary_buf[4096]; static size_t binary_len;
static unsigned pending_pub_id; static char pending_pub_topic[128];
static bool powered_down = true, gsm_available = true;   /* gsm_available=false: the network is gone (outage scenario) */
static unsigned qmtpub_count, qpowd_count, recv_msgid = 100u;

/* ---- channel model: publish loss, receipt latency/loss, an MQTT broker that refuses while the network is fine ---- */
static float ch_publish_loss, ch_receipt_loss;          /* probabilities 0..1 */
static uint32_t ch_receipt_latency_ms = 60u;            /* server round trip seen by the station */
static uint32_t ch_mqtt_refuse_start, ch_mqtt_refuse_end;   /* QMTOPEN fails in this window */
static uint32_t ch_rng = 0x1234567u;
static unsigned ch_publishes_lost, ch_receipts_lost;
static float ch_rand(void) { ch_rng ^= ch_rng << 13; ch_rng ^= ch_rng >> 17; ch_rng ^= ch_rng << 5; return (float)(ch_rng & 0xffffffu) / 16777216.0f; }
static bool mqtt_refused(void) { return ch_mqtt_refuse_end && sim_now >= ch_mqtt_refuse_start && sim_now < ch_mqtt_refuse_end; }
/* delayed modem lines (the BG95 reports a failed publish only after its own retries, ~15 s) and delayed downlink */
typedef struct { uint32_t at_ms; char line[64]; } delayed_line_t;
static delayed_line_t delayed_lines[16];
typedef struct { uint32_t at_ms; bool used; char topic[128]; uint8_t payload[512]; size_t n; } delayed_msg_t;
static delayed_msg_t delayed_msgs[32];
static void reply(const char *line);
static void reply_later(const char *line, uint32_t delay_ms) {
  for (unsigned i = 0u; i < 16u; i++) if (!delayed_lines[i].line[0]) { delayed_lines[i].at_ms = sim_now + delay_ms; snprintf(delayed_lines[i].line, sizeof(delayed_lines[i].line), "%s", line); return; }
}
static void inject_downlink(const char *topic, const uint8_t *payload, size_t n);
static void lora_downlink(const uint8_t *frame, size_t n);
static void channel_tick(void) {
  for (unsigned i = 0u; i < 16u; i++) if (delayed_lines[i].line[0] && (int32_t)(sim_now - delayed_lines[i].at_ms) >= 0) { if (!powered_down) reply(delayed_lines[i].line); delayed_lines[i].line[0] = 0; }
  for (unsigned i = 0u; i < 32u; i++) if (delayed_msgs[i].used && (int32_t)(sim_now - delayed_msgs[i].at_ms) >= 0) { inject_downlink(delayed_msgs[i].topic, delayed_msgs[i].payload, delayed_msgs[i].n); delayed_msgs[i].used = false; }
}

static void modem_reset_state(void) { binary_expected = 0u; binary_len = 0u; cmd_len = 0u; rx_head = rx_tail = 0u; powered_down = true; for (unsigned i = 0u; i < 16u; i++) delayed_lines[i].line[0] = 0; }
static void rx_push(const void *d, size_t n) { for (size_t i = 0u; i < n; i++) { rx_fifo[rx_tail] = ((const uint8_t *)d)[i]; rx_tail = (rx_tail + 1u) % sizeof(rx_fifo); assert(rx_tail != rx_head); } }
static void reply(const char *line) { rx_push(line, strlen(line)); rx_push("\r\n", 2u); }

static void on_at_command(const char *c) {
  if (powered_down) return;
  if (strcmp(c, "AT") == 0) { reply("OK"); return; }
  if (strcmp(c, "AT+CPIN?") == 0) { reply("+CPIN: READY"); reply("OK"); return; }
  if (strcmp(c, "AT+QCCID") == 0) { reply("+QCCID: 89701012345678901234"); reply("OK"); return; }
  if (strcmp(c, "AT+CIMI") == 0) { reply("250011234567890"); reply("OK"); return; }
  if (strcmp(c, "AT+COPS?") == 0) { reply("+COPS: 0,0,\"Twin Operator\",7"); reply("OK"); return; }
  if (strncmp(c, "AT+CGDCONT=", 11u) == 0) { reply("OK"); return; }
  if (strcmp(c, "AT+CEREG?") == 0) { reply(gsm_available ? "+CEREG: 2,1,\"001A\",\"00BC1234\",8" : "+CEREG: 2,2"); reply("OK"); return; }
  if (strcmp(c, "AT+CREG?") == 0) { reply(gsm_available ? "+CREG: 2,1" : "+CREG: 2,2"); reply("OK"); return; }
  if (strcmp(c, "AT+CGCONTRDP=1") == 0) { reply("+CGCONTRDP: 1,5,\"internet\",\"10.10.0.2.255.255.255.0\",\"10.10.0.1\",\"1.1.1.1\",\"8.8.8.8\""); reply("OK"); return; }
  if (strncmp(c, "AT+QSSLCFG=", 11u) == 0 || strncmp(c, "AT+QMTCFG=", 10u) == 0) { reply("OK"); return; }
  if (strcmp(c, "AT+QIACT=1") == 0) { reply(gsm_available ? "OK" : "ERROR"); return; }
  if (strncmp(c, "AT+QMTOPEN=", 11u) == 0) { reply("OK"); reply(gsm_available && !mqtt_refused() ? "+QMTOPEN: 0,0" : "+QMTOPEN: 0,-1"); return; }
  if (strncmp(c, "AT+QMTCONN=", 11u) == 0) { reply("OK"); reply("+QMTCONN: 0,0,0"); return; }
  if (strncmp(c, "AT+QMTSUB=", 10u) == 0) {
    unsigned client, id; char r[64], topic[128];
    if (sscanf(c, "AT+QMTSUB=%u,%u", &client, &id) == 2) {
      reply("OK"); snprintf(r, sizeof(r), "+QMTSUB: %u,%u,0,1", client, id); reply(r);
      if (sscanf(c, "AT+QMTSUB=%*u,%*u,\"%127[^\"]\"", topic) == 1) link_subscribed(topic);
    }
    return;
  }
  if (strncmp(c, "AT+QMTPUB=", 10u) == 0) {
    unsigned client, id, qos, retain, len; char topic[128];
    if (sscanf(c, "AT+QMTPUB=%u,%u,%u,%u,\"%127[^\"]\",%u", &client, &id, &qos, &retain, topic, &len) == 6) {
      qmtpub_count++; pending_pub_id = id; strcpy(pending_pub_topic, topic); binary_expected = len; binary_len = 0u;
      rx_push(">", 1u);
    }
    return;
  }
  if (strcmp(c, "AT+QPOWD") == 0) { qpowd_count++; reply("OK"); reply("POWERED DOWN"); powered_down = true; g_cell_status = false; return; }
  reply("OK");
}

int bsp_uart_write(bsp_uart_id_t id, const uint8_t *data, size_t len) {
  (void)id;
  for (size_t i = 0u; i < len; i++) {
    if (binary_expected) {
      binary_buf[binary_len++] = data[i];
      if (binary_len == binary_expected) {
        char r[64];
        binary_expected = 0u;
        if (gsm_available && ch_rand() >= ch_publish_loss) {
          link_send(pending_pub_topic, binary_buf, binary_len);
          snprintf(r, sizeof(r), "+QMTPUB: 0,%u,0", pending_pub_id);
          reply(r);
        } else if (gsm_available) {
          ch_publishes_lost++;                                            /* lost on air: the modem gives up after its retries */
          snprintf(r, sizeof(r), "+QMTPUB: 0,%u,2", pending_pub_id);
          reply_later(r, 15000u);
        } else {
          snprintf(r, sizeof(r), "+QMTPUB: 0,%u,2", pending_pub_id);      /* publish failed: network gone */
          reply(r);
        }
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
  size_t n = 0u; (void)id;
  while (n < cap && rx_head != rx_tail) { out[n++] = rx_fifo[rx_head]; rx_head = (rx_head + 1u) % sizeof(rx_fifo); }
  return n;
}
bool bsp_uart_init(bsp_uart_id_t id, uint32_t baud) { (void)id; (void)baud; return true; }
uint32_t bsp_uart_rx_overruns(bsp_uart_id_t id) { (void)id; return 0u; }
void app_uart_rx_notify_from_isr(bsp_uart_id_t id) { (void)id; }

/* Downlink from the server: +QMTRECV frame as the BG95 delivers it (recv/mode with length). */
static void inject_downlink(const char *topic, const uint8_t *payload, size_t n) {
  char head[192];
  const int k = snprintf(head, sizeof(head), "+QMTRECV: 0,%u,\"%s\",%zu,\"", recv_msgid++, topic, n);
  if (powered_down || !gsm_available || k <= 0) return;
  rx_push(head, (size_t)k); rx_push(payload, n); rx_push("\"\r\n", 3u);
}
static bool link_handle_line(char *line) {
  if (strncmp(line, "PUB ", 4u) == 0) {
    char topic[128]; char *hex; size_t n = 0u;
    static uint8_t payload[4096];
    if (sscanf(line + 4, "%127s", topic) == 1 && (hex = strchr(line + 4, ' ')) != NULL) {
      hex++;
      for (; hex[0] && hex[1] && n < sizeof(payload); hex += 2) { unsigned v; if (sscanf(hex, "%2x", &v) != 1) break; payload[n++] = (uint8_t)v; }
      if (strstr(topic, "/receipt")) link_receipts++; else link_commands++;
      if (ch_rand() < ch_receipt_loss) { ch_receipts_lost++; tlog("link: <- %s (%zu B) LOST on air", topic, n); }
      else {
        unsigned slot = 32u;
        for (unsigned i = 0u; i < 32u; i++) if (!delayed_msgs[i].used) { slot = i; break; }
        if (slot < 32u && n <= sizeof(delayed_msgs[0].payload)) { delayed_msgs[slot].used = true; delayed_msgs[slot].at_ms = sim_now + ch_receipt_latency_ms; snprintf(delayed_msgs[slot].topic, sizeof(delayed_msgs[slot].topic), "%s", topic); memcpy(delayed_msgs[slot].payload, payload, n); delayed_msgs[slot].n = n; }
        tlog("link: <- %s (%zu B), delivered in %lu ms", topic, n, (unsigned long)ch_receipt_latency_ms);
      }
    }
    return true;
  }
  if (strncmp(line, "LORA ", 5u) == 0) {
    static uint8_t frame[64]; size_t n = 0u; const char *hex = line + 5;
    for (; hex[0] && hex[1] && n < sizeof(frame); hex += 2) { unsigned v; if (sscanf(hex, "%2x", &v) != 1) break; frame[n++] = (uint8_t)v; }
    lora_downlink(frame, n);
    return true;
  }
  if (strncmp(line, "REPORT ", 7u) == 0) { printf("SERVER %s\n", line + 7); return true; }
  return strcmp(line, "OK") == 0;
}
static void link_poll(void) {
  ssize_t r;
  if (link_in < 0) return;
  while ((r = read(link_in, link_buf + link_len, sizeof(link_buf) - 1u - link_len)) > 0) link_len += (size_t)r;
  for (;;) {
    char *nl = memchr(link_buf, '\n', link_len);
    if (!nl) break;
    *nl = 0;
    (void)link_handle_line(link_buf);
    memmove(link_buf, nl + 1, link_len - (size_t)(nl + 1 - link_buf));
    link_len -= (size_t)(nl + 1 - link_buf);
  }
}

/* ---- LoRa: the radio channel (airtime, loss, gateway round trip) and the station uplink --------------- */
static zs_lora_uplink_t lora;
static bool lora_enabled;                       /* --lora: a gateway is in range (the regional gate is assumed closed) */
static float ch_lora_loss;                      /* frame loss probability, each direction */
static uint32_t ch_lora_gateway_ms = 800u;      /* gateway -> server -> ACK round trip */
static unsigned lora_tx_frames, lora_acks_rx;
typedef struct { uint32_t at_ms; bool used; uint8_t frame[64]; size_t n; } lora_pending_t;
static lora_pending_t lora_to_gateway[8], lora_to_station[8];
static uint8_t twin_engineer_key[32];
/* recent detections cache for the LoRa summary (event_id -> fields); zeros for events from before a reboot */
typedef struct { uint64_t event_id; uint8_t class_id, confidence, level; uint16_t f0; bool used; } summary_t;
static summary_t summaries[16];
static void remember_summary(uint64_t id, uint8_t cls, uint8_t conf, uint8_t level, uint16_t f0) {
  static unsigned next;
  summaries[next] = (summary_t){id, cls, conf, level, f0, true}; next = (next + 1u) % 16u;
}
static bool lora_summarize(void *c, const zs_event_outbox_item_t *it, zs_lora_event_t *e) {
  (void)c;
  e->battery_mv = 13200u; e->battery_pct = 80u;
  for (unsigned i = 0u; i < 16u; i++) if (summaries[i].used && summaries[i].event_id == it->event_id) { e->class_id = summaries[i].class_id; e->confidence_u8 = summaries[i].confidence; e->presence_level = summaries[i].level; e->f0_hz = summaries[i].f0; return true; }
  return false;
}
static bool lora_tx(void *c, const uint8_t *frame, size_t n) {
  (void)c;
  lora_tx_frames++;
  if (ch_rand() < ch_lora_loss) { tlog("lora: frame lost on air"); return true; }        /* the radio sent it; nobody heard */
  for (unsigned i = 0u; i < 8u; i++) if (!lora_to_gateway[i].used) { lora_to_gateway[i].used = true; lora_to_gateway[i].at_ms = sim_now + zs_lora_airtime_ms(n, 9u, 125000u, 5u); memcpy(lora_to_gateway[i].frame, frame, n); lora_to_gateway[i].n = n; return true; }
  return false;
}
static const zs_lora_uplink_port_t lora_port = {NULL, lora_tx, lora_summarize};
static void lora_channel_tick(void) {
  for (unsigned i = 0u; i < 8u; i++) if (lora_to_gateway[i].used && (int32_t)(sim_now - lora_to_gateway[i].at_ms) >= 0) {
    char *line = malloc(2u * lora_to_gateway[i].n + 16u); size_t k = (size_t)sprintf(line, "LORA ");
    for (size_t j = 0u; j < lora_to_gateway[i].n; j++) k += (size_t)sprintf(line + k, "%02x", lora_to_gateway[i].frame[j]);
    line[k++] = '\n';
    if (link_out >= 0 && write(link_out, line, k) != (ssize_t)k) tlog("lora: link write failed");
    free(line); lora_to_gateway[i].used = false;
    if (link_out >= 0) link_await_reply();
  }
  for (unsigned i = 0u; i < 8u; i++) if (lora_to_station[i].used && (int32_t)(sim_now - lora_to_station[i].at_ms) >= 0) {
    lora_to_station[i].used = false;
    if (ch_rand() < ch_lora_loss) { tlog("lora: ack lost on air"); continue; }
    if (zs_lora_uplink_on_rx(&lora, lora_to_station[i].frame, lora_to_station[i].n, sim_now)) { lora_acks_rx++; tlog("lora: ack -> delivered"); }
  }
}
/* the gateway's ACK arrives from the link: schedule it at the station after the round trip + airtime */
static void lora_downlink(const uint8_t *frame, size_t n) {
  for (unsigned i = 0u; i < 8u; i++) if (!lora_to_station[i].used) { lora_to_station[i].used = true; lora_to_station[i].at_ms = sim_now + ch_lora_gateway_ms + zs_lora_airtime_ms(n, 9u, 125000u, 5u); memcpy(lora_to_station[i].frame, frame, n); lora_to_station[i].n = n; return; }
}

/* The modem answers a PWRKEY pulse by raising STATUS and leaving power-down. */
static bool pwrkey_seen;
static void modem_physics(void) {
  if (g_pwrkey) pwrkey_seen = true;
  if (!g_pwrkey && pwrkey_seen && g_modem_rail) { g_cell_status = true; powered_down = false; pwrkey_seen = false; }
}

/* ---- RAM outbox / journal ---------------------------------------------------------------------- */
#define OUTBOX_SLOTS 64u
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

/* ---- station: audio ring, pipeline, modes (mirrors tasks.c) ------------------------------------ */
#define RING_FRAMES 36000u
#define TICK_MS 20u
#define TICK_FRAMES 640u
static int16_t ring_storage[RING_FRAMES * ZS_AUDIO_CHANNELS];
static zs_audio_ring_t ring;
static int16_t window_pcm[ZS_PIPELINE_WINDOW_SAMPLES];
static zs_dsp_ctx_t dsp_ctx;
static zs_station_pipeline_t pipeline;
static zs_mode_scheduler_t modes;
static uint32_t mode_bits;
static unsigned events_emitted_total, sessions_done, quiet_windows;
static uint32_t seen_events;
static scene_t scene;
static float scene_level;                 /* recent RMS of the scene, for the AAD wake emulation */
static FILE *dump_pcm;                    /* --dump-pcm: the mono scene as PCM16LE 32 kHz (for tools/presence_eval) */

static void mode_event(zs_mode_event_t ev) { mode_bits |= 1u << ev; }
static bool pl_extract(void *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) { (void)ctx; return zs_dsp_mcu_extract_1s(&dsp_ctx, pcm, n, out); }
static int64_t pl_sample_time(void *ctx, uint64_t sample) { (void)ctx; return (int64_t)1800000000000000LL + (int64_t)sample * 1000000LL / 32000LL; }
static bool pl_emit(void *ctx, const zs_detection_t *d) {
  static uint8_t ws[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES + 64u];
  zs_detection_t e = *d; (void)ctx;
  e.route.transport = ZS_ROUTE_LTE; e.power.battery_pct = 80u; e.power.battery_mv = 13200u;
  const bool ok = zs_event_outbox_enqueue_detection(&outbox_io, &e, 2u, ws, sizeof(ws)) == ZS_EVENT_OUTBOX_OK;
  events_emitted_total += ok;
  if (ok) remember_summary(d->event_id, d->classification.class_id, d->classification.confidence_u8, pipeline.presence.level, (uint16_t)pipeline.last_gate.f0_hz);
  tlog("station: event %llu emitted (level %u conf %u) -> outbox %s", (unsigned long long)d->event_id, pipeline.presence.level, pipeline.presence.confidence_u8, ok ? "ok" : "REFUSED");
  return ok;
}
static zs_station_pipeline_port_t pipeline_port = {NULL, pl_extract, pl_sample_time, pl_emit, 17u, 5u, 0u, 0u};

/* --inject-events N AT_S: N synthetic detections straight into the outbox (burst scenarios without the classifier) */
static unsigned inject_count; static uint32_t inject_at_ms; static bool injected;
static void inject_tick(void) {
  if (injected || inject_count == 0u || sim_now < inject_at_ms) return;
  injected = true;
  for (unsigned i = 0u; i < inject_count; i++) {
    static uint8_t ws[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES + 64u];
    zs_detection_t d; memset(&d, 0, sizeof(d));
    d.schema_ver = 4u; d.station_id = 17u; d.boot_id = 5u; d.seq_no = 1000u + i; d.event_id = ((uint64_t)5u << 32) | (1000u + i);
    d.event_time_us = pl_sample_time(NULL, ring.total_frames) + (int64_t)i * 1000000LL; d.classification.class_id = 3u; d.classification.confidence_u8 = 200u;
    d.route.transport = ZS_ROUTE_LTE; d.power.battery_mv = 13200u; d.power.battery_pct = 80u;
    if (zs_event_outbox_enqueue_detection(&outbox_io, &d, 2u, ws, sizeof(ws)) == ZS_EVENT_OUTBOX_OK) { events_emitted_total++; remember_summary(d.event_id, 3u, 200u, 3u, 190u); }
  }
  tlog("twin: injected %u events into the outbox", inject_count);
  mode_event(ZS_MODE_EV_OUTBOX_PENDING);
}

static void dsp_mode_events(void) {
  const uint8_t level = pipeline.presence.level;
  if (modes.mode == ZS_MODE_S1_LISTEN) {
    quiet_windows = 0u;
    if (level >= ZS_PRESENCE_SUSPECT) mode_event(ZS_MODE_EV_GATE_POSITIVE);
    if (pipeline.events_emitted != seen_events) { seen_events = pipeline.events_emitted; mode_event(ZS_MODE_EV_OUTBOX_PENDING); }
    return;
  }
  if (modes.mode != ZS_MODE_S2_DSP) { quiet_windows = 0u; seen_events = pipeline.events_emitted; return; }
  if (pipeline.events_emitted != seen_events) { seen_events = pipeline.events_emitted; quiet_windows = 0u; mode_event(ZS_MODE_EV_DSP_DONE_EVENT); return; }
  if (level == ZS_PRESENCE_NONE) { if (++quiet_windows >= 6u) { quiet_windows = 0u; mode_event(ZS_MODE_EV_DSP_DONE_NOTHING); } }
  else quiet_windows = 0u;
}

static bool fill_heartbeat(void *ctx, zs_heartbeat_t *hb) {
  uint16_t pending = 0u; (void)ctx;
  hb->schema_ver = 2u; hb->time_us = pl_sample_time(NULL, ring.total_frames);
  hb->power.battery_pct = 80u; hb->power.battery_mv = 13200u; hb->route.transport = ZS_ROUTE_LTE;
  strcpy(hb->firmware_ver, "twin"); strcpy(hb->model_ver, "c46"); strcpy(hb->hardware_rev, "Rev.A"); hb->self_test_ok = true;
  hb->detector_present = true; hb->detector.boot_id = 5u; hb->detector.uptime_s = sim_now / 1000u;
  hb->detector.windows = pipeline.windows; hb->detector.windows_dropped = pipeline.windows_dropped;
  hb->detector.confirmed_windows = pipeline.confirmed_windows; hb->detector.suspect_windows = pipeline.suspect_windows;
  hb->detector.events_emitted = pipeline.events_emitted; hb->detector.presence_level = pipeline.presence.level;
  if (zs_event_outbox_pending_count(&outbox_io, &pending) == ZS_EVENT_OUTBOX_OK) hb->detector.outbox_pending = pending;
  return true;
}
static uint32_t outbox_retry_at_ms, outbox_retry_backoff_ms = 300000u, outbox_retries;
static void session_done(void *ctx) { (void)ctx; sessions_done++; outbox_retry_backoff_ms = 300000u; outbox_retry_at_ms = 0u; mode_event(ZS_MODE_EV_COMMS_DONE); tlog("comms: session done -> COMMS_DONE"); }
static const app_comms_hooks_t hooks = {fill_heartbeat, NULL, comms_log, session_done};

/* Outbox retry (mirrors tasks.c): events left in the outbox after an S3 that did not finish (no network, S3
   watchdog) are re-offered to the scheduler with a backoff: 5 min, 10, 20, ... up to 1 h; COMMS_DONE resets it. */
static void outbox_retry_tick(void) {
  static uint32_t last_check_ms;
  uint16_t pending = 0u;
  if ((uint32_t)(sim_now - last_check_ms) < 10000u) return;
  last_check_ms = sim_now;
  if (modes.mode == ZS_MODE_S3_COMMS || modes.mode == ZS_MODE_S4_SERVICE) return;
  if (zs_event_outbox_pending_count(&outbox_io, &pending) != ZS_EVENT_OUTBOX_OK || pending == 0u) { outbox_retry_at_ms = 0u; return; }
  if (outbox_retry_at_ms == 0u) { outbox_retry_at_ms = sim_now + outbox_retry_backoff_ms; return; }
  if ((int32_t)(sim_now - outbox_retry_at_ms) < 0) return;
  outbox_retries++;
  tlog("outbox: %u event(s) still pending -> retry S3 (backoff %lu s)", pending, (unsigned long)(outbox_retry_backoff_ms / 1000u));
  mode_event(ZS_MODE_EV_OUTBOX_PENDING);
  if (outbox_retry_backoff_ms < 3600000u) outbox_retry_backoff_ms *= 2u;
  outbox_retry_at_ms = sim_now + outbox_retry_backoff_ms;
}

/* GSM health (mirrors tasks.c): consecutive S3 sessions that end without COMMS_DONE (watchdog) mark the link
   degraded after 3: the S3 watchdog drops from 180 s to 60 s so a dead network costs less modem time per retry,
   and the route hint switches to LoRa for the phase-2 transport; a completed session restores everything. */
static unsigned comms_fail_streak, degraded_after = 3u; static bool gsm_degraded;
static uint32_t gsm_probe_ms = 1800000u, last_s3_exit_ms;   /* while degraded: probe GSM every 30 min (S3 capped at 60 s) */
/* LoRa duty: while the route hint is LoRa the uplink drains the outbox regardless of the mode (the radio is cheap:
   no S3 needed); a delivered outbox resets the outbox retry so S3 is not re-entered for events LoRa has sent. */
static void lora_step(void) {
  static uint32_t last_ms;
  if ((uint32_t)(sim_now - last_ms) < 100u) return;
  last_ms = sim_now;
  const zs_lora_uplink_result_t r = zs_lora_uplink_tick(&lora, sim_now, gsm_degraded);
  if (r == ZS_LORA_UPLINK_SENT) tlog("lora: frame %u sent (event %llu, budget %lu ms)", lora.frames_sent, (unsigned long long)lora.item.event_id, (unsigned long)lora.budget_ms);
  else if (r == ZS_LORA_UPLINK_NO_BUDGET && (lora.budget_waits % 50u) == 1u) tlog("lora: duty-cycle budget exhausted, waiting");
}
static void comms_health_on_s3_exit(bool done) {
  last_s3_exit_ms = sim_now;
  if (done) { comms_fail_streak = 0u; if (gsm_degraded) { gsm_degraded = false; modes.policy.comms_max_ms = 180000u; tlog("comms: link healthy again, S3 watchdog 180 s"); } return; }
  comms_fail_streak++;
  if (!gsm_degraded && comms_fail_streak >= degraded_after) { gsm_degraded = true; modes.policy.comms_max_ms = 60000u; tlog("comms: DEGRADED after %u failed sessions -> S3 watchdog 60 s, route hint LoRa", comms_fail_streak); }
}

static void gsm_probe_tick(void) {
  if (!gsm_degraded || modes.mode == ZS_MODE_S3_COMMS || modes.mode == ZS_MODE_S4_SERVICE) return;
  if ((uint32_t)(sim_now - last_s3_exit_ms) < gsm_probe_ms) return;
  tlog("comms: GSM probe (%lu s since the last session)", (unsigned long)((sim_now - last_s3_exit_ms) / 1000u));
  last_s3_exit_ms = sim_now;
  mode_event(ZS_MODE_EV_OUTBOX_PENDING);
}

/* ---- remote commands: executor mirroring app_commands.c over zs_station_params (RAM record = the NOR one) ---- */
static uint8_t params_mem[2][64];
static bool pm_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > 64u) return false; memcpy(d, &params_mem[s][o], n); return true; }
static bool pm_erase(void *c, uint8_t s) { (void)c; if (s > 1u) return false; memset(params_mem[s], 0xff, 64u); return true; }
static bool pm_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > 64u) return false; for (size_t i = 0u; i < n; i++) { if ((params_mem[s][o + i] & d[i]) != d[i]) return false; params_mem[s][o + i] = d[i]; } return true; }
static const zs_station_params_io_t params_io = {NULL, pm_read, pm_erase, pm_write};
static zs_station_params_t params;
static unsigned cmd_executed, cmd_rejected, cmd_reboots_scheduled, twin_reboots;
static bool reboot_pending; static uint32_t reboot_at_ms;
static void params_apply(const zs_station_params_t *p) {
  modes.policy.heartbeat_period_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_HEARTBEAT_PERIOD_S) * 1000u;
  modes.policy.listen_dwell_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_LISTEN_DWELL_S) * 1000u;
  pipeline_port.channel = (uint8_t)zs_station_params_get(p, ZS_PARAM_MIC_CHANNEL);
  pipeline_port.update_period_windows = (uint8_t)zs_station_params_get(p, ZS_PARAM_EVENT_UPDATE_WINDOWS);
  degraded_after = (unsigned)zs_station_params_get(p, ZS_PARAM_COMMS_DEGRADED_AFTER);
  gsm_probe_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_GSM_PROBE_S) * 1000u;
}
static bool twin_execute(void *ctx, const zs_command_t *cmd, zs_command_ack_result_t *result, uint16_t *detail) {
  (void)ctx;
  *result = ZS_COMMAND_ACK_OK; *detail = 0u;
  if (cmd->code == ZS_COMMAND_SET_PARAMS) {
    zs_station_params_t next;
    const uint16_t reject = zs_station_params_apply_command(&params, &cmd->params, &next);
    if (reject) { *result = ZS_COMMAND_ACK_REJECTED; *detail = reject; }
    else if (zs_station_params_commit(&params_io, &next) != ZS_STATION_PARAMS_OK) { *result = ZS_COMMAND_ACK_FAILED; *detail = 1u; }
    else { params = next; params_apply(&params); tlog("command: SET_PARAMS applied, params v%lu (heartbeat %ld s, mic %ld, dwell %ld s)", (unsigned long)params.version, (long)params.value[0], (long)params.value[1], (long)params.value[5]); }
  } else if (cmd->code == ZS_COMMAND_REBOOT) {
    const uint32_t delay_s = cmd->reboot.delay_s > 5u ? cmd->reboot.delay_s : 5u;
    reboot_pending = true; reboot_at_ms = sim_now + delay_s * 1000u; cmd_reboots_scheduled++;
    tlog("command: REBOOT in %lu s", (unsigned long)delay_s);
  } else { *result = ZS_COMMAND_ACK_REJECTED; *detail = 1u; }
  if (*result == ZS_COMMAND_ACK_OK) cmd_executed++; else cmd_rejected++;
  return true;
}
/* Trusted wall clock for the command validity window (the target: zs_command_clock over GNSS/NITZ). */
static bool twin_clock(uint32_t now_ms, uint64_t *now_us) { (void)now_ms; *now_us = twin_wall_us(); return true; }
/* The reboot the executor scheduled: the scheduler restarts and the parameters come back from the record (the
   command journal and the outbox live in NOR and survive as they are). */
static void reboot_tick(void) {
  zs_station_params_t loaded;
  if (!reboot_pending || (int32_t)(sim_now - reboot_at_ms) < 0) return;
  reboot_pending = false; twin_reboots++;
  if (zs_station_params_load(&params_io, &loaded) != ZS_STATION_PARAMS_OK || memcmp(&loaded, &params, sizeof(params)) != 0) {
    tlog("twin: FAIL parameters did not survive the reboot"); exit(1);
  }
  zs_mode_init(&modes, NULL, sim_now);
  params_apply(&loaded);
  (void)zs_mode_on_event(&modes, ZS_MODE_EV_BOOT_DONE, sim_now);
  tlog("twin: REBOOT by command, params v%lu reloaded from the record", (unsigned long)loaded.version);
}

static void supervisor_tick(void) {
  static zs_mode_t last = ZS_MODE_SHUTDOWN;
  reboot_tick();
  outbox_retry_tick();
  gsm_probe_tick();
  for (unsigned ev = 1u; ev < 32u; ev++) if (mode_bits & (1u << ev)) (void)zs_mode_on_event(&modes, (zs_mode_event_t)ev, sim_now);
  mode_bits = 0u;
  (void)zs_mode_tick(&modes, sim_now);
  if (modes.mode != last) {
    const zs_mode_power_t p = zs_mode_power_for(modes.mode);
    tlog("mode %s -> %s", zs_mode_name(last), zs_mode_name(modes.mode));
    if (last == ZS_MODE_S3_COMMS) comms_health_on_s3_exit(modes.journal[(modes.journal_head + ZS_MODE_JOURNAL_DEPTH - 1u) % ZS_MODE_JOURNAL_DEPTH].event == ZS_MODE_EV_COMMS_DONE);
    bsp_gpio_mic_rail(p.mic_1v8);
    app_comms_allow_modem(p.modem);
    last = modes.mode;
  }
}

static void audio_tick(void) {
  const bool mdf_on = zs_mode_power_for(modes.mode).mdf_clock;
  float acc = 0.0f;
  for (unsigned i = 0u; i < TICK_FRAMES; i++) {
    const float v = scene_next(&scene);
    int16_t frame[ZS_AUDIO_CHANNELS];
    acc += v * v;
    for (unsigned c = 0u; c < ZS_AUDIO_CHANNELS; c++) frame[c] = (int16_t)(v * 30000.0f);
    if (dump_pcm) fwrite(&frame[0], sizeof(int16_t), 1u, dump_pcm);
    if (mdf_on) zs_audio_ring_push(&ring, frame);
  }
  scene_level = 0.9f * scene_level + 0.1f * acc / (float)TICK_FRAMES;
  /* the T5838 AAD: a loud enough scene wakes the station from S0 */
  if (modes.mode == ZS_MODE_S0_SLEEP && scene_level > 0.002f) mode_event(ZS_MODE_EV_MIC_WAKE);
  if ((modes.mode == ZS_MODE_S1_LISTEN || modes.mode == ZS_MODE_S2_DSP) && zs_station_pipeline_fetch(&pipeline, &ring)) {
    while (pipeline.pending) { (void)zs_station_pipeline_run_pending(&pipeline); dsp_mode_events(); }
  }
}

int main(int argc, char **argv) {
  const char *scene_name = "drone", *server_cmd = NULL;
  uint32_t seconds = 120u, seed = 1u, outage_start = 0u, outage_end = 0u;
  int expect_events = -1, expect_delivered = -1, expect_commands = -1, expect_reboots = -1;
  zs_station_config_t cfg;
  static scene_segment_t segs[4]; size_t nseg = 0u;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--scene") && i + 1 < argc) scene_name = argv[++i];
    else if (!strcmp(argv[i], "--seconds") && i + 1 < argc) seconds = (uint32_t)atoi(argv[++i]);
    else if (!strcmp(argv[i], "--seed") && i + 1 < argc) seed = (uint32_t)atoi(argv[++i]);
    else if (!strcmp(argv[i], "--server") && i + 1 < argc) server_cmd = argv[++i];
    else if (!strcmp(argv[i], "--dump-pcm") && i + 1 < argc) dump_pcm = fopen(argv[++i], "wb");
    else if (!strcmp(argv[i], "--expect-events") && i + 1 < argc) expect_events = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--expect-delivered") && i + 1 < argc) expect_delivered = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--gsm-outage") && i + 2 < argc) { outage_start = (uint32_t)atoi(argv[++i]) * 1000u; outage_end = (uint32_t)atoi(argv[++i]) * 1000u; }
    else if (!strcmp(argv[i], "--publish-loss") && i + 1 < argc) ch_publish_loss = (float)atof(argv[++i]);
    else if (!strcmp(argv[i], "--receipt-loss") && i + 1 < argc) ch_receipt_loss = (float)atof(argv[++i]);
    else if (!strcmp(argv[i], "--receipt-latency") && i + 1 < argc) ch_receipt_latency_ms = (uint32_t)atoi(argv[++i]);
    else if (!strcmp(argv[i], "--mqtt-refuse") && i + 2 < argc) { ch_mqtt_refuse_start = (uint32_t)atoi(argv[++i]) * 1000u; ch_mqtt_refuse_end = (uint32_t)atoi(argv[++i]) * 1000u; }
    else if (!strcmp(argv[i], "--lora")) lora_enabled = true;
    else if (!strcmp(argv[i], "--lora-loss") && i + 1 < argc) ch_lora_loss = (float)atof(argv[++i]);
    else if (!strcmp(argv[i], "--lora-gateway-ms") && i + 1 < argc) ch_lora_gateway_ms = (uint32_t)atoi(argv[++i]);
    else if (!strcmp(argv[i], "--degraded-after") && i + 1 < argc) degraded_after = (unsigned)atoi(argv[++i]);
    else if (!strcmp(argv[i], "--gsm-probe-s") && i + 1 < argc) gsm_probe_ms = (uint32_t)atoi(argv[++i]) * 1000u;
    else if (!strcmp(argv[i], "--inject-events") && i + 2 < argc) { inject_count = (unsigned)atoi(argv[++i]); inject_at_ms = (uint32_t)atoi(argv[++i]) * 1000u; }
    else if (!strcmp(argv[i], "--expect-commands") && i + 1 < argc) expect_commands = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--expect-reboots") && i + 1 < argc) expect_reboots = atoi(argv[++i]);
    else { fprintf(stderr, "usage: station_twin --scene drone|quiet|ground [--seconds N] [--seed S] [--server CMD] [--gsm-outage FROM_S TO_S] [--publish-loss P] [--receipt-loss P] [--receipt-latency MS] [--mqtt-refuse FROM_S TO_S] [--lora] [--lora-loss P] [--lora-gateway-ms MS] [--degraded-after N] [--gsm-probe-s S] [--inject-events N AT_S] [--dump-pcm FILE] [--expect-events N] [--expect-delivered N] [--expect-commands N] [--expect-reboots N]\n"); return 2; }
  }
  if (!strcmp(scene_name, "drone")) { segs[nseg++] = (scene_segment_t){SCENE_DRONE_FLYBY, 20000u, 60000u, 185.0f, 1.0f}; if (seconds > 150u) segs[nseg++] = (scene_segment_t){SCENE_DRONE_FLYBY, 100000u, 130000u, 210.0f, 0.8f}; }
  else if (!strcmp(scene_name, "ground")) segs[nseg++] = (scene_segment_t){SCENE_GROUND_VEHICLE, 20000u, 60000u, 0.0f, 1.0f};
  scene_init(&scene, segs, nseg, 0.02f, seed);
  ch_rng ^= seed * 2654435761u;

  if (server_cmd && !link_start(server_cmd)) { fprintf(stderr, "cannot start the server twin\n"); return 3; }
  memset(outbox_mem, 0xff, sizeof(outbox_mem)); memset(journal_mem, 0xff, sizeof(journal_mem));
  zs_audio_ring_init(&ring, ring_storage, RING_FRAMES, 32000u);
  zs_dsp_mcu_init(&dsp_ctx);
  { size_t work; zs_complex_t *scratch = zs_dsp_mcu_borrow_work(&work); assert(work >= ZS_AIR_SCRATCH_COMPLEX); assert(zs_station_pipeline_init(&pipeline, &pipeline_port, scratch, window_pcm)); }
  zs_station_config_defaults(&cfg, 17u, ZS_STATION_CONFIG_REGION_RU868);
  cfg.version = 1u; strcpy(cfg.server_host, "muhoed.twin"); cfg.mqtt_port = 8883u; strcpy(cfg.ca_reference, "dioneya-root");
  strcpy(cfg.tenant, "pilot1"); strcpy(cfg.topic_prefix, "zs/v1"); cfg.preferred_sim = 1u; strcpy(cfg.apn[0], "internet");
  assert(zs_station_config_validate(&cfg) == 0u && zs_station_config_compute_hash(&cfg, cfg.config_hash));
  for (unsigned i = 0u; i < 32u; i++) twin_engineer_key[i] = (uint8_t)(0xa0u + i);
  assert(zs_lora_uplink_init(&lora, &lora_port, &outbox_io, 17u, 1u, twin_engineer_key, 9u, 125000u, sim_now));
  /* remote commands: the repository test key (tools/generate_command_set_vector.py), the twin wall clock and the
     executor; the parameter record starts empty (defaults, the CLI flags above stay in force until a command) */
  (void)zs_command_set_vector_reboot; (void)zs_command_set_vector_params;
  memset(params_mem, 0xff, sizeof(params_mem));
  (void)zs_station_params_load(&params_io, &params);
  app_comms_set_command_key(zs_command_set_vector_public_key);
  app_comms_set_clock(twin_clock);
  app_comms_set_executor(twin_execute, NULL);
  app_comms_bind(&outbox_io, &journal_io, &hooks);
  app_comms_set_config(&cfg, 5u);
  app_comms_request(true);
  zs_mode_init(&modes, NULL, sim_now);
  (void)zs_mode_on_event(&modes, ZS_MODE_EV_BOOT_DONE, sim_now);
  tlog("twin: scene %s, %u s, seed %u, server %s", scene_name, seconds, seed, server_cmd ? "pipe" : "none");

  const uint32_t end = sim_now + seconds * 1000u;
  while (sim_now < end) {
    if (outage_end && sim_now >= outage_start && sim_now < outage_end) { if (gsm_available) { gsm_available = false; tlog("radio: GSM outage begins"); } }
    else if (!gsm_available) { gsm_available = true; tlog("radio: GSM back"); }
    audio_tick();
    inject_tick();
    supervisor_tick();
    modem_physics();
    channel_tick();
    app_comms_step();
    if (lora_enabled) { lora_channel_tick(); lora_step(); }
    link_poll();
    sim_now += TICK_MS;
  }
  {
    uint16_t pending = 0u;
    (void)zs_event_outbox_pending_count(&outbox_io, &pending);
    tlog("twin: end. mode %s, windows %lu (confirmed %lu suspect %lu), events emitted %u, published %lu, receipts %u, outbox pending %u, sessions done %u, QPOWD %u",
         zs_mode_name(modes.mode), (unsigned long)pipeline.windows, (unsigned long)pipeline.confirmed_windows, (unsigned long)pipeline.suspect_windows,
         events_emitted_total, (unsigned long)app_comms_state()->events_published, link_receipts, pending, sessions_done, qpowd_count);
    tlog("twin: outbox retries %u, channel: publishes lost %u, receipts lost %u, gsm %s (fail streak %u)", outbox_retries, ch_publishes_lost, ch_receipts_lost, gsm_degraded ? "DEGRADED" : "ok", comms_fail_streak);
    if (lora_enabled) tlog("twin: lora frames %u acks %u timeouts %u budget waits %u airtime %lu ms", lora.frames_sent, lora.acks, lora.ack_timeouts, lora.budget_waits, (unsigned long)lora.airtime_ms_total);
    tlog("twin: commands executed %u rejected %u, reboots scheduled %u done %u, params v%lu", cmd_executed, cmd_rejected, cmd_reboots_scheduled, twin_reboots, (unsigned long)params.version);
  }
  {
    uint16_t pending = 0u;
    (void)zs_event_outbox_pending_count(&outbox_io, &pending);
    if (expect_events >= 0 && (int)events_emitted_total < expect_events) { tlog("twin: FAIL expected >= %d events, got %u", expect_events, events_emitted_total); return 1; }
    if (expect_delivered >= 0 && ((int)(link_receipts + lora.acks) < expect_delivered || pending != 0u)) { tlog("twin: FAIL expected %d delivered events with an empty outbox (mqtt receipts %u, lora acks %u, pending %u)", expect_delivered, link_receipts, lora.acks, pending); return 1; }
    if (expect_commands >= 0 && (int)cmd_executed != expect_commands) { tlog("twin: FAIL expected %d executed commands, got %u", expect_commands, cmd_executed); return 1; }
    if (expect_reboots >= 0 && ((int)twin_reboots != expect_reboots || (int)cmd_reboots_scheduled != expect_reboots)) { tlog("twin: FAIL expected %d reboots (scheduled %u, done %u)", expect_reboots, cmd_reboots_scheduled, twin_reboots); return 1; }
  }
  if (link_out >= 0) { link_report(); fcntl(link_in, F_SETFL, fcntl(link_in, F_GETFL) & ~O_NONBLOCK); close(link_out); for (;;) { ssize_t r = read(link_in, link_buf + link_len, sizeof(link_buf) - 1u - link_len); if (r <= 0) break; link_len += (size_t)r; } link_buf[link_len] = 0; { char *p = strstr(link_buf, "REPORT "); if (p) printf("SERVER %s", p + 7); } waitpid(server_pid, NULL, 0); }
  return 0;
}

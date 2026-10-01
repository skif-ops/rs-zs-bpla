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
 * Firmware update (ICD addendum F): two simulated flash banks with a boot record page each; CMD_UPDATE_FIRMWARE is
 * downloaded by the real app_comms driver (fwreq/fw through the BG95 responder and the server twin), installed by a
 * simulated bank swap and reset, run on trial through the real boot guard (zs_fw_boot) and confirmed by a session;
 * --ota-hang-version makes that image hang at start so the early IWDG resets it until the guard swaps back.
 *
 * Network configuration (ICD addendum G): the BG95 responder opens MQTT only to muhoed.twin:8883 and muhoed2.twin:443
 * (the same server twin behind two names), any other host fails its DNS lookup; CMD_SET_NETWORK_CONFIG goes through
 * the real app_comms trial and the RAM configuration record stands in for the NOR one.
 *
 * Bearing stream (ICD addendum H): the source is rendered as a plane wave on the 3+1 array; after an event of a new
 * track the tracking window keeps the detector running in S3 and the bearings go out in batches on the bearing topic.
 *
 * Field (--world, docs/STATION_TWIN_FIELD_2026-10-01.md): one process per station of a shared field, the same target
 * over all of them; the station finds its position by a simulated GNSS receiver (GGA) or its installation record
 * (zs_station_position, as tasks.c) and the publishes go to --log-uplink for server/tools/twin_field.py.
 *
 * Nothing on the target changes: the twin reuses the modules and mirrors the task wiring of tasks.c.
 *   station_twin --scene drone|quiet|ground --seconds N --server "python3 -m twin.twin_server" [--seed S]
 *   station_twin --world X,Y,Z,VX,VY,VZ --station-id N --pos E,N [--installed] --seconds N --server ... --log-uplink F
 *   (--world up to three times: several targets at once, each with its own synthetic source or --world-sound)
 */
#include "app_comms.h"
#include "array_render.h"
#include "bsp_gpio.h"
#include "bsp_uart.h"
#include "scene.h"
#include "task.h"
#include "zs_audio.h"
#include "zs_audio_recorder.h"
#include "zs_command_journal.h"
#include "zs_command_keys.h"
#include "zs_command_set_vector.h"
#include "zs_dsp_mcu.h"
#include "zs_fw_boot.h"
#include "zs_fw_update.h"
#include "zs_fw_update_vector.h"
#include "zs_model_store.h"
#include "zs_event_outbox.h"
#include "zs_lora_uplink.h"
#include "zs_power_modes.h"
#include "zs_prehistory.h"
#include "zs_selftest.h"
#include "zs_station_config.h"
#include "zs_station_params.h"
#include "zs_station_pipeline.h"
#include "zs_station_position.h"
#include "zs_gnss.h"
#include "zs_track_window.h"

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
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
static FILE *uplink_log;                         /* --log-uplink: every publish that reached the broker, with wall time */
static uint64_t twin_wall_us(void);
static void link_send(const char *topic, const uint8_t *payload, size_t n) {
  if (uplink_log) { fprintf(uplink_log, "%llu %s ", (unsigned long long)twin_wall_us(), topic); for (size_t i = 0u; i < n; i++) fprintf(uplink_log, "%02x", payload[i]); fputc('\n', uplink_log); }
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
static unsigned endpoint1_opens, endpoint2_opens, endpoint_failures;   /* QMTOPEN to muhoed.twin:8883 / muhoed2.twin:443 / elsewhere */

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
typedef struct { uint32_t at_ms; bool used; char topic[128]; uint8_t payload[2304]; size_t n; } delayed_msg_t;
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
  if (strncmp(c, "AT+QMTOPEN=", 11u) == 0) {
    /* the brokers this twin can reach (the Muhoed twin behind both names); any other host fails its DNS lookup (4) */
    char host[80] = ""; unsigned port = 0u;
    const bool known = sscanf(c, "AT+QMTOPEN=%*u,\"%79[^\"]\",%u", host, &port) == 2 &&
                       ((strcmp(host, "muhoed.twin") == 0 && port == 8883u) || (strcmp(host, "muhoed2.twin") == 0 && port == 443u));
    reply("OK");
    if (!gsm_available || mqtt_refused()) { reply("+QMTOPEN: 0,-1"); return; }
    if (!known) { endpoint_failures++; tlog("modem: QMTOPEN %s:%u -> DNS failure", host, port); reply("+QMTOPEN: 0,4"); return; }
    if (strcmp(host, "muhoed2.twin") == 0) endpoint2_opens++; else endpoint1_opens++;
    reply("+QMTOPEN: 0,0");
    return;
  }
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
static int16_t window_pcm[ZS_PIPELINE_WINDOW_SAMPLES] __attribute__((aligned(4)));   /* the pipeline lends it as floats */
static zs_dsp_ctx_t dsp_ctx;
static zs_station_pipeline_t pipeline;
static zs_mode_scheduler_t modes;
static uint32_t mode_bits;
static unsigned events_emitted_total, sessions_done, quiet_windows;
static uint32_t seen_events;
static scene_t scene;
static array_render_t array_render;       /* the source as a plane wave on the 3+1 array (bearings) */
static unsigned bearings_total, bearings_streamed;
static float bearing_err_sum, bearing_err_max;
/* tracking window (mirrors tasks.c) */
static zs_track_window_t track;
static bool track_open, track_close_request, track_s3_extension, gsm_degraded;
static uint32_t track_max_ms = (uint32_t)ZS_PARAM_TRACK_MAX_S_DEFAULT * 1000u;   /* track_max_s (addendum D id 7) */
static float scene_level;                 /* recent RMS of the scene, for the AAD wake emulation */
static FILE *dump_pcm;                    /* --dump-pcm: the mono scene as PCM16LE 32 kHz (for tools/presence_eval) */

static void mode_event(zs_mode_event_t ev) { mode_bits |= 1u << ev; }

/* ---- field (--world): one target flies a straight line in a shared ENU frame around 55 N 37 E, 150 m MSL; every
   twin process is one station of the same field (--station-id, --pos).  The station hears the target where it was
   range / c earlier: direction of that point, level by spherical spreading (full level at --world-ref-m and closer)
   and air absorption (--world-absorption-db-km).  The sound is the synthetic electric multirotor of the drone scene,
   or a recording (--world-sound FILE.wav: PCM16, any rate, the first channel, looped; read at the emission time, so it
   carries the Doppler shift of the pass).  The station knows where it stands from a simulated GNSS receiver (a GGA
   of its position every second, as the target's GNSS task parses them) or, with --installed, from the installation
   record of a commissioned station; the receiver's fixes then check that record. ---- */
#define FIELD_LAT0 55.0
#define FIELD_LON0 37.0
#define FIELD_ALT0 150.0
#define FIELD_C 343.0
static bool world_mode, world_installed;
static unsigned twin_station_id = 17u;
static double st_enu[3];                        /* this station, m east/north/up of the field origin */
static double tg_p0[3], tg_v[3];                /* the target at scene time 0 and its velocity */
static float tg_f0 = 185.0f;                    /* blade-pass fundamental of the synthetic source */
/* more targets at once (--world repeated): each its own synthetic source (own f0) or recording (the k-th --world-sound
   for the k-th target; f0 then names its fundamental for the statistics), own plane wave on the array; the
   microphones hear the sum.  Target 0 keeps the globals above, targets 1.. live here. */
#define WORLD_MAX_TARGETS 3u
static unsigned world_targets;
static double xt_p0[WORLD_MAX_TARGETS][3], xt_v[WORLD_MAX_TARGETS][3];
static float xt_f0[WORLD_MAX_TARGETS], xt_gain[WORLD_MAX_TARGETS];
static scene_segment_t xt_seg[WORLD_MAX_TARGETS];
static scene_t xt_scene[WORLD_MAX_TARGETS];
static array_render_t xt_render[WORLD_MAX_TARGETS];
static double xt_te[WORLD_MAX_TARGETS], xt_te_rate[WORLD_MAX_TARGETS];   /* emission time of the sound arriving now */
static double world_ref_m = 800.0;              /* full source level at this range and closer */
static double world_absorption_db_km = 2.0;     /* air absorption around 500 Hz (ISO 9613-1, 10..20 C, 70 % RH) */
static float world_level = 0.5f;                /* source level at --world-ref-m (the drone scene's scale) */
static float world_gain = 1.0f;
static double world_te, world_te_rate = 1.0;    /* emission time of the sound arriving now, d(te)/d(ta) */
typedef struct { float *x; size_t n; double rate; } world_wav_t;
static world_wav_t world_wav[WORLD_MAX_TARGETS]; /* --world-sound, k-th for target k: the recording's first channel, scaled */
static zs_station_position_t station_pos;       /* as tasks.c: GNSS fixes and the installation record */
static zs_gnss_nmea_t gnss_nmea;
static uint32_t gnss_next_ms;

static void field_geodetic(const double enu[3], double *lat, double *lon, double *alt) {
  *lat = FIELD_LAT0 + enu[1] / 111320.0;
  *lon = FIELD_LON0 + enu[0] / (111320.0 * cos(FIELD_LAT0 * M_PI / 180.0));
  *alt = FIELD_ALT0 + enu[2];
}
/* the receiver: a GGA of the station's position once a second (8 satellites, HDOP 0.9) */
static void gnss_tick(void) {
  char body[112], line[128];
  double lat, lon, alt;
  unsigned sum = 0u;
  uint32_t t;
  if ((int32_t)(sim_now - gnss_next_ms) < 0) return;
  gnss_next_ms = sim_now + 1000u;
  field_geodetic(st_enu, &lat, &lon, &alt);
  t = (uint32_t)(twin_wall_us() / 1000000u % 86400u);
  snprintf(body, sizeof(body), "GNGGA,%02u%02u%02u.00,%02d%07.4f,N,%03d%07.4f,E,1,08,0.90,%.1f,M,14.0,M,,", t / 3600u, t / 60u % 60u, t % 60u,
           (int)lat, (lat - floor(lat)) * 60.0, (int)lon, (lon - floor(lon)) * 60.0, alt);
  for (const char *c = body; *c; c++) sum ^= (unsigned char)*c;
  snprintf(line, sizeof(line), "$%s*%02X", body, sum & 0xffu);
  if (zs_gnss_parse_line(&gnss_nmea, line)) (void)zs_station_position_on_gnss(&station_pos, &gnss_nmea, sim_now);
}
/* --installed: the record a BLE commissioning stores (the surveyed position, the default trust thresholds) */
static void field_install(void) {
  zs_position_trust_config_t c;
  double lat, lon, alt;
  memset(&c, 0, sizeof(c));
  field_geodetic(st_enu, &lat, &lon, &alt);
  c.configured = true; c.locked = true;
  c.installation.lat_e7 = (int32_t)llround(lat * 1e7); c.installation.lon_e7 = (int32_t)llround(lon * 1e7);
  c.installation.alt_dm = (int32_t)llround(alt * 10.0); c.installation.pos_accuracy_m = 1u; c.installation.altitude_source = 1u;
  c.warning_distance_m = 25u; c.suspect_distance_m = 75u; c.gross_jump_distance_m = 250u;
  c.warning_consecutive_fixes = 3u; c.suspect_consecutive_fixes = 10u;
  zs_station_position_set_installation(&station_pos, &c);
}
/* direction and gain of the sound arriving now (scene time ta): emitted at te = ta - range(te) / c */
static void target_step(const double p0[3], const double vel[3], double ta, float *az, float *el, float *gain, double *te_out, double *te_rate) {
  double te = ta, v[3], r = 0.0, radial = 0.0;
  for (unsigned it = 0u; it < 8u; it++) {
    for (unsigned k = 0u; k < 3u; k++) v[k] = p0[k] + vel[k] * te - st_enu[k];
    r = sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    te = ta - r / FIELD_C;
  }
  for (unsigned k = 0u; k < 3u; k++) radial += r > 0.0 ? vel[k] * v[k] / r : 0.0;
  *az = (float)fmod(atan2(v[0], v[1]) * 180.0 / M_PI + 360.0, 360.0);
  *el = (float)(atan2(v[2], hypot(v[0], v[1])) * 180.0 / M_PI);
  *gain = (float)(r <= world_ref_m ? 1.0 : world_ref_m / r * pow(10.0, -world_absorption_db_km * (r - world_ref_m) / 1000.0 / 20.0));
  *te_out = te;
  *te_rate = 1.0 / (1.0 + radial / FIELD_C);   /* receding: the recording plays slower (lower pitch) */
}
static void world_step(double ta, float *az, float *el) { target_step(tg_p0, tg_v, ta, az, el, &world_gain, &world_te, &world_te_rate); }
/* the target a bearing follows: the one whose fundamental is nearest (log ratio) when the bearing has one (several
   sources, zs_comb_bearing), else the nearest true direction; *err = the azimuth error against it */
static unsigned truth_target(float az_deg, float f0_hz, float *err) {
  unsigned best = 0u;
  float e = fabsf(fmodf(az_deg - array_render.azimuth_deg + 540.0f, 360.0f) - 180.0f);
  float d = f0_hz > 0.0f ? fabsf(logf(f0_hz / tg_f0)) : 0.0f;
  for (unsigned t = 1u; t < world_targets; t++) {
    const float f = fabsf(fmodf(az_deg - xt_render[t].azimuth_deg + 540.0f, 360.0f) - 180.0f);
    const float dt = f0_hz > 0.0f ? fabsf(logf(f0_hz / xt_f0[t])) : 0.0f;
    if (f0_hz > 0.0f ? dt < d : f < e) { best = t; e = f; d = dt; }
  }
  *err = e;
  return best;
}
static unsigned bearings_of_target[WORLD_MAX_TARGETS];
static float bearing_err_of_target[WORLD_MAX_TARGETS];
/* the recording at emission time te (seconds, looped), linear interpolation */
static float world_wav_at(const world_wav_t *w, double te) {
  double pos = fmod(te * w->rate, (double)w->n);
  size_t i;
  float f;
  if (pos < 0.0) pos += (double)w->n;
  i = (size_t)pos; f = (float)(pos - (double)i);
  return w->x[i] * (1.0f - f) + w->x[(i + 1u) % w->n] * f;
}
static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
/* WAV PCM16: the first channel, scaled so its RMS is that of the synthetic source at the same level */
static bool world_wav_load(const char *path, world_wav_t *w) {
  FILE *f = fopen(path, "rb");
  uint8_t h[12], ch[8];
  unsigned channels = 0u, bits = 0u, format = 0u;
  double sum = 0.0;
  if (!f || fread(h, 1u, 12u, f) != 12u || memcmp(h, "RIFF", 4u) || memcmp(h + 8, "WAVE", 4u)) { if (f) fclose(f); return false; }
  while (fread(ch, 1u, 8u, f) == 8u) {
    const uint32_t n = le32(ch + 4);
    if (!memcmp(ch, "fmt ", 4u) && n >= 16u) {
      uint8_t fmt[16];
      if (fread(fmt, 1u, 16u, f) != 16u) break;
      format = fmt[0] | fmt[1] << 8; channels = fmt[2] | fmt[3] << 8; w->rate = le32(fmt + 4); bits = fmt[14] | fmt[15] << 8;
      if (fseek(f, (long)(n - 16u + (n & 1u)), SEEK_CUR) != 0) break;
    } else if (!memcmp(ch, "data", 4u) && format == 1u && bits == 16u && channels > 0u && w->rate > 0.0) {
      const size_t frames = n / (2u * channels);
      int16_t *pcm = malloc(n);
      if (!pcm || frames < 2u || fread(pcm, 1u, n, f) != n) { free(pcm); break; }
      w->x = malloc(frames * sizeof(float));
      if (!w->x) { free(pcm); break; }
      for (size_t i = 0u; i < frames; i++) { w->x[i] = pcm[i * channels] / 32768.0f; sum += (double)w->x[i] * w->x[i]; }
      free(pcm);
      w->n = frames;
      fclose(f);
      if (sum <= 0.0) return false;
      {
        const float scale = (float)(0.243 * world_level / sqrt(sum / (double)frames));   /* the drone scene: RMS 0.243 x level */
        for (size_t i = 0u; i < frames; i++) w->x[i] *= scale;
      }
      return true;
    } else if (fseek(f, (long)(n + (n & 1u)), SEEK_CUR) != 0) break;
  }
  fclose(f);
  return false;
}
static bool parse3(const char *s, double out[3], unsigned need) {
  return sscanf(s, "%lf,%lf,%lf", &out[0], &out[1], &out[2]) >= (int)need;
}

/* ---- self-test (mirrors the supervisor of tasks.c): --selftest-fail-until S makes the microphone test fail until
   S seconds; the station boots with BOOT_FAILED, reports in a session, keeps the detector off and repeats the test
   after every session ---- */
static uint32_t selftest_fail_until_ms;
static uint16_t selftest_failed_mask;
static unsigned selftest_runs, selftest_recoveries;
static bool twin_selftest(void) {
  selftest_runs++;
  selftest_failed_mask = sim_now < selftest_fail_until_ms ? (uint16_t)(1u << ZS_ST_ID_MIC_CAPTURE) : 0u;
  tlog("selftest: %s (failed mask 0x%04x)", selftest_failed_mask ? "required test FAILED" : "PASS", (unsigned)selftest_failed_mask);
  return selftest_failed_mask == 0u;
}

/* ---- audio prehistory (mirrors app_audio_rec + the capture policy of tasks.c): RAM ring of 128 one-second records
   (the station has ~2500; the twin needs more than one event's before + after) ---- */
#define PRE_RECORDS 128u
static uint8_t pre_flash[PRE_RECORDS * 16384u];
static int pre_read(void *c, uint32_t a, uint8_t *d, size_t n) { (void)c; if ((uint64_t)a + n > sizeof(pre_flash)) return -1; memcpy(d, pre_flash + a, n); return 0; }
static int pre_write(void *c, uint32_t a, const uint8_t *d, size_t n) { (void)c; if ((uint64_t)a + n > sizeof(pre_flash)) return -1; for (size_t i = 0u; i < n; i++) { if ((pre_flash[a + i] & d[i]) != d[i]) return -2; pre_flash[a + i] &= d[i]; } return 0; }
static int pre_erase(void *c, uint32_t a, size_t n) { (void)c; if (a % 4096u || n % 4096u || (uint64_t)a + n > sizeof(pre_flash)) return -1; memset(pre_flash + a, 0xff, n); return 0; }
static const zs_archive_storage_t pre_storage = {NULL, sizeof(pre_flash), 4096u, pre_read, pre_write, pre_erase};
static zs_prehistory_t prehistory;
static zs_audio_recorder_t recorder;
static bool capture_on, capture_was_stopped;
static uint32_t capture_stopped_ms;
static int64_t capture_gaps_us;           /* zs_time_on_capture_gap on the target: the time mapping keeps up with pauses */
static uint32_t post_capture_until_ms;
static int64_t first_event_time_us;
static void post_capture_open(void) { post_capture_until_ms = sim_now + 30000u; }
static bool capture_wanted(zs_mode_t mode) { return zs_mode_power_for(mode).mdf_clock || (mode != ZS_MODE_SHUTDOWN && ((int32_t)(sim_now - post_capture_until_ms) < 0 || track_open)); }
static void capture_set(bool on) {
  if (on == capture_on) return;
  capture_on = on;
  if (on && capture_was_stopped) capture_gaps_us += (int64_t)(sim_now - capture_stopped_ms) * 1000;
  if (!on) { capture_stopped_ms = sim_now; capture_was_stopped = true; }
  if (on) zs_audio_recorder_start(&recorder, ring.total_frames); else zs_audio_recorder_stop(&recorder);
}
/* events of this run for CMD_REQUEST_AUDIO (mirrors app_audio_rec's table; the twin's clock is always trusted) */
typedef struct { uint64_t event_id; int64_t time_us; } twin_event_t;
static twin_event_t twin_events[16]; static unsigned twin_events_next;
static bool forget_events;   /* --forget-events: the station lost its table (as after a reboot); requests rely on the server's time */
static const zs_prehistory_t *src_ring(void) { return &prehistory; }
static void src_range(uint64_t *oldest, uint64_t *next) { *next = prehistory.next_sequence; *oldest = prehistory.next_sequence - prehistory.available_records; }
static bool src_event_time(uint64_t id, int64_t *t, bool *trusted) { for (unsigned i = 0u; i < 16u; i++) if (id && twin_events[i].event_id == id) { *t = twin_events[i].time_us; *trusted = true; return true; } return false; }
static int64_t pl_sample_time(void *ctx, uint64_t sample);
static int64_t src_now_us(void) { return pl_sample_time(NULL, ring.total_frames); }
static bool src_recording(void) { return capture_on; }
static const app_comms_audio_source_t audio_source = {src_ring, src_range, src_event_time, src_now_us, src_recording};
static bool pl_extract(void *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]) { (void)ctx; return zs_dsp_mcu_extract_1s(&dsp_ctx, pcm, n, out); }
static int64_t pl_sample_time(void *ctx, uint64_t sample) { (void)ctx; return (int64_t)1800000000000000LL + (int64_t)sample * 1000000LL / 32000LL + capture_gaps_us; }
static bool pl_emit(void *ctx, const zs_detection_t *d) {
  static uint8_t ws[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES + 64u];
  zs_detection_t e = *d; (void)ctx;
  e.route.transport = ZS_ROUTE_LTE; e.power.battery_pct = 80u; e.power.battery_mv = 13200u;
  e.gnss.time_trust = ZS_TIME_TRUST_GNSS_TRUSTED; e.gnss.pps_ok = true; e.gnss.expected_time_error_us = 100u;   /* as tasks.c: the twin's clock is trusted */
  (void)zs_station_position_fill(&station_pos, sim_now, &e.station, &e.gnss);   /* as tasks.c: installation or GNSS fix */
  const bool ok = zs_event_outbox_enqueue_detection(&outbox_io, &e, 2u, ws, sizeof(ws)) == ZS_EVENT_OUTBOX_OK;
  events_emitted_total += ok;
  if (ok) remember_summary(d->event_id, d->classification.class_id, d->classification.confidence_u8, pipeline.presence.level, (uint16_t)pipeline.last_gate.f0_hz);
  if (ok && first_event_time_us == 0) first_event_time_us = d->event_time_us;
  if (!forget_events) { twin_events[twin_events_next] = (twin_event_t){d->event_id, d->event_time_us}; twin_events_next = (twin_events_next + 1u) % 16u; }
  tlog("station: event %llu emitted (level %u conf %u class %u f0 %u) -> outbox %s; doa %s az %.1f el %.1f sigma %.1f (truth az %.1f el %.1f)",
       (unsigned long long)d->event_id, pipeline.presence.level, pipeline.presence.confidence_u8, d->classification.class_id,
       (unsigned)pipeline.last_gate.f0_hz, ok ? "ok" : "REFUSED",
       d->doa.valid ? "valid" : "none", d->doa.azimuth_cdeg / 100.0, d->doa.elevation_cdeg / 100.0, d->doa.sigma_cdeg / 100.0,
       array_render.azimuth_deg, array_render.elevation_deg);
  return ok;
}
/* every bearing of a CONFIRMED window, against the rendered truth */
static void pl_bearing(void *ctx, const zs_bearing_t *b, uint64_t end_sample, uint64_t track_event_id) {
  float e;
  const unsigned t = truth_target(b->azimuth_deg, b->f0_hz, &e);
  zs_bearing_record_t r;
  (void)ctx;
  bearings_total++;
  bearings_of_target[t]++;
  bearing_err_of_target[t] += e;
  bearing_err_sum += e;
  if (e > bearing_err_max) bearing_err_max = e;
  /* the open window's bearings go to the live stream under the window's track (tasks.c: pl_bearing) */
  (void)track_event_id;
  if (track_open && zs_bearing_record_from(&r, track.track_event_id, pl_sample_time(NULL, end_sample), ZS_TIME_TRUST_GNSS_TRUSTED, b)) {
    app_comms_bearing_push(&r);
    bearings_streamed++;
  }
}
static zs_station_pipeline_port_t pipeline_port = {NULL, pl_extract, pl_sample_time, pl_emit, 17u, 5u, 0u, 0u, NULL, pl_bearing};

/* --inject-events N AT_S: N synthetic detections straight into the outbox (burst scenarios without the classifier) */
static unsigned inject_count; static uint32_t inject_at_ms; static bool injected;
static void inject_tick(void) {
  if (injected || inject_count == 0u || sim_now < inject_at_ms) return;
  injected = true;
  for (unsigned i = 0u; i < inject_count; i++) {
    static uint8_t ws[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES + 64u];
    zs_detection_t d; memset(&d, 0, sizeof(d));
    d.schema_ver = 4u; d.station_id = twin_station_id; d.boot_id = 5u; d.seq_no = 1000u + i; d.event_id = ((uint64_t)5u << 32) | (1000u + i);
    d.event_time_us = pl_sample_time(NULL, ring.total_frames) + (int64_t)i * 1000000LL; d.classification.class_id = 3u; d.classification.confidence_u8 = 200u;
    d.route.transport = ZS_ROUTE_LTE; d.power.battery_mv = 13200u; d.power.battery_pct = 80u;
    if (zs_event_outbox_enqueue_detection(&outbox_io, &d, 2u, ws, sizeof(ws)) == ZS_EVENT_OUTBOX_OK) { events_emitted_total++; remember_summary(d.event_id, 3u, 200u, 3u, 190u); }
  }
  tlog("twin: injected %u events into the outbox", inject_count);
  mode_event(ZS_MODE_EV_OUTBOX_PENDING);
}

/* the tracking window after every analysed window (tasks.c: track_step) */
static void track_step(bool new_event) {
  zs_track_end_t end = ZS_TRACK_END_NONE;
  if (new_event && zs_track_window_on_event(&track, pipeline.track_event_id, !gsm_degraded, sim_now)) {
    track_open = true; track_s3_extension = true; track_close_request = false;
    app_comms_set_tracking(true);
    tlog("track: window open for event %llu (max %lu s)", (unsigned long long)track.track_event_id, (unsigned long)(track_max_ms / 1000u));
    return;
  }
  if (!track_open) return;
  if (track_close_request) { zs_track_window_end(&track); end = ZS_TRACK_END_MODE; }
  else end = zs_track_window_on_window(&track, pipeline.presence.level == ZS_PRESENCE_CONFIRMED, sim_now);
  if (end == ZS_TRACK_END_NONE) return;
  track_open = false; track_close_request = false;
  app_comms_set_tracking(false);
  tlog("track: window closed (%s) after %lu windows", zs_track_end_name(end), (unsigned long)track.windows);
}

static void dsp_mode_events(void) {
  const uint8_t level = pipeline.presence.level;
  track_step(pipeline.events_emitted != seen_events && (modes.mode == ZS_MODE_S1_LISTEN || modes.mode == ZS_MODE_S2_DSP));
  if (modes.mode == ZS_MODE_S1_LISTEN) {
    quiet_windows = 0u;
    if (level >= ZS_PRESENCE_SUSPECT) mode_event(ZS_MODE_EV_GATE_POSITIVE);
    if (pipeline.events_emitted != seen_events) { seen_events = pipeline.events_emitted; post_capture_open(); mode_event(ZS_MODE_EV_OUTBOX_PENDING); }
    return;
  }
  if (modes.mode != ZS_MODE_S2_DSP) { quiet_windows = 0u; seen_events = pipeline.events_emitted; return; }
  if (pipeline.events_emitted != seen_events) { seen_events = pipeline.events_emitted; quiet_windows = 0u; post_capture_open(); mode_event(ZS_MODE_EV_DSP_DONE_EVENT); return; }
  if (level == ZS_PRESENCE_NONE) { if (++quiet_windows >= 6u) { quiet_windows = 0u; mode_event(ZS_MODE_EV_DSP_DONE_NOTHING); } }
  else quiet_windows = 0u;
}

/* station secrets (the NOR record of tasks.c): the command key and, during a rotation, the next one (addendum E) */
static uint8_t secrets_mem[2][ZS_STATION_SECRETS_SLOT_BYTES];
static bool sm_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > ZS_STATION_SECRETS_SLOT_BYTES) return false; memcpy(d, &secrets_mem[s][o], n); return true; }
static bool sm_erase(void *c, uint8_t s) { (void)c; if (s > 1u) return false; memset(secrets_mem[s], 0xff, ZS_STATION_SECRETS_SLOT_BYTES); return true; }
static bool sm_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > ZS_STATION_SECRETS_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((secrets_mem[s][o + i] & d[i]) != d[i]) return false; secrets_mem[s][o + i] = d[i]; } return true; }
static const zs_station_secrets_io_t secrets_io = {NULL, sm_read, sm_erase, sm_write};
static zs_station_secrets_t secrets;        /* the RAM copy tasks.c keeps (heartbeat key ids) */
static unsigned key_rotations, key_promotions;
static void command_keys_reload(const char *what) {
  zs_command_trust_key_t keys[2];
  if (zs_station_secrets_load(&secrets_io, &secrets, NULL) != ZS_STATION_SECRETS_OK) return;
  app_comms_set_command_keys(keys, zs_command_keys_trust_set(&secrets, keys));
  if (what) tlog("command key: %s (secrets v%lu)", what, (unsigned long)secrets.version);
}
static zs_station_params_t params;        /* the runtime parameter set in force (remote commands below) */
static uint32_t fw_running_version(void);
static uint8_t fw_state_now(void);
static uint32_t fw_bank_version(const uint8_t *bank);
static uint8_t *fw_other(void);
static void fw_session_done(void);
static bool fill_heartbeat(void *ctx, zs_heartbeat_t *hb) {
  uint16_t pending = 0u; (void)ctx;
  hb->schema_ver = 2u; hb->time_us = pl_sample_time(NULL, ring.total_frames);
  hb->power.battery_pct = 80u; hb->power.battery_mv = 13200u; hb->route.transport = ZS_ROUTE_LTE;
  strcpy(hb->firmware_ver, "twin"); (void)zs_model_active_describe(hb->model_ver, sizeof(hb->model_ver)); strcpy(hb->hardware_rev, "Rev.A"); hb->self_test_ok = selftest_failed_mask == 0u;
  (void)zs_station_position_fill(&station_pos, sim_now, &hb->station, &hb->gnss);
  hb->detector_present = true; hb->detector.boot_id = pipeline_port.boot_id; hb->detector.uptime_s = sim_now / 1000u;
  hb->detector.windows = pipeline.windows; hb->detector.windows_dropped = pipeline.windows_dropped;
  hb->detector.confirmed_windows = pipeline.confirmed_windows; hb->detector.suspect_windows = pipeline.suspect_windows;
  hb->detector.events_emitted = pipeline.events_emitted; hb->detector.presence_level = pipeline.presence.level;
  if (zs_event_outbox_pending_count(&outbox_io, &pending) == ZS_EVENT_OUTBOX_OK) hb->detector.outbox_pending = pending;
  hb->detector.params_version = params.version;
  hb->detector.selftest_failed = selftest_failed_mask;
  hb->detector.command_key_id = secrets.command_key_set ? zs_command_key_id_u64(secrets.command_public_key) : 0u;
  hb->detector.command_next_key_id = secrets.command_next_key_set ? zs_command_key_id_u64(secrets.command_next_key) : 0u;
  hb->detector.fw_version = fw_running_version();                    /* addendum F: keys 18..20 */
  hb->detector.fw_state = fw_state_now();
  hb->detector.fw_other_version = fw_bank_version(fw_other());
  app_comms_net_heartbeat(&hb->detector);                            /* addendum G: keys 21..23 */
  return true;
}
static uint32_t outbox_retry_at_ms, outbox_retry_backoff_ms = 300000u, outbox_retries;
static void session_done(void *ctx) { (void)ctx; sessions_done++; outbox_retry_backoff_ms = 300000u; outbox_retry_at_ms = 0u; mode_event(ZS_MODE_EV_COMMS_DONE); tlog("comms: session done -> COMMS_DONE"); fw_session_done(); }
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
static unsigned comms_fail_streak, degraded_after = 3u;
static uint32_t comms_max_base_ms = 180000u;               /* + 300 s while an audio upload runs (mirrors tasks.c) */
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
  if (done) { comms_fail_streak = 0u; if (gsm_degraded) { gsm_degraded = false; comms_max_base_ms = 180000u; tlog("comms: link healthy again, S3 watchdog 180 s"); } return; }
  comms_fail_streak++;
  if (!gsm_degraded && comms_fail_streak >= degraded_after) { gsm_degraded = true; comms_max_base_ms = 60000u; tlog("comms: DEGRADED after %u failed sessions -> S3 watchdog 60 s, route hint LoRa", comms_fail_streak); }
}

static void gsm_probe_tick(void) {
  if (!gsm_degraded || modes.mode == ZS_MODE_S3_COMMS || modes.mode == ZS_MODE_S4_SERVICE) return;
  if ((uint32_t)(sim_now - last_s3_exit_ms) < gsm_probe_ms) return;
  tlog("comms: GSM probe (%lu s since the last session)", (unsigned long)((sim_now - last_s3_exit_ms) / 1000u));
  last_s3_exit_ms = sim_now;
  mode_event(ZS_MODE_EV_OUTBOX_PENDING);
}

/* ---- station configuration record (the NOR record the ble task loads in tasks.c): a remote network configuration
   that proved itself is committed here (addendum G) ---- */
static uint8_t cfg_mem[2][ZS_STATION_CONFIG_SLOT_BYTES];
static bool cf_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > ZS_STATION_CONFIG_SLOT_BYTES) return false; memcpy(d, &cfg_mem[s][o], n); return true; }
static bool cf_erase(void *c, uint8_t s) { (void)c; if (s > 1u) return false; memset(cfg_mem[s], 0xff, ZS_STATION_CONFIG_SLOT_BYTES); return true; }
static bool cf_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > ZS_STATION_CONFIG_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((cfg_mem[s][o + i] & d[i]) != d[i]) return false; cfg_mem[s][o + i] = d[i]; } return true; }
static const zs_station_config_io_t cfg_io = {NULL, cf_read, cf_erase, cf_write};
static void net_committed(const zs_station_config_t *cfg) { tlog("twin: configuration v%lu stored (%s:%u)", (unsigned long)cfg->version, cfg->server_host, cfg->mqtt_port); }

/* ---- remote commands: executor mirroring app_commands.c over zs_station_params (RAM record = the NOR one) ---- */
static uint8_t params_mem[2][64];
static bool pm_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > 64u) return false; memcpy(d, &params_mem[s][o], n); return true; }
static bool pm_erase(void *c, uint8_t s) { (void)c; if (s > 1u) return false; memset(params_mem[s], 0xff, 64u); return true; }
static bool pm_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > 64u) return false; for (size_t i = 0u; i < n; i++) { if ((params_mem[s][o + i] & d[i]) != d[i]) return false; params_mem[s][o + i] = d[i]; } return true; }
static const zs_station_params_io_t params_io = {NULL, pm_read, pm_erase, pm_write};
static unsigned cmd_executed, cmd_rejected, cmd_reboots_scheduled, twin_reboots;
static bool reboot_pending; static uint32_t reboot_at_ms;
static void params_apply(const zs_station_params_t *p) {
  modes.policy.heartbeat_period_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_HEARTBEAT_PERIOD_S) * 1000u;
  modes.policy.listen_dwell_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_LISTEN_DWELL_S) * 1000u;
  pipeline_port.channel = (uint8_t)zs_station_params_get(p, ZS_PARAM_MIC_CHANNEL);
  if (recorder.channel != pipeline_port.channel) { const bool on = capture_on; capture_set(false); recorder.channel = pipeline_port.channel; capture_set(on); }
  pipeline_port.update_period_windows = (uint8_t)zs_station_params_get(p, ZS_PARAM_EVENT_UPDATE_WINDOWS);
  degraded_after = (unsigned)zs_station_params_get(p, ZS_PARAM_COMMS_DEGRADED_AFTER);
  gsm_probe_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_GSM_PROBE_S) * 1000u;
  track_max_ms = (uint32_t)zs_station_params_get(p, ZS_PARAM_TRACK_MAX_S) * 1000u;
  track.max_ms = track_max_ms;
}
static bool twin_execute(void *ctx, const zs_command_t *cmd, zs_command_ack_result_t *result, uint16_t *detail) {
  (void)ctx;
  *result = ZS_COMMAND_ACK_OK; *detail = 0u;
  /* addendum E, as app_commands.c: a command signed by the next key promotes it first */
  if (zs_command_keys_on_verified(&secrets_io, cmd->key_id)) { key_promotions++; command_keys_reload("next key promoted, old key dropped"); }
  if (cmd->code == ZS_COMMAND_ROTATE_KEY) {
    zs_command_keys_rotate(&secrets_io, cmd->rotate.public_key, result, detail);
    if (*result == ZS_COMMAND_ACK_OK) { key_rotations++; command_keys_reload("next key installed, both trusted"); }
  } else if (cmd->code == ZS_COMMAND_SET_PARAMS) {
    zs_station_params_t next;
    const uint16_t reject = zs_station_params_apply_command(&params, &cmd->params, &next);
    if (reject) { *result = ZS_COMMAND_ACK_REJECTED; *detail = reject; }
    else if (zs_station_params_commit(&params_io, &next) != ZS_STATION_PARAMS_OK) { *result = ZS_COMMAND_ACK_FAILED; *detail = 1u; }
    else { params = next; params_apply(&params); tlog("command: SET_PARAMS applied, params v%lu (heartbeat %ld s, mic %ld, dwell %ld s)", (unsigned long)params.version, (long)params.value[0], (long)params.value[1], (long)params.value[5]); }
  } else if (cmd->code == ZS_COMMAND_REBOOT) {
    const uint32_t delay_s = cmd->reboot.delay_s > 5u ? cmd->reboot.delay_s : 5u;
    reboot_pending = true; reboot_at_ms = sim_now + delay_s * 1000u; cmd_reboots_scheduled++;
    tlog("command: REBOOT in %lu s", (unsigned long)delay_s);
  } else if (cmd->code == ZS_COMMAND_REQUEST_AUDIO) {
    if (!app_comms_request_audio(cmd, result, detail)) { tlog("command: REQUEST_AUDIO accepted, upload follows"); return false; }
  } else if (cmd->code == ZS_COMMAND_UPDATE_FIRMWARE) {
    if (!app_comms_update_firmware(cmd, result, detail)) { tlog("command: UPDATE_FIRMWARE accepted, download follows"); return false; }
  } else if (cmd->code == ZS_COMMAND_SET_NETWORK) {
    (void)app_comms_set_network(cmd, result, detail);                  /* addendum G, as app_commands.c */
    tlog("command: SET_NETWORK_CONFIG -> result %u detail %u", (unsigned)*result, (unsigned)*detail);
  } else { *result = ZS_COMMAND_ACK_REJECTED; *detail = 1u; }
  if (*result == ZS_COMMAND_ACK_OK) cmd_executed++; else cmd_rejected++;
  return true;
}
/* Trusted wall clock for the command validity window (the target: zs_command_clock over GNSS/NITZ). */
static bool twin_clock(uint32_t now_ms, uint64_t *now_us) { (void)now_ms; *now_us = twin_wall_us(); return true; }
static void model_boot(void);
/* The reboot the executor scheduled: the scheduler restarts and the parameters come back from the record (the
   command journal and the outbox live in NOR and survive as they are). */
static void reboot_tick(void) {
  zs_station_params_t loaded;
  zs_station_params_result_t r;
  if (!reboot_pending || (int32_t)(sim_now - reboot_at_ms) < 0) return;
  reboot_pending = false; twin_reboots++;
  r = zs_station_params_load(&params_io, &loaded);                  /* never set: the defaults come back */
  if ((r != ZS_STATION_PARAMS_OK && !(r == ZS_STATION_PARAMS_NOT_FOUND && params.version == 0u)) || memcmp(&loaded, &params, sizeof(params)) != 0) {
    tlog("twin: FAIL parameters did not survive the reboot"); exit(1);
  }
  zs_mode_init(&modes, NULL, sim_now);
  params_apply(&loaded);
  model_boot();
  (void)zs_mode_on_event(&modes, twin_selftest() ? ZS_MODE_EV_BOOT_DONE : ZS_MODE_EV_BOOT_FAILED, sim_now);
  tlog("twin: REBOOT by command, params v%lu reloaded from the record", (unsigned long)loaded.version);
}


/* ---- firmware update (addendum F): two flash banks with their boot record pages, install, trial, hang ------------
   The bank mapped at "0x08000000" is fw_bank[fw_active]; the download (app_comms, through fw_io) fills the other one.
   An install swaps them and resets; every reset runs the real boot guard on the running bank's record first. */
#define FW_BANK_BYTES (128u * 1024u)
#define FW_PAGE 8192u
#define FW_IMAGE_BYTES (FW_BANK_BYTES - FW_PAGE)
static uint8_t fw_bank[2][FW_BANK_BYTES];
static unsigned fw_active;
static uint32_t fw_hang_version;               /* --ota-hang-version: this image hangs right after the boot guard */
static zs_fw_boot_record_t fw_own;
static zs_fw_boot_action_t fw_action;
static bool fw_install_pending, fw_hung, fw_iwdg_early;
static uint32_t fw_install_at_ms, fw_hung_since_ms, fw_boot_ms;
static unsigned fw_installs, fw_trial_boots, fw_rollbacks, fw_confirms, fw_iwdg_resets;
static uint8_t *fw_other(void) { return fw_bank[fw_active ^ 1u]; }
static bool fwb_erase(void *c, uint32_t o, uint32_t n) { (void)c; if (o % FW_PAGE || n % FW_PAGE || o + n > FW_BANK_BYTES) return false; memset(fw_other() + o, 0xff, n); return true; }
static bool fwb_program(void *c, uint32_t o, const uint8_t *d, size_t n) {
  (void)c;
  if (o % 16u || n % 16u || o + n > FW_IMAGE_BYTES) return false;
  for (size_t i = 0u; i < n; i++) if (fw_other()[o + i] != 0xffu) return false;       /* a quad-word is programmed once */
  memcpy(fw_other() + o, d, n);
  return true;
}
static bool fwb_read(void *c, uint32_t o, uint8_t *d, size_t n) { (void)c; if (o + n > FW_BANK_BYTES) return false; memcpy(d, fw_other() + o, n); return true; }
static const zs_fw_image_io_t fw_io = {NULL, FW_IMAGE_BYTES, FW_PAGE, FW_IMAGE_BYTES, fwb_erase, fwb_program, fwb_read, NULL};
/* record pages: ctx 0 = the running bank, 1 = the other bank */
static uint8_t *fw_record(void *c) { return fw_bank[fw_active ^ (unsigned)(uintptr_t)c] + FW_IMAGE_BYTES; }
static bool fwr_read(void *c, uint32_t o, uint8_t *d, size_t n) { if (o + n > FW_PAGE) return false; memcpy(d, fw_record(c) + o, n); return true; }
static bool fwr_program(void *c, uint32_t o, const uint8_t slot[ZS_FW_BOOT_SLOT_BYTES]) {
  uint8_t *page = fw_record(c);
  if (o % ZS_FW_BOOT_SLOT_BYTES || o + ZS_FW_BOOT_SLOT_BYTES > FW_PAGE) return false;
  for (unsigned i = 0u; i < ZS_FW_BOOT_SLOT_BYTES; i++) if (page[o + i] != 0xffu) return false;
  memcpy(page + o, slot, ZS_FW_BOOT_SLOT_BYTES);
  return true;
}
static const zs_fw_boot_port_t fw_own_port = {(void *)(uintptr_t)0u, fwr_read, fwr_program};
static const zs_fw_boot_port_t fw_other_port = {(void *)(uintptr_t)1u, fwr_read, fwr_program};
static uint32_t fw_bank_version(const uint8_t *bank) { zs_fw_info_t info; return zs_fw_info_parse(bank + ZS_FW_INFO_OFFSET, &info) ? info.version : 0u; }
static uint32_t fw_running_version(void) { return fw_bank_version(fw_bank[fw_active]); }
static bool fw_on_trial(void) { return fw_own.armed && !fw_own.confirmed; }
static void fw_install(uint32_t version) { fw_install_pending = true; fw_install_at_ms = sim_now + 3000u; tlog("fw: install of v%lu in 3 s (bank swap + reset)", (unsigned long)version); }
static zs_fw_release_key_t fw_release_key;       /* the repository test release key (tools/generate_fw_update_vector.py) */
static const app_comms_fw_port_t fw_port = {&fw_io, &fw_other_port, &fw_release_key, 1u, ZS_FW_TARGET_STM32_APP, fw_running_version, fw_on_trial, fw_install};
/* model packages (addendum I): the NOR model region of tasks.c as two RAM slots of 64 KiB, the same release key */
#define MODEL_BLOCK 4096u
#define MODEL_SLOT_BYTES (16u * MODEL_BLOCK)
static uint8_t model_mem[2u * MODEL_SLOT_BYTES];
static bool mf_erase(void *c, uint32_t a, uint32_t n) { (void)c; if (a % MODEL_BLOCK || n % MODEL_BLOCK || a + n > sizeof(model_mem)) return false; memset(model_mem + a, 0xff, n); return true; }
static bool mf_program(void *c, uint32_t a, const uint8_t *d, size_t n) {
  (void)c;
  if (a + n > sizeof(model_mem)) return false;
  for (size_t i = 0u; i < n; i++) model_mem[a + i] &= d[i];                        /* NOR: bits only go 1 -> 0 */
  return true;
}
static bool mf_read(void *c, uint32_t a, uint8_t *d, size_t n) { (void)c; if (a + n > sizeof(model_mem)) return false; memcpy(d, model_mem + a, n); return true; }
static const zs_model_flash_t model_flash = {NULL, mf_erase, mf_program, mf_read};
static zs_model_store_t model_store;
static app_comms_model_port_t model_port;
/* every boot, as tasks.c bind_model_store: RAM holds the built-in model until the stored package is loaded */
static void model_boot(void) {
  uint32_t size, version;
  char text[ZS_MODEL_DESCRIBE_MAX];
  zs_model_activate_builtin();
  assert(zs_model_store_init(&model_store, &model_flash, 0u, MODEL_SLOT_BYTES, MODEL_BLOCK));
  if (zs_model_store_active(&model_store, &size, &version)) (void)zs_model_activate(zs_model_store_read_active, &model_store, size, version);
  model_port = (app_comms_model_port_t){&model_store, &fw_release_key, 1u};
  app_comms_set_model_port(&model_port);
  (void)zs_model_active_describe(text, sizeof(text));
  if (zs_model_active_version()) tlog("twin: model %s loaded from the store", text);
}
static void model_factory(void) { memset(model_mem, 0xff, sizeof(model_mem)); model_boot(); }
/* heartbeat key 19 as tasks.c/app_fw computes it */
static uint8_t fw_state_now(void) {
  zs_fw_boot_record_t other;
  uint8_t state = app_comms_fw_state();
  if (state == 0u && fw_on_trial()) state = 3u;
  if (state == 0u && zs_fw_boot_read(&fw_other_port, &other) && other.armed && !other.confirmed && other.rolled_back) state = 4u;
  return state;
}
/* the factory image: 16 KiB with its .fw_info, programmed by SWD into bank 1 (not swapped), records erased */
static void fw_factory(uint32_t version) {
  memset(fw_bank, 0xff, sizeof(fw_bank));
  for (unsigned i = 0u; i < 16384u; i++) fw_bank[0][i] = (uint8_t)(i * 13u + 5u);
  zs_fw_info_encode(ZS_FW_TARGET_STM32_APP, version, fw_bank[0] + ZS_FW_INFO_OFFSET);
  fw_active = 0u;
  memcpy(fw_release_key.public_key, zs_fw_update_vector_release_public_key, sizeof(fw_release_key.public_key));
}
static void fw_boot_guard(void) {
  for (unsigned n = 0u; n < 4u; n++) {
    fw_action = zs_fw_boot_guard(&fw_own_port, &fw_own);
    if (fw_action != ZS_FW_BOOT_ROLLBACK) break;
    fw_rollbacks++;
    tlog("fw: boot guard: v%lu not confirmed after %u attempts -> ROLLBACK (bank swap + reset)", (unsigned long)fw_own.version, fw_own.attempts);
    fw_active ^= 1u;
  }
  fw_iwdg_early = fw_action == ZS_FW_BOOT_TRIAL;         /* app_fw starts the IWDG right away while on trial */
  fw_trial_boots += fw_iwdg_early;
  fw_boot_ms = sim_now;
  fw_hung = fw_hang_version != 0u && fw_running_version() == fw_hang_version;
  fw_hung_since_ms = sim_now;
}
/* A simulated reset (install, IWDG, trial timeout): RAM is gone, the stores (journal, outbox, params) stay. */
static void station_reset(const char *why) {
  zs_station_params_t loaded;
  fw_boot_guard();
  app_comms_reset();
  model_boot();
  { zs_station_config_t stored; if (zs_station_config_store_load(&cfg_io, &stored, NULL) == ZS_STATION_CONFIG_OK) app_comms_set_config(&stored, 5u); }
  capture_set(false);
  zs_mode_init(&modes, NULL, sim_now);
  if (zs_station_params_load(&params_io, &loaded) == ZS_STATION_PARAMS_OK) { params = loaded; params_apply(&params); }
  tlog("twin: RESET (%s): running v%lu from bank %u, boot %s (attempt %u)%s", why, (unsigned long)fw_running_version(), fw_active + 1u,
       zs_fw_boot_action_name(fw_action), fw_own.attempts, fw_hung ? " - the image HANGS at start" : "");
  if (!fw_hung) (void)zs_mode_on_event(&modes, twin_selftest() ? ZS_MODE_EV_BOOT_DONE : ZS_MODE_EV_BOOT_FAILED, sim_now);
}
static void fw_tick(void) {
  if (fw_install_pending && (int32_t)(sim_now - fw_install_at_ms) >= 0) {
    fw_install_pending = false;
    fw_installs++;
    fw_active ^= 1u;                                                 /* SWAP_BANK toggled, option bytes reloaded */
    station_reset("install");
    return;
  }
  if (fw_hung) {
    if (fw_iwdg_early && (uint32_t)(sim_now - fw_hung_since_ms) >= 32000u) { fw_iwdg_resets++; station_reset("IWDG"); }
    return;
  }
  if (fw_on_trial() && (uint32_t)(sim_now - fw_boot_ms) >= ZS_FW_BOOT_TRIAL_TIMEOUT_MS) station_reset("trial timeout");
}
/* the session completed with the self-test passed: a trial image proved itself (tasks.c: comms_session_done) */
static void fw_session_done(void) {
  if (fw_on_trial() && selftest_failed_mask == 0u && zs_fw_boot_confirm(&fw_own_port, &fw_own)) {
    fw_confirms++;
    tlog("fw: v%lu confirmed (self-test passed, session completed)", (unsigned long)fw_running_version());
  }
}

static void supervisor_tick(void) {
  static zs_mode_t last = ZS_MODE_SHUTDOWN;
  reboot_tick();
  outbox_retry_tick();
  gsm_probe_tick();
  for (unsigned ev = 1u; ev < 32u; ev++) if (mode_bits & (1u << ev)) (void)zs_mode_on_event(&modes, (zs_mode_event_t)ev, sim_now);
  mode_bits = 0u;
  modes.policy.comms_max_ms = comms_max_base_ms + (app_comms_audio_busy() ? 300000u : 0u) + (app_comms_fw_busy() ? 900000u : 0u) +
                              (app_comms_net_busy() ? 300000u : 0u) + (track_s3_extension ? track_max_ms : 0u);
  (void)zs_mode_tick(&modes, sim_now);
  if (capture_on && !capture_wanted(modes.mode)) capture_set(false);   /* the post-event window closed */
  if (modes.mode != last) {
    const zs_mode_power_t p = zs_mode_power_for(modes.mode);
    tlog("mode %s -> %s", zs_mode_name(last), zs_mode_name(modes.mode));
    if (last == ZS_MODE_S3_COMMS) comms_health_on_s3_exit(modes.journal[(modes.journal_head + ZS_MODE_JOURNAL_DEPTH - 1u) % ZS_MODE_JOURNAL_DEPTH].event == ZS_MODE_EV_COMMS_DONE);
    if (last == ZS_MODE_S3_COMMS) track_s3_extension = false;
    if (track_open && (last == ZS_MODE_S3_COMMS || modes.mode == ZS_MODE_S0_SLEEP || modes.mode == ZS_MODE_S4_SERVICE || modes.mode == ZS_MODE_SHUTDOWN))
      track_close_request = true;
    bsp_gpio_mic_rail(p.mic_1v8);
    app_comms_allow_modem(p.modem);
    capture_set(capture_wanted(modes.mode));
    last = modes.mode;
    /* retest after a session while failed (tasks.c): a pass resumes the normal boot path */
    if (modes.selftest_failed && modes.mode == ZS_MODE_S0_SLEEP && twin_selftest()) {
      selftest_recoveries++;
      tlog("selftest: recovered, detection resumes");
      (void)zs_mode_on_event(&modes, ZS_MODE_EV_BOOT_DONE, sim_now);
    }
  }
}

static void audio_tick(void) {
  const bool mdf_on = capture_on;
  float acc = 0.0f;
  {
    float az, el;          /* the source moves along its segment: re-aim the plane wave every tick (20 ms) */
    if (world_mode) {
      world_step((double)scene.sample / 32000.0, &az, &el); array_render_set_direction(&array_render, az, el, 15.0f);
      for (unsigned t = 1u; t < world_targets; t++) {
        target_step(xt_p0[t], xt_v[t], (double)scene.sample / 32000.0, &az, &el, &xt_gain[t], &xt_te[t], &xt_te_rate[t]);
        array_render_set_direction(&xt_render[t], az, el, 15.0f);
      }
    }
    else if (scene_direction(&scene, &az, &el) && (az != array_render.azimuth_deg || el != array_render.elevation_deg))
      array_render_set_direction(&array_render, az, el, 15.0f);
  }
  for (unsigned i = 0u; i < TICK_FRAMES; i++) {
    float src, bg, out[ZS_AUDIO_CHANNELS], v;
    scene_next_parts(&scene, &src, &bg);
    if (world_wav[0].x) src = world_wav_at(&world_wav[0], world_te + (double)i / 32000.0 * world_te_rate);
    if (world_mode) src *= world_gain;
    array_render_push(&array_render, src, out);
    for (unsigned t = 1u; t < world_targets; t++) {
      float xs, xb, xo[ZS_AUDIO_CHANNELS];
      scene_next_parts(&xt_scene[t], &xs, &xb);
      if (world_wav[t].x) xs = world_wav_at(&world_wav[t], xt_te[t] + (double)i / 32000.0 * xt_te_rate[t]);
      array_render_push(&xt_render[t], xs * xt_gain[t], xo);
      for (unsigned c = 0u; c < ZS_AUDIO_CHANNELS; c++) out[c] += xo[c];
    }
    out[0] += bg;
    for (unsigned c = 1u; c < ZS_AUDIO_CHANNELS; c++) out[c] += scene_background(&scene, c);
    for (unsigned c = 0u; c < ZS_AUDIO_CHANNELS; c++) out[c] = out[c] > 1.0f ? 1.0f : (out[c] < -1.0f ? -1.0f : out[c]);
    v = out[0];
    int16_t frame[ZS_AUDIO_CHANNELS];
    acc += v * v;
    for (unsigned c = 0u; c < ZS_AUDIO_CHANNELS; c++) frame[c] = (int16_t)(out[c] * 30000.0f);
    if (dump_pcm) fwrite(&frame[0], sizeof(int16_t), 1u, dump_pcm);
    if (mdf_on) zs_audio_ring_push(&ring, frame);
  }
  scene_level = 0.9f * scene_level + 0.1f * acc / (float)TICK_FRAMES;
  /* the T5838 AAD: a loud enough scene wakes the station from S0 */
  if (modes.mode == ZS_MODE_S0_SLEEP && scene_level > 0.002f) mode_event(ZS_MODE_EV_MIC_WAKE);
  if ((modes.mode == ZS_MODE_S1_LISTEN || modes.mode == ZS_MODE_S2_DSP || track_open) && zs_station_pipeline_fetch(&pipeline, &ring)) {
    while (pipeline.pending) { (void)zs_station_pipeline_run_pending(&pipeline); dsp_mode_events(); }
  }
  (void)zs_audio_recorder_step(&recorder, &ring, ring.total_frames, 32000u);
}

int main(int argc, char **argv) {
  const char *scene_name = "drone", *server_cmd = NULL, *world_sound[WORLD_MAX_TARGETS] = {NULL};
  unsigned world_sounds = 0u;
  uint32_t seconds = 120u, seed = 1u, outage_start = 0u, outage_end = 0u;
  int expect_events = -1, expect_delivered = -1, expect_commands = -1, expect_reboots = -1, expect_post_audio = -1;
  int expect_fw_version = -1, expect_fw_state = -1, expect_net_version = -1, expect_net_state = -1;
  float expect_bearing_error = -1.0f;
  int expect_streamed = -1;
  uint32_t factory_version = 1u;
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
    else if (!strcmp(argv[i], "--expect-post-audio") && i + 1 < argc) expect_post_audio = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--forget-events")) forget_events = true;
    else if (!strcmp(argv[i], "--selftest-fail-until") && i + 1 < argc) selftest_fail_until_ms = sim_now + (uint32_t)atoi(argv[++i]) * 1000u;
    else if (!strcmp(argv[i], "--fw-version") && i + 1 < argc) factory_version = (uint32_t)atoi(argv[++i]);
    else if (!strcmp(argv[i], "--ota-hang-version") && i + 1 < argc) fw_hang_version = (uint32_t)atoi(argv[++i]);
    else if (!strcmp(argv[i], "--expect-fw-version") && i + 1 < argc) expect_fw_version = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--expect-fw-state") && i + 1 < argc) expect_fw_state = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--expect-net-version") && i + 1 < argc) expect_net_version = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--expect-net-state") && i + 1 < argc) expect_net_state = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--expect-bearing-error") && i + 1 < argc) expect_bearing_error = (float)atof(argv[++i]);
    else if (!strcmp(argv[i], "--track-max-s") && i + 1 < argc) track_max_ms = (uint32_t)atoi(argv[++i]) * 1000u;
    else if (!strcmp(argv[i], "--expect-streamed") && i + 1 < argc) expect_streamed = atoi(argv[++i]);
    else if (!strcmp(argv[i], "--station-id") && i + 1 < argc) twin_station_id = (unsigned)atoi(argv[++i]);
    else if (!strcmp(argv[i], "--pos") && i + 1 < argc && parse3(argv[++i], st_enu, 2)) {}
    else if (!strcmp(argv[i], "--world") && i + 1 < argc) {
      double p[7] = {0, 0, 0, 0, 0, 0, 185.0};
      const int got = sscanf(argv[++i], "%lf,%lf,%lf,%lf,%lf,%lf,%lf", &p[0], &p[1], &p[2], &p[3], &p[4], &p[5], &p[6]);
      if ((got != 6 && got != 7) || world_targets >= WORLD_MAX_TARGETS || p[6] < 40.0 || p[6] > 1000.0) { fprintf(stderr, "--world x0,y0,z0,vx,vy,vz[,f0_hz] (up to %u targets)\n", WORLD_MAX_TARGETS); return 2; }
      if (world_targets == 0u) { for (unsigned k = 0u; k < 3u; k++) { tg_p0[k] = p[k]; tg_v[k] = p[3 + k]; } tg_f0 = (float)p[6]; }
      else { for (unsigned k = 0u; k < 3u; k++) { xt_p0[world_targets][k] = p[k]; xt_v[world_targets][k] = p[3 + k]; } xt_f0[world_targets] = (float)p[6]; }
      world_targets++;
      world_mode = true;
    }
    else if (!strcmp(argv[i], "--world-ref-m") && i + 1 < argc) world_ref_m = atof(argv[++i]);
    else if (!strcmp(argv[i], "--world-absorption-db-km") && i + 1 < argc) world_absorption_db_km = atof(argv[++i]);
    else if (!strcmp(argv[i], "--world-level") && i + 1 < argc) world_level = (float)atof(argv[++i]);
    else if (!strcmp(argv[i], "--world-sound") && i + 1 < argc && world_sounds < WORLD_MAX_TARGETS) world_sound[world_sounds++] = argv[++i];
    else if (!strcmp(argv[i], "--installed")) world_installed = true;
    else if (!strcmp(argv[i], "--log-uplink") && i + 1 < argc) uplink_log = fopen(argv[++i], "w");
    else { fprintf(stderr, "usage: station_twin --scene drone|quiet|ground [--seconds N] [--seed S] [--server CMD] [--gsm-outage FROM_S TO_S] [--publish-loss P] [--receipt-loss P] [--receipt-latency MS] [--mqtt-refuse FROM_S TO_S] [--lora] [--lora-loss P] [--lora-gateway-ms MS] [--degraded-after N] [--gsm-probe-s S] [--inject-events N AT_S] [--dump-pcm FILE] [--expect-events N] [--expect-delivered N] [--expect-commands N] [--expect-reboots N] [--expect-post-audio S] [--forget-events] [--selftest-fail-until S] [--fw-version N] [--ota-hang-version N] [--expect-fw-version N] [--expect-fw-state S] [--expect-net-version N] [--expect-net-state S] [--expect-bearing-error DEG] [--track-max-s S] [--expect-streamed N] [--station-id N] [--pos E,N[,U]] [--installed] [--world X,Y,Z,VX,VY,VZ[,F0] ...] [--world-ref-m M] [--world-absorption-db-km A] [--world-level L] [--world-sound FILE.wav ...] [--log-uplink FILE]\n"); return 2; }
  }
  for (unsigned k = 0u; k < world_sounds; k++)          /* the k-th recording is the k-th target's sound */
    if (!world_wav_load(world_sound[k], &world_wav[k])) { fprintf(stderr, "--world-sound: %s is not a PCM16 WAV\n", world_sound[k]); return 2; }
  if (world_mode && !world_wav[0].x) segs[nseg++] = (scene_segment_t){SCENE_DRONE_FLYBY, 0u, seconds * 1000u, tg_f0, world_level, 0.0f, 0.0f, 0.0f, true};
  else if (!strcmp(scene_name, "drone")) { segs[nseg++] = (scene_segment_t){SCENE_DRONE_FLYBY, 20000u, 60000u, 185.0f, 1.0f, 60.0f, 140.0f, 20.0f, false}; if (seconds > 150u) segs[nseg++] = (scene_segment_t){SCENE_DRONE_FLYBY, 100000u, 130000u, 210.0f, 0.8f, 300.0f, 250.0f, 35.0f, false}; }
  else if (!strcmp(scene_name, "ground")) segs[nseg++] = (scene_segment_t){SCENE_GROUND_VEHICLE, 20000u, 60000u, 0.0f, 1.0f, 200.0f, 200.0f, 0.0f, false};
  scene_init(&scene, segs, nseg, 0.02f, seed);
  for (unsigned t = 1u; t < world_targets; t++) {           /* the other targets: source only (the background is scene's) */
    xt_seg[t] = (scene_segment_t){SCENE_DRONE_FLYBY, 0u, seconds * 1000u, xt_f0[t], world_level, 0.0f, 0.0f, 0.0f, true};
    scene_init(&xt_scene[t], &xt_seg[t], 1u, 0.0f, seed * 7919u + t);
    array_render_init(&xt_render[t], NULL, 32000.0f);
  }
  array_render_init(&array_render, NULL, 32000.0f);
  zs_track_window_init(&track, track_max_ms, 6u);
  ch_rng ^= seed * 2654435761u;

  if (server_cmd && !link_start(server_cmd)) { fprintf(stderr, "cannot start the server twin\n"); return 3; }
  memset(outbox_mem, 0xff, sizeof(outbox_mem)); memset(journal_mem, 0xff, sizeof(journal_mem));
  zs_audio_ring_init(&ring, ring_storage, RING_FRAMES, 32000u);
  memset(pre_flash, 0xff, sizeof(pre_flash));
  assert(zs_prehistory_init(&prehistory, &pre_storage, 0u, sizeof(pre_flash), 32000u) && zs_audio_recorder_init(&recorder, &prehistory, pl_sample_time, NULL));
  zs_dsp_mcu_init(&dsp_ctx);
  pipeline_port.station_id = twin_station_id;
  zs_station_position_init(&station_pos);
  zs_gnss_nmea_init(&gnss_nmea);
  if (world_installed) field_install();
  { size_t work; zs_complex_t *scratch = zs_dsp_mcu_borrow_work(&work); assert(work >= ZS_AIR_SCRATCH_COMPLEX); assert(zs_station_pipeline_init(&pipeline, &pipeline_port, scratch, window_pcm)); }
  zs_station_config_defaults(&cfg, twin_station_id, ZS_STATION_CONFIG_REGION_RU868);
  cfg.version = 1u; strcpy(cfg.server_host, "muhoed.twin"); cfg.mqtt_port = 8883u; strcpy(cfg.ca_reference, "dioneya-root");
  strcpy(cfg.tenant, "pilot1"); strcpy(cfg.topic_prefix, "zs/v1"); cfg.preferred_sim = 1u; strcpy(cfg.apn[0], "internet");
  assert(zs_station_config_validate(&cfg) == 0u && zs_station_config_compute_hash(&cfg, cfg.config_hash));
  memset(cfg_mem, 0xff, sizeof(cfg_mem));                       /* commissioned over BLE: the record is stored */
  assert(zs_station_config_store_commit(&cfg_io, &cfg, true, true) == ZS_STATION_CONFIG_OK && zs_station_config_store_load(&cfg_io, &cfg, NULL) == ZS_STATION_CONFIG_OK);
  for (unsigned i = 0u; i < 32u; i++) twin_engineer_key[i] = (uint8_t)(0xa0u + i);
  assert(zs_lora_uplink_init(&lora, &lora_port, &outbox_io, twin_station_id, 1u, twin_engineer_key, 9u, 125000u, sim_now));
  /* remote commands: the repository test key (tools/generate_command_set_vector.py), the twin wall clock and the
     executor; the parameter record starts empty (defaults, the CLI flags above stay in force until a command) */
  (void)zs_command_set_vector_reboot; (void)zs_command_set_vector_params;
  memset(params_mem, 0xff, sizeof(params_mem));
  (void)zs_station_params_load(&params_io, &params);
  /* provisioned over BLE: the repository test key is the command key (the secrets record survives the reboots) */
  memset(secrets_mem, 0xff, sizeof(secrets_mem));
  memset(&secrets, 0, sizeof(secrets));
  secrets.command_key_set = true; memcpy(secrets.command_public_key, zs_command_set_vector_public_key, sizeof(secrets.command_public_key));
  assert(zs_station_secrets_commit(&secrets_io, &secrets) == ZS_STATION_SECRETS_OK);
  command_keys_reload(NULL);
  app_comms_set_clock(twin_clock);
  app_comms_set_executor(twin_execute, NULL);
  app_comms_set_audio_source(&audio_source);
  fw_factory(factory_version);
  fw_boot_guard();
  app_comms_set_fw_port(&fw_port);
  model_factory();
  (void)zs_fw_update_vector_image; (void)zs_fw_update_vector_manifest; (void)zs_fw_update_vector_signature; (void)zs_fw_update_vector_command;
  (void)zs_fw_update_vector_request0; (void)zs_fw_update_vector_chunk0; (void)zs_fw_update_vector_chunk1; (void)zs_fw_update_vector_chunk2;
  app_comms_bind(&outbox_io, &journal_io, &hooks);
  app_comms_bind_config_store(&cfg_io, net_committed);
  app_comms_set_config(&cfg, 5u);
  app_comms_request(true);
  zs_mode_init(&modes, NULL, sim_now);
  (void)zs_mode_on_event(&modes, twin_selftest() ? ZS_MODE_EV_BOOT_DONE : ZS_MODE_EV_BOOT_FAILED, sim_now);
  tlog("twin: scene %s, %u s, seed %u, server %s", scene_name, seconds, seed, server_cmd ? "pipe" : "none");
  if (world_mode)
    tlog("field: station %u at E %.0f N %.0f U %.0f m (%s); target from E %.0f N %.0f U %.0f m at %.1f/%.1f/%.1f m/s, %s, full level within %.0f m, air %.1f dB/km",
         twin_station_id, st_enu[0], st_enu[1], st_enu[2], world_installed ? "installation record" : "GNSS position", tg_p0[0], tg_p0[1], tg_p0[2],
         tg_v[0], tg_v[1], tg_v[2], world_wav[0].x ? world_sound[0] : "synthetic electric multirotor", world_ref_m, world_absorption_db_km);
  for (unsigned t = 1u; t < world_targets; t++)
    tlog("field: target %u from E %.0f N %.0f U %.0f m at %.1f/%.1f/%.1f m/s, %s %.0f Hz", t + 1u, xt_p0[t][0], xt_p0[t][1], xt_p0[t][2],
         xt_v[t][0], xt_v[t][1], xt_v[t][2], world_wav[t].x ? world_sound[t] : "synthetic", xt_f0[t]);

  const uint32_t end = sim_now + seconds * 1000u;
  while (sim_now < end) {
    if (outage_end && sim_now >= outage_start && sim_now < outage_end) { if (gsm_available) { gsm_available = false; tlog("radio: GSM outage begins"); } }
    else if (!gsm_available) { gsm_available = true; tlog("radio: GSM back"); }
    fw_tick();
    if (!fw_hung) {                               /* a hung image does nothing until the IWDG resets it */
      gnss_tick();
      audio_tick();
      inject_tick();
      supervisor_tick();
    }
    modem_physics();
    channel_tick();
    if (!fw_hung) app_comms_step();
    if (lora_enabled && !fw_hung) { lora_channel_tick(); lora_step(); }
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
    tlog("twin: selftest runs %u recoveries %u, failed mask 0x%04x", selftest_runs, selftest_recoveries, (unsigned)selftest_failed_mask);
    tlog("twin: command keys %u (rotations %u promotions %u)", (unsigned)app_comms_command_key_count(), key_rotations, key_promotions);
    tlog("twin: firmware v%lu (bank %u, state %u), other bank v%lu; installs %u trial boots %u iwdg resets %u rollbacks %u confirms %u",
         (unsigned long)fw_running_version(), fw_active + 1u, (unsigned)fw_state_now(), (unsigned long)fw_bank_version(fw_other()),
         fw_installs, fw_trial_boots, fw_iwdg_resets, fw_rollbacks, fw_confirms);
    {
      zs_detector_health_t d; zs_station_config_t stored;
      memset(&d, 0, sizeof(d)); app_comms_net_heartbeat(&d);
      tlog("twin: network config v%lu state %u (last failed v%lu), stored v%lu; broker opens muhoed.twin %u muhoed2.twin %u, failed endpoints %u",
           (unsigned long)d.net_config_version, (unsigned)d.net_state, (unsigned long)d.net_failed_version,
           zs_station_config_store_load(&cfg_io, &stored, NULL) == ZS_STATION_CONFIG_OK ? (unsigned long)stored.version : 0ul,
           endpoint1_opens, endpoint2_opens, endpoint_failures);
    }
  }
  /* prehistory around the first event: complete seconds recorded before it and after it (the post-event window) */
  unsigned audio_before = 0u, audio_after = 0u;
  {
    zs_prehistory_record_info_t info;
    for (uint64_t s = prehistory.next_sequence - prehistory.available_records; s < prehistory.next_sequence; s++)
      if (first_event_time_us && zs_prehistory_read_record_info(&prehistory, s, &info)) { if (info.start_time_us >= first_event_time_us) audio_after++; else audio_before++; }
    tlog("twin: bearings %u (computed %lu of %lu asked, no audio %lu, weak %lu, unsolved %lu), azimuth error mean %.2f max %.2f deg",
         bearings_total, (unsigned long)pipeline.bearing_ctx.computed, (unsigned long)pipeline.bearing_ctx.attempts,
         (unsigned long)pipeline.bearing_ctx.no_audio, (unsigned long)pipeline.bearing_ctx.weak, (unsigned long)pipeline.bearing_ctx.unsolved,
         bearings_total ? bearing_err_sum / (float)bearings_total : 0.0f, bearing_err_max);
    if (world_targets > 1u) {
      for (unsigned t = 0u; t < world_targets; t++)
        tlog("twin: target %u (%.0f Hz): %u bearings, azimuth error mean %.2f deg", t + 1u, t ? xt_f0[t] : tg_f0, bearings_of_target[t],
             bearings_of_target[t] ? bearing_err_of_target[t] / (float)bearings_of_target[t] : 0.0f);
      tlog("twin: comb bearings in %lu windows (asked %lu, computed %lu, few bins %lu, weak %lu, unsolved %lu)",
           (unsigned long)pipeline.comb_windows, (unsigned long)pipeline.comb_stats.attempts, (unsigned long)pipeline.comb_stats.computed,
           (unsigned long)pipeline.comb_stats.few_bins, (unsigned long)pipeline.comb_stats.weak, (unsigned long)pipeline.comb_stats.unsolved);
    }
    tlog("twin: tracks %lu (target lost %lu, time limit %lu, mode %lu, refused on link %lu), bearings streamed %u",
         (unsigned long)track.tracks, (unsigned long)track.ended_lost, (unsigned long)track.ended_max, (unsigned long)track.ended_mode,
         (unsigned long)track.refused_link, bearings_streamed);
    tlog("twin: rec committed %u aborted %u overruns %u errors %u, ring holds %u s; around the first event: %u s before, %u s after",
         recorder.frames_committed, recorder.frames_aborted, recorder.overruns, recorder.storage_errors, (unsigned)prehistory.available_records, audio_before, audio_after);
  }
  {
    uint16_t pending = 0u;
    (void)zs_event_outbox_pending_count(&outbox_io, &pending);
    if (expect_events >= 0 && (int)events_emitted_total < expect_events) { tlog("twin: FAIL expected >= %d events, got %u", expect_events, events_emitted_total); return 1; }
    if (expect_delivered >= 0 && ((int)(link_receipts + lora.acks) < expect_delivered || pending != 0u)) { tlog("twin: FAIL expected %d delivered events with an empty outbox (mqtt receipts %u, lora acks %u, pending %u)", expect_delivered, link_receipts, lora.acks, pending); return 1; }
    if (expect_commands >= 0 && (int)cmd_executed != expect_commands) { tlog("twin: FAIL expected %d executed commands, got %u", expect_commands, cmd_executed); return 1; }
    if (expect_post_audio >= 0 && (int)audio_after < expect_post_audio) { tlog("twin: FAIL expected >= %d s of audio after the event, got %u", expect_post_audio, audio_after); return 1; }
    if (expect_fw_version >= 0 && fw_running_version() != (uint32_t)expect_fw_version) { tlog("twin: FAIL expected firmware v%d, running v%lu", expect_fw_version, (unsigned long)fw_running_version()); return 1; }
    if (expect_fw_state >= 0 && fw_state_now() != (uint8_t)expect_fw_state) { tlog("twin: FAIL expected firmware state %d, got %u", expect_fw_state, (unsigned)fw_state_now()); return 1; }
    if (expect_net_version >= 0 || expect_net_state >= 0) {
      zs_detector_health_t d; memset(&d, 0, sizeof(d)); app_comms_net_heartbeat(&d);
      if (expect_net_version >= 0 && d.net_config_version != (uint32_t)expect_net_version) { tlog("twin: FAIL expected network config v%d, got v%lu", expect_net_version, (unsigned long)d.net_config_version); return 1; }
      if (expect_net_state >= 0 && d.net_state != (uint8_t)expect_net_state) { tlog("twin: FAIL expected network state %d, got %u", expect_net_state, (unsigned)d.net_state); return 1; }
    }
    if (expect_bearing_error >= 0.0f && (bearings_total == 0u || bearing_err_sum / (float)bearings_total > expect_bearing_error)) {
      tlog("twin: FAIL expected bearings with a mean azimuth error <= %.1f deg (%u bearings, mean %.2f)", expect_bearing_error, bearings_total,
           bearings_total ? bearing_err_sum / (float)bearings_total : 0.0f);
      return 1;
    }
    if (expect_streamed >= 0 && (int)bearings_streamed < expect_streamed) { tlog("twin: FAIL expected >= %d streamed bearings, got %u", expect_streamed, bearings_streamed); return 1; }
    if (expect_reboots >= 0 && ((int)twin_reboots != expect_reboots || (int)cmd_reboots_scheduled != expect_reboots)) { tlog("twin: FAIL expected %d reboots (scheduled %u, done %u)", expect_reboots, cmd_reboots_scheduled, twin_reboots); return 1; }
  }
  if (link_out >= 0) { link_report(); fcntl(link_in, F_SETFL, fcntl(link_in, F_GETFL) & ~O_NONBLOCK); close(link_out); for (;;) { ssize_t r = read(link_in, link_buf + link_len, sizeof(link_buf) - 1u - link_len); if (r <= 0) break; link_len += (size_t)r; } link_buf[link_len] = 0; { char *p = strstr(link_buf, "REPORT "); if (p) printf("SERVER %s", p + 7); } waitpid(server_pid, NULL, 0); }
  return 0;
}

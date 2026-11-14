#include "app_nrf_update.h"
#include "FreeRTOS.h"
#include "app_config.h"
#include "bsp_gpio.h"
#include "bsp_uart.h"
#include "task.h"
#include "zs_mcumgr_serial.h"
#include "zs_nor_image_store.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static zs_nor_image_store_t store;
static bool bound;
static app_print_fn print;
static volatile bool update_pending;
static uint32_t put_offset;

static void say(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void say(const char *fmt, ...) {
  /* the console printer is variadic; forward through a fixed buffer */
  char buf[160];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  if (print) print("%s", buf);
}

void app_nrf_update_bind(zs_nor_t *nor, const zs_nor_storage_layout_t *layout, app_print_fn printer) {
  print = printer;
  bound = nor && layout && zs_nor_image_store_init(&store, nor, layout->nrf_image_base_address, layout->nrf_image_partition_bytes);
}

/* ---- console: nrfimg -------------------------------------------------------------------------- */

static int hexval(char c) { return (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : (c >= 'A' && c <= 'F') ? c - 'A' + 10 : -1; }

static bool parse_sha(const char *s, uint8_t out[32]) {
  for (unsigned i = 0u; i < 32u; i++) { int h = hexval(s[2u * i]), l = hexval(s[2u * i + 1u]); if (h < 0 || l < 0) return false; out[i] = (uint8_t)((h << 4) | l); }
  return s[64] == '\0' || s[64] == ' ';
}

static int b64val(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  return c == '+' ? 62 : c == '/' ? 63 : -1;
}

static size_t b64decode(const char *s, uint8_t *out, size_t cap) {
  size_t o = 0u, n = strlen(s);
  if (n % 4u) return 0u;
  for (size_t i = 0u; i < n; i += 4u) {
    int a = b64val(s[i]), b = b64val(s[i + 1u]);
    if (a < 0 || b < 0) return 0u;
    uint32_t v = ((uint32_t)a << 18) | ((uint32_t)b << 12);
    unsigned bytes = 1u;
    if (s[i + 2u] != '=') { int c = b64val(s[i + 2u]); if (c < 0) return 0u; v |= (uint32_t)c << 6; bytes = 2u; }
    if (s[i + 3u] != '=') { int d = b64val(s[i + 3u]); if (d < 0 || bytes != 2u) return 0u; v |= (uint32_t)d; bytes = 3u; }
    if (o + bytes > cap) return 0u;
    out[o++] = (uint8_t)(v >> 16);
    if (bytes > 1u) out[o++] = (uint8_t)(v >> 8);
    if (bytes > 2u) out[o++] = (uint8_t)v;
  }
  return o;
}

static void status(void) {
  zs_nor_image_info_t info;
  if (!bound) { say("nrfimg: no NOR slot (record stores are in RAM)\r\n"); return; }
  if (zs_nor_image_store_open(&store, false, &info))
    say("nrfimg: image %lu bytes v%lu sha %02x%02x%02x%02x.. slot @0x%08lx (%lu bytes)\r\n", (unsigned long)info.size, (unsigned long)info.version,
        info.sha256[0], info.sha256[1], info.sha256[2], info.sha256[3], (unsigned long)store.base, (unsigned long)zs_nor_image_store_capacity(&store));
  else say("nrfimg: slot empty or invalid (@0x%08lx, %lu bytes)%s\r\n", (unsigned long)store.base, (unsigned long)zs_nor_image_store_capacity(&store), store.writing ? ", write in progress" : "");
}

bool app_nrf_console(const char *line) {
  if (strncmp(line, "nrfupd", 6u) == 0) {
    zs_nor_image_info_t info;
    if (!bound || !zs_nor_image_store_open(&store, true, &info)) { say("nrfupd: no valid image in the NOR slot\r\n"); return true; }
    update_pending = true;
    say("nrfupd: %lu bytes v%lu queued, the ble task takes it from here\r\n", (unsigned long)info.size, (unsigned long)info.version);
    return true;
  }
  if (strncmp(line, "nrfimg", 6u) != 0) return false;
  const char *arg = line + 6;
  while (*arg == ' ') arg++;
  if (!bound) { say("nrfimg: no NOR slot (record stores are in RAM)\r\n"); return true; }
  if (*arg == '\0') { status(); return true; }
  if (strncmp(arg, "begin ", 6u) == 0) {
    char *end; uint8_t sha[32];
    unsigned long size = strtoul(arg + 6, &end, 10), version = strtoul(end, &end, 10);
    while (*end == ' ') end++;
    if (size == 0u || !parse_sha(end, sha)) { say("nrfimg: usage begin <size> <version> <sha256hex>\r\n"); return true; }
    if (!zs_nor_image_store_begin(&store, (uint32_t)size, (uint32_t)version, sha)) { say("nrfimg: begin failed (size %lu > slot %lu?)\r\n", size, (unsigned long)zs_nor_image_store_capacity(&store)); return true; }
    put_offset = 0u;
    say("ok 0\r\n");
    return true;
  }
  if (strncmp(arg, "put ", 4u) == 0) {
    char *end; uint8_t data[96];
    unsigned long off = strtoul(arg + 4, &end, 10);
    while (*end == ' ') end++;
    const size_t n = b64decode(end, data, sizeof(data));
    if (!store.writing) { say("fail no session\r\n"); return true; }
    if (off != put_offset) { say("fail offset %lu expected %lu\r\n", off, (unsigned long)put_offset); return true; }   /* the sender resends from the expected offset */
    if (n == 0u || !zs_nor_image_store_write(&store, data, n)) { say("fail write at %lu\r\n", off); zs_nor_image_store_abort(&store); return true; }
    put_offset += (uint32_t)n;
    say("ok %lu\r\n", (unsigned long)put_offset);
    return true;
  }
  if (strcmp(arg, "end") == 0) {
    if (zs_nor_image_store_finish(&store)) { say("ok verified %lu bytes\r\n", (unsigned long)put_offset); status(); }
    else say("fail verify (sha or length)\r\n");
    return true;
  }
  say("nrfimg: begin <size> <version> <sha256hex> | put <off> <base64> | end\r\n");
  return true;
}

/* ---- nrfupd: MCUboot serial recovery over the IPC UART ----------------------------------------- */

bool app_nrf_update_pending(void) { return update_pending; }

static bool wait_reply(zs_mcumgr_decoder_t *dec, zs_mcumgr_upload_t *up, uint32_t timeout_ms) {
  const TickType_t start = xTaskGetTickCount();
  uint8_t buf[64];
  while ((uint32_t)(xTaskGetTickCount() - start) < pdMS_TO_TICKS(timeout_ms)) {
    size_t n;
    while ((n = bsp_uart_read(BSP_UART_BLE, buf, sizeof(buf))) > 0u) {
      for (size_t i = 0u; i < n; i++) {
        const uint8_t *pkt; size_t len;
        if (zs_mcumgr_decoder_feed(dec, buf[i], &pkt, &len) && zs_mcumgr_upload_response(up, pkt, len)) return true;
      }
    }
    vTaskDelay(pdMS_TO_TICKS(2));
  }
  return false;
}

void app_nrf_update_run(void) {
  static uint8_t serial[640];
  static zs_mcumgr_upload_t up;
  static zs_mcumgr_decoder_t dec;
  zs_nor_image_info_t info;
  uint8_t drain[64];
  update_pending = false;
  if (!bound || !zs_nor_image_store_open(&store, true, &info)) { say("nrfupd: slot invalid\r\n"); return; }
  /* pin authority: hold reset via BLE_EN, assert DFU_REQ, release reset, keep the request through boot */
  bsp_gpio_ble_enable(false);
  bsp_gpio_ble_dfu_request(true);
  vTaskDelay(pdMS_TO_TICKS(20));
  bsp_gpio_ble_enable(true);
  vTaskDelay(pdMS_TO_TICKS(500));
  bsp_gpio_ble_dfu_request(false);
  while (bsp_uart_read(BSP_UART_BLE, drain, sizeof(drain)) > 0u) { }
  zs_mcumgr_upload_init_reader(&up, zs_nor_image_store_reader, &store, info.size, info.sha256);
  zs_mcumgr_decoder_init(&dec);
  say("nrfupd: recovery entered, uploading %lu bytes\r\n", (unsigned long)info.size);
  const TickType_t t0 = xTaskGetTickCount();
  unsigned timeouts = 0u, next_report = 10u;
  while (!up.done && !up.failed) {
    const size_t n = zs_mcumgr_upload_request(&up, serial, sizeof(serial));
    if (n == 0u) break;
    if (bsp_uart_write(BSP_UART_BLE, serial, n) < 0) { say("nrfupd: uart write failed\r\n"); break; }
    if (!wait_reply(&dec, &up, 2000u)) {
      if (++timeouts >= 5u) { say("nrfupd: no reply from the bootloader (%lu bad frames)\r\n", (unsigned long)dec.bad_frames); break; }
      continue;                                             /* resend the same request */
    }
    timeouts = 0u;
    const unsigned pct = (unsigned)((uint64_t)up.offset * 100u / info.size);
    if (pct >= next_report) { say("nrfupd: %u%% (%lu/%lu)\r\n", pct, (unsigned long)up.offset, (unsigned long)info.size); next_report = pct + 10u; }
  }
  if (!up.done) { say("nrfupd: FAILED at %lu (rc %d, retries %u); module stays in recovery, run nrfupd again or bledfu\r\n", (unsigned long)up.offset, up.last_rc, up.retries); return; }
  const size_t n = zs_mcumgr_reset_request(up.seq, serial, sizeof(serial));
  if (n) (void)bsp_uart_write(BSP_UART_BLE, serial, n);
  vTaskDelay(pdMS_TO_TICKS(300));
  say("nrfupd: done in %lu s, reset sent; MCUboot swaps and boots the image in test mode, the bridge confirms after IDENTITY_SET\r\n",
      (unsigned long)((xTaskGetTickCount() - t0) / 1000u));
}

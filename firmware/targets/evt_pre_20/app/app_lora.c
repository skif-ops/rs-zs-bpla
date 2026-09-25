#include "app_lora.h"
#include "app_config.h"
#include "app_power.h"
#include "bsp_spi.h"
#include "FreeRTOS.h"
#include "task.h"
#include "zs_lora_uplink.h"
#include "zs_sx1262.h"
#include <string.h>

static zs_sx1262_t radio;
static zs_lora_uplink_t uplink;
static const zs_event_outbox_io_t *outbox_io;
static uint32_t station_id;
static uint8_t engineer_key[32];
static bool key_set, radio_ok, route_lora, bound;
static void (*log_fn)(const char *fmt, ...);
static uint32_t dry_frames, live_frames, acks, radio_errors;
static bool rx_open; static uint32_t rx_close_ms;

/* recent detections for the frame summary (event_id -> fields); zeros for events from before a reboot */
typedef struct { uint64_t event_id; uint8_t class_id, confidence, level; uint16_t f0; bool used; } summary_t;
static summary_t summaries[16];
void app_lora_remember_event(uint64_t event_id, uint8_t class_id, uint8_t confidence_u8, uint8_t presence_level, uint16_t f0_hz) {
  static unsigned next;
  summaries[next] = (summary_t){event_id, class_id, confidence_u8, presence_level, f0_hz, true};
  next = (next + 1u) % 16u;
}
static bool summarize(void *ctx, const zs_event_outbox_item_t *item, zs_lora_event_t *e) {
  zs_power_t p;
  (void)ctx;
  if (app_power_snapshot(&p)) { e->battery_mv = p.battery_mv; e->battery_pct = p.battery_pct; }
  for (unsigned i = 0u; i < 16u; i++) if (summaries[i].used && summaries[i].event_id == item->event_id) {
    e->class_id = summaries[i].class_id; e->confidence_u8 = summaries[i].confidence; e->presence_level = summaries[i].level; e->f0_hz = summaries[i].f0;
    return true;
  }
  return false;
}

/* ---- HAL port of the driver ---- */
static int spi_transfer(void *ctx, unsigned bus, const uint8_t *tx, uint8_t *rx, size_t len) { (void)ctx; (void)bus; return bsp_spi_transfer(tx, rx, len) ? 0 : -1; }
static void gpio_write(void *ctx, unsigned id, bool level) { (void)ctx; bsp_lora_pin_write((bsp_lora_pin_t)id, level); }
static bool gpio_read(void *ctx, unsigned id) { (void)ctx; return bsp_lora_pin_read((bsp_lora_pin_t)id); }
static void delay(void *ctx, uint32_t ms) { (void)ctx; vTaskDelay(pdMS_TO_TICKS(ms)); }
static uint32_t millis(void *ctx) { (void)ctx; return xTaskGetTickCount(); }
static const zs_hal_port_t hal = {NULL, millis, delay, NULL, spi_transfer, NULL, NULL, gpio_write, gpio_read};

/* ---- radio port of the uplink: DRY (log only) or LIVE (SetTx + receive window) ---- */
static bool tx(void *ctx, const uint8_t *frame, size_t n) {
  (void)ctx;
  const uint32_t airtime = zs_lora_airtime_ms(n, APP_LORA_SF, APP_LORA_BW_HZ, 5u);
  if (!APP_LORA_TX_ENABLED) {
    dry_frames++;
    if (log_fn) log_fn("lora: DRY frame %lu (%u B, airtime %lu ms, budget %lu ms): %02x%02x%02x%02x...\r\n", (unsigned long)dry_frames, (unsigned)n, (unsigned long)airtime, (unsigned long)uplink.budget_ms, frame[0], frame[1], frame[2], frame[3]);
    return true;                                                     /* the uplink books the airtime; no ACK will come */
  }
  if (!radio_ok || !zs_sx1262_transmit(&radio, frame, n, airtime + 500u)) { radio_errors++; return false; }
  live_frames++;
  return true;
}
static const zs_lora_uplink_port_t port = {NULL, tx, summarize};

void app_lora_bind(const zs_event_outbox_io_t *outbox, uint32_t id, const uint8_t key[32], void (*log)(const char *fmt, ...)) {
  outbox_io = outbox; station_id = id; log_fn = log;
  if (key) { memcpy(engineer_key, key, sizeof(engineer_key)); key_set = true; }
  bound = outbox && id;
}
void app_lora_set_route_hint(bool lora_preferred) { route_lora = lora_preferred; }

static bool radio_bring_up(void) {
  zs_sx1262_init(&radio, &hal, 0u, BSP_LORA_PIN_NSS, BSP_LORA_PIN_BUSY, BSP_LORA_PIN_RESET);
  zs_sx1262_set_packet_pins(&radio, BSP_LORA_PIN_DIO1, BSP_LORA_PIN_TXEN, BSP_LORA_PIN_RXEN);
  if (!zs_sx1262_reset(&radio)) return false;
  return zs_sx1262_configure_lora(&radio, APP_LORA_FREQUENCY_HZ, APP_LORA_SF, APP_LORA_BW_HZ, 5u, APP_LORA_TX_DBM, ZS_SX1262_SYNC_WORD_PRIVATE);
}

/* LIVE only: after TxDone open the ACK window; on RxDone hand the frame to the uplink. */
static void radio_service(uint32_t now) {
  uint16_t irq;
  if (!APP_LORA_TX_ENABLED || !radio_ok) return;
  if (!zs_sx1262_irq_pending(&radio)) { if (rx_open && (int32_t)(now - rx_close_ms) >= 0) rx_open = false; return; }
  if (!zs_sx1262_read_irq(&radio, &irq)) { radio_errors++; return; }
  if (irq & ZS_SX1262_IRQ_TX_DONE) {
    if (zs_sx1262_receive(&radio, ZS_LORA_UPLINK_ACK_WINDOW_MS)) { rx_open = true; rx_close_ms = now + ZS_LORA_UPLINK_ACK_WINDOW_MS + 500u; }
  }
  if (irq & ZS_SX1262_IRQ_RX_DONE) {
    uint8_t frame[64]; size_t n;
    rx_open = false;
    if (zs_sx1262_read_packet(&radio, frame, sizeof(frame), &n) && zs_lora_uplink_on_rx(&uplink, frame, n, now)) { acks++; if (log_fn) log_fn("lora: ack -> delivered\r\n"); }
  }
  if (irq & ZS_SX1262_IRQ_TIMEOUT) rx_open = false;
}

void app_lora_task(void *arg) {
  bool uplink_ready = false;
  (void)arg;
  vTaskDelay(pdMS_TO_TICKS(500));
  radio_ok = bsp_spi_init() && radio_bring_up();
  if (log_fn) log_fn("lora: radio %s (%lu Hz, SF%u, %s)\r\n", radio_ok ? "up" : "NOT responding", (unsigned long)APP_LORA_FREQUENCY_HZ, APP_LORA_SF, APP_LORA_TX_ENABLED ? "LIVE" : "DRY: tx_enabled false until the RU868 profile and RF gate");
  if (radio_ok) (void)zs_sx1262_set_sleep(&radio);                 /* idle until the first frame */
  for (;;) {
    const uint32_t now = xTaskGetTickCount();
    if (!uplink_ready && bound && key_set) uplink_ready = zs_lora_uplink_init(&uplink, &port, outbox_io, station_id, APP_LORA_PROFILE_ID, engineer_key, APP_LORA_SF, APP_LORA_BW_HZ, now);
    if (uplink_ready) {
      const zs_lora_uplink_result_t r = zs_lora_uplink_tick(&uplink, now, route_lora);
      (void)r;
      radio_service(now);
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}

void app_lora_status(void (*print)(const char *fmt, ...)) {
  print("lora radio %s %s | route %s | frames dry %lu live %lu acks %lu timeouts %lu budget %lu ms airtime %lu ms | radio errors %lu spi errors %lu\r\n",
        radio_ok ? "up" : "down", APP_LORA_TX_ENABLED ? "LIVE" : "DRY", route_lora ? "lora" : "gsm",
        (unsigned long)dry_frames, (unsigned long)live_frames, (unsigned long)acks, (unsigned long)uplink.ack_timeouts,
        (unsigned long)uplink.budget_ms, (unsigned long)uplink.airtime_ms_total, (unsigned long)radio_errors, (unsigned long)bsp_spi_errors());
}

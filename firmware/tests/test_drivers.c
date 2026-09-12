#include "zs_audio.h"
#include "zs_bg95.h"
#include "zs_gnss.h"
#include "zs_sx1262.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  char uart[1024];
  size_t uart_size;
  uint8_t spi[128];
  size_t spi_size;
  bool gpio[32];
  uint32_t now_ms;
} mock_t;

static uint32_t millis(void *ctx) {
  return ((mock_t *)ctx)->now_ms;
}

static void delay_ms(void *ctx, uint32_t value) {
  ((mock_t *)ctx)->now_ms += value;
}

static int uart_write(void *ctx, unsigned channel, const uint8_t *data, size_t size) {
  mock_t *mock = ctx;
  (void)channel;
  if (mock->uart_size + size >= sizeof(mock->uart)) return -1;
  memcpy(mock->uart + mock->uart_size, data, size);
  mock->uart_size += size;
  mock->uart[mock->uart_size] = '\0';
  return 0;
}

static int spi_transfer(void *ctx, unsigned bus, const uint8_t *tx,
                        uint8_t *rx, size_t size) {
  mock_t *mock = ctx;
  (void)bus;
  if (size > sizeof(mock->spi)) return -1;
  memcpy(mock->spi, tx, size);
  mock->spi_size = size;
  if (rx) memset(rx, 0, size);
  return 0;
}

static void gpio_write(void *ctx, unsigned id, bool value) {
  mock_t *mock = ctx;
  if (id < 32u) mock->gpio[id] = value;
}

static bool gpio_read(void *ctx, unsigned id) {
  return id < 32u ? ((mock_t *)ctx)->gpio[id] : false;
}

static zs_hal_port_t port(mock_t *mock) {
  zs_hal_port_t io = {0};
  io.ctx = mock;
  io.millis = millis;
  io.delay_ms = delay_ms;
  io.uart_write = uart_write;
  io.spi_transfer = spi_transfer;
  io.gpio_write = gpio_write;
  io.gpio_read = gpio_read;
  return io;
}

static void test_bg95(void) {
  mock_t mock = {0};
  zs_hal_port_t io = port(&mock);
  zs_bg95_t modem;
  zs_bg95_init(&modem, &io, 1u, 1u, "internet");
  zs_bg95_power_on(&modem, 0u);
  assert(modem.state == ZS_BG95_POWERING);
  zs_bg95_tick(&modem, 700u);
  assert(modem.state == ZS_BG95_AT_SYNC);
  zs_bg95_tick(&modem, 700u);
  assert(strstr(mock.uart, "AT\r\n"));
  zs_bg95_on_line(&modem, "OK", 701u);
  assert(strstr(mock.uart, "AT+CPIN?"));
  zs_bg95_on_line(&modem, "+CPIN: READY", 702u);
  zs_bg95_on_line(&modem, "OK", 703u);
  assert(strstr(mock.uart, "AT+QCCID"));
  zs_bg95_on_line(&modem, "+QCCID: 89701012345678901234", 704u);
  zs_bg95_on_line(&modem, "OK", 705u);
  assert(strstr(mock.uart, "AT+CIMI"));
  zs_bg95_on_line(&modem, "250011234567890", 706u);
  zs_bg95_on_line(&modem, "OK", 707u);
  assert(strstr(mock.uart, "AT+COPS?"));
  zs_bg95_on_line(&modem, "ERROR", 708u);
  assert(strstr(mock.uart, "AT+CGDCONT=1,\"IP\",\"internet\""));
  zs_bg95_on_line(&modem, "OK", 709u);
  assert(strstr(mock.uart, "AT+CEREG?"));
  zs_bg95_on_line(&modem, "+CEREG: 0,1", 710u);
  assert(zs_bg95_ready(&modem));
  assert(modem.network == ZS_BG95_NET_LTE);
  assert(strcmp(modem.network_settings.imsi, "250011234567890") == 0);
  assert(strcmp(modem.network_settings.iccid, "89701012345678901234") == 0);
}

static void test_gnss(void) {
  zs_gnss_nmea_t gnss;
  zs_gnss_nmea_init(&gnss);
  assert(zs_gnss_parse_line(&gnss,
                            "$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.90,545.4,M,46.9,M,,"));
  assert(gnss.valid_fix && gnss.satellites == 8u && gnss.hdop_x100 == 90u);
  assert(gnss.position.alt_dm == 5454);
  assert(zs_gnss_parse_line(&gnss,
                            "$GNRMC,123520,A,4807.038,N,01131.000,E,10.0,84.4,230394,,,A"));
  assert(gnss.rmc_valid);
  assert(gnss.course_cdeg == 8440u);
  assert(gnss.utc_epoch_valid);
  assert(gnss.utc_epoch_us == INT64_C(764426120000000));
  assert(strcmp(gnss.utc_ddmmyy, "230394") == 0);
}

static void test_sx1262(void) {
  mock_t mock = {0};
  zs_hal_port_t io = port(&mock);
  zs_sx1262_t radio;
  unsigned i;
  zs_sx1262_init(&radio, &io, 2u, 2u, 3u, 4u);
  for (i = 0u; i < 7u; ++i) {
    assert(zs_sx1262_frequency_allowed_ru868(zs_ru868_candidate_channels_hz[i]));
  }
  assert(!zs_sx1262_frequency_allowed_ru868(868100000u));
  assert(!zs_sx1262_set_frequency(&radio, 868300000u));
  assert(zs_sx1262_set_frequency(&radio, zs_ru868_candidate_channels_hz[5]));
  assert(radio.frequency_hz == 868900000u);
  assert(zs_sx1262_set_lora_modulation(&radio, 9u, 125000u, 5u));
  assert(zs_sx1262_start_rx_duty_cycle(&radio, 500000u, 9500000u));
}

static void test_audio(void) {
  int16_t memory[8u * 4u];
  zs_audio_ring_t ring;
  int16_t output[4];
  int i;
  zs_audio_ring_init(&ring, memory, 8u, 32000u);
  for (i = 0; i < 10; ++i) {
    int16_t frame[4] = {(int16_t)i, (int16_t)(i + 10),
                        (int16_t)(i + 20), (int16_t)(i + 30)};
    zs_audio_ring_push(&ring, frame);
  }
  assert(zs_audio_ring_copy_mono(&ring, 10u, 4u, output, 0u));
  assert(output[0] == 6 && output[3] == 9);
  assert(zs_audio_ring_copy_average(&ring, 10u, 4u, output));
  assert(output[0] == 21 && output[3] == 24);
}

int main(void) {
  test_bg95();
  test_gnss();
  test_sx1262();
  test_audio();
  puts("zs_driver_tests: OK");
  return 0;
}

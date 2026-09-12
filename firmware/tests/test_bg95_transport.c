#include "zs_bg95.h"

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  char uart[4096];
  size_t used;
  bool gpio[8];
} mock_t;

static int uart_write(void *ctx, unsigned channel, const uint8_t *data, size_t len) {
  mock_t *mock = ctx;
  (void)channel;
  if (mock->used + len >= sizeof(mock->uart)) return -1;
  memcpy(mock->uart + mock->used, data, len);
  mock->used += len;
  mock->uart[mock->used] = '\0';
  return 0;
}

static void gpio_write(void *ctx, unsigned id, bool level) {
  mock_t *mock = ctx;
  if (id < 8u) mock->gpio[id] = level;
}

static zs_hal_port_t port(mock_t *mock) {
  zs_hal_port_t io = {0};
  io.ctx = mock;
  io.uart_write = uart_write;
  io.gpio_write = gpio_write;
  return io;
}

static void expect_last(const zs_bg95_t *modem, const char *command) {
  assert(strcmp(modem->last_command, command) == 0);
  assert(modem->command_pending);
}

static void reach_registered(zs_bg95_t *modem, mock_t *mock, const char *apn) {
  zs_hal_port_t io = port(mock);
  zs_bg95_init(modem, &io, 1u, 2u, apn);
  zs_bg95_power_on(modem, 0u);
  assert(mock->gpio[2]);
  zs_bg95_tick(modem, 700u);
  assert(!mock->gpio[2]);
  zs_bg95_tick(modem, 700u);
  expect_last(modem, "AT");
  zs_bg95_on_line(modem, "OK", 701u);
  expect_last(modem, "AT+CPIN?");
  zs_bg95_on_line(modem, "+CPIN: READY", 702u);
  assert(strstr(modem->last_command, "AT+CGDCONT=1,\"IP\"") != NULL);
  zs_bg95_on_line(modem, "OK", 703u);
  expect_last(modem, "AT+CEREG?");
  zs_bg95_on_line(modem, "+CEREG: 2,1,\"001A\",\"00BC1234\",8", 704u);
  assert(modem->state == ZS_BG95_READY);
}

static void test_mqtt_tls_happy_path(void) {
  mock_t mock = {0};
  zs_bg95_t modem;
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                    "dioneya-001-boot1", "UFS:pilot-ca.pem", true));
  assert(zs_bg95_start_mqtt(&modem, 1000u));
  expect_last(&modem, "AT+QIACT=1");
  zs_bg95_on_line(&modem, "OK", 1001u);
  expect_last(&modem, "AT+QSSLCFG=\"sslversion\",1,4");
  zs_bg95_on_line(&modem, "OK", 1002u);
  expect_last(&modem, "AT+QSSLCFG=\"seclevel\",1,2");
  zs_bg95_on_line(&modem, "OK", 1003u);
  expect_last(&modem, "AT+QSSLCFG=\"cacert\",1,\"UFS:pilot-ca.pem\"");
  zs_bg95_on_line(&modem, "OK", 1004u);
  expect_last(&modem, "AT+QMTCFG=\"ssl\",0,1,1");
  zs_bg95_on_line(&modem, "OK", 1005u);
  expect_last(&modem, "AT+QMTOPEN=0,\"pilot.example\",443");
  zs_bg95_on_line(&modem, "OK", 1006u);
  assert(modem.state == ZS_BG95_MQTT_OPENING);
  zs_bg95_on_line(&modem, "+QMTOPEN: 0,0", 1010u);
  expect_last(&modem, "AT+QMTCONN=0,\"dioneya-001-boot1\"");
  zs_bg95_on_line(&modem, "+QMTCONN: 0,0,0", 1011u);
  assert(zs_bg95_online(&modem));
  assert(modem.mqtt_open && modem.mqtt_connected);
}

static void test_fail_closed_policy_and_urc(void) {
  mock_t mock = {0};
  zs_bg95_t modem;
  reach_registered(&modem, &mock, "private.apn");
  assert(!zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                     "dioneya-001", "UFS:ca.pem", true));
  assert(!zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 1883u,
                                     "dioneya-001", "UFS:ca.pem", true));
  assert(!zs_bg95_configure_mqtt_tls(&modem, "pilot.example\"", 443u,
                                     "dioneya-001", "UFS:ca.pem", true));
  assert(!zs_bg95_start_mqtt(&modem, 2000u));

  memset(&mock, 0, sizeof(mock));
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 8883u,
                                    "dioneya-001", "UFS:ca.pem", true));
  assert(zs_bg95_start_mqtt(&modem, 3000u));
  zs_bg95_on_line(&modem, "ERROR", 3001u);
  assert(modem.state == ZS_BG95_ERROR);
  assert(!zs_bg95_online(&modem));

  memset(&mock, 0, sizeof(mock));
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                    "dioneya-001", "UFS:ca.pem", true));
  assert(!zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 1883u,
                                     "dioneya-001", "UFS:ca.pem", true));
  assert(!modem.transport_configured);
}

static void test_timeout_and_negative_results(void) {
  mock_t mock = {0};
  zs_bg95_t modem;
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                    "dioneya-001", "UFS:ca.pem", true));
  assert(zs_bg95_start_mqtt(&modem, 4000u));
  zs_bg95_tick(&modem, 124000u);
  assert(modem.state == ZS_BG95_ERROR);

  memset(&mock, 0, sizeof(mock));
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                    "dioneya-001", "UFS:ca.pem", true));
  assert(zs_bg95_start_mqtt(&modem, 5000u));
  zs_bg95_on_line(&modem, "OK", 5001u);
  zs_bg95_on_line(&modem, "OK", 5002u);
  zs_bg95_on_line(&modem, "OK", 5003u);
  zs_bg95_on_line(&modem, "OK", 5004u);
  zs_bg95_on_line(&modem, "OK", 5005u);
  zs_bg95_on_line(&modem, "+QMTOPEN: 0,3", 5006u);
  assert(modem.state == ZS_BG95_ERROR);

  memset(&mock, 0, sizeof(mock));
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                    "dioneya-001", "UFS:ca.pem", true));
  assert(zs_bg95_start_mqtt(&modem, 6000u));
  zs_bg95_on_line(&modem, "+CEREG: 0,2", 6001u);
  assert(modem.state == ZS_BG95_ERROR);
}

int main(void) {
  test_mqtt_tls_happy_path();
  test_fail_closed_policy_and_urc();
  test_timeout_and_negative_results();
  puts("zs_bg95_transport_tests: OK");
  return 0;
}

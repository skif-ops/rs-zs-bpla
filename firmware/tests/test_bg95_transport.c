#include "zs_bg95.h"

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  char uart[8192];
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

static bool bytes_contain(const void *object, size_t size, const char *text) {
  const unsigned char *bytes = object;
  size_t i, n = strlen(text);
  if (n == 0u || n > size) return false;
  for (i = 0u; i + n <= size; ++i) {
    if (memcmp(bytes + i, text, n) == 0) return true;
  }
  return false;
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
  expect_last(modem, "AT+CPIN?");
  zs_bg95_on_line(modem, "OK", 703u);
  assert(strstr(modem->last_command, "AT+CGDCONT=1,\"IP\"") != NULL);
  zs_bg95_on_line(modem, "OK", 704u);
  expect_last(modem, "AT+CEREG?");
  zs_bg95_on_line(modem, "+CEREG: 2,1,\"001A\",\"00BC1234\",8", 705u);
  assert(modem->state == ZS_BG95_READY);
}

static void provide_pdp_settings(zs_bg95_t *modem, uint32_t now_ms, const char *apn) {
  char line[320];
  int n;
  zs_bg95_on_line(modem, "OK", now_ms);
  expect_last(modem, "AT+CGCONTRDP=1");
  n = snprintf(line, sizeof(line),
               "+CGCONTRDP: 1,5,\"%s\",\"10.10.0.2.255.255.255.0\","
               "\"10.10.0.1\",\"1.1.1.1\",\"8.8.8.8\"", apn);
  assert(n > 0 && (size_t)n < sizeof(line));
  zs_bg95_on_line(modem, line, now_ms + 1u);
  zs_bg95_on_line(modem, "OK", now_ms + 2u);
  expect_last(modem, "AT+QSSLCFG=\"sslversion\",1,4");
}

static void test_mqtt_tls_happy_path(void) {
  mock_t mock = {0};
  zs_bg95_t modem;
  const zs_bg95_network_settings_t *settings;
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                    "dioneya-001-boot1", "UFS:pilot-ca.pem", true));
  assert(zs_bg95_start_mqtt(&modem, 1000u));
  expect_last(&modem, "AT+QIACT=1");
  provide_pdp_settings(&modem, 1001u, "internet");
  settings = zs_bg95_get_network_settings(&modem);
  assert(settings && settings->valid);
  assert(strcmp(settings->apn, "internet") == 0);
  assert(strcmp(settings->local_address, "10.10.0.2.255.255.255.0") == 0);
  assert(strcmp(settings->gateway, "10.10.0.1") == 0);
  assert(strcmp(settings->primary_dns, "1.1.1.1") == 0);
  assert(strcmp(settings->secondary_dns, "8.8.8.8") == 0);
  zs_bg95_on_line(&modem, "OK", 1004u);
  expect_last(&modem, "AT+QSSLCFG=\"seclevel\",1,2");
  zs_bg95_on_line(&modem, "OK", 1005u);
  expect_last(&modem, "AT+QSSLCFG=\"cacert\",1,\"UFS:pilot-ca.pem\"");
  zs_bg95_on_line(&modem, "OK", 1006u);
  expect_last(&modem, "AT+QMTCFG=\"ssl\",0,1,1");
  zs_bg95_on_line(&modem, "OK", 1007u);
  expect_last(&modem, "AT+QMTOPEN=0,\"pilot.example\",443");
  zs_bg95_on_line(&modem, "OK", 1008u);
  assert(modem.state == ZS_BG95_MQTT_OPENING);
  zs_bg95_on_line(&modem, "+QMTOPEN: 0,0", 1010u);
  expect_last(&modem, "AT+QMTCONN=0,\"dioneya-001-boot1\"");
  zs_bg95_on_line(&modem, "+QMTCONN: 0,0,0", 1011u);
  assert(zs_bg95_online(&modem));
  assert(modem.mqtt_open && modem.mqtt_connected);
}

static void boot_to_auto_apn(zs_bg95_t *modem, mock_t *mock,
                             const zs_bg95_apn_profile_t *profiles,
                             size_t profile_count, const char *imsi,
                             const char *network_apn) {
  zs_hal_port_t io = port(mock);
  char line[96];
  int n;
  zs_bg95_init(modem, &io, 1u, 2u, NULL);
  assert(zs_bg95_configure_auto_network(modem, profiles, profile_count));
  assert(zs_bg95_configure_mqtt_tls(modem, "pilot.example", 443u,
                                    "dioneya-auto", "UFS:pilot-ca.pem", true));
  zs_bg95_power_on(modem, 0u);
  zs_bg95_tick(modem, 700u);
  zs_bg95_tick(modem, 700u);
  zs_bg95_on_line(modem, "OK", 701u);
  expect_last(modem, "AT+CPIN?");
  zs_bg95_on_line(modem, "+CPIN: READY", 702u);
  zs_bg95_on_line(modem, "OK", 703u);
  expect_last(modem, "AT+QCCID");
  zs_bg95_on_line(modem, "+QCCID: 89701012345678901234", 704u);
  zs_bg95_on_line(modem, "OK", 705u);
  expect_last(modem, "AT+CIMI");
  zs_bg95_on_line(modem, imsi, 706u);
  assert(modem->state != ZS_BG95_ERROR);
  zs_bg95_on_line(modem, "OK", 707u);
  expect_last(modem, "AT+COPS?");
  zs_bg95_on_line(modem, "+COPS: 0,0,\"Test Operator\",7", 708u);
  zs_bg95_on_line(modem, "OK", 709u);
  expect_last(modem, "AT+CGNAPN");
  n = snprintf(line, sizeof(line), "+CGNAPN: 1,\"%s\"", network_apn);
  assert(n > 0 && (size_t)n < sizeof(line));
  zs_bg95_on_line(modem, line, 710u);
  zs_bg95_on_line(modem, "OK", 711u);
}

static void test_automatic_network_settings(void) {
  static const zs_bg95_apn_profile_t profiles[] = {
    {"25001", "", true, true},
    {"25002", "catalog.apn", true, false}
  };
  mock_t mock = {0};
  zs_bg95_t modem;
  const zs_bg95_network_settings_t *settings;
  const char *full_imsi = "250011234567890";
  const char *full_iccid = "89701012345678901234";

  boot_to_auto_apn(&modem, &mock, profiles, 2u, full_imsi, "network.apn");
  expect_last(&modem, "AT+CGDCONT=1,\"IP\",\"network.apn\"");
  assert(modem.network_settings.apn_source == ZS_BG95_APN_NETWORK);
  assert(strcmp(modem.network_settings.home_plmn, "25001") == 0);
  assert(strcmp(modem.network_settings.iccid_suffix, "1234") == 0);
  assert(strcmp(modem.network_settings.registered_operator, "Test Operator") == 0);
  assert(modem.network_settings.access_technology == 7u);
  assert(!bytes_contain(&modem, sizeof(modem), full_imsi));
  assert(!bytes_contain(&modem, sizeof(modem), full_iccid));

  zs_bg95_on_line(&modem, "OK", 712u);
  expect_last(&modem, "AT+CEREG?");
  zs_bg95_on_line(&modem, "+CEREG: 2,1", 713u);
  assert(zs_bg95_start_mqtt(&modem, 714u));
  provide_pdp_settings(&modem, 715u, "network.apn");
  settings = zs_bg95_get_network_settings(&modem);
  assert(settings && settings->valid);
  assert(settings->apn_source == ZS_BG95_APN_NETWORK);
}

static void test_catalog_fallback_and_unknown_sim(void) {
  static const zs_bg95_apn_profile_t profiles[] = {
    {"25002", "catalog.apn", true, false}
  };
  mock_t mock = {0};
  zs_bg95_t modem;
  zs_hal_port_t io = port(&mock);

  zs_bg95_init(&modem, &io, 1u, 2u, NULL);
  assert(zs_bg95_configure_auto_network(&modem, profiles, 1u));
  zs_bg95_power_on(&modem, 0u);
  zs_bg95_tick(&modem, 700u);
  zs_bg95_tick(&modem, 700u);
  zs_bg95_on_line(&modem, "OK", 701u);
  zs_bg95_on_line(&modem, "+CPIN: READY", 702u);
  zs_bg95_on_line(&modem, "OK", 703u);
  expect_last(&modem, "AT+QCCID");
  zs_bg95_on_line(&modem, "ERROR", 704u);
  expect_last(&modem, "AT+CIMI");
  zs_bg95_on_line(&modem, "250021234567890", 705u);
  zs_bg95_on_line(&modem, "OK", 706u);
  expect_last(&modem, "AT+COPS?");
  zs_bg95_on_line(&modem, "ERROR", 707u);
  expect_last(&modem, "AT+CGNAPN");
  zs_bg95_on_line(&modem, "ERROR", 708u);
  expect_last(&modem, "AT+CGDCONT=1,\"IP\",\"catalog.apn\"");
  assert(modem.network_settings.apn_source == ZS_BG95_APN_CATALOG);

  memset(&mock, 0, sizeof(mock));
  io = port(&mock);
  zs_bg95_init(&modem, &io, 1u, 2u, NULL);
  assert(zs_bg95_configure_auto_network(&modem, profiles, 1u));
  zs_bg95_power_on(&modem, 0u);
  zs_bg95_tick(&modem, 700u);
  zs_bg95_tick(&modem, 700u);
  zs_bg95_on_line(&modem, "OK", 701u);
  zs_bg95_on_line(&modem, "+CPIN: READY", 702u);
  zs_bg95_on_line(&modem, "OK", 703u);
  zs_bg95_on_line(&modem, "ERROR", 704u);
  zs_bg95_on_line(&modem, "999991234567890", 705u);
  assert(modem.state == ZS_BG95_ERROR);
}

static void test_fail_closed_policy_and_urc(void) {
  static const zs_bg95_apn_profile_t private_profile[] = {
    {"25001", "private.apn", true, false}
  };
  static const zs_bg95_apn_profile_t unapproved_profile[] = {
    {"25001", "internet", false, false}
  };
  static const zs_bg95_apn_profile_t duplicate_profiles[] = {
    {"25001", "internet", true, false},
    {"25001", "alternate", true, false}
  };
  mock_t mock = {0};
  zs_bg95_t modem;
  zs_hal_port_t io = port(&mock);

  zs_bg95_init(&modem, &io, 1u, 2u, "private.apn");
  assert(modem.apn[0] == '\0');
  assert(!zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                     "dioneya-001", "UFS:ca.pem", true));
  assert(!zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 1883u,
                                     "dioneya-001", "UFS:ca.pem", true));
  assert(!zs_bg95_configure_mqtt_tls(&modem, "pilot.example\"", 443u,
                                     "dioneya-001", "UFS:ca.pem", true));
  assert(!zs_bg95_start_mqtt(&modem, 2000u));

  zs_bg95_init(&modem, &io, 1u, 2u, NULL);
  assert(!zs_bg95_configure_auto_network(&modem, private_profile, 1u));
  assert(!zs_bg95_configure_auto_network(&modem, unapproved_profile, 1u));
  assert(!zs_bg95_configure_auto_network(&modem, duplicate_profiles, 2u));

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
  provide_pdp_settings(&modem, 5001u, "internet");
  zs_bg95_on_line(&modem, "OK", 5004u);
  zs_bg95_on_line(&modem, "OK", 5005u);
  zs_bg95_on_line(&modem, "OK", 5006u);
  zs_bg95_on_line(&modem, "OK", 5007u);
  zs_bg95_on_line(&modem, "+QMTOPEN: 0,3", 5008u);
  assert(modem.state == ZS_BG95_ERROR);

  memset(&mock, 0, sizeof(mock));
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                    "dioneya-001", "UFS:ca.pem", true));
  assert(zs_bg95_start_mqtt(&modem, 6000u));
  zs_bg95_on_line(&modem, "OK", 6001u);
  zs_bg95_on_line(&modem,
                  "+CGCONTRDP: 1,5,\"wrong.apn\",\"10.0.0.2\",\"10.0.0.1\",\"1.1.1.1\"",
                  6002u);
  assert(modem.state == ZS_BG95_ERROR);

  memset(&mock, 0, sizeof(mock));
  reach_registered(&modem, &mock, "internet");
  assert(zs_bg95_configure_mqtt_tls(&modem, "pilot.example", 443u,
                                    "dioneya-001", "UFS:ca.pem", true));
  assert(zs_bg95_start_mqtt(&modem, 7000u));
  zs_bg95_on_line(&modem, "+CEREG: 0,2", 7001u);
  assert(modem.state == ZS_BG95_ERROR);
}

int main(void) {
  test_mqtt_tls_happy_path();
  test_automatic_network_settings();
  test_catalog_fallback_and_unknown_sim();
  test_fail_closed_policy_and_urc();
  test_timeout_and_negative_results();
  puts("zs_bg95_transport_tests: OK");
  return 0;
}

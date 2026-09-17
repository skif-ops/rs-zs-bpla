#include "zs_protocol.h"

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static bool contains_bytes(const uint8_t *data, size_t size, const char *text) {
  size_t i, n = strlen(text);
  if (n == 0u || n > size) return false;
  for (i = 0u; i + n <= size; ++i) {
    if (memcmp(data + i, text, n) == 0) return true;
  }
  return false;
}

static zs_heartbeat_t heartbeat(void) {
  zs_heartbeat_t message = {0};
  message.schema_ver = 1u;
  message.station_id = 424242u;
  message.time_us = INT64_C(1780000000000000);
  message.station.lat_e7 = 557550800;
  message.station.lon_e7 = 376176300;
  message.station.alt_dm = 1560;
  message.station.pos_accuracy_m = 8u;
  message.station.altitude_source = 1u;
  message.station.position_source = ZS_POSITION_SOURCE_CONFIGURED_INSTALL;
  message.gnss.fix_type = 3u;
  message.gnss.satellites = 12u;
  message.gnss.hdop_x100 = 80u;
  message.gnss.pps_ok = true;
  message.gnss.expected_time_error_us = 65u;
  message.gnss.position_trust = ZS_POSITION_TRUST_CONFIGURED_OK;
  message.gnss.time_trust = ZS_TIME_TRUST_GNSS_TRUSTED;
  message.power.battery_pct = 81u;
  message.power.battery_mv = 12750u;
  message.power.solar_mv = 18100u;
  message.power.temperature_c10 = 245;
  message.power.battery_bus_mv = 12750u;
  message.power.battery_current_ma = -500;
  message.power.battery_power_mw = 6375u;
  message.power.monitor_status = 0u;
  message.route.transport = ZS_ROUTE_LTE;
  message.route.rssi_dbm = -72;
  message.route.snr_db10 = 90;
  strcpy(message.cellular.imsi, "250011234567890");
  strcpy(message.cellular.iccid, "89701012345678901234");
  strcpy(message.cellular.home_plmn, "25001");
  strcpy(message.cellular.registered_operator, "Test Operator");
  strcpy(message.cellular.apn, "network.apn");
  strcpy(message.cellular.local_address, "10.10.0.2.255.255.255.0");
  strcpy(message.cellular.gateway, "10.10.0.1");
  strcpy(message.cellular.primary_dns, "1.1.1.1");
  strcpy(message.cellular.secondary_dns, "8.8.8.8");
  message.cellular.access_technology = 7u;
  message.cellular.apn_source = 2u;
  message.cellular.settings_valid = true;
  strcpy(message.firmware_ver, "evt-pre-20-test");
  strcpy(message.model_ver, "model-test");
  strcpy(message.hardware_rev, "EVT-PRE-20-Rev.A");
  message.self_test_ok = true;
  return message;
}

int main(void) {
  uint8_t encoded[1024];
  zs_heartbeat_t message = heartbeat();
  size_t size = zs_protocol_encode_heartbeat(&message, encoded, sizeof(encoded));
  assert(size > 0u && size < sizeof(encoded));
  assert(contains_bytes(encoded, size, message.cellular.imsi));
  assert(contains_bytes(encoded, size, message.cellular.iccid));
  assert(zs_protocol_encode_heartbeat(&message, encoded, 32u) == 0u);

  strcpy(message.cellular.imsi, "invalid");
  assert(zs_protocol_encode_heartbeat(&message, encoded, sizeof(encoded)) == 0u);
  message = heartbeat();
  message.cellular.settings_valid = false;
  assert(zs_protocol_encode_heartbeat(&message, encoded, sizeof(encoded)) == 0u);

  puts("zs_heartbeat_telemetry_tests: OK");
  return 0;
}

#include "zs_protocol.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(void) {
  zs_heartbeat_t message = {0};
  uint8_t encoded[1024];
  size_t size;

  message.schema_ver = 2u;   /* with the detector map (key 13); schema 1 = the same without it */
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
  message.self_test_ok = false;               /* a required self-test failed: see detector key 15 */
  message.detector_present = true;
  message.detector.boot_id = 7u;
  message.detector.uptime_s = 3600u;
  message.detector.windows = 7190u;
  message.detector.windows_dropped = 2u;
  message.detector.confirmed_windows = 120u;
  message.detector.suspect_windows = 45u;
  message.detector.engine_windows = 300u;
  message.detector.events_emitted = 13u;
  message.detector.events_refused = 0u;
  message.detector.outbox_pending = 1u;
  message.detector.window_max_ms = 187u;
  message.detector.presence_level = 3u;
  message.detector.reset_cause = 4u;          /* IWDG: the previous boot ended by the hardware watchdog */
  message.detector.watchdog_missed = 0x0020u;  /* task 5 had stopped checking in */
  message.detector.params_version = 3u;        /* runtime parameter set v3 (CMD_SET_PARAMS) */
  message.detector.selftest_failed = 0x0010u;  /* mic_capture (id 4) failed */
  message.detector.command_key_id = UINT64_C(0xa1b2c3d4e5f60718);       /* addendum E: rotation in flight */
  message.detector.command_next_key_id = UINT64_C(0x0102030405060708);
  message.detector.fw_version = 7u; message.detector.fw_state = 3u;       /* addendum F: v7 on trial, */
  message.detector.fw_other_version = 6u;                                 /* v6 in the other bank */
  message.detector.net_config_version = 4u; message.detector.net_state = 3u;   /* addendum G: v4 in use, */
  message.detector.net_failed_version = 5u;                               /* v5 failed its trial and was rolled back */

  size = zs_protocol_encode_heartbeat(&message, encoded, sizeof(encoded));
  if (size == 0u || fwrite(encoded, 1u, size, stdout) != size) return 1;
  return 0;
}

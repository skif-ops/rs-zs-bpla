#include "zs_protocol.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
  zs_detection_t m;
  memset(&m, 0, sizeof(m));

  m.schema_ver = 4;
  m.station_id = 424242;
  m.seq_no = 7;
  m.boot_id = 9;
  m.event_id = 0x0102030405060708ULL;
  m.event_time_us = 1780000000123456LL;
  m.station.lat_e7 = 557550000;
  m.station.lon_e7 = 376150000;
  m.station.alt_dm = 1870;
  m.gnss.pps_ok = true;
  m.gnss.fix_type = 3;
  m.gnss.satellites = 17;
  m.gnss.hdop_x100 = 72;
  m.gnss.expected_time_error_us = 65;

  m.classification.class_id = ZS_CLASS_PISTON_UAV;
  m.classification.confidence_u8 = 231;
  m.hierarchy.family_id = ZS_FAMILY_PROP_PISTON;
  m.hierarchy.family_confidence_u8 = 220;
  m.hierarchy.type_id = ZS_TYPE_UNKNOWN;
  m.hierarchy.type_confidence_u8 = 42;
  m.hierarchy.family_status = ZS_DECISION_PROVISIONAL;
  m.hierarchy.type_status = ZS_DECISION_UNKNOWN;

  m.single_station.height_dm = 1250;
  m.single_station.height_sigma_dm = 450;
  m.single_station.speed_dmps = 125;
  m.single_station.speed_sigma_dmps = 45;
  m.single_station.confidence_u8 = 104;
  m.single_station.valid_flags = 0x03u;
  m.single_station.motion_hint = ZS_MOTION_APPROACH;

  m.detector_profile = 1;
  m.sample_rate_hz = 32000;
  for (unsigned i = 0; i < ZS_FEATURE_COUNT; i++) {
    m.features[i] = (float)i / 8.0f;
  }

  m.power.battery_pct = 83;
  m.power.battery_mv = 12750;
  m.power.solar_mv = 18200;
  m.power.temperature_c10 = -125;
  m.power.battery_bus_mv = 12750;
  m.power.battery_current_ma = 1000;
  m.power.battery_power_mw = 12750;
  m.power.monitor_status = 0;
  m.route.transport = ZS_ROUTE_LORA;
  m.route.hop_count = 3;
  m.route.rssi_dbm = -91;
  m.route.snr_db10 = 75;
  m.route.gateway_id = 77;
  m.doa.valid = true;
  m.doa.azimuth_cdeg = 27123;
  m.doa.elevation_cdeg = 850;
  m.doa.sigma_cdeg = 600;

  m.spatial.tdoa12_us = -117;
  m.spatial.tdoa13_us = 46;
  m.spatial.tdoa14_us = -311;
  m.spatial.residual_us = 7;
  m.spatial.confidence_u8 = 209;
  m.spatial.geometry_id = 1;
  m.spatial.valid_flags = 0x03u;

  unsigned char b[512];
  const bool summary = argc > 1 && strcmp(argv[1], "--summary") == 0;
  size_t n = summary ? zs_protocol_encode_detection_summary(&m, b, sizeof(b))
                     : zs_protocol_encode_detection(&m, b, sizeof(b));
  if (!n) {
    return 2;
  }
  return fwrite(b, 1, n, stdout) == n ? 0 : 3;
}

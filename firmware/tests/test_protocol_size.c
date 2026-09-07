#include "zs_protocol.h"

#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(void) {
  zs_detection_t m;
  memset(&m, 0, sizeof(m));

  m.schema_ver = 3u;
  m.station_id = UINT32_MAX;
  m.seq_no = UINT32_MAX;
  m.boot_id = UINT32_MAX;
  m.event_id = UINT64_MAX;
  m.event_time_us = INT64_MAX;

  m.station.lat_e7 = INT32_MIN;
  m.station.lon_e7 = INT32_MAX;
  m.station.alt_dm = INT32_MIN;

  m.gnss.pps_ok = true;
  m.gnss.jam = true;
  m.gnss.spoof = true;
  m.gnss.fix_type = UINT8_MAX;
  m.gnss.satellites = UINT8_MAX;
  m.gnss.hdop_x100 = UINT16_MAX;
  m.gnss.expected_time_error_us = UINT32_MAX;

  m.classification.class_id = UINT8_MAX;
  m.classification.confidence_u8 = UINT8_MAX;
  m.detector_profile = UINT8_MAX;
  m.sample_rate_hz = UINT16_MAX;

  m.power.battery_pct = 100u;
  m.power.battery_mv = UINT16_MAX;
  m.power.solar_mv = UINT16_MAX;
  m.power.temperature_c10 = INT16_MIN;
  m.route.transport = ZS_ROUTE_LORA;
  m.route.hop_count = 15u;
  m.route.rssi_dbm = INT16_MIN;
  m.route.snr_db10 = INT16_MAX;
  m.route.gateway_id = UINT32_MAX;

  m.doa.azimuth_cdeg = INT16_MAX;
  m.doa.elevation_cdeg = INT16_MIN;
  m.doa.sigma_cdeg = UINT16_MAX;
  m.doa.valid = true;

  m.hierarchy.family_id = UINT8_MAX;
  m.hierarchy.family_confidence_u8 = UINT8_MAX;
  m.hierarchy.type_id = UINT8_MAX;
  m.hierarchy.type_confidence_u8 = UINT8_MAX;
  m.hierarchy.family_status = UINT8_MAX;
  m.hierarchy.type_status = UINT8_MAX;

  m.single_station.height_dm = INT16_MIN;
  m.single_station.height_sigma_dm = UINT16_MAX;
  m.single_station.speed_dmps = UINT16_MAX;
  m.single_station.speed_sigma_dmps = UINT16_MAX;
  m.single_station.confidence_u8 = UINT8_MAX;
  m.single_station.valid_flags = UINT8_MAX;
  m.single_station.motion_hint = UINT8_MAX;

  m.spatial.tdoa12_us = INT16_MIN;
  m.spatial.tdoa13_us = INT16_MAX;
  m.spatial.tdoa14_us = INT16_MIN;
  m.spatial.residual_us = UINT16_MAX;
  m.spatial.confidence_u8 = UINT8_MAX;
  m.spatial.geometry_id = UINT8_MAX;
  m.spatial.valid_flags = UINT8_MAX;

  uint8_t buffer[512];
  const size_t n = zs_protocol_encode_detection_summary(&m, buffer, sizeof(buffer));
  assert(n > 0u);
  assert(n <= 220u);

  printf("zs_protocol_size_tests: worst-case P0=%zu bytes\n", n);
  return 0;
}

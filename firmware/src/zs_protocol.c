#include "zs_protocol.h"
#include "zs_cbor.h"
#include <ctype.h>
#include <string.h>

uint16_t zs_float_to_f16(float f) {
  uint32_t x;
  memcpy(&x, &f, sizeof(x));
  const uint32_t sign = (x >> 16) & 0x8000u;
  int32_t exp = (int32_t)((x >> 23) & 0xffu) - 127 + 15;
  uint32_t mant = x & 0x7fffffu;
  if (exp <= 0) {
    if (exp < -10) return (uint16_t)sign;
    mant = (mant | 0x800000u) >> (1 - exp);
    return (uint16_t)(sign + ((mant + 0x1000u) >> 13));
  }
  if (exp >= 31) return (uint16_t)(sign | 0x7c00u);
  return (uint16_t)(sign | ((uint32_t)exp << 10) | ((mant + 0x1000u) >> 13));
}

static void kvu(zs_cbor_t *c, uint64_t k, uint64_t v) { zs_cbor_uint(c, k); zs_cbor_uint(c, v); }
static void kvi(zs_cbor_t *c, uint64_t k, int64_t v) { zs_cbor_uint(c, k); zs_cbor_int(c, v); }
static void kvb(zs_cbor_t *c, uint64_t k, bool v) { zs_cbor_uint(c, k); zs_cbor_bool(c, v); }
static void kvt(zs_cbor_t *c, uint64_t k, const char *v) { zs_cbor_uint(c, k); zs_cbor_text(c, v); }

static size_t bounded_length(const char *text, size_t capacity) {
  size_t n = 0u;
  if (!text) return capacity;
  while (n < capacity && text[n] != '\0') ++n;
  return n;
}

static bool valid_text(const char *text, size_t capacity, bool allow_empty) {
  size_t n = bounded_length(text, capacity);
  return n < capacity && (allow_empty || n > 0u);
}

static bool valid_digits(const char *text, size_t capacity,
                         size_t minimum, size_t maximum) {
  size_t i, n = bounded_length(text, capacity);
  if (n < minimum || n > maximum || n >= capacity) return false;
  for (i = 0u; i < n; ++i) {
    if (!isdigit((unsigned char)text[i])) return false;
  }
  return true;
}

static size_t encode_detection_impl(const zs_detection_t *m, uint8_t *out, size_t cap, bool full) {
  if (!m || !out || cap == 0) return 0;

  zs_cbor_t c;
  zs_cbor_init(&c, out, cap);

  /* v1.5/schema 4: P0 summary keeps the established compact power/route map
     so the worst-case LoRa payload stays <=220 bytes. INA226 current/power/status
     are additive full-packet fields only. */
  zs_cbor_map(&c, full ? 15 : 13);
  kvu(&c, 0, m->schema_ver);
  kvu(&c, 1, 2);
  kvu(&c, 2, m->station_id);
  kvu(&c, 3, m->seq_no);
  kvu(&c, 4, m->boot_id);
  kvu(&c, 5, m->event_id);
  kvi(&c, 6, m->event_time_us);

  const uint16_t flags =
      (m->gnss.jam ? 1u : 0u) |
      (m->gnss.spoof ? 2u : 0u) |
      (m->station.position_source == ZS_POSITION_SOURCE_CONFIGURED_INSTALL ? 4u : 0u) |
      (m->gnss.position_warn ? 8u : 0u) |
      (m->gnss.position_suspect ? 16u : 0u) |
      (m->gnss.time_suspect ? 32u : 0u) |
      (m->gnss.time_holdover ? 64u : 0u) |
      (m->gnss.position_trust == ZS_POSITION_TRUST_REVALIDATION_REQUIRED ? 128u : 0u);
  kvu(&c, 7, flags);

  zs_cbor_uint(&c, 8);
  zs_cbor_map(&c, 16);
  kvi(&c, 0, m->station.lat_e7);
  kvi(&c, 1, m->station.lon_e7);
  kvi(&c, 2, m->station.alt_dm);
  kvb(&c, 3, m->gnss.pps_ok);
  kvu(&c, 4, m->classification.class_id);
  kvu(&c, 5, m->classification.confidence_u8);
  kvu(&c, 6, m->gnss.fix_type);
  kvu(&c, 7, m->gnss.satellites);
  kvu(&c, 8, m->gnss.hdop_x100);
  kvu(&c, 9, m->gnss.expected_time_error_us);
  kvu(&c, 10, m->detector_profile);
  kvu(&c, 11, m->sample_rate_hz);
  kvu(&c, 12, m->gnss.position_delta_m);
  kvu(&c, 13, m->gnss.position_trust);
  kvu(&c, 14, m->gnss.time_trust);
  kvu(&c, 15, m->station.pos_accuracy_m);

  if (full) {
    zs_cbor_uint(&c, 9);
    uint16_t f16[ZS_FEATURE_COUNT];
    for (unsigned i = 0; i < ZS_FEATURE_COUNT; i++) f16[i] = zs_float_to_f16(m->features[i]);
    zs_cbor_bytes(&c, f16, sizeof(f16));
  }

  zs_cbor_uint(&c, 10);
  zs_cbor_map(&c, full ? 13 : 9);
  kvu(&c, 0, m->power.battery_pct);
  kvu(&c, 1, m->power.battery_mv);
  kvu(&c, 2, m->power.solar_mv);
  kvi(&c, 3, m->power.temperature_c10);
  kvu(&c, 4, m->route.transport);
  kvu(&c, 5, m->route.hop_count);
  kvi(&c, 6, m->route.rssi_dbm);
  kvi(&c, 7, m->route.snr_db10);
  kvu(&c, 8, m->route.gateway_id);
  if (full) {
    kvu(&c, 9, m->power.battery_bus_mv);
    kvi(&c, 10, m->power.battery_current_ma);
    kvu(&c, 11, m->power.battery_power_mw);
    kvu(&c, 12, m->power.monitor_status);
  }

  if (full) {
    zs_cbor_uint(&c, 11);
    zs_cbor_map(&c, 4);
    kvi(&c, 0, m->doa.azimuth_cdeg);
    kvi(&c, 1, m->doa.elevation_cdeg);
    kvu(&c, 2, m->doa.sigma_cdeg);
    kvb(&c, 3, m->doa.valid);
  }

  zs_cbor_uint(&c, 12);
  zs_cbor_map(&c, 6);
  kvu(&c, 0, m->hierarchy.family_id);
  kvu(&c, 1, m->hierarchy.family_confidence_u8);
  kvu(&c, 2, m->hierarchy.type_id);
  kvu(&c, 3, m->hierarchy.type_confidence_u8);
  kvu(&c, 4, m->hierarchy.family_status);
  kvu(&c, 5, m->hierarchy.type_status);

  zs_cbor_uint(&c, 13);
  zs_cbor_map(&c, 7);
  kvi(&c, 0, m->single_station.height_dm);
  kvu(&c, 1, m->single_station.height_sigma_dm);
  kvu(&c, 2, m->single_station.speed_dmps);
  kvu(&c, 3, m->single_station.speed_sigma_dmps);
  kvu(&c, 4, m->single_station.confidence_u8);
  kvu(&c, 5, m->single_station.valid_flags);
  kvu(&c, 6, m->single_station.motion_hint);

  zs_cbor_uint(&c, 14);
  zs_cbor_map(&c, 7);
  kvi(&c, 0, m->spatial.tdoa12_us);
  kvi(&c, 1, m->spatial.tdoa13_us);
  kvi(&c, 2, m->spatial.tdoa14_us);
  kvu(&c, 3, m->spatial.residual_us);
  kvu(&c, 4, m->spatial.confidence_u8);
  kvu(&c, 5, m->spatial.geometry_id);
  kvu(&c, 6, m->spatial.valid_flags);

  return c.error ? 0 : c.len;
}

size_t zs_protocol_encode_detection(const zs_detection_t *m, uint8_t *out, size_t cap) {
  return encode_detection_impl(m, out, cap, true);
}

size_t zs_protocol_encode_detection_summary(const zs_detection_t *m, uint8_t *out, size_t cap) {
  return encode_detection_impl(m, out, cap, false);
}

size_t zs_protocol_encode_heartbeat(const zs_heartbeat_t *m, uint8_t *out, size_t cap) {
  zs_cbor_t c;
  const zs_cellular_telemetry_t *cell;
  if (!m || !out || cap == 0u || m->schema_ver != 1u) return 0u;
  cell = &m->cellular;
  if (!cell->settings_valid ||
      !valid_digits(cell->imsi, sizeof(cell->imsi), 14u, 16u) ||
      !valid_digits(cell->iccid, sizeof(cell->iccid), 18u, 22u) ||
      !valid_text(cell->home_plmn, sizeof(cell->home_plmn), true) ||
      !valid_text(cell->registered_operator, sizeof(cell->registered_operator), true) ||
      !valid_text(cell->apn, sizeof(cell->apn), false) ||
      !valid_text(cell->local_address, sizeof(cell->local_address), false) ||
      !valid_text(cell->gateway, sizeof(cell->gateway), false) ||
      !valid_text(cell->primary_dns, sizeof(cell->primary_dns), false) ||
      !valid_text(cell->secondary_dns, sizeof(cell->secondary_dns), true) ||
      cell->apn_source < 1u || cell->apn_source > 3u ||
      !valid_text(m->firmware_ver, sizeof(m->firmware_ver), false) ||
      !valid_text(m->model_ver, sizeof(m->model_ver), false) ||
      !valid_text(m->hardware_rev, sizeof(m->hardware_rev), false)) return 0u;

  zs_cbor_init(&c, out, cap);
  zs_cbor_map(&c, 13u);
  kvu(&c, 0u, m->schema_ver);
  kvu(&c, 1u, 3u);
  kvu(&c, 2u, m->station_id);
  kvi(&c, 3u, m->time_us);

  zs_cbor_uint(&c, 4u);
  zs_cbor_map(&c, 6u);
  kvi(&c, 0u, m->station.lat_e7);
  kvi(&c, 1u, m->station.lon_e7);
  kvi(&c, 2u, m->station.alt_dm);
  kvu(&c, 3u, m->station.pos_accuracy_m);
  kvu(&c, 4u, m->station.altitude_source);
  kvu(&c, 5u, m->station.position_source);

  zs_cbor_uint(&c, 5u);
  zs_cbor_map(&c, 14u);
  kvu(&c, 0u, m->gnss.fix_type);
  kvu(&c, 1u, m->gnss.satellites);
  kvu(&c, 2u, m->gnss.hdop_x100);
  kvb(&c, 3u, m->gnss.pps_ok);
  kvu(&c, 4u, m->gnss.expected_time_error_us);
  kvb(&c, 5u, m->gnss.jam);
  kvb(&c, 6u, m->gnss.spoof);
  kvu(&c, 7u, m->gnss.position_delta_m);
  kvb(&c, 8u, m->gnss.position_warn);
  kvb(&c, 9u, m->gnss.position_suspect);
  kvb(&c, 10u, m->gnss.time_suspect);
  kvb(&c, 11u, m->gnss.time_holdover);
  kvu(&c, 12u, m->gnss.position_trust);
  kvu(&c, 13u, m->gnss.time_trust);

  zs_cbor_uint(&c, 6u);
  zs_cbor_map(&c, 8u);
  kvu(&c, 0u, m->power.battery_pct);
  kvu(&c, 1u, m->power.battery_mv);
  kvu(&c, 2u, m->power.solar_mv);
  kvi(&c, 3u, m->power.temperature_c10);
  kvu(&c, 4u, m->power.battery_bus_mv);
  kvi(&c, 5u, m->power.battery_current_ma);
  kvu(&c, 6u, m->power.battery_power_mw);
  kvu(&c, 7u, m->power.monitor_status);

  zs_cbor_uint(&c, 7u);
  zs_cbor_map(&c, 5u);
  kvu(&c, 0u, m->route.transport);
  kvu(&c, 1u, m->route.hop_count);
  kvi(&c, 2u, m->route.rssi_dbm);
  kvi(&c, 3u, m->route.snr_db10);
  kvu(&c, 4u, m->route.gateway_id);

  kvt(&c, 8u, m->firmware_ver);
  kvt(&c, 9u, m->model_ver);
  kvt(&c, 10u, m->hardware_rev);
  kvb(&c, 11u, m->self_test_ok);

  zs_cbor_uint(&c, 12u);
  zs_cbor_map(&c, 12u);
  kvt(&c, 0u, cell->imsi);
  kvt(&c, 1u, cell->iccid);
  kvt(&c, 2u, cell->home_plmn);
  kvt(&c, 3u, cell->registered_operator);
  kvt(&c, 4u, cell->apn);
  kvt(&c, 5u, cell->local_address);
  kvt(&c, 6u, cell->gateway);
  kvt(&c, 7u, cell->primary_dns);
  kvt(&c, 8u, cell->secondary_dns);
  kvu(&c, 9u, cell->access_technology);
  kvu(&c, 10u, cell->apn_source);
  kvb(&c, 11u, cell->settings_valid);

  return c.error ? 0u : c.len;
}

#include "zs_protocol.h"
#include "zs_cbor.h"
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

static size_t encode_detection_impl(const zs_detection_t *m, uint8_t *out, size_t cap, bool full) {
  if (!m || !out || cap == 0) return 0;

  zs_cbor_t c;
  zs_cbor_init(&c, out, cap);

  /* v1.3 P0 summary omits feature key 9 and redundant DOA key 11.
     Direction is recoverable from spatial key 14 + geometry_id. */
  zs_cbor_map(&c, full ? 15 : 13);
  kvu(&c, 0, m->schema_ver);
  kvu(&c, 1, 2);
  kvu(&c, 2, m->station_id);
  kvu(&c, 3, m->seq_no);
  kvu(&c, 4, m->boot_id);
  kvu(&c, 5, m->event_id);
  kvi(&c, 6, m->event_time_us);

  const uint16_t flags = (m->gnss.jam ? 1u : 0u) | (m->gnss.spoof ? 2u : 0u);
  kvu(&c, 7, flags);

  zs_cbor_uint(&c, 8);
  zs_cbor_map(&c, 12);
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

  if (full) {
    zs_cbor_uint(&c, 9);
    uint16_t f16[ZS_FEATURE_COUNT];
    for (unsigned i = 0; i < ZS_FEATURE_COUNT; i++) f16[i] = zs_float_to_f16(m->features[i]);
    zs_cbor_bytes(&c, f16, sizeof(f16));
  }

  zs_cbor_uint(&c, 10);
  zs_cbor_map(&c, 9);
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

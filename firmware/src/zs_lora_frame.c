#include "zs_lora_frame.h"
#include "zs_sha256.h"
#include <string.h>

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { for (unsigned i = 0u; i < 4u; i++) p[i] = (uint8_t)(v >> (8u * i)); }
static uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

void zs_lora_derive_key(const uint8_t engineer_key[32], uint8_t key[ZS_LORA_KEY_BYTES]) {
  uint8_t material[sizeof(ZS_LORA_KEY_CONTEXT) - 1u + 32u];
  memcpy(material, ZS_LORA_KEY_CONTEXT, sizeof(ZS_LORA_KEY_CONTEXT) - 1u);
  memcpy(material + sizeof(ZS_LORA_KEY_CONTEXT) - 1u, engineer_key, 32u);
  zs_sha256_digest(material, sizeof(material), key);
  memset(material, 0, sizeof(material));
}

static void tag(const uint8_t *key, const uint8_t *data, size_t n, const char *suffix, uint8_t out[ZS_LORA_TAG_BYTES]) {
  uint8_t buf[64], mac[32];
  size_t k = n;
  memcpy(buf, data, n);
  if (suffix) { const size_t s = strlen(suffix); memcpy(buf + k, suffix, s); k += s; }
  zs_hmac_sha256(key, ZS_LORA_KEY_BYTES, buf, k, mac);
  memcpy(out, mac, ZS_LORA_TAG_BYTES);
}

bool zs_lora_encode_event(const zs_lora_event_t *e, const uint8_t key[ZS_LORA_KEY_BYTES], uint8_t out[ZS_LORA_EVENT_FRAME_BYTES]) {
  if (!e || !key || !out || e->station_id == 0u || e->presence_level > 3u) return false;
  out[0] = ZS_LORA_FRAME_EVENT_TYPE;
  put16(out + 1, e->profile_id);
  put32(out + 3, e->station_id); put32(out + 7, e->boot_id); put32(out + 11, e->seq_no);
  put32(out + 15, e->time_s); put16(out + 19, e->time_ms);
  out[21] = e->class_id; out[22] = e->confidence_u8; out[23] = e->presence_level;
  put16(out + 24, e->f0_hz); put16(out + 26, e->battery_mv); out[28] = e->battery_pct; out[29] = e->flags;
  tag(key, out, 30u, NULL, out + 30);
  return true;
}

bool zs_lora_decode_event(const uint8_t *frame, size_t n, const uint8_t key[ZS_LORA_KEY_BYTES], zs_lora_event_t *e) {
  uint8_t t[ZS_LORA_TAG_BYTES];
  if (!frame || !key || !e || n != ZS_LORA_EVENT_FRAME_BYTES || frame[0] != ZS_LORA_FRAME_EVENT_TYPE) return false;
  tag(key, frame, 30u, NULL, t);
  if (!zs_sha256_equal(t, frame + 30, ZS_LORA_TAG_BYTES)) return false;
  memset(e, 0, sizeof(*e));
  e->profile_id = get16(frame + 1);
  e->station_id = get32(frame + 3); e->boot_id = get32(frame + 7); e->seq_no = get32(frame + 11);
  e->time_s = get32(frame + 15); e->time_ms = get16(frame + 19);
  e->class_id = frame[21]; e->confidence_u8 = frame[22]; e->presence_level = frame[23];
  e->f0_hz = get16(frame + 24); e->battery_mv = get16(frame + 26); e->battery_pct = frame[28]; e->flags = frame[29];
  return e->station_id != 0u && e->presence_level <= 3u;
}

bool zs_lora_encode_ack(uint32_t station_id, uint32_t boot_id, uint32_t seq_no, const uint8_t key[ZS_LORA_KEY_BYTES], uint8_t out[ZS_LORA_ACK_FRAME_BYTES]) {
  if (!key || !out || station_id == 0u) return false;
  out[0] = ZS_LORA_FRAME_ACK_TYPE;
  put32(out + 1, station_id); put32(out + 5, boot_id); put32(out + 9, seq_no);
  tag(key, out, 13u, "ACK", out + 13);
  return true;
}

bool zs_lora_decode_ack(const uint8_t *frame, size_t n, const uint8_t key[ZS_LORA_KEY_BYTES], uint32_t *station_id, uint32_t *boot_id, uint32_t *seq_no) {
  uint8_t t[ZS_LORA_TAG_BYTES];
  if (!frame || !key || n != ZS_LORA_ACK_FRAME_BYTES || frame[0] != ZS_LORA_FRAME_ACK_TYPE) return false;
  tag(key, frame, 13u, "ACK", t);
  if (!zs_sha256_equal(t, frame + 13, ZS_LORA_TAG_BYTES)) return false;
  if (station_id) *station_id = get32(frame + 1);
  if (boot_id) *boot_id = get32(frame + 5);
  if (seq_no) *seq_no = get32(frame + 9);
  return get32(frame + 1) != 0u;
}

/* Semtech AN1200.13 time-on-air; integer arithmetic in microseconds. */
uint32_t zs_lora_airtime_ms(size_t payload_bytes, uint8_t sf, uint32_t bandwidth_hz, uint8_t cr_denominator) {
  if (sf < 5u || sf > 12u || bandwidth_hz == 0u || cr_denominator < 5u || cr_denominator > 8u) return 0u;
  const uint64_t tsym_us = ((uint64_t)1u << sf) * 1000000ull / bandwidth_hz;
  const uint64_t preamble_us = (8u * 4u + 17u) * tsym_us / 4u;                   /* (8 + 4.25) symbols */
  const bool ldro = (sf >= 11u && bandwidth_hz <= 125000u);
  const int num = (int)(8u * payload_bytes) - 4 * (int)sf + 28 + 16;            /* explicit header, CRC on */
  const int den = 4 * ((int)sf - (ldro ? 2 : 0));
  int n = (num + den - 1) / den;
  if (n < 0) n = 0;
  const uint64_t payload_symbols = 8u + (uint64_t)n * (uint64_t)(cr_denominator);
  return (uint32_t)((preamble_us + payload_symbols * tsym_us + 999u) / 1000u);
}

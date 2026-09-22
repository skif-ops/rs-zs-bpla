/* Host tests: BLE framing (B.2), IPC link (C), and the Android-like client <-> nRF bridge <-> STM32 service loop. */
#include "zs_ble_bridge.h"
#include "zs_ble_framing.h"
#include "zs_cbor.h"
#include "zs_ipc_link.h"
#include "zs_ipc_service.h"
#include "zs_sha256.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

/* ---- framing ---------------------------------------------------------------------------- */

static void test_framing_vectors(void) {
  uint8_t value[4096], frame[244], out[4096];
  for (unsigned i = 0u; i < sizeof(value); i++) value[i] = (uint8_t)i;
  /* 300 bytes at MTU 247: two frames of 244 (240 data) and 2 + 60 (Kotlin LongValueFramingTest.frameLayoutForMtu247) */
  zs_ble_splitter_t s; zs_ble_reassembler_t r;
  assert(zs_ble_splitter_init(&s, value, 300u));
  assert(zs_ble_splitter_next(&s, 244u, frame, sizeof(frame)) == 244u);
  assert(frame[0] == 0u && frame[1] == ZS_BLE_FRAME_FLAG_FIRST && frame[2] == 0x01u && frame[3] == 0x2cu && frame[4] == 0u);
  zs_ble_reassembler_init(&r, out, sizeof(out));
  assert(zs_ble_reassembler_feed(&r, frame, 244u) && !r.complete);
  assert(zs_ble_splitter_next(&s, 244u, frame, sizeof(frame)) == 62u);
  assert(frame[0] == 1u && frame[1] == ZS_BLE_FRAME_FLAG_LAST);
  assert(zs_ble_reassembler_feed(&r, frame, 62u) && r.complete && r.filled == 300u && memcmp(out, value, 300u) == 0);
  assert(zs_ble_splitter_next(&s, 244u, frame, sizeof(frame)) == 0u);
  /* single frame, empty value, MTU 23 */
  assert(zs_ble_splitter_init(&s, value, 0u));
  assert(zs_ble_splitter_next(&s, 20u, frame, sizeof(frame)) == 4u && frame[1] == (ZS_BLE_FRAME_FLAG_FIRST | ZS_BLE_FRAME_FLAG_LAST));
  zs_ble_reassembler_reset(&r);
  assert(zs_ble_reassembler_feed(&r, frame, 4u) && r.complete && r.filled == 0u);
  /* 4096 bytes at 16-byte payload: sequence wraps past 255 */
  assert(zs_ble_splitter_init(&s, value, 4096u));
  zs_ble_reassembler_reset(&r);
  unsigned frames = 0u;
  for (;;) { const size_t n = zs_ble_splitter_next(&s, 16u, frame, sizeof(frame)); if (!n) break; assert(zs_ble_reassembler_feed(&r, frame, n)); frames++; }
  assert(frames > 256u && r.complete && memcmp(out, value, 4096u) == 0);
  /* errors: seq gap, no FIRST after reset, truncated LAST, oversized announcement */
  assert(zs_ble_splitter_init(&s, value, 700u));
  uint8_t f0[244], f1[244], f2[244]; size_t n0 = zs_ble_splitter_next(&s, 244u, f0, 244u), n1 = zs_ble_splitter_next(&s, 244u, f1, 244u), n2 = zs_ble_splitter_next(&s, 244u, f2, 244u);
  zs_ble_reassembler_reset(&r);
  assert(zs_ble_reassembler_feed(&r, f0, n0) && !zs_ble_reassembler_feed(&r, f2, n2) && !zs_ble_reassembler_feed(&r, f1, n1));
  assert(zs_ble_reassembler_feed(&r, f0, n0) && zs_ble_reassembler_feed(&r, f1, n1) && !zs_ble_reassembler_feed(&r, f2, n2 - 1u));
  const uint8_t huge[5] = {0u, ZS_BLE_FRAME_FLAG_FIRST, 0x20u, 0x00u, 1u};
  zs_ble_reassembler_reset(&r); assert(!zs_ble_reassembler_feed(&r, huge, 5u));
  printf("framing ok\n");
}

/* ---- IPC link --------------------------------------------------------------------------- */

static void test_ipc_link(void) {
  uint8_t payload[600], wire[700], rxbuf[ZS_IPC_PAYLOAD_MAX + 4u];
  zs_ipc_decoder_t d;
  uint8_t type, seq; const uint8_t *p; size_t n;
  assert(zs_ipc_crc16((const uint8_t *)"123456789", 9u) == 0x29B1u);
  for (unsigned i = 0u; i < sizeof(payload); i++) payload[i] = (i % 7u == 0u) ? 0u : (i % 300u == 1u ? 0xffu : (uint8_t)i); /* zeros + long runs */
  memset(&payload[300], 0x55, 300u); /* run longer than 254 without zeros */
  zs_ipc_decoder_init(&d, rxbuf, sizeof(rxbuf));
  const size_t w = zs_ipc_encode(ZS_IPC_READ_VALUE, 0x42u, payload, sizeof(payload), wire, sizeof(wire));
  assert(w > sizeof(payload) + 4u && wire[w - 1u] == 0u);
  for (size_t i = 0u; i < w - 1u; i++) assert(wire[i] != 0u);
  bool got = false;
  for (size_t i = 0u; i < w; i++) if (zs_ipc_decoder_feed(&d, wire[i], &type, &seq, &p, &n)) { got = true; assert(i == w - 1u); }
  assert(got && type == ZS_IPC_READ_VALUE && seq == 0x42u && n == sizeof(payload) && memcmp(p, payload, n) == 0);
  /* empty payload, then a corrupted frame (CRC) and resync on the next good one */
  const size_t w0 = zs_ipc_encode(ZS_IPC_PING, 1u, NULL, 0u, wire, sizeof(wire));
  got = false; for (size_t i = 0u; i < w0; i++) if (zs_ipc_decoder_feed(&d, wire[i], &type, &seq, &p, &n)) got = true;
  assert(got && type == ZS_IPC_PING && n == 0u);
  const uint8_t small[3] = {1, 2, 3};
  const size_t w1 = zs_ipc_encode(ZS_IPC_NOTIFY, 2u, small, 3u, wire, sizeof(wire));
  wire[2] ^= 0x10u; /* flip a payload bit */
  got = false; for (size_t i = 0u; i < w1; i++) if (zs_ipc_decoder_feed(&d, wire[i], &type, &seq, &p, &n)) got = true;
  assert(!got && d.crc_errors == 1u);
  const size_t w2 = zs_ipc_encode(ZS_IPC_NOTIFY, 3u, small, 3u, wire, sizeof(wire));
  got = false; for (size_t i = 0u; i < w2; i++) if (zs_ipc_decoder_feed(&d, wire[i], &type, &seq, &p, &n)) got = true;
  assert(got && seq == 3u && n == 3u && p[2] == 3u);
  /* garbage between frames is dropped as a framing error */
  const uint8_t junk[4] = {0x05, 0x01, 0x02, 0x00};
  got = false; for (size_t i = 0u; i < 4u; i++) if (zs_ipc_decoder_feed(&d, junk[i], &type, &seq, &p, &n)) got = true;
  assert(!got && d.framing_errors == 1u);
  printf("ipc link ok\n");
}

/* ---- end to end: client <-> bridge <-> service ------------------------------------------- */

typedef struct { uint8_t slots[ZS_STATION_CONFIG_SLOT_COUNT][ZS_STATION_CONFIG_SLOT_BYTES]; } cfg_store_t;
typedef struct { uint8_t slots[ZS_INSTALLATION_STORE_SLOT_COUNT][ZS_INSTALLATION_STORE_SLOT_BYTES]; } pos_store_t;

static bool cfg_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { cfg_store_t *st = c; if (s >= 2u || o + n > ZS_STATION_CONFIG_SLOT_BYTES) return false; memcpy(d, &st->slots[s][o], n); return true; }
static bool cfg_erase(void *c, uint8_t s) { cfg_store_t *st = c; if (s >= 2u) return false; memset(st->slots[s], 0xff, ZS_STATION_CONFIG_SLOT_BYTES); return true; }
static bool cfg_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) { cfg_store_t *st = c; if (s >= 2u || o + n > ZS_STATION_CONFIG_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((st->slots[s][o + i] & d[i]) != d[i]) return false; st->slots[s][o + i] = d[i]; } return true; }
static bool pos_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { pos_store_t *st = c; if (s >= 2u || o + n > ZS_INSTALLATION_STORE_SLOT_BYTES) return false; memcpy(d, &st->slots[s][o], n); return true; }
static bool pos_erase(void *c, uint8_t s) { pos_store_t *st = c; if (s >= 2u) return false; memset(st->slots[s], 0xff, ZS_INSTALLATION_STORE_SLOT_BYTES); return true; }
static bool pos_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) { pos_store_t *st = c; if (s >= 2u || o + n > ZS_INSTALLATION_STORE_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((st->slots[s][o + i] & d[i]) != d[i]) return false; st->slots[s][o + i] = d[i]; } return true; }
static bool audit_append(void *c, const zs_commissioning_audit_event_t *e) { unsigned *count = c; (void)e; (*count)++; return true; }

typedef struct {
  zs_ble_bridge_t bridge;
  zs_ipc_service_t service;
  /* client side */
  uint8_t notify_buf[ZS_BLE_VALUE_MAX];
  zs_ble_reassembler_t notify_rx;
  uint16_t notify_char;
  unsigned notify_complete;
  uint8_t last_notify[ZS_BLE_VALUE_MAX]; size_t last_notify_len;
  bool subscribed;
  size_t att;
  char local_name[32];
  bool advertising; uint16_t adv_seconds;
  uint8_t secret[16]; bool secret_set;
  /* service side */
  bool service_mode, secure; zs_commissioning_role_t role; uint32_t now;
  cfg_store_t cfg; pos_store_t pos; unsigned audits;
  zs_selftest_registry_t selftest;
  zs_ipc_identity_t identity;
  zs_station_config_io_t cfg_io; zs_installation_store_io_t pos_io; zs_commissioning_audit_io_t audit_io;
  zs_ble_bridge_port_t bport; zs_ipc_service_port_t sport;
} world_t;

/* UART: bytes from the nRF go straight into the STM32 decoder and vice versa. */
static bool nrf_uart_send(void *ctx, const uint8_t *w, size_t n) { world_t *W = ctx; zs_ipc_service_on_uart_rx(&W->service, w, n); return true; }
static bool stm_uart_send(void *ctx, const uint8_t *w, size_t n) { world_t *W = ctx; zs_ble_bridge_on_uart_rx(&W->bridge, w, n); return true; }
static bool gatt_notify(void *ctx, uint16_t id, const uint8_t *f, size_t n) {
  world_t *W = ctx;
  if (!W->subscribed) return false;
  if (W->notify_char != id) { zs_ble_reassembler_reset(&W->notify_rx); W->notify_char = id; }
  assert(zs_ble_reassembler_feed(&W->notify_rx, f, n));
  if (W->notify_rx.complete) { W->notify_complete++; W->last_notify_len = W->notify_rx.filled; memcpy(W->last_notify, W->notify_buf, W->last_notify_len); zs_ble_reassembler_reset(&W->notify_rx); }
  return true;
}
static size_t att_payload(void *ctx) { return ((world_t *)ctx)->att; }
static void advertise(void *ctx, bool on, uint16_t s) { world_t *W = ctx; W->advertising = on; W->adv_seconds = s; }
static void set_name(void *ctx, const char *n) { strcpy(((world_t *)ctx)->local_name, n); }
static void set_secret(void *ctx, const uint8_t s[16]) { world_t *W = ctx; memcpy(W->secret, s, 16u); W->secret_set = true; }
static uint32_t now_ms(void *ctx) { return ((world_t *)ctx)->now; }
static bool service_mode(void *ctx, uint32_t *started) { *started = 1000u; return ((world_t *)ctx)->service_mode; }
static zs_commissioning_role_t peer_role(void *ctx) { return ((world_t *)ctx)->role; }
static bool peer_secure(void *ctx) { return ((world_t *)ctx)->secure; }
static zs_selftest_code_t st_pass(void *ctx, uint32_t *d) { (void)ctx; *d = 3900u; return ZS_ST_PASS; }
static zs_selftest_code_t st_fail(void *ctx, uint32_t *d) { (void)ctx; *d = 7u; return ZS_ST_FAIL; }

static void world_init(world_t *W) {
  memset(W, 0, sizeof(*W));
  memset(W->cfg.slots, 0xff, sizeof(W->cfg.slots)); memset(W->pos.slots, 0xff, sizeof(W->pos.slots));
  W->att = 244u; W->service_mode = true; W->secure = true; W->role = ZS_COMMISSIONING_ROLE_INSTALLER; W->now = 5000u; W->subscribed = true;
  zs_ble_reassembler_init(&W->notify_rx, W->notify_buf, sizeof(W->notify_buf));
  strcpy(W->identity.serial, "DIO-EVT-012"); strcpy(W->identity.hardware_revision, "Rev.A");
  strcpy(W->identity.firmware_version, "0.1.0-b1"); strcpy(W->identity.bootloader_version, "0.1.0");
  W->identity.station_id = 12u; W->identity.region = ZS_STATION_CONFIG_REGION_RU868;
  W->cfg_io = (zs_station_config_io_t){&W->cfg, cfg_read, cfg_erase, cfg_write};
  W->pos_io = (zs_installation_store_io_t){&W->pos, pos_read, pos_erase, pos_write};
  W->audit_io = (zs_commissioning_audit_io_t){&W->audits, audit_append};
  zs_selftest_init(&W->selftest);
  zs_selftest_register(&W->selftest, ZS_ST_ID_POWER_INA226, "power", st_pass, NULL, true);
  zs_selftest_register(&W->selftest, ZS_ST_ID_LORA_SPI, "lora_spi", st_fail, NULL, false);
  W->bport = (zs_ble_bridge_port_t){W, nrf_uart_send, gatt_notify, att_payload, advertise, set_name, set_secret};
  W->sport = (zs_ipc_service_port_t){W, stm_uart_send, now_ms, service_mode, peer_role, peer_secure, &W->cfg_io, &W->pos_io, &W->audit_io, &W->selftest, &W->identity};
  zs_ble_bridge_init(&W->bridge, &W->bport);
  assert(zs_ipc_service_init(&W->service, &W->sport));
}

/* Android-like client primitives over the bridge. */
static bool client_read_long(world_t *W, uint16_t id, uint8_t *out, size_t cap, size_t *len) {
  uint8_t frame[244]; zs_ble_reassembler_t r; size_t n;
  zs_ble_reassembler_init(&r, out, cap);
  for (unsigned i = 0u; i < 64u; i++) {
    if (!zs_ble_bridge_on_gatt_read(&W->bridge, id, frame, sizeof(frame), &n)) return false;
    if (!zs_ble_reassembler_feed(&r, frame, n)) return false;
    if (r.complete) { *len = r.filled; return true; }
  }
  return false;
}
static uint8_t client_write_long(world_t *W, uint16_t id, const uint8_t *value, size_t len) {
  zs_ble_splitter_t s; uint8_t frame[244];
  const unsigned before = W->notify_complete;
  assert(zs_ble_splitter_init(&s, value, len));
  for (;;) { const size_t n = zs_ble_splitter_next(&s, W->att, frame, sizeof(frame)); if (!n) break; assert(zs_ble_bridge_on_gatt_write(&W->bridge, id, frame, n)); }
  assert(W->notify_complete == before + 1u && W->notify_char == id); /* status notify arrived synchronously */
  return W->last_notify_len == 1u ? W->last_notify[0] : 0xffu;
}

static size_t config_patch(uint8_t *buf, size_t cap, uint32_t version) {
  zs_cbor_t c; uint8_t fp[32]; for (unsigned i = 0u; i < 32u; i++) fp[i] = (uint8_t)i;
  zs_cbor_init(&c, buf, cap); zs_cbor_map(&c, 11u);
  zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, version);
  zs_cbor_uint(&c, 2u); zs_cbor_text(&c, "muhoed.example.ru");
  zs_cbor_uint(&c, 3u); zs_cbor_uint(&c, 8883u);
  zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 443u);
  zs_cbor_uint(&c, 5u); zs_cbor_text(&c, "dioneya-root");
  zs_cbor_uint(&c, 6u); zs_cbor_bytes(&c, fp, 32u);
  zs_cbor_uint(&c, 7u); zs_cbor_text(&c, "pilot1");
  zs_cbor_uint(&c, 8u); zs_cbor_text(&c, "zs/v1");
  zs_cbor_uint(&c, 9u); zs_cbor_uint(&c, 1u);
  zs_cbor_uint(&c, 10u); zs_cbor_text(&c, "internet");
  zs_cbor_uint(&c, 11u); zs_cbor_text(&c, "");
  assert(!c.error); return c.len;
}

static size_t installation_request(uint8_t *buf, size_t cap, bool recommission, uint32_t version, int32_t lat) {
  zs_cbor_t c; zs_cbor_init(&c, buf, cap); zs_cbor_map(&c, 14u);
  zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, recommission ? 1u : 0u);
  zs_cbor_uint(&c, 2u); zs_cbor_int(&c, lat);
  zs_cbor_uint(&c, 3u); zs_cbor_int(&c, 376173000);
  zs_cbor_uint(&c, 4u); zs_cbor_int(&c, 1564);
  zs_cbor_uint(&c, 5u); zs_cbor_uint(&c, 4u);
  zs_cbor_uint(&c, 6u); zs_cbor_uint(&c, 3u);
  zs_cbor_uint(&c, 7u); zs_cbor_uint(&c, version);
  zs_cbor_uint(&c, 8u); zs_cbor_bool(&c, true);
  zs_cbor_uint(&c, 9u); zs_cbor_uint(&c, UINT64_C(1800000000000000));
  zs_cbor_uint(&c, 10u); zs_cbor_uint(&c, 25u);
  zs_cbor_uint(&c, 11u); zs_cbor_uint(&c, 75u);
  zs_cbor_uint(&c, 12u); zs_cbor_uint(&c, 250u);
  zs_cbor_uint(&c, 13u); zs_cbor_uint(&c, 3u);
  zs_cbor_uint(&c, 14u); zs_cbor_uint(&c, 10u);
  assert(!c.error); return c.len;
}

static void test_end_to_end(void) {
  static world_t W;
  uint8_t out[4096], req[256], expect[256]; size_t n, m;
  world_init(&W);
  assert(strcmp(W.local_name, "DIO-EVT-012") == 0);                  /* IDENTITY_SET at init */
  assert(zs_ipc_service_set_window(&W.service, true, 600u) && W.advertising && W.adv_seconds == 600u);
  const uint8_t secret[16] = {0x48, 0x65, 0x6c, 0x6c, 0x6f, 0x21, 0xde, 0xad, 0xbe, 0xef, 0x48, 0x65, 0x6c, 0x6c, 0x6f, 0x21};
  assert(zs_ipc_service_set_pairing_secret(&W.service, secret) && W.secret_set && memcmp(W.secret, secret, 16u) == 0);

  /* connection: caches for identity + installation (empty) are pushed; config is absent on a fresh station */
  zs_ble_bridge_on_link(&W.bridge, 2u);
  assert(W.service.link_state == 2u);
  assert(client_read_long(&W, ZS_CHAR_IDENTITY, out, sizeof(out), &n));
  m = zs_ipc_encode_identity(&W.identity, expect, sizeof(expect));
  assert(n == m && memcmp(out, expect, n) == 0 && out[0] == 0xa6u && out[1] == 0x01u && out[2] == 0x6bu);
  assert(client_read_long(&W, ZS_CHAR_INSTALLATION_POSITION, out, sizeof(out), &n) && n == 1u && out[0] == 0xa0u);
  assert(!client_read_long(&W, ZS_CHAR_CONFIG_READ, out, sizeof(out), &n));   /* nothing stored yet -> cache miss */
  assert(!client_read_long(&W, ZS_CHAR_CONFIG_WRITE, out, sizeof(out), &n));  /* write-only characteristic */

  /* config_write: service mode / authorization gates, then a real commit and read-back with the station hash */
  n = config_patch(req, sizeof(req), 1u);
  W.service_mode = false; assert(client_write_long(&W, ZS_CHAR_CONFIG_WRITE, req, n) == ZS_BLE_STATUS_NOT_IN_SERVICE_MODE);
  W.service_mode = true; W.secure = false; assert(client_write_long(&W, ZS_CHAR_CONFIG_WRITE, req, n) == ZS_BLE_STATUS_NOT_AUTHORIZED);
  W.secure = true;
  assert(client_write_long(&W, ZS_CHAR_CONFIG_WRITE, req, n) == ZS_BLE_STATUS_OK);
  assert(client_read_long(&W, ZS_CHAR_CONFIG_READ, out, sizeof(out), &n));
  m = zs_station_config_encode_readback(&W.service.config, expect, sizeof(expect));
  assert(n == m && memcmp(out, expect, n) == 0 && zs_station_config_hash_valid(&W.service.config) && W.service.config.version == 1u);
  assert(strcmp(W.service.config.server_host, "muhoed.example.ru") == 0 && W.service.config.station_id == 12u);
  n = config_patch(req, sizeof(req), 1u);
  assert(client_write_long(&W, ZS_CHAR_CONFIG_WRITE, req, n) == ZS_BLE_STATUS_REJECTED_VERSION);
  req[5] ^= 0x40u; /* corrupt the host text -> malformed / validation */
  n = config_patch(req, sizeof(req), 2u); req[10] = 0x20u; /* replace a host byte with a space */
  assert(client_write_long(&W, ZS_CHAR_CONFIG_WRITE, req, n) == ZS_BLE_STATUS_REJECTED_VALIDATION);
  assert(W.service.config.version == 1u);

  /* installation_position: INITIAL, then INITIAL again (locked), then RECOMMISSION v2 */
  n = installation_request(req, sizeof(req), false, 1u, 557558000);
  assert(client_write_long(&W, ZS_CHAR_INSTALLATION_POSITION, req, n) == ZS_BLE_STATUS_OK && W.audits == 2u);
  assert(client_read_long(&W, ZS_CHAR_INSTALLATION_POSITION, out, sizeof(out), &n) && out[0] == 0xb0u);
  zs_installation_record_t stored; uint8_t slot;
  assert(zs_installation_store_load(&W.pos_io, &stored, &slot) == ZS_INSTALLATION_STORE_OK);
  m = zs_ipc_encode_installation_readback(&stored, true, expect, sizeof(expect));
  assert(n == m && memcmp(out, expect, n) == 0 && stored.version == 1u && stored.trust.installation.lat_e7 == 557558000 && zs_installation_record_hash_valid(&stored));
  n = installation_request(req, sizeof(req), false, 2u, 557558100);
  assert(client_write_long(&W, ZS_CHAR_INSTALLATION_POSITION, req, n) == ZS_BLE_STATUS_POSITION_LOCKED);
  n = installation_request(req, sizeof(req), true, 2u, 557558100);
  assert(client_write_long(&W, ZS_CHAR_INSTALLATION_POSITION, req, n) == ZS_BLE_STATUS_OK);
  assert(zs_installation_store_load(&W.pos_io, &stored, &slot) == ZS_INSTALLATION_STORE_OK && stored.version == 2u && stored.trust.installation.lat_e7 == 557558100);
  assert(client_read_long(&W, ZS_CHAR_INSTALLATION_POSITION, out, sizeof(out), &n) && n == zs_ipc_encode_installation_readback(&stored, true, expect, sizeof(expect)) && memcmp(out, expect, n) == 0);
  n = installation_request(req, sizeof(req), true, 3u, 557558100); req[2] = 0x02u; /* operation value becomes unsupported */
  assert(client_write_long(&W, ZS_CHAR_INSTALLATION_POSITION, req, n) == ZS_BLE_STATUS_REJECTED_VALIDATION);

  /* self-test: write 0x01, the report is notified as a framed CBOR map {1:[1,3900], 8:[2,7]} */
  const uint8_t run = 0x01u;
  assert(client_write_long(&W, ZS_CHAR_SELF_TEST, &run, 1u) == 0xffu); /* not a 1-byte status */
  const uint8_t report[] = {0xa2, 0x01, 0x82, 0x01, 0x19, 0x0f, 0x3c, 0x08, 0x82, 0x02, 0x07};
  assert(W.last_notify_len == sizeof(report) && memcmp(W.last_notify, report, sizeof(report)) == 0);

  /* MTU 23 path: the same read-back is split into many small frames */
  W.att = 20u;
  zs_ble_bridge_on_link(&W.bridge, 2u);
  assert(client_read_long(&W, ZS_CHAR_CONFIG_READ, out, sizeof(out), &n) && n == zs_station_config_encode_readback(&W.service.config, expect, sizeof(expect)) && memcmp(out, expect, n) == 0);
  /* disconnect: writes in flight are dropped */
  zs_ble_bridge_on_link(&W.bridge, 0u);
  assert(W.service.link_state == 0u && W.bridge.write_char == 0u);
  printf("end to end ok (writes ok=%u rejected=%u audits=%u)\n", W.service.writes_ok, W.service.writes_rejected, W.audits);
}

int main(void) {
  test_framing_vectors();
  test_ipc_link();
  test_end_to_end();
  printf("ble bridge tests passed\n");
  return 0;
}

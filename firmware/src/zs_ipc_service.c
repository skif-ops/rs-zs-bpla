#include "zs_ipc_service.h"
#include "zs_sha256.h"
#include "zs_cbor.h"
#include "zs_cbor_read.h"
#include <string.h>

/* ---- IPC plumbing ------------------------------------------------------------------------ */

static bool send_ipc(zs_ipc_service_t *s, uint8_t type, const uint8_t *payload, size_t len) {
  const size_t n = zs_ipc_encode(type, s->ipc_seq++, payload, len, s->wire, sizeof(s->wire));
  return n != 0u && s->port->uart_send(s->port->ctx, s->wire, n);
}

static bool push_value(zs_ipc_service_t *s, uint8_t type, uint16_t char_id, const uint8_t *value, size_t len) {
  uint8_t payload[2u + ZS_BLE_VALUE_MAX];
  if (len > ZS_BLE_VALUE_MAX) return false;
  zs_ipc_put_u16(payload, char_id);
  memcpy(&payload[2], value, len);
  return send_ipc(s, type, payload, 2u + len);
}

static bool send_status(zs_ipc_service_t *s, uint16_t char_id, uint8_t status) {
  uint8_t p[3];
  zs_ipc_put_u16(p, char_id); p[2] = status;
  if (status == ZS_BLE_STATUS_OK) s->writes_ok++; else s->writes_rejected++;
  return send_ipc(s, ZS_IPC_WRITE_STATUS, p, 3u);
}

/* ---- encoders ---------------------------------------------------------------------------- */

size_t zs_ipc_encode_identity(const zs_ipc_identity_t *id, uint8_t *buf, size_t cap) {
  zs_cbor_t c;
  zs_cbor_init(&c, buf, cap);
  zs_cbor_map(&c, 6u);
  zs_cbor_uint(&c, 1u); zs_cbor_text(&c, id->serial);
  zs_cbor_uint(&c, 2u); zs_cbor_uint(&c, id->station_id);
  zs_cbor_uint(&c, 3u); zs_cbor_text(&c, id->hardware_revision);
  zs_cbor_uint(&c, 4u); zs_cbor_text(&c, id->firmware_version);
  zs_cbor_uint(&c, 5u); zs_cbor_text(&c, id->bootloader_version);
  zs_cbor_uint(&c, 6u); zs_cbor_uint(&c, id->region);
  return c.error ? 0u : c.len;
}

size_t zs_ipc_encode_installation_readback(const zs_installation_record_t *r, bool audit_committed, uint8_t *buf, size_t cap) {
  zs_cbor_t c;
  zs_cbor_init(&c, buf, cap);
  zs_cbor_map(&c, 16u);
  zs_cbor_uint(&c, 2u); zs_cbor_int(&c, r->trust.installation.lat_e7);
  zs_cbor_uint(&c, 3u); zs_cbor_int(&c, r->trust.installation.lon_e7);
  zs_cbor_uint(&c, 4u); zs_cbor_int(&c, r->trust.installation.alt_dm);
  zs_cbor_uint(&c, 5u); zs_cbor_uint(&c, r->trust.installation.pos_accuracy_m);
  zs_cbor_uint(&c, 6u); zs_cbor_uint(&c, r->source);
  zs_cbor_uint(&c, 7u); zs_cbor_uint(&c, r->version);
  zs_cbor_uint(&c, 8u); zs_cbor_bool(&c, r->trust.locked);
  zs_cbor_uint(&c, 9u); zs_cbor_uint(&c, r->commissioned_time_us);
  zs_cbor_uint(&c, 10u); zs_cbor_uint(&c, r->trust.warning_distance_m);
  zs_cbor_uint(&c, 11u); zs_cbor_uint(&c, r->trust.suspect_distance_m);
  zs_cbor_uint(&c, 12u); zs_cbor_uint(&c, r->trust.gross_jump_distance_m);
  zs_cbor_uint(&c, 13u); zs_cbor_uint(&c, r->trust.warning_consecutive_fixes);
  zs_cbor_uint(&c, 14u); zs_cbor_uint(&c, r->trust.suspect_consecutive_fixes);
  zs_cbor_uint(&c, 15u); zs_cbor_uint(&c, r->storage_generation);
  zs_cbor_uint(&c, 16u); zs_cbor_bytes(&c, r->commissioning_hash, ZS_INSTALLATION_HASH_BYTES);
  zs_cbor_uint(&c, 17u); zs_cbor_bool(&c, audit_committed);
  return c.error ? 0u : c.len;
}

bool zs_ipc_decode_installation_request(const uint8_t *p, size_t len, zs_commissioning_operation_t *op, zs_installation_record_t *rec) {
  zs_cbor_reader_t r;
  uint32_t n;
  uint64_t last = 0u;
  bool seen[15] = {false};
  zs_cbor_reader_init(&r, p, len);
  memset(rec, 0, sizeof(*rec));
  if (!zs_cbor_read_map(&r, &n) || n != 14u) return false;
  for (uint32_t i = 0u; i < n; i++) {
    uint64_t key, u; int64_t v; bool b;
    if (!zs_cbor_read_uint(&r, &key) || key < 1u || key > 14u || (i > 0u && key <= last) || seen[key]) return false;
    last = key; seen[key] = true;
    switch (key) {
      case 1: if (!zs_cbor_read_uint(&r, &u) || u > 1u) return false; *op = u ? ZS_COMMISSIONING_OPERATION_RECOMMISSION : ZS_COMMISSIONING_OPERATION_INITIAL; break;
      case 2: if (!zs_cbor_read_int(&r, &v) || v < -900000000 || v > 900000000) return false; rec->trust.installation.lat_e7 = (int32_t)v; break;
      case 3: if (!zs_cbor_read_int(&r, &v) || v < -1800000000 || v > 1800000000) return false; rec->trust.installation.lon_e7 = (int32_t)v; break;
      case 4: if (!zs_cbor_read_int(&r, &v) || v < -50000 || v > 100000) return false; rec->trust.installation.alt_dm = (int32_t)v; break;
      case 5: if (!zs_cbor_read_uint(&r, &u) || u < 1u || u > 1000u) return false; rec->trust.installation.pos_accuracy_m = (uint16_t)u; break;
      case 6: if (!zs_cbor_read_uint(&r, &u) || u > 3u) return false; rec->source = (uint8_t)u; break;
      case 7: if (!zs_cbor_read_uint(&r, &u) || u == 0u || u > 0xffffffffull) return false; rec->version = (uint32_t)u; break;
      case 8: if (!zs_cbor_read_bool(&r, &b) || !b) return false; rec->trust.locked = true; break;
      case 9: if (!zs_cbor_read_uint(&r, &u) || u == 0u) return false; rec->commissioned_time_us = u; break;
      case 10: if (!zs_cbor_read_uint(&r, &u) || u > 0xffffu) return false; rec->trust.warning_distance_m = (uint16_t)u; break;
      case 11: if (!zs_cbor_read_uint(&r, &u) || u > 0xffffu) return false; rec->trust.suspect_distance_m = (uint16_t)u; break;
      case 12: if (!zs_cbor_read_uint(&r, &u) || u > 0xffffu) return false; rec->trust.gross_jump_distance_m = (uint16_t)u; break;
      case 13: if (!zs_cbor_read_uint(&r, &u) || u > 0xffu) return false; rec->trust.warning_consecutive_fixes = (uint8_t)u; break;
      case 14: if (!zs_cbor_read_uint(&r, &u) || u > 0xffu) return false; rec->trust.suspect_consecutive_fixes = (uint8_t)u; break;
      default: return false;
    }
  }
  if (!zs_cbor_reader_at_end(&r)) return false;
  rec->trust.configured = true;
  rec->trust.installation.altitude_source = 1u; /* CONFIGURED (matches the Android canonical hash) */
  rec->trust.installation.position_source = 1u;
  return true;
}

/* ---- caches ------------------------------------------------------------------------------ */

static bool push_identity(zs_ipc_service_t *s) {
  uint8_t buf[160];
  const size_t n = zs_ipc_encode_identity(s->port->identity, buf, sizeof(buf));
  return n != 0u && push_value(s, ZS_IPC_READ_VALUE, ZS_CHAR_IDENTITY, buf, n);
}

static bool push_config(zs_ipc_service_t *s) {
  uint8_t buf[ZS_STATION_CONFIG_SLOT_BYTES + 64u];
  if (!s->config_loaded) return true; /* nothing stored yet: reads stay empty until the first write */
  const size_t n = zs_station_config_encode_readback(&s->config, buf, sizeof(buf));
  return n != 0u && push_value(s, ZS_IPC_READ_VALUE, ZS_CHAR_CONFIG_READ, buf, n);
}

zs_commissioning_role_t zs_ipc_service_role(const zs_ipc_service_t *s) {
  if (!s || !s->port->peer_secure(s->port->ctx)) return ZS_COMMISSIONING_ROLE_NONE;
  if (s->session_role == ZS_COMMISSIONING_ROLE_ENGINEER) return ZS_COMMISSIONING_ROLE_ENGINEER;
  return s->port->peer_role ? s->port->peer_role(s->port->ctx) : ZS_COMMISSIONING_ROLE_INSTALLER;
}

void zs_ipc_role_tag(const uint8_t key[32], const char *serial, const uint8_t nonce[ZS_ROLE_NONCE_BYTES], uint8_t tag[ZS_ROLE_TAG_BYTES]) {
  uint8_t msg[sizeof(ZS_ROLE_CONTEXT) - 1u + 16u + ZS_ROLE_NONCE_BYTES], mac[32];
  size_t n = 0u;
  const size_t sl = strlen(serial) < 16u ? strlen(serial) : 16u;
  memcpy(msg, ZS_ROLE_CONTEXT, sizeof(ZS_ROLE_CONTEXT) - 1u); n += sizeof(ZS_ROLE_CONTEXT) - 1u;
  memcpy(msg + n, serial, sl); n += sl;
  memcpy(msg + n, nonce, ZS_ROLE_NONCE_BYTES); n += ZS_ROLE_NONCE_BYTES;
  zs_hmac_sha256(key, 32u, msg, n, mac);
  memcpy(tag, mac, ZS_ROLE_TAG_BYTES);
}

static bool push_role(zs_ipc_service_t *s) {
  const uint8_t role = (uint8_t)zs_ipc_service_role(s);
  return push_value(s, ZS_IPC_READ_VALUE, ZS_CHAR_SESSION_ROLE, &role, 1u);
}

static void role_reset(zs_ipc_service_t *s) {
  s->session_role = ZS_COMMISSIONING_ROLE_NONE;
  s->role_nonce_valid = false;
  s->role_failures = 0u;
  memset(s->role_nonce, 0, sizeof(s->role_nonce));
}

static void handle_role_write(zs_ipc_service_t *s, const uint8_t *p, size_t len) {
  uint32_t started = 0u;
  if (len == 0u) { (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_REJECTED_VALIDATION); return; }
  if (!s->port->service_mode(s->port->ctx, &started)) { (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_NOT_IN_SERVICE_MODE); return; }
  if (!s->port->peer_secure(s->port->ctx) || !s->port->engineer_key || !s->port->random || s->role_failures >= ZS_ROLE_MAX_FAILURES) {
    s->role_rejections++;
    (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_NOT_AUTHORIZED);
    return;
  }
  if (p[0] == ZS_ROLE_OP_CHALLENGE && len == 1u) {
    uint8_t out[1u + ZS_ROLE_NONCE_BYTES];
    if (!s->port->random(s->port->ctx, s->role_nonce, ZS_ROLE_NONCE_BYTES)) { (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_STORAGE_ERROR); return; }
    s->role_nonce_valid = true;
    out[0] = ZS_ROLE_OP_CHALLENGE; memcpy(out + 1, s->role_nonce, ZS_ROLE_NONCE_BYTES);
    (void)push_value(s, ZS_IPC_NOTIFY, ZS_CHAR_SESSION_ROLE, out, sizeof(out));
    (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_OK);
    return;
  }
  if (p[0] == ZS_ROLE_OP_RESPONSE && len == 1u + ZS_ROLE_TAG_BYTES) {
    uint8_t tag[ZS_ROLE_TAG_BYTES], out[2];
    if (!s->role_nonce_valid) { s->role_rejections++; (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_NOT_AUTHORIZED); return; }
    s->role_nonce_valid = false;                                   /* one attempt per nonce */
    zs_ipc_role_tag(s->port->engineer_key, s->port->identity->serial, s->role_nonce, tag);
    if (!zs_sha256_equal(tag, p + 1, ZS_ROLE_TAG_BYTES)) {
      s->role_failures++; s->role_rejections++;
      (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_NOT_AUTHORIZED);
      return;
    }
    s->session_role = ZS_COMMISSIONING_ROLE_ENGINEER;
    s->role_elevations++;
    out[0] = ZS_ROLE_OP_RESULT; out[1] = (uint8_t)ZS_COMMISSIONING_ROLE_ENGINEER;
    (void)push_value(s, ZS_IPC_NOTIFY, ZS_CHAR_SESSION_ROLE, out, sizeof(out));
    (void)push_role(s);
    (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_OK);
    return;
  }
  (void)send_status(s, ZS_CHAR_SESSION_ROLE, ZS_BLE_STATUS_REJECTED_VALIDATION);
}

static zs_commissioning_context_t context(zs_ipc_service_t *s) {
  zs_commissioning_context_t c;
  uint32_t started = 0u;
  memset(&c, 0, sizeof(c));
  c.origin = ZS_COMMISSIONING_ORIGIN_BLE_LOCAL;
  c.role = zs_ipc_service_role(s);
  c.ble_secure_connections = s->port->peer_secure(s->port->ctx);
  c.peer_identity_verified = c.ble_secure_connections;
  c.physical_service_mode = s->port->service_mode(s->port->ctx, &started);
  c.service_mode_started_ms = started;
  c.now_ms = s->port->now_ms(s->port->ctx);
  return c;
}

static bool push_installation(zs_ipc_service_t *s, bool audit_committed) {
  zs_installation_record_t rec;
  uint8_t buf[192];
  const zs_commissioning_context_t ctx = context(s);
  const zs_commissioning_result_t r = zs_installation_commissioning_read(s->port->installation_io, &ctx, &rec);
  size_t n;
  if (r == ZS_COMMISSIONING_OK) n = zs_ipc_encode_installation_readback(&rec, audit_committed, buf, sizeof(buf));
  else { buf[0] = 0xa0u; n = 1u; } /* empty map: nothing stored (or not readable in this context) */
  return n != 0u && push_value(s, ZS_IPC_READ_VALUE, ZS_CHAR_INSTALLATION_POSITION, buf, n);
}

/* ---- write handlers ---------------------------------------------------------------------- */

static uint8_t config_status(zs_station_config_result_t r) {
  switch (r) {
    case ZS_STATION_CONFIG_OK: return ZS_BLE_STATUS_OK;
    case ZS_STATION_CONFIG_VERSION_REJECTED: return ZS_BLE_STATUS_REJECTED_VERSION;
    case ZS_STATION_CONFIG_AUTH_REQUIRED: return ZS_BLE_STATUS_NOT_AUTHORIZED;
    case ZS_STATION_CONFIG_IO_ERROR: case ZS_STATION_CONFIG_VERIFY_FAILED: return ZS_BLE_STATUS_STORAGE_ERROR;
    default: return ZS_BLE_STATUS_REJECTED_VALIDATION;
  }
}

static void handle_config_write(zs_ipc_service_t *s, const uint8_t *patch, size_t len) {
  zs_station_config_t next;
  uint32_t errors = 0u;
  uint32_t started = 0u;
  const bool service = s->port->service_mode(s->port->ctx, &started);
  if (!service) { (void)send_status(s, ZS_CHAR_CONFIG_WRITE, ZS_BLE_STATUS_NOT_IN_SERVICE_MODE); return; }
  if (!s->port->peer_secure(s->port->ctx)) { (void)send_status(s, ZS_CHAR_CONFIG_WRITE, ZS_BLE_STATUS_NOT_AUTHORIZED); return; }
  zs_station_config_result_t r = zs_station_config_apply_patch(&s->config, patch, len, &next, &errors);
  if (r != ZS_STATION_CONFIG_OK) { (void)send_status(s, ZS_CHAR_CONFIG_WRITE, config_status(r)); return; }
  r = zs_station_config_store_commit(s->port->config_io, &next, true, true);
  if (r != ZS_STATION_CONFIG_OK) { (void)send_status(s, ZS_CHAR_CONFIG_WRITE, config_status(r)); return; }
  uint8_t slot;
  if (zs_station_config_store_load(s->port->config_io, &s->config, &slot) != ZS_STATION_CONFIG_OK) {
    (void)send_status(s, ZS_CHAR_CONFIG_WRITE, ZS_BLE_STATUS_STORAGE_ERROR); return;
  }
  s->config_loaded = true;
  (void)push_config(s);
  (void)send_status(s, ZS_CHAR_CONFIG_WRITE, ZS_BLE_STATUS_OK);
}

static uint8_t commissioning_status(zs_commissioning_result_t r) {
  switch (r) {
    case ZS_COMMISSIONING_OK: return ZS_BLE_STATUS_OK;
    case ZS_COMMISSIONING_LOCKED: return ZS_BLE_STATUS_POSITION_LOCKED;
    case ZS_COMMISSIONING_VERSION_REJECTED: return ZS_BLE_STATUS_REJECTED_VERSION;
    case ZS_COMMISSIONING_SERVICE_MODE_REQUIRED: return ZS_BLE_STATUS_NOT_IN_SERVICE_MODE;
    case ZS_COMMISSIONING_LOCAL_BLE_REQUIRED: case ZS_COMMISSIONING_PEER_AUTH_REQUIRED: case ZS_COMMISSIONING_POLICY_ROLE_REQUIRED:
      return ZS_BLE_STATUS_NOT_AUTHORIZED;
    case ZS_COMMISSIONING_STORAGE_IO_ERROR: case ZS_COMMISSIONING_VERIFY_FAILED: case ZS_COMMISSIONING_READBACK_FAILED:
    case ZS_COMMISSIONING_AUDIT_REQUIRED: case ZS_COMMISSIONING_AUDIT_FINALIZE_FAILED:
      return ZS_BLE_STATUS_STORAGE_ERROR;
    default: return ZS_BLE_STATUS_REJECTED_VALIDATION;
  }
}

static void handle_installation_write(zs_ipc_service_t *s, const uint8_t *p, size_t len) {
  zs_commissioning_operation_t op;
  zs_installation_record_t req, readback;
  bool committed = false;
  if (!zs_ipc_decode_installation_request(p, len, &op, &req)) { (void)send_status(s, ZS_CHAR_INSTALLATION_POSITION, ZS_BLE_STATUS_REJECTED_VALIDATION); return; }
  const zs_commissioning_context_t ctx = context(s);
  const zs_commissioning_result_t r = zs_installation_commissioning_apply(s->port->installation_io, s->port->audit_io, &ctx, op, &req, &readback, &committed);
  if (r != ZS_COMMISSIONING_OK) { (void)send_status(s, ZS_CHAR_INSTALLATION_POSITION, commissioning_status(r)); return; }
  (void)push_installation(s, committed);
  (void)send_status(s, ZS_CHAR_INSTALLATION_POSITION, ZS_BLE_STATUS_OK);
}

static void handle_self_test(zs_ipc_service_t *s, const uint8_t *p, size_t len) {
  uint8_t buf[256];
  if (len != 1u || p[0] != 0x01u || s->port->selftest == NULL) { (void)send_status(s, ZS_CHAR_SELF_TEST, ZS_BLE_STATUS_REJECTED_VALIDATION); return; }
  (void)zs_selftest_run_all(s->port->selftest, s->port->now_ms(s->port->ctx));
  const size_t n = zs_selftest_encode(s->port->selftest, buf, sizeof(buf));
  if (n == 0u) { (void)send_status(s, ZS_CHAR_SELF_TEST, ZS_BLE_STATUS_STORAGE_ERROR); return; }
  (void)push_value(s, ZS_IPC_NOTIFY, ZS_CHAR_SELF_TEST, buf, n);
}

static void on_ipc(zs_ipc_service_t *s, uint8_t type, const uint8_t *p, size_t len) {
  switch (type) {
    case ZS_IPC_PONG:
      if (len >= 1u) { s->pongs_seen++; s->peer_protocol_version = p[0]; }
      break;
    case ZS_IPC_PING: { const uint8_t v = ZS_IPC_PROTOCOL_VERSION; (void)send_ipc(s, ZS_IPC_PONG, &v, 1u); break; }
    case ZS_IPC_LINK_STATE:
      if (len >= 1u) {
        s->link_state = p[0];
        if (p[0] == 0u) role_reset(s);                              /* the role lives with the link (B.9) */
        else { (void)push_identity(s); (void)push_config(s); (void)push_installation(s, true); (void)push_role(s); }
      }
      break;
    case ZS_IPC_READ_REQUEST: {
      if (len != 2u) break;
      const uint16_t id = zs_ipc_get_u16(p);
      if (id == ZS_CHAR_IDENTITY) (void)push_identity(s);
      else if (id == ZS_CHAR_CONFIG_READ) (void)push_config(s);
      else if (id == ZS_CHAR_INSTALLATION_POSITION) (void)push_installation(s, true);
      else if (id == ZS_CHAR_SESSION_ROLE) (void)push_role(s);
      break;
    }
    case ZS_IPC_CHAR_WRITE: {
      if (len < 2u) break;
      const uint16_t id = zs_ipc_get_u16(p);
      if (id == ZS_CHAR_CONFIG_WRITE) handle_config_write(s, &p[2], len - 2u);
      else if (id == ZS_CHAR_INSTALLATION_POSITION) handle_installation_write(s, &p[2], len - 2u);
      else if (id == ZS_CHAR_SELF_TEST) handle_self_test(s, &p[2], len - 2u);
      else if (id == ZS_CHAR_SESSION_ROLE) handle_role_write(s, &p[2], len - 2u);
      else (void)send_status(s, id, ZS_BLE_STATUS_REJECTED_VALIDATION);
      break;
    }
    default: break;
  }
}

/* ---- API --------------------------------------------------------------------------------- */

bool zs_ipc_service_init(zs_ipc_service_t *s, const zs_ipc_service_port_t *port) {
  uint8_t slot;
  memset(s, 0, sizeof(*s));
  s->port = port;
  zs_ipc_decoder_init(&s->rx, s->rx_buf, sizeof(s->rx_buf));
  if (zs_station_config_store_load(port->config_io, &s->config, &slot) == ZS_STATION_CONFIG_OK) s->config_loaded = true;
  else zs_station_config_defaults(&s->config, port->identity->station_id, port->identity->region);
  const size_t name_len = strlen(port->identity->serial);
  return send_ipc(s, ZS_IPC_IDENTITY_SET, (const uint8_t *)port->identity->serial, name_len);
}

bool zs_ipc_service_set_window(zs_ipc_service_t *s, bool open, uint16_t seconds) {
  uint8_t p[3];
  p[0] = open ? 1u : 0u; zs_ipc_put_u16(&p[1], seconds);
  if (open) (void)push_identity(s);
  return send_ipc(s, ZS_IPC_SERVICE_WINDOW, p, 3u);
}

bool zs_ipc_service_ping(zs_ipc_service_t *s) {
  const uint8_t v = ZS_IPC_PROTOCOL_VERSION;
  s->pings_sent++;
  return send_ipc(s, ZS_IPC_PING, &v, 1u);
}

bool zs_ipc_service_set_pairing_secret(zs_ipc_service_t *s, const uint8_t secret[16]) {
  return send_ipc(s, ZS_IPC_PAIRING_SECRET_SET, secret, 16u);
}

void zs_ipc_service_on_uart_rx(zs_ipc_service_t *s, const uint8_t *data, size_t len) {
  for (size_t i = 0u; i < len; i++) {
    uint8_t type, seq; const uint8_t *payload; size_t n;
    if (zs_ipc_decoder_feed(&s->rx, data[i], &type, &seq, &payload, &n)) on_ipc(s, type, payload, n);
  }
}

#include "zs_ble_bridge.h"
#include "zs_sha256.h"
#include <string.h>

static bool send_ipc(zs_ble_bridge_t *b, uint8_t type, const uint8_t *payload, size_t len) {
  const size_t n = zs_ipc_encode(type, b->ipc_seq++, payload, len, b->wire, sizeof(b->wire));
  return n != 0u && b->port->uart_send(b->port->ctx, b->wire, n);
}

static bool cacheable(uint16_t id) {
  return id == ZS_CHAR_IDENTITY || id == ZS_CHAR_CONFIG_READ || id == ZS_CHAR_INSTALLATION_POSITION ||
         id == ZS_CHAR_POSITION_TRUST_POLICY || id == ZS_CHAR_SESSION_ROLE || id == ZS_CHAR_STATION_SECRETS ||
         id == ZS_CHAR_STATUS || id == ZS_CHAR_GNSS_INTEGRITY;
}

static bool writable(uint16_t id) {
  return id == ZS_CHAR_CONFIG_WRITE || id == ZS_CHAR_INSTALLATION_POSITION || id == ZS_CHAR_POSITION_TRUST_POLICY ||
         id == ZS_CHAR_SESSION_ROLE || id == ZS_CHAR_STATION_SECRETS || id == ZS_CHAR_SELF_TEST || id == ZS_CHAR_OTA_MANIFEST ||
         id == ZS_CHAR_OTA_IMAGE_CHUNK || id == ZS_CHAR_OTA_CONTROL;
}

static zs_ble_bridge_cache_t *cache_slot(zs_ble_bridge_t *b, uint16_t id, bool create) {
  for (size_t i = 0u; i < ZS_BLE_BRIDGE_CACHE_SLOTS; i++) if (b->cache[i].char_id == id) return &b->cache[i];
  if (!create) return NULL;
  for (size_t i = 0u; i < ZS_BLE_BRIDGE_CACHE_SLOTS; i++) if (b->cache[i].char_id == 0u) { b->cache[i].char_id = id; return &b->cache[i]; }
  return NULL;
}

void zs_ble_bridge_init(zs_ble_bridge_t *b, const zs_ble_bridge_port_t *port) {
  memset(b, 0, sizeof(*b));
  b->port = port;
  zs_ble_reassembler_init(&b->write_rx, b->write_buf, sizeof(b->write_buf));
  zs_ipc_decoder_init(&b->rx, b->rx_buf, sizeof(b->rx_buf));
}

bool zs_ble_bridge_on_gatt_write(zs_ble_bridge_t *b, uint16_t char_id, const uint8_t *frame, size_t len) {
  if (!writable(char_id)) return false;
  if (b->write_char != char_id) { zs_ble_reassembler_reset(&b->write_rx); b->write_char = char_id; }
  if (!zs_ble_reassembler_feed(&b->write_rx, frame, len)) { b->write_char = 0u; return false; }
  if (!b->write_rx.complete) return true;
  uint8_t payload[2u + ZS_BLE_BRIDGE_WRITE_BYTES];
  zs_ipc_put_u16(payload, char_id);
  memcpy(&payload[2], b->write_buf, b->write_rx.filled);
  const size_t n = b->write_rx.filled;
  zs_ble_reassembler_reset(&b->write_rx);
  b->write_char = 0u;
  return send_ipc(b, ZS_IPC_CHAR_WRITE, payload, 2u + n);
}

bool zs_ble_bridge_on_gatt_read(zs_ble_bridge_t *b, uint16_t char_id, uint8_t *frame, size_t cap, size_t *len) {
  zs_ble_bridge_cache_t *c = cacheable(char_id) ? cache_slot(b, char_id, false) : NULL;
  if (c == NULL || !c->valid) {
    if (cacheable(char_id)) { uint8_t id[2]; zs_ipc_put_u16(id, char_id); (void)send_ipc(b, ZS_IPC_READ_REQUEST, id, 2u); }
    return false;
  }
  if (c->reader.done) zs_ble_splitter_init(&c->reader, c->value, c->len); /* next read starts over */
  *len = zs_ble_splitter_next(&c->reader, b->port->att_payload(b->port->ctx), frame, cap);
  return *len != 0u;
}

void zs_ble_bridge_on_link(zs_ble_bridge_t *b, uint8_t state) {
  b->link_state = state;
  for (size_t i = 0u; i < ZS_BLE_BRIDGE_CACHE_SLOTS; i++) b->cache[i].reader.done = true;
  zs_ble_reassembler_reset(&b->write_rx);
  b->write_char = 0u;
  (void)send_ipc(b, ZS_IPC_LINK_STATE, &state, 1u);
}

static void notify_value(zs_ble_bridge_t *b, uint16_t char_id, const uint8_t *value, size_t len) {
  zs_ble_splitter_t s;
  uint8_t frame[ZS_BLE_ATT_PAYLOAD_MAX];
  if (!zs_ble_splitter_init(&s, value, len)) return;
  for (;;) {
    const size_t n = zs_ble_splitter_next(&s, b->port->att_payload(b->port->ctx), frame, sizeof(frame));
    if (n == 0u) break;
    if (!b->port->gatt_notify(b->port->ctx, char_id, frame, n)) { b->dropped_notifications++; break; }
  }
}

static void on_ipc(zs_ble_bridge_t *b, uint8_t type, const uint8_t *p, size_t len) {
  switch (type) {
    case ZS_IPC_PING: { const uint8_t v = ZS_IPC_PROTOCOL_VERSION; (void)send_ipc(b, ZS_IPC_PONG, &v, 1u); break; }
    case ZS_IPC_SERVICE_WINDOW:
      if (len >= 3u && b->port->advertise) b->port->advertise(b->port->ctx, p[0] != 0u, zs_ipc_get_u16(&p[1]));
      break;
    case ZS_IPC_IDENTITY_SET: {
      char name[32];
      if (len == 0u || len >= sizeof(name) || b->port->set_local_name == NULL) break;
      memcpy(name, p, len); name[len] = '\0';
      b->port->set_local_name(b->port->ctx, name);
      break;
    }
    case ZS_IPC_PAIRING_SECRET_SET:
      if (len == 16u && b->port->set_pairing_secret) b->port->set_pairing_secret(b->port->ctx, p);
      break;
    case ZS_IPC_WRITE_STATUS:
      if (len == 3u) notify_value(b, zs_ipc_get_u16(p), &p[2], 1u);
      break;
    case ZS_IPC_READ_VALUE: {
      if (len < 2u || len - 2u > ZS_BLE_BRIDGE_CACHE_BYTES) break;
      const uint16_t id = zs_ipc_get_u16(p);
      zs_ble_bridge_cache_t *c = cacheable(id) ? cache_slot(b, id, true) : NULL;
      if (c == NULL) break;
      c->len = (uint16_t)(len - 2u);
      memcpy(c->value, &p[2], c->len);
      c->valid = true;
      zs_ble_splitter_init(&c->reader, c->value, c->len);
      c->reader.done = true; /* the next read restarts from frame 0 */
      break;
    }
    case ZS_IPC_NOTIFY:
      if (len >= 2u) notify_value(b, zs_ipc_get_u16(p), &p[2], len - 2u);
      break;
    default: break;
  }
}

void zs_ble_bridge_on_uart_rx(zs_ble_bridge_t *b, const uint8_t *data, size_t len) {
  for (size_t i = 0u; i < len; i++) {
    uint8_t type, seq; const uint8_t *payload; size_t n;
    if (zs_ipc_decoder_feed(&b->rx, data[i], &type, &seq, &payload, &n)) on_ipc(b, type, payload, n);
  }
}

const zs_ble_bridge_cache_t *zs_ble_bridge_cache(const zs_ble_bridge_t *b, uint16_t char_id) {
  for (size_t i = 0u; i < ZS_BLE_BRIDGE_CACHE_SLOTS; i++) if (b->cache[i].char_id == char_id && b->cache[i].valid) return &b->cache[i];
  return NULL;
}

uint32_t zs_ble_pairing_passkey(const uint8_t secret[16]) {
  uint8_t material[11u + 16u], digest[32];
  memcpy(material, "DIO-PAIR-V1", 11u);
  memcpy(&material[11], secret, 16u);
  zs_sha256_digest(material, sizeof(material), digest);
  return (((uint32_t)digest[0] << 24) | ((uint32_t)digest[1] << 16) | ((uint32_t)digest[2] << 8) | digest[3]) % 1000000u;
}

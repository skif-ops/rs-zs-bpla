#ifndef ZS_BLE_BRIDGE_H
#define ZS_BLE_BRIDGE_H
/*
 * nRF52840 side of the BLE contract (addendum B): a transparent bridge between
 * GATT characteristics and the STM32 over the IPC link (addendum C).
 *   - writes: BLE frames are reassembled (B.2) and forwarded as CHAR_WRITE;
 *   - reads:  served from a per-characteristic cache filled by READ_VALUE pushes
 *             (a cache miss sends READ_REQUEST and fails the ATT read);
 *   - WRITE_STATUS / NOTIFY from the STM32 become framed notifications.
 * Portable: the BLE stack and the UART are behind zs_ble_bridge_port_t, so the
 * whole bridge is exercised by host tests against an Android-like client.
 */
#include "zs_ble_framing.h"
#include "zs_ipc_link.h"

/* 16-bit characteristic ids of the d10eXXXX-5a53-4c55-b0a1-000000000000 base (B.1). */
enum {
  ZS_CHAR_IDENTITY = 0x0101,
  ZS_CHAR_CONFIG_READ = 0x0201,
  ZS_CHAR_CONFIG_WRITE = 0x0202,
  ZS_CHAR_INSTALLATION_POSITION = 0x0203,
  ZS_CHAR_POSITION_TRUST_POLICY = 0x0204,
  ZS_CHAR_SESSION_ROLE = 0x0205,           /* B.9: installer by pairing, engineer by HMAC challenge */
  ZS_CHAR_STATUS = 0x0301,
  ZS_CHAR_GNSS_INTEGRITY = 0x0302,
  ZS_CHAR_SELF_TEST = 0x0303,
  ZS_CHAR_LOG_CHUNK = 0x0401,
  ZS_CHAR_OTA_MANIFEST = 0x0501,
  ZS_CHAR_OTA_IMAGE_CHUNK = 0x0502,
  ZS_CHAR_OTA_CONTROL = 0x0503
};

#define ZS_BLE_BRIDGE_CACHE_SLOTS 7u   /* identity, config_read, installation_position, policy, session_role, status, gnss */
#define ZS_BLE_BRIDGE_CACHE_BYTES 1024u
#define ZS_BLE_BRIDGE_WRITE_BYTES ZS_BLE_VALUE_MAX
#define ZS_BLE_BRIDGE_NOTIFY_BYTES ZS_BLE_VALUE_MAX

typedef struct {
  void *ctx;
  /* Sends one IPC frame to the STM32 (already COBS-encoded by the bridge). */
  bool (*uart_send)(void *ctx, const uint8_t *wire, size_t len);
  /* Sends one ATT notification frame on the characteristic; false when not subscribed / no link. */
  bool (*gatt_notify)(void *ctx, uint16_t char_id, const uint8_t *frame, size_t len);
  /* Current ATT payload size (MTU - 3), 20..244. */
  size_t (*att_payload)(void *ctx);
  /* Advertising control and identity, driven by the STM32. */
  void (*advertise)(void *ctx, bool on, uint16_t seconds);
  void (*set_local_name)(void *ctx, const char *name);
  void (*set_pairing_secret)(void *ctx, const uint8_t secret[16]);
} zs_ble_bridge_port_t;

typedef struct {
  uint16_t char_id;
  uint16_t len;
  uint8_t value[ZS_BLE_BRIDGE_CACHE_BYTES];
  zs_ble_splitter_t reader; /* read cursor for the framed value */
  bool valid;
} zs_ble_bridge_cache_t;

typedef struct {
  const zs_ble_bridge_port_t *port;
  zs_ble_bridge_cache_t cache[ZS_BLE_BRIDGE_CACHE_SLOTS];
  uint16_t write_char;
  zs_ble_reassembler_t write_rx;
  uint8_t write_buf[ZS_BLE_BRIDGE_WRITE_BYTES];
  uint8_t ipc_seq;
  uint8_t wire[ZS_IPC_PAYLOAD_MAX + ZS_IPC_PAYLOAD_MAX / 254u + 6u];
  zs_ipc_decoder_t rx;
  uint8_t rx_buf[ZS_IPC_PAYLOAD_MAX + 4u];
  uint8_t link_state;
  uint32_t dropped_notifications;
} zs_ble_bridge_t;

void zs_ble_bridge_init(zs_ble_bridge_t *b, const zs_ble_bridge_port_t *port);

/* GATT events from the BLE stack. */
bool zs_ble_bridge_on_gatt_write(zs_ble_bridge_t *b, uint16_t char_id, const uint8_t *frame, size_t len);
/* Next frame of the cached value; false = cache miss (READ_REQUEST sent) or bad characteristic. */
bool zs_ble_bridge_on_gatt_read(zs_ble_bridge_t *b, uint16_t char_id, uint8_t *frame, size_t cap, size_t *len);
void zs_ble_bridge_on_link(zs_ble_bridge_t *b, uint8_t state);

/* UART bytes from the STM32. */
void zs_ble_bridge_on_uart_rx(zs_ble_bridge_t *b, const uint8_t *data, size_t len);

/* Pairing passkey of addendum B.7: BE32(SHA-256("DIO-PAIR-V1" || secret16)[0..3]) mod 1e6. */
uint32_t zs_ble_pairing_passkey(const uint8_t secret[16]);

/* Introspection for tests / diagnostics. */
const zs_ble_bridge_cache_t *zs_ble_bridge_cache(const zs_ble_bridge_t *b, uint16_t char_id);

#endif

#ifndef ZS_IPC_SERVICE_H
#define ZS_IPC_SERVICE_H
/*
 * STM32U585 side of the BLE contract: answers CHAR_WRITE / READ_REQUEST from the
 * nRF52840 bridge (addendum C) with the station's own modules — station config
 * store, installation commissioning, self-test registry — and pushes READ_VALUE
 * caches for the characteristics the phone reads back.  Portable, host-tested.
 */
#include "zs_ble_bridge.h"
#include "zs_installation_commissioning.h"
#include "zs_selftest.h"
#include "zs_station_config.h"

/* config_write / installation_position status byte (addendum B.3 + B.6). */
enum {
  ZS_BLE_STATUS_OK = 0x00,
  ZS_BLE_STATUS_REJECTED_VALIDATION = 0x01,
  ZS_BLE_STATUS_REJECTED_VERSION = 0x02,
  ZS_BLE_STATUS_NOT_IN_SERVICE_MODE = 0x03,
  ZS_BLE_STATUS_NOT_AUTHORIZED = 0x04,
  ZS_BLE_STATUS_STORAGE_ERROR = 0x05,
  ZS_BLE_STATUS_POSITION_LOCKED = 0x06
};

typedef struct {
  char serial[16];
  char hardware_revision[16];
  char firmware_version[24];
  char bootloader_version[24];
  uint32_t station_id;
  uint8_t region; /* ZS_STATION_CONFIG_REGION_* */
} zs_ipc_identity_t;

typedef struct {
  void *ctx;
  bool (*uart_send)(void *ctx, const uint8_t *wire, size_t len);
  uint32_t (*now_ms)(void *ctx);
  /* Physical service mode (TAMPER_IN held 5 s) and its start time; role from the pairing step. */
  bool (*service_mode)(void *ctx, uint32_t *started_ms);
  zs_commissioning_role_t (*peer_role)(void *ctx);
  bool (*peer_secure)(void *ctx); /* LE Secure Connections + label secret verified */
  const zs_station_config_io_t *config_io;
  const zs_installation_store_io_t *installation_io;
  const zs_commissioning_audit_io_t *audit_io;
  zs_selftest_registry_t *selftest;
  const zs_ipc_identity_t *identity;
  /* B.9 session role. engineer_key: 32-byte per-station key from provisioning (station.json), NULL = engineer
     elevation refused; random: nonce source (hardware RNG), NULL = elevation refused. Both optional for B1. */
  const uint8_t *engineer_key;
  bool (*random)(void *ctx, uint8_t *out, size_t len);
} zs_ipc_service_port_t;

/* B.9 session_role characteristic (0x0205): read = [role]; write [0x01] asks for a challenge, the station notifies
   [0x01][nonce16]; write [0x02][tag16] with tag = HMAC-SHA256(engineer_key, "DIO-ROLE-V1" || serial || nonce)[0..15]
   elevates the session to engineer (notify [0x03][role]); status byte as for the other writes. The role lives with
   the link: LINK_STATE 0 drops it. Three failed tags lock elevation for the rest of the link. */
#define ZS_ROLE_OP_CHALLENGE 0x01u
#define ZS_ROLE_OP_RESPONSE 0x02u
#define ZS_ROLE_OP_RESULT 0x03u
#define ZS_ROLE_NONCE_BYTES 16u
#define ZS_ROLE_TAG_BYTES 16u
#define ZS_ROLE_MAX_FAILURES 3u
#define ZS_ROLE_CONTEXT "DIO-ROLE-V1"

typedef struct {
  const zs_ipc_service_port_t *port;
  zs_station_config_t config;
  bool config_loaded;
  uint8_t ipc_seq;
  uint8_t link_state;
  uint8_t wire[ZS_IPC_PAYLOAD_MAX + ZS_IPC_PAYLOAD_MAX / 254u + 6u];
  zs_ipc_decoder_t rx;
  uint8_t rx_buf[ZS_IPC_PAYLOAD_MAX + 4u];
  uint32_t writes_ok, writes_rejected;
  uint32_t pings_sent, pongs_seen;
  uint8_t peer_protocol_version; /* from the last PONG, 0 until the bridge answered */
  /* B.9 session role */
  uint8_t session_role;          /* zs_commissioning_role_t: NONE until secure, INSTALLER by pairing, ENGINEER by challenge */
  uint8_t role_nonce[ZS_ROLE_NONCE_BYTES];
  bool role_nonce_valid;
  uint8_t role_failures;
  uint32_t role_elevations, role_rejections;
} zs_ipc_service_t;

/* Effective role of the current BLE peer (used for commissioning; exposed for the console). */
zs_commissioning_role_t zs_ipc_service_role(const zs_ipc_service_t *s);
/* Computes the engineer response tag for a nonce (shared with tests and the Android/PKI side). */
void zs_ipc_role_tag(const uint8_t key[32], const char *serial, const uint8_t nonce[ZS_ROLE_NONCE_BYTES], uint8_t tag[ZS_ROLE_TAG_BYTES]);

bool zs_ipc_service_init(zs_ipc_service_t *s, const zs_ipc_service_port_t *port);
/* Opens/closes the advertising window on the nRF and pushes identity + caches. */
bool zs_ipc_service_set_window(zs_ipc_service_t *s, bool open, uint16_t seconds);
/* Link check: PING with our protocol version; the bridge answers PONG (pongs_seen / peer_protocol_version). */
bool zs_ipc_service_ping(zs_ipc_service_t *s);
/* Pushes the label pairing secret (from station.json / provisioning) to the nRF for OOB. */
bool zs_ipc_service_set_pairing_secret(zs_ipc_service_t *s, const uint8_t secret[16]);
void zs_ipc_service_on_uart_rx(zs_ipc_service_t *s, const uint8_t *data, size_t len);

/* Encoders shared with tests (identity B.4, installation read-back B.6). */
size_t zs_ipc_encode_identity(const zs_ipc_identity_t *id, uint8_t *buf, size_t cap);
size_t zs_ipc_encode_installation_readback(const zs_installation_record_t *r, bool audit_committed, uint8_t *buf, size_t cap);
/* Decodes an installation_position write (B.6); returns false when malformed. */
bool zs_ipc_decode_installation_request(const uint8_t *p, size_t len, zs_commissioning_operation_t *op, zs_installation_record_t *rec);

#endif

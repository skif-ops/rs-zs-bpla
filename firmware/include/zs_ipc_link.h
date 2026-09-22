#ifndef ZS_IPC_LINK_H
#define ZS_IPC_LINK_H
/*
 * Inter-processor link STM32U585 <-> nRF52840 over UART (ICD BLE addendum C).
 * Frame on the wire: COBS( [type:1][seq:1][payload...][crc16 BE] ) + 0x00 delimiter.
 * CRC-16/CCITT-FALSE over type..payload.  Max payload: one full GATT value + 3.
 * The nRF is a transparent GATT <-> UART bridge; all decisions live on the STM32.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_IPC_PAYLOAD_MAX (4096u + 3u)
#define ZS_IPC_PROTOCOL_VERSION 1u

enum {
  ZS_IPC_PING = 0x01,            /* either -> [version] */
  ZS_IPC_PONG = 0x02,            /* either -> [version] */
  ZS_IPC_LINK_STATE = 0x10,      /* nRF -> STM: [state] 0 disconnected, 1 connected, 2 secured (LESC) */
  ZS_IPC_SERVICE_WINDOW = 0x11,  /* STM -> nRF: [open][seconds BE16]  advertising on/off */
  ZS_IPC_IDENTITY_SET = 0x12,    /* STM -> nRF: [local name, ASCII]  advertising name (serial) */
  ZS_IPC_PAIRING_SECRET_SET = 0x13, /* STM -> nRF: [16 bytes] label secret for OOB / passkey */
  ZS_IPC_CHAR_WRITE = 0x20,      /* nRF -> STM: [char_id BE16][value...] complete reassembled value */
  ZS_IPC_WRITE_STATUS = 0x21,    /* STM -> nRF: [char_id BE16][status]  -> notified as a single frame */
  ZS_IPC_READ_VALUE = 0x22,      /* STM -> nRF: [char_id BE16][value...] cache for reads */
  ZS_IPC_NOTIFY = 0x23,          /* STM -> nRF: [char_id BE16][value...] framed notification */
  ZS_IPC_READ_REQUEST = 0x24     /* nRF -> STM: [char_id BE16] cache miss, please push READ_VALUE */
};

uint16_t zs_ipc_crc16(const uint8_t *data, size_t len);

/* Encodes one frame (COBS + delimiter). Returns wire length or 0 if `cap` is too small. */
size_t zs_ipc_encode(uint8_t type, uint8_t seq, const uint8_t *payload, size_t len, uint8_t *wire, size_t cap);

/* Byte-stream decoder: feed received bytes one at a time. */
typedef struct {
  uint8_t *buf;      /* COBS-decoded frame buffer, cap >= ZS_IPC_PAYLOAD_MAX + 4 */
  size_t cap, len;
  size_t block_left; /* COBS state */
  bool block_had_zero;
  bool overflow;
  uint32_t crc_errors, framing_errors;
} zs_ipc_decoder_t;

void zs_ipc_decoder_init(zs_ipc_decoder_t *d, uint8_t *buf, size_t cap);
/*
 * Returns true when a complete, CRC-valid frame is available: *type, *seq set,
 * *payload points into the decoder buffer (valid until the next feed), *len set.
 */
bool zs_ipc_decoder_feed(zs_ipc_decoder_t *d, uint8_t byte, uint8_t *type, uint8_t *seq, const uint8_t **payload, size_t *len);

static inline void zs_ipc_put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static inline uint16_t zs_ipc_get_u16(const uint8_t *p) { return (uint16_t)(((uint16_t)p[0] << 8) | p[1]); }

#endif

#include "zs_ipc_link.h"
#include <string.h>

uint16_t zs_ipc_crc16(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFFu;
  for (size_t i = 0u; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
  }
  return crc;
}

/* COBS encoder over a virtual byte sequence made of up to four parts (header, payload halves, CRC): the frame is
   never assembled in one buffer, so encoding costs no stack beyond the output (the STM32 BLE task and the nRF
   bridge thread run with 4 KB stacks; a 4 KB frame copy on the stack overflowed both). */
typedef struct { const uint8_t *p; size_t n; } part_t;

static size_t cobs_encode_parts(const part_t *parts, size_t count, uint8_t *out, size_t cap) {
  size_t write = 1u, code_pos = 0u;
  uint8_t code = 1u;
  if (cap < 1u) return 0u;
  for (size_t k = 0u; k < count; k++) {
    for (size_t i = 0u; i < parts[k].n; i++) {
      const uint8_t v = parts[k].p[i];
      if (v == 0u) {
        out[code_pos] = code; code = 1u; code_pos = write++;
        if (write > cap) return 0u;
      } else {
        if (write >= cap) return 0u;
        out[write++] = v; code++;
        if (code == 0xFFu) { out[code_pos] = code; code = 1u; code_pos = write++; if (write > cap) return 0u; }
      }
    }
  }
  if (code_pos >= cap) return 0u;
  out[code_pos] = code;
  return write;
}

static uint16_t crc16_update(uint16_t crc, const uint8_t *data, size_t len) {
  for (size_t i = 0u; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (int b = 0; b < 8; b++) crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
  }
  return crc;
}

size_t zs_ipc_encode2(uint8_t type, uint8_t seq, const uint8_t *head, size_t head_len, const uint8_t *payload, size_t len, uint8_t *wire, size_t cap) {
  uint8_t hdr[2], crcb[2];
  part_t parts[4];
  uint16_t crc;
  if ((head == NULL && head_len != 0u) || (payload == NULL && len != 0u) || head_len + len > ZS_IPC_PAYLOAD_MAX || wire == NULL) return 0u;
  hdr[0] = type; hdr[1] = seq;
  crc = crc16_update(0xFFFFu, hdr, 2u);
  crc = crc16_update(crc, head, head_len);
  crc = crc16_update(crc, payload, len);
  zs_ipc_put_u16(crcb, crc);
  parts[0].p = hdr; parts[0].n = 2u;
  parts[1].p = head; parts[1].n = head_len;
  parts[2].p = payload; parts[2].n = len;
  parts[3].p = crcb; parts[3].n = 2u;
  const size_t n = cobs_encode_parts(parts, 4u, wire, cap > 0u ? cap - 1u : 0u);
  if (n == 0u) return 0u;
  wire[n] = 0u;
  return n + 1u;
}

size_t zs_ipc_encode(uint8_t type, uint8_t seq, const uint8_t *payload, size_t len, uint8_t *wire, size_t cap) {
  return zs_ipc_encode2(type, seq, NULL, 0u, payload, len, wire, cap);
}

void zs_ipc_decoder_init(zs_ipc_decoder_t *d, uint8_t *buf, size_t cap) {
  memset(d, 0, sizeof(*d));
  d->buf = buf; d->cap = cap;
}

static void decoder_restart(zs_ipc_decoder_t *d) {
  d->len = 0u; d->block_left = 0u; d->block_had_zero = false; d->overflow = false;
}

bool zs_ipc_decoder_feed(zs_ipc_decoder_t *d, uint8_t byte, uint8_t *type, uint8_t *seq, const uint8_t **payload, size_t *len) {
  if (byte == 0u) { /* delimiter: finish the frame */
    const bool had = d->len > 0u || d->block_left > 0u || d->overflow;
    if (!had) return false; /* idle zeros between frames */
    if (d->overflow || d->block_left != 0u || d->len < 4u) { d->framing_errors++; decoder_restart(d); return false; }
    const size_t body = d->len - 2u;
    if (zs_ipc_crc16(d->buf, body) != zs_ipc_get_u16(&d->buf[body])) { d->crc_errors++; decoder_restart(d); return false; }
    *type = d->buf[0]; *seq = d->buf[1]; *payload = &d->buf[2]; *len = body - 2u;
    decoder_restart(d);
    return true;
  }
  if (d->overflow) return false;
  if (d->block_left == 0u) { /* code byte */
    if (d->block_had_zero) { if (d->len < d->cap) d->buf[d->len++] = 0u; else d->overflow = true; }
    d->block_left = (size_t)byte - 1u;
    d->block_had_zero = byte != 0xFFu;
    return false;
  }
  if (d->len < d->cap) d->buf[d->len++] = byte; else d->overflow = true;
  d->block_left--;
  return false;
}

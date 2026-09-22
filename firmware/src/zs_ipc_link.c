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

/* COBS encode of `in` into `out`; returns encoded length (without delimiter). */
static size_t cobs_encode(const uint8_t *in, size_t len, uint8_t *out, size_t cap) {
  size_t read = 0u, write = 1u, code_pos = 0u;
  uint8_t code = 1u;
  if (cap < 1u) return 0u;
  while (read < len) {
    if (in[read] == 0u) {
      out[code_pos] = code; code = 1u; code_pos = write++;
      if (write > cap) return 0u;
    } else {
      if (write >= cap) return 0u;
      out[write++] = in[read]; code++;
      if (code == 0xFFu) { out[code_pos] = code; code = 1u; code_pos = write++; if (write > cap) return 0u; }
    }
    read++;
  }
  if (code_pos >= cap) return 0u;
  out[code_pos] = code;
  return write;
}

size_t zs_ipc_encode(uint8_t type, uint8_t seq, const uint8_t *payload, size_t len, uint8_t *wire, size_t cap) {
  uint8_t raw[ZS_IPC_PAYLOAD_MAX + 4u];
  if ((payload == NULL && len != 0u) || len > ZS_IPC_PAYLOAD_MAX || wire == NULL) return 0u;
  raw[0] = type; raw[1] = seq;
  if (len) memcpy(&raw[2], payload, len);
  const uint16_t crc = zs_ipc_crc16(raw, len + 2u);
  zs_ipc_put_u16(&raw[len + 2u], crc);
  const size_t n = cobs_encode(raw, len + 4u, wire, cap > 0u ? cap - 1u : 0u);
  if (n == 0u) return 0u;
  wire[n] = 0u;
  return n + 1u;
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

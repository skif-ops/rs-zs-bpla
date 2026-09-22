#include "zs_ble_framing.h"
#include <string.h>

bool zs_ble_splitter_init(zs_ble_splitter_t *s, const uint8_t *value, size_t len) {
  if (s == NULL || (value == NULL && len != 0u) || len > ZS_BLE_VALUE_MAX) return false;
  s->value = value; s->len = len; s->pos = 0u; s->seq = 0u; s->done = false;
  return true;
}

size_t zs_ble_splitter_next(zs_ble_splitter_t *s, size_t att_payload, uint8_t *frame, size_t cap) {
  if (s == NULL || s->done || frame == NULL) return 0u;
  if (att_payload < ZS_BLE_FRAME_HEADER + ZS_BLE_FRAME_FIRST_EXTRA + 1u || cap < att_payload) return 0u;
  const bool first = s->pos == 0u;
  size_t o = ZS_BLE_FRAME_HEADER + (first ? ZS_BLE_FRAME_FIRST_EXTRA : 0u);
  size_t room = att_payload - o;
  size_t n = s->len - s->pos;
  if (n > room) n = room;
  const bool last = s->pos + n >= s->len;
  frame[0] = s->seq;
  frame[1] = (uint8_t)((first ? ZS_BLE_FRAME_FLAG_FIRST : 0u) | (last ? ZS_BLE_FRAME_FLAG_LAST : 0u));
  if (first) { frame[2] = (uint8_t)(s->len >> 8); frame[3] = (uint8_t)s->len; }
  if (n) memcpy(&frame[o], &s->value[s->pos], n);
  s->pos += n;
  s->seq++;
  if (last) s->done = true;
  return o + n;
}

void zs_ble_reassembler_init(zs_ble_reassembler_t *r, uint8_t *buf, size_t cap) {
  r->buf = buf; r->cap = cap;
  zs_ble_reassembler_reset(r);
}

void zs_ble_reassembler_reset(zs_ble_reassembler_t *r) {
  r->total = 0u; r->filled = 0u; r->expected_seq = 0u; r->active = false; r->complete = false;
}

bool zs_ble_reassembler_feed(zs_ble_reassembler_t *r, const uint8_t *frame, size_t len) {
  if (r == NULL || frame == NULL || r->complete || len < ZS_BLE_FRAME_HEADER) { if (r) zs_ble_reassembler_reset(r); return false; }
  const uint8_t seq = frame[0], flags = frame[1];
  const bool first = (flags & ZS_BLE_FRAME_FLAG_FIRST) != 0u, last = (flags & ZS_BLE_FRAME_FLAG_LAST) != 0u;
  size_t o = ZS_BLE_FRAME_HEADER;
  if (first) {
    if (r->active || seq != 0u || len < ZS_BLE_FRAME_HEADER + ZS_BLE_FRAME_FIRST_EXTRA) { zs_ble_reassembler_reset(r); return false; }
    r->total = ((size_t)frame[2] << 8) | frame[3];
    if (r->total > ZS_BLE_VALUE_MAX || r->total > r->cap) { zs_ble_reassembler_reset(r); return false; }
    r->active = true; r->filled = 0u;
    o += ZS_BLE_FRAME_FIRST_EXTRA;
  } else if (!r->active || seq != r->expected_seq) { zs_ble_reassembler_reset(r); return false; }
  const size_t n = len - o;
  if (r->filled + n > r->total) { zs_ble_reassembler_reset(r); return false; }
  if (n) memcpy(&r->buf[r->filled], &frame[o], n);
  r->filled += n;
  r->expected_seq = (uint8_t)(seq + 1u);
  if (last) {
    if (r->filled != r->total) { zs_ble_reassembler_reset(r); return false; }
    r->complete = true;
  }
  return true;
}

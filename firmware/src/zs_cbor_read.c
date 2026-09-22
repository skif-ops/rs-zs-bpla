#include "zs_cbor_read.h"
#include <string.h>

void zs_cbor_reader_init(zs_cbor_reader_t *r, const uint8_t *buf, size_t len) { r->buf = buf; r->len = len; r->pos = 0u; }

static bool head(zs_cbor_reader_t *r, uint8_t want_major, uint64_t *value) {
  if (r->pos >= r->len) return false;
  const uint8_t ib = r->buf[r->pos];
  if ((ib >> 5) != want_major) return false;
  const uint8_t ai = ib & 0x1fu;
  size_t extra;
  if (ai < 24u) { *value = ai; r->pos++; return true; }
  if (ai == 24u) extra = 1u; else if (ai == 25u) extra = 2u; else if (ai == 26u) extra = 4u; else if (ai == 27u) extra = 8u; else return false;
  if (r->pos + 1u + extra > r->len) return false;
  uint64_t v = 0u;
  for (size_t i = 0u; i < extra; i++) v = (v << 8) | r->buf[r->pos + 1u + i];
  /* canonical: the shortest encoding must have been used */
  if ((extra == 1u && v < 24u) || (extra == 2u && v < 0x100u) || (extra == 4u && v < 0x10000u) || (extra == 8u && v < 0x100000000ull)) return false;
  *value = v; r->pos += 1u + extra;
  return true;
}

bool zs_cbor_read_map(zs_cbor_reader_t *r, uint32_t *count) { uint64_t v; if (!head(r, 5u, &v) || v > 0xffffffffull) return false; *count = (uint32_t)v; return true; }
bool zs_cbor_read_uint(zs_cbor_reader_t *r, uint64_t *v) { return head(r, 0u, v); }

bool zs_cbor_read_int(zs_cbor_reader_t *r, int64_t *v) {
  uint64_t u;
  if (r->pos >= r->len) return false;
  if ((r->buf[r->pos] >> 5) == 1u) { if (!head(r, 1u, &u) || u > 0x7fffffffffffffffull) return false; *v = -1 - (int64_t)u; return true; }
  if (!head(r, 0u, &u) || u > 0x7fffffffffffffffull) return false;
  *v = (int64_t)u; return true;
}

bool zs_cbor_read_bool(zs_cbor_reader_t *r, bool *v) {
  if (r->pos >= r->len) return false;
  if (r->buf[r->pos] == 0xf5u) { *v = true; r->pos++; return true; }
  if (r->buf[r->pos] == 0xf4u) { *v = false; r->pos++; return true; }
  return false;
}

bool zs_cbor_read_bytes(zs_cbor_reader_t *r, const uint8_t **data, size_t *n) {
  uint64_t len;
  if (!head(r, 2u, &len) || len > r->len - r->pos) return false;
  *data = &r->buf[r->pos]; *n = (size_t)len; r->pos += (size_t)len;
  return true;
}

bool zs_cbor_read_text(zs_cbor_reader_t *r, char *dst, size_t cap) {
  uint64_t len;
  if (!head(r, 3u, &len) || len > r->len - r->pos || len >= cap) return false;
  memcpy(dst, &r->buf[r->pos], (size_t)len); dst[len] = '\0'; r->pos += (size_t)len;
  return true;
}

bool zs_cbor_reader_at_end(const zs_cbor_reader_t *r) { return r->pos == r->len; }

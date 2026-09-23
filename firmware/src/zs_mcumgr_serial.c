#include "zs_mcumgr_serial.h"
#include "zs_cbor.h"
#include "zs_cbor_read.h"
#include "zs_sha256.h"
#include <string.h>

#define START1 0x06u
#define START2 0x09u
#define CONT1 0x04u
#define CONT2 0x14u
#define FRAME_RAW_BYTES 93u   /* 93 raw bytes -> 124 base64 chars + 2 markers + '\n' = 127 */

uint16_t zs_mcumgr_crc16(const uint8_t *data, size_t len) {   /* CRC-16/XMODEM: poly 0x1021, init 0, no reflection */
  uint16_t crc = 0u;
  for (size_t i = 0u; i < len; i++) {
    crc ^= (uint16_t)((uint16_t)data[i] << 8);
    for (unsigned b = 0u; b < 8u; b++) crc = (uint16_t)((crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1));
  }
  return crc;
}

static const char b64tab[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static size_t b64_encode(const uint8_t *in, size_t n, uint8_t *out) {
  size_t o = 0u;
  for (size_t i = 0u; i < n; i += 3u) {
    uint32_t v = (uint32_t)in[i] << 16;
    if (i + 1u < n) v |= (uint32_t)in[i + 1u] << 8;
    if (i + 2u < n) v |= in[i + 2u];
    out[o++] = (uint8_t)b64tab[(v >> 18) & 63u];
    out[o++] = (uint8_t)b64tab[(v >> 12) & 63u];
    out[o++] = (i + 1u < n) ? (uint8_t)b64tab[(v >> 6) & 63u] : (uint8_t)'=';
    out[o++] = (i + 2u < n) ? (uint8_t)b64tab[v & 63u] : (uint8_t)'=';
  }
  return o;
}

static int b64_val(uint8_t c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

static bool b64_decode(const uint8_t *in, size_t n, uint8_t *out, size_t cap, size_t *out_len) {
  size_t o = 0u;
  if (n % 4u) return false;
  for (size_t i = 0u; i < n; i += 4u) {
    int a = b64_val(in[i]), b = b64_val(in[i + 1u]);
    if (a < 0 || b < 0) return false;
    uint32_t v = ((uint32_t)a << 18) | ((uint32_t)b << 12);
    unsigned bytes = 1u;
    if (in[i + 2u] != '=') { int c = b64_val(in[i + 2u]); if (c < 0) return false; v |= (uint32_t)c << 6; bytes = 2u; }
    if (in[i + 3u] != '=') { int d = b64_val(in[i + 3u]); if (d < 0 || bytes != 2u) return false; v |= (uint32_t)d; bytes = 3u; }
    if (o + bytes > cap) return false;
    out[o++] = (uint8_t)(v >> 16);
    if (bytes > 1u) out[o++] = (uint8_t)(v >> 8);
    if (bytes > 2u) out[o++] = (uint8_t)v;
  }
  *out_len = o;
  return true;
}

size_t zs_mcumgr_smp_build(uint8_t op, uint16_t group, uint8_t id, uint8_t seq, const uint8_t *cbor, size_t cbor_len, uint8_t *out, size_t cap) {
  if (cbor_len > 0xffffu || cap < 8u + cbor_len) return 0u;
  out[0] = op; out[1] = 0u;
  out[2] = (uint8_t)(cbor_len >> 8); out[3] = (uint8_t)cbor_len;
  out[4] = (uint8_t)(group >> 8); out[5] = (uint8_t)group;
  out[6] = seq; out[7] = id;
  memcpy(out + 8, cbor, cbor_len);
  return 8u + cbor_len;
}

bool zs_mcumgr_smp_parse(const uint8_t *pkt, size_t len, zs_smp_header_t *hdr, const uint8_t **cbor, size_t *cbor_len) {
  if (!pkt || len < 8u) return false;
  const uint16_t plen = (uint16_t)(((uint16_t)pkt[2] << 8) | pkt[3]);
  if (8u + (size_t)plen != len) return false;
  hdr->op = (uint8_t)(pkt[0] & 0x07u); hdr->flags = pkt[1]; hdr->len = plen;
  hdr->group_hi = pkt[4]; hdr->group_lo = pkt[5]; hdr->seq = pkt[6]; hdr->id = pkt[7];
  *cbor = pkt + 8; *cbor_len = plen;
  return true;
}

size_t zs_mcumgr_frame_encode(const uint8_t *pkt, size_t len, uint8_t *out, size_t cap) {
  if (!pkt || len + 2u > 0xffffu) return 0u;
  uint8_t raw[ZS_MCUMGR_PACKET_MAX + 4u];
  if (len + 4u > sizeof(raw)) return 0u;
  const uint16_t wire_len = (uint16_t)(len + 2u), crc = zs_mcumgr_crc16(pkt, len);
  raw[0] = (uint8_t)(wire_len >> 8); raw[1] = (uint8_t)wire_len;
  memcpy(raw + 2, pkt, len);
  raw[2 + len] = (uint8_t)(crc >> 8); raw[3 + len] = (uint8_t)crc;
  const size_t total = len + 4u;
  size_t o = 0u;
  for (size_t off = 0u; off < total; off += FRAME_RAW_BYTES) {
    const size_t n = (total - off) < FRAME_RAW_BYTES ? (total - off) : FRAME_RAW_BYTES;
    const size_t need = 2u + ((n + 2u) / 3u) * 4u + 1u;
    if (o + need > cap) return 0u;
    out[o++] = off ? CONT1 : START1;
    out[o++] = off ? CONT2 : START2;
    o += b64_encode(raw + off, n, out + o);
    out[o++] = (uint8_t)'\n';
  }
  return o;
}

void zs_mcumgr_decoder_init(zs_mcumgr_decoder_t *d) { memset(d, 0, sizeof(*d)); }

static bool decoder_line(zs_mcumgr_decoder_t *d, const uint8_t **packet, size_t *len) {
  const uint8_t *l = d->line;
  const size_t n = d->line_len;
  if (n < 2u) return false;
  const bool first = (l[0] == START1 && l[1] == START2), cont = (l[0] == CONT1 && l[1] == CONT2);
  if (!first && !cont) { d->bad_frames++; return false; }
  if (first) { d->packet_len = 0u; d->expected = 0u; d->in_packet = true; }
  else if (!d->in_packet) { d->bad_frames++; return false; }
  uint8_t chunk[FRAME_RAW_BYTES + 3u];
  size_t got = 0u;
  if (!b64_decode(l + 2, n - 2u, chunk, sizeof(chunk), &got) || d->packet_len + got > sizeof(d->packet)) { d->bad_frames++; d->in_packet = false; return false; }
  memcpy(d->packet + d->packet_len, chunk, got);
  d->packet_len += got;
  if (d->expected == 0u && d->packet_len >= 2u) d->expected = (size_t)(((size_t)d->packet[0] << 8) | d->packet[1]) + 2u;
  if (d->expected == 0u || d->packet_len < d->expected) return false;
  d->in_packet = false;
  if (d->packet_len != d->expected || d->expected < 4u) { d->bad_frames++; return false; }
  const size_t plen = d->expected - 4u;
  const uint16_t crc = (uint16_t)(((uint16_t)d->packet[2 + plen] << 8) | d->packet[3 + plen]);
  if (crc != zs_mcumgr_crc16(d->packet + 2, plen)) { d->bad_frames++; return false; }
  d->packets++;
  *packet = d->packet + 2; *len = plen;
  return true;
}

bool zs_mcumgr_decoder_feed(zs_mcumgr_decoder_t *d, uint8_t byte, const uint8_t **packet, size_t *len) {
  if (byte == '\n' || byte == '\r') {
    const bool got = decoder_line(d, packet, len);
    d->line_len = 0u;
    return got;
  }
  if (d->line_len < ZS_MCUMGR_FRAME_MAX) d->line[d->line_len++] = byte;
  else { d->line_len = 0u; d->bad_frames++; d->in_packet = false; }
  return false;
}

/* ---- image upload client ------------------------------------------------------------------------ */

void zs_mcumgr_upload_init(zs_mcumgr_upload_t *u, const uint8_t *image, size_t size) {
  memset(u, 0, sizeof(*u));
  u->image = image; u->size = size;
  zs_sha256_digest(image, size, u->sha);
}

void zs_mcumgr_upload_init_reader(zs_mcumgr_upload_t *u, zs_mcumgr_image_read_fn read, void *ctx, size_t size, const uint8_t sha256[32]) {
  memset(u, 0, sizeof(*u));
  u->read = read; u->read_ctx = ctx; u->size = size;
  memcpy(u->sha, sha256, 32u);
}

size_t zs_mcumgr_upload_request(zs_mcumgr_upload_t *u, uint8_t *serial, size_t cap) {
  if (!u || u->done || u->failed || (!u->image && !u->read)) return 0u;
  uint8_t cbor[ZS_MCUMGR_PACKET_MAX], pkt[ZS_MCUMGR_PACKET_MAX];
  zs_cbor_t c; zs_cbor_init(&c, cbor, sizeof(cbor));
  size_t n = u->size - u->offset;
  if (n > ZS_MCUMGR_UPLOAD_CHUNK) n = ZS_MCUMGR_UPLOAD_CHUNK;
  const uint8_t *src = u->image ? u->image + u->offset : u->chunk;
  if (!u->image && !u->read(u->read_ctx, u->offset, u->chunk, n)) { u->failed = true; return 0u; }
  if (u->offset == 0u) {
    zs_cbor_map(&c, 5u);
    zs_cbor_text(&c, "image"); zs_cbor_uint(&c, 0u);
    zs_cbor_text(&c, "len"); zs_cbor_uint(&c, u->size);
    zs_cbor_text(&c, "sha"); zs_cbor_bytes(&c, u->sha, sizeof(u->sha));
  } else {
    zs_cbor_map(&c, 2u);
  }
  zs_cbor_text(&c, "off"); zs_cbor_uint(&c, u->offset);
  zs_cbor_text(&c, "data"); zs_cbor_bytes(&c, src, n);
  if (c.error) { u->failed = true; return 0u; }
  const size_t plen = zs_mcumgr_smp_build(ZS_MCUMGR_OP_WRITE, ZS_MCUMGR_GROUP_IMAGE, ZS_MCUMGR_IMAGE_ID_UPLOAD, u->seq, cbor, c.len, pkt, sizeof(pkt));
  return plen ? zs_mcumgr_frame_encode(pkt, plen, serial, cap) : 0u;
}

bool zs_mcumgr_upload_response(zs_mcumgr_upload_t *u, const uint8_t *pkt, size_t len) {
  zs_smp_header_t h; const uint8_t *cbor; size_t cbor_len;
  if (!u || !zs_mcumgr_smp_parse(pkt, len, &h, &cbor, &cbor_len)) return false;
  if (h.op != (ZS_MCUMGR_OP_WRITE | 1u) || h.group_hi != 0u || h.group_lo != ZS_MCUMGR_GROUP_IMAGE || h.id != ZS_MCUMGR_IMAGE_ID_UPLOAD || h.seq != u->seq) return false;
  zs_cbor_reader_t r; zs_cbor_reader_init(&r, cbor, cbor_len);
  uint32_t count; int64_t rc = 0; uint64_t off = u->offset; bool have_off = false;
  if (!zs_cbor_read_map(&r, &count)) return false;
  for (uint32_t i = 0u; i < count; i++) {
    char key[8];
    if (!zs_cbor_read_text(&r, key, sizeof(key))) return false;
    if (!strcmp(key, "rc")) { if (!zs_cbor_read_int(&r, &rc)) return false; }
    else if (!strcmp(key, "off")) { if (!zs_cbor_read_uint(&r, &off)) return false; have_off = true; }
    else return false;   /* MCUboot serial recovery sends only rc/off; anything else is not this protocol */
  }
  u->last_rc = (int)rc;
  u->seq++;
  if (rc != 0) { if (++u->retries >= 3u) u->failed = true; return true; }
  if (!have_off || off > u->size) { if (++u->retries >= 3u) u->failed = true; return true; }
  u->retries = 0u;
  u->offset = (size_t)off;          /* resume from what the target has; a skipped chunk is resent */
  if (u->offset == u->size) u->done = true;
  return true;
}

size_t zs_mcumgr_reset_request(uint8_t seq, uint8_t *serial, size_t cap) {
  uint8_t cbor[4], pkt[16];
  zs_cbor_t c; zs_cbor_init(&c, cbor, sizeof(cbor));
  zs_cbor_map(&c, 0u);
  const size_t plen = zs_mcumgr_smp_build(ZS_MCUMGR_OP_WRITE, ZS_MCUMGR_GROUP_OS, ZS_MCUMGR_OS_ID_RESET, seq, cbor, c.len, pkt, sizeof(pkt));
  return plen ? zs_mcumgr_frame_encode(pkt, plen, serial, cap) : 0u;
}

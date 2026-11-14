#include "zs_nor_image_store.h"
#include <string.h>

static const uint8_t MAGIC[8] = {'Z', 'S', 'N', 'R', 'F', 'I', 'M', 'G'};

/* CRC-16/XMODEM, the same polynomial the mcumgr serial transport uses; kept local to avoid the dependency */
static uint16_t crc16(const uint8_t *d, size_t n) {
  uint16_t c = 0u;
  for (size_t i = 0u; i < n; i++) { c ^= (uint16_t)((uint16_t)d[i] << 8); for (unsigned b = 0u; b < 8u; b++) c = (uint16_t)((c & 0x8000u) ? (uint16_t)((c << 1) ^ 0x1021u) : (uint16_t)(c << 1)); }
  return c;
}

static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static uint32_t get32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }

bool zs_nor_image_store_init(zs_nor_image_store_t *s, zs_nor_t *nor, uint32_t base_address, uint32_t partition_bytes) {
  if (!s) return false;
  memset(s, 0, sizeof(*s));
  if (!nor || nor->geometry.erase_bytes == 0u || base_address % nor->geometry.erase_bytes != 0u ||
      partition_bytes % nor->geometry.erase_bytes != 0u || partition_bytes < 2u * nor->geometry.erase_bytes ||
      (uint64_t)base_address + partition_bytes > nor->geometry.capacity_bytes)
    return false;
  s->nor = nor; s->base = base_address; s->bytes = partition_bytes; s->erase_bytes = nor->geometry.erase_bytes;
  return true;
}

uint32_t zs_nor_image_store_capacity(const zs_nor_image_store_t *s) { return s && s->nor ? s->bytes - s->erase_bytes : 0u; }

bool zs_nor_image_store_begin(zs_nor_image_store_t *s, uint32_t size, uint32_t version, const uint8_t sha256[32]) {
  if (!s || !s->nor || !sha256 || size == 0u || size > zs_nor_image_store_capacity(s)) return false;
  s->writing = false; s->valid = false;
  const uint32_t data_blocks = (size + s->erase_bytes - 1u) / s->erase_bytes;
  if (!zs_nor_erase(s->nor, s->base, (size_t)(data_blocks + 1u) * s->erase_bytes)) return false;   /* header block + image */
  s->writing = true; s->write_size = size; s->write_version = version; s->written = 0u;
  memcpy(s->expected_sha, sha256, 32u);
  zs_sha256_init(&s->running);
  return true;
}

bool zs_nor_image_store_write(zs_nor_image_store_t *s, const uint8_t *data, size_t len) {
  if (!s || !s->writing || !data) return false;
  if ((uint64_t)s->written + len > s->write_size) { s->writing = false; return false; }
  if (len && !zs_nor_program(s->nor, s->base + s->erase_bytes + s->written, data, len)) { s->writing = false; return false; }
  zs_sha256_update(&s->running, data, len);
  s->written += (uint32_t)len;
  return true;
}

static bool read_back_sha(zs_nor_image_store_t *s, uint32_t size, uint8_t out[32]) {
  zs_sha256_t ctx; uint8_t buf[256];
  zs_sha256_init(&ctx);
  for (uint32_t off = 0u; off < size; off += sizeof(buf)) {
    const size_t n = (size - off) < sizeof(buf) ? (size - off) : sizeof(buf);
    if (!zs_nor_read(s->nor, s->base + s->erase_bytes + off, buf, n)) return false;
    zs_sha256_update(&ctx, buf, n);
  }
  zs_sha256_final(&ctx, out);
  return true;
}

bool zs_nor_image_store_finish(zs_nor_image_store_t *s) {
  uint8_t digest[32], back[32], hdr[ZS_NOR_IMAGE_HEADER_BYTES];
  if (!s || !s->writing) return false;
  s->writing = false;
  if (s->written != s->write_size) return false;
  zs_sha256_final(&s->running, digest);
  if (memcmp(digest, s->expected_sha, 32u) != 0) return false;            /* the sender's SHA-256 does not match what it sent */
  if (!read_back_sha(s, s->write_size, back) || memcmp(back, digest, 32u) != 0) return false;   /* what landed in NOR */
  memset(hdr, 0xff, sizeof(hdr));
  memcpy(hdr, MAGIC, 8u);
  put32(hdr + 8, ZS_NOR_IMAGE_FORMAT); put32(hdr + 12, s->write_version); put32(hdr + 16, s->write_size);
  memcpy(hdr + 20, digest, 32u);
  const uint16_t crc = crc16(hdr, 52u);
  hdr[52] = (uint8_t)(crc >> 8); hdr[53] = (uint8_t)crc;
  if (!zs_nor_program(s->nor, s->base, hdr, sizeof(hdr))) return false;
  return zs_nor_image_store_open(s, false, NULL);
}

void zs_nor_image_store_abort(zs_nor_image_store_t *s) { if (s) { s->writing = false; } }

bool zs_nor_image_store_open(zs_nor_image_store_t *s, bool verify, zs_nor_image_info_t *info) {
  uint8_t hdr[ZS_NOR_IMAGE_HEADER_BYTES];
  if (!s || !s->nor) return false;
  s->valid = false;
  if (!zs_nor_read(s->nor, s->base, hdr, sizeof(hdr)) || memcmp(hdr, MAGIC, 8u) != 0) return false;
  const uint16_t crc = (uint16_t)(((uint16_t)hdr[52] << 8) | hdr[53]);
  if (crc != crc16(hdr, 52u) || get32(hdr + 8) != ZS_NOR_IMAGE_FORMAT) return false;
  const uint32_t size = get32(hdr + 16);
  if (size == 0u || size > zs_nor_image_store_capacity(s)) return false;
  s->info.format = ZS_NOR_IMAGE_FORMAT; s->info.version = get32(hdr + 12); s->info.size = size;
  memcpy(s->info.sha256, hdr + 20, 32u);
  if (verify) { uint8_t back[32]; if (!read_back_sha(s, size, back) || memcmp(back, s->info.sha256, 32u) != 0) return false; }
  s->valid = true;
  if (info) *info = s->info;
  return true;
}

bool zs_nor_image_store_read(zs_nor_image_store_t *s, uint32_t offset, uint8_t *dst, size_t len) {
  if (!s || !s->valid || !dst || (uint64_t)offset + len > s->info.size) return false;
  return zs_nor_read(s->nor, s->base + s->erase_bytes + offset, dst, len);
}

bool zs_nor_image_store_reader(void *ctx, size_t offset, uint8_t *dst, size_t len) {
  return zs_nor_image_store_read((zs_nor_image_store_t *)ctx, (uint32_t)offset, dst, len);
}

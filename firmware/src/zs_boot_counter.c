#include "zs_boot_counter.h"

#include <string.h>

static const uint8_t MAGIC[8] = {'Z', 'S', 'B', 'O', 'O', 'T', '0', '1'};

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static void put_le32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static unsigned zero_bits(uint8_t b) { unsigned n = 0u; for (unsigned i = 0u; i < 8u; i++) if (!(b & (1u << i))) n++; return n; }

static uint32_t bitmap_bits(const zs_boot_counter_t *c) { return (c->block_bytes - ZS_BOOT_COUNTER_HEADER_BYTES) * 8u; }

/* Counts cleared bits; stops at the first byte that still has all its bits set (everything after it is 0xff). */
static bool count_bitmap(zs_boot_counter_t *c) {
  uint8_t buf[64];
  uint32_t off = ZS_BOOT_COUNTER_HEADER_BYTES, bits = 0u;
  while (off < c->block_bytes) {
    const size_t n = (c->block_bytes - off) < sizeof(buf) ? (size_t)(c->block_bytes - off) : sizeof(buf);
    if (!zs_nor_read(c->nor, c->base_address + off, buf, n)) return false;
    for (size_t i = 0u; i < n; i++) {
      if (buf[i] == 0xffu) { c->used_bits = bits; return true; }
      bits += zero_bits(buf[i]);
      if (buf[i] != 0u) { c->used_bits = bits; return true; }   /* partial byte: the running edge */
    }
    off += (uint32_t)n;
  }
  c->used_bits = bits;
  return true;
}

bool zs_boot_counter_open(zs_boot_counter_t *c, zs_nor_t *nor, uint32_t base_address, uint32_t block_bytes) {
  uint8_t header[ZS_BOOT_COUNTER_HEADER_BYTES];
  if (!c) return false;
  memset(c, 0, sizeof(*c));
  if (!nor || block_bytes <= ZS_BOOT_COUNTER_HEADER_BYTES) return false;
  c->nor = nor; c->base_address = base_address; c->block_bytes = block_bytes;
  if (!zs_nor_read(nor, base_address, header, sizeof(header))) return false;
  if (memcmp(header, MAGIC, sizeof(MAGIC)) != 0 || le32(header + 8) != (uint32_t)~le32(header + 12)) return true;   /* unformatted: value 0 */
  c->base = le32(header + 8);
  c->formatted = true;
  return count_bitmap(c);
}

uint32_t zs_boot_counter_value(const zs_boot_counter_t *c) { return (c && c->formatted) ? c->base + c->used_bits : 0u; }

static bool format_block(zs_boot_counter_t *c, uint32_t base) {
  uint8_t header[ZS_BOOT_COUNTER_HEADER_BYTES];
  memcpy(header, MAGIC, sizeof(MAGIC));
  put_le32(header + 8, base);
  put_le32(header + 12, ~base);
  if (!zs_nor_erase(c->nor, c->base_address, c->block_bytes)) return false;
  if (!zs_nor_program(c->nor, c->base_address, header, sizeof(header))) return false;
  c->base = base; c->used_bits = 0u; c->formatted = true;
  return true;
}

bool zs_boot_counter_increment(zs_boot_counter_t *c, uint32_t *boot_id) {
  uint8_t byte;
  uint32_t idx;
  if (!c || !c->nor) return false;
  if (!c->formatted) { if (!format_block(c, 0u)) return false; }
  else if (c->used_bits >= bitmap_bits(c)) { if (!format_block(c, c->base + c->used_bits)) return false; }   /* bitmap exhausted: carry into the base */
  idx = ZS_BOOT_COUNTER_HEADER_BYTES + c->used_bits / 8u;
  byte = (uint8_t)(0xffu << ((c->used_bits % 8u) + 1u));         /* clear one more bit (LSB first) */
  if (!zs_nor_program(c->nor, c->base_address + idx, &byte, 1u)) return false;
  c->used_bits++;
  if (boot_id) *boot_id = c->base + c->used_bits;
  return true;
}

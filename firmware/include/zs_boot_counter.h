#ifndef ZS_BOOT_COUNTER_H
#define ZS_BOOT_COUNTER_H
/*
 * Monotonic boot counter in one NOR erase block (B3): `boot_id` for detection events and heartbeats
 * (event_id = boot_id << 32 | seq_no, so it must never repeat across power cycles).
 *
 * Block layout:  [0..8)  magic "ZSBOOT01"   [8..12) base LE32   [12..16) ~base LE32   [16..) bitmap
 * Every boot clears one more bit of the bitmap (NOR programs 1 -> 0 without an erase), so an increment
 * costs one byte program and the count survives power loss at any point: boot_id = base + cleared bits.
 * When the bitmap is exhausted (32640 boots for a 4 KiB block) the block is erased and rewritten with
 * base = old base + bitmap bits.  A block with no valid header (factory, erased, corrupt) starts at 0.
 */
#include "zs_nor.h"

#include <stdbool.h>
#include <stdint.h>

#define ZS_BOOT_COUNTER_HEADER_BYTES 16u

typedef struct {
  zs_nor_t *nor;
  uint32_t base_address;
  uint32_t block_bytes;
  uint32_t base;          /* header base */
  uint32_t used_bits;     /* cleared bits in the bitmap */
  bool formatted;         /* header valid */
} zs_boot_counter_t;

/* Reads the block; false only on I/O failure or bad arguments. The current count is zs_boot_counter_value(). */
bool zs_boot_counter_open(zs_boot_counter_t *c, zs_nor_t *nor, uint32_t base_address, uint32_t block_bytes);
/* boot_id after the last increment (0 before the first ever boot). */
uint32_t zs_boot_counter_value(const zs_boot_counter_t *c);
/* Records one boot; returns the new boot_id in *boot_id. Formats the block when needed. */
bool zs_boot_counter_increment(zs_boot_counter_t *c, uint32_t *boot_id);

#endif

#ifndef ZS_NOR_STORAGE_LAYOUT_H
#define ZS_NOR_STORAGE_LAYOUT_H

#include "zs_archive.h"

#include <stdbool.h>
#include <stdint.h>

typedef struct {
  uint32_t capacity_bytes;
  uint32_t erase_block_bytes;
  uint16_t outbox_slot_count;
  uint32_t outbox_base_address;
  uint32_t outbox_partition_bytes;
  zs_archive_layout_t archive;
} zs_nor_storage_layout_t;

/*
 * Reserve one complete erase block per event-outbox slot at the end of NOR.
 * The audio archive owns the aligned prefix. outbox_slot_count is deliberately
 * supplied by the target so a production retention policy is not guessed here.
 */
bool zs_nor_storage_layout_make(uint32_t capacity_bytes,
                                uint32_t erase_block_bytes,
                                uint16_t outbox_slot_count,
                                zs_nor_storage_layout_t *out);

#endif

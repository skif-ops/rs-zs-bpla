#ifndef ZS_NOR_COMMAND_JOURNAL_H
#define ZS_NOR_COMMAND_JOURNAL_H

#include "zs_command_journal.h"
#include "zs_nor.h"

#include <stdbool.h>
#include <stdint.h>

typedef struct {
  zs_nor_t *nor;
  uint32_t base_address;
  uint16_t slot_count;
} zs_nor_command_journal_adapter_t;

/*
 * Bind the command journal to a dedicated NOR partition. Every logical record
 * owns one whole erase block, so replacing an incomplete or expired record
 * cannot erase another ACCEPTED/COMPLETED record. Partition selection and
 * endurance remain target responsibilities.
 */
bool zs_nor_command_journal_io_init(
    zs_nor_command_journal_adapter_t *adapter,
    zs_nor_t *nor,
    uint32_t base_address,
    uint16_t slot_count,
    zs_command_journal_io_t *out_io);

#endif

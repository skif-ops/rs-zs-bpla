#ifndef ZS_NOR_STORAGE_LAYOUT_H
#define ZS_NOR_STORAGE_LAYOUT_H

#include "zs_archive.h"
#include "zs_nor_archive.h"
#include "zs_nor_command_journal.h"
#include "zs_nor_event_outbox.h"

#include <stdbool.h>
#include <stdint.h>

typedef struct {
  uint32_t capacity_bytes;
  uint32_t erase_block_bytes;
  uint16_t command_slot_count;
  uint16_t outbox_slot_count;
  uint32_t command_base_address;
  uint32_t command_partition_bytes;
  uint32_t outbox_base_address;
  uint32_t outbox_partition_bytes;
  zs_archive_layout_t archive;
} zs_nor_storage_layout_t;

typedef struct {
  zs_nor_storage_layout_t layout;
  zs_nor_probe_info_t nor_probe;
  zs_nor_archive_adapter_t archive_adapter;
  zs_nor_command_journal_adapter_t command_adapter;
  zs_nor_event_outbox_adapter_t outbox_adapter;
} zs_nor_storage_bindings_t;

/*
 * Reserve one erase block per command-journal and event-outbox slot at the end
 * of NOR. The audio archive owns the aligned prefix, followed by command
 * journal, then event outbox. Both slot counts are target inputs.
 */
bool zs_nor_storage_layout_make(uint32_t capacity_bytes,
                                uint32_t erase_block_bytes,
                                uint16_t command_slot_count,
                                uint16_t outbox_slot_count,
                                zs_nor_storage_layout_t *out);

/*
 * Validate exact W25Q512JV JEDEC/SFDP/QE state, then bind all three consumers
 * from one layout. Archive storage is capped at the command boundary even
 * though all adapters share the same NOR device.
 * bindings must remain at a stable address while any returned interface is
 * in use because their ctx pointers refer to its embedded adapters.
 */
bool zs_nor_storage_bind(zs_nor_storage_bindings_t *bindings,
                         zs_nor_t *nor,
                         uint16_t command_slot_count,
                         uint16_t outbox_slot_count,
                         zs_archive_storage_t *out_archive_storage,
                         zs_command_journal_io_t *out_command_io,
                         zs_event_outbox_io_t *out_outbox_io);

#endif

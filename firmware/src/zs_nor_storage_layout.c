#include "zs_nor_storage_layout.h"

#include "zs_event_outbox.h"

#include <string.h>

bool zs_nor_storage_layout_make(uint32_t capacity_bytes,
                                uint32_t erase_block_bytes,
                                uint16_t command_slot_count,
                                uint16_t outbox_slot_count,
                                zs_nor_storage_layout_t *out) {
  uint64_t command_bytes;
  uint64_t outbox_bytes;
  uint64_t reserved_bytes;
  uint32_t archive_bytes;
  uint64_t archive_end;

  if (out) memset(out, 0, sizeof(*out));
  if (!out || capacity_bytes == 0u || erase_block_bytes == 0u ||
      command_slot_count < 2u || outbox_slot_count == 0u ||
      erase_block_bytes < ZS_COMMAND_JOURNAL_SLOT_BYTES ||
      erase_block_bytes < ZS_EVENT_OUTBOX_SLOT_BYTES ||
      capacity_bytes % erase_block_bytes != 0u)
    return false;

  command_bytes =
      (uint64_t)command_slot_count * (uint64_t)erase_block_bytes;
  outbox_bytes =
      (uint64_t)outbox_slot_count * (uint64_t)erase_block_bytes;
  reserved_bytes = command_bytes + outbox_bytes;
  if (command_bytes > UINT32_MAX || outbox_bytes > UINT32_MAX ||
      reserved_bytes >= capacity_bytes || reserved_bytes > UINT32_MAX)
    return false;
  archive_bytes = capacity_bytes - (uint32_t)reserved_bytes;

  if (!zs_archive_make_default_layout(
          0u, archive_bytes, erase_block_bytes, &out->archive))
    return false;

  archive_end = (uint64_t)out->archive.base_address +
                out->archive.prehistory_ring_bytes +
                (uint64_t)out->archive.slot_bytes * out->archive.slot_count;
  if (archive_end > archive_bytes ||
      (uint64_t)archive_bytes + command_bytes + outbox_bytes !=
          capacity_bytes) {
    memset(out, 0, sizeof(*out));
    return false;
  }

  out->capacity_bytes = capacity_bytes;
  out->erase_block_bytes = erase_block_bytes;
  out->command_slot_count = command_slot_count;
  out->outbox_slot_count = outbox_slot_count;
  out->command_base_address = archive_bytes;
  out->command_partition_bytes = (uint32_t)command_bytes;
  out->outbox_base_address = archive_bytes + (uint32_t)command_bytes;
  out->outbox_partition_bytes = (uint32_t)outbox_bytes;
  return true;
}

bool zs_nor_storage_bind(zs_nor_storage_bindings_t *bindings,
                         zs_nor_t *nor,
                         uint16_t command_slot_count,
                         uint16_t outbox_slot_count,
                         zs_archive_storage_t *out_archive_storage,
                         zs_command_journal_io_t *out_command_io,
                         zs_event_outbox_io_t *out_outbox_io) {
  if (bindings) memset(bindings, 0, sizeof(*bindings));
  if (out_archive_storage)
    memset(out_archive_storage, 0, sizeof(*out_archive_storage));
  if (out_command_io) memset(out_command_io, 0, sizeof(*out_command_io));
  if (out_outbox_io) memset(out_outbox_io, 0, sizeof(*out_outbox_io));
  if (!bindings || !nor || !out_archive_storage || !out_command_io ||
      !out_outbox_io)
    return false;

  if (!zs_nor_storage_layout_make(
          nor->geometry.capacity_bytes,
          nor->geometry.erase_bytes,
          command_slot_count,
          outbox_slot_count,
          &bindings->layout) ||
      zs_nor_probe_w25q512jv(nor, &bindings->nor_probe) != ZS_NOR_PROBE_OK ||
      !zs_nor_archive_storage_init(
          &bindings->archive_adapter, nor, out_archive_storage) ||
      !zs_nor_command_journal_io_init(
          &bindings->command_adapter,
          nor,
          bindings->layout.command_base_address,
          bindings->layout.command_slot_count,
          out_command_io) ||
      !zs_nor_event_outbox_io_init(
          &bindings->outbox_adapter,
          nor,
          bindings->layout.outbox_base_address,
          bindings->layout.outbox_slot_count,
          out_outbox_io)) {
    memset(bindings, 0, sizeof(*bindings));
    memset(out_archive_storage, 0, sizeof(*out_archive_storage));
    memset(out_command_io, 0, sizeof(*out_command_io));
    memset(out_outbox_io, 0, sizeof(*out_outbox_io));
    return false;
  }

  out_archive_storage->size_bytes = bindings->layout.command_base_address;
  return true;
}

bool zs_nor_storage_layout_make_stores(uint32_t capacity_bytes,
                                       uint32_t erase_block_bytes,
                                       uint16_t command_slot_count,
                                       uint16_t outbox_slot_count,
                                       zs_nor_storage_layout_t *out) {
  const uint64_t stores = (uint64_t)ZS_NOR_STORAGE_STORE_BLOCKS * erase_block_bytes;
  if (out) memset(out, 0, sizeof(*out));
  if (!out || erase_block_bytes == 0u || erase_block_bytes < ZS_STATION_CONFIG_SLOT_BYTES ||
      erase_block_bytes < ZS_INSTALLATION_STORE_SLOT_BYTES || stores >= capacity_bytes ||
      capacity_bytes % erase_block_bytes != 0u)
    return false;
  if (!zs_nor_storage_layout_make(capacity_bytes - (uint32_t)stores, erase_block_bytes,
                                  command_slot_count, outbox_slot_count, out))
    return false;
  out->capacity_bytes = capacity_bytes;
  out->config_base_address = out->outbox_base_address + out->outbox_partition_bytes;
  out->installation_base_address = out->config_base_address + ZS_STATION_CONFIG_SLOT_COUNT * erase_block_bytes;
  out->stores_partition_bytes = (uint32_t)stores;
  return true;
}

/* zs_nor_storage_bind_stores lives in zs_nor_slot_store.c: it is the only layout entry point that
   needs the slot-store adapter, and keeping it there leaves this file free of that dependency for
   the audit builds that link the v1 layout alone. */

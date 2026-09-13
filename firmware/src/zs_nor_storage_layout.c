#include "zs_nor_storage_layout.h"

#include "zs_event_outbox.h"

#include <string.h>

bool zs_nor_storage_layout_make(uint32_t capacity_bytes,
                                uint32_t erase_block_bytes,
                                uint16_t outbox_slot_count,
                                zs_nor_storage_layout_t *out) {
  uint64_t outbox_bytes;
  uint32_t archive_bytes;
  uint64_t archive_end;

  if (out) memset(out, 0, sizeof(*out));
  if (!out || capacity_bytes == 0u || erase_block_bytes == 0u ||
      outbox_slot_count == 0u ||
      erase_block_bytes < ZS_EVENT_OUTBOX_SLOT_BYTES ||
      capacity_bytes % erase_block_bytes != 0u)
    return false;

  outbox_bytes =
      (uint64_t)outbox_slot_count * (uint64_t)erase_block_bytes;
  if (outbox_bytes >= capacity_bytes || outbox_bytes > UINT32_MAX)
    return false;
  archive_bytes = capacity_bytes - (uint32_t)outbox_bytes;

  if (!zs_archive_make_default_layout(
          0u, archive_bytes, erase_block_bytes, &out->archive))
    return false;

  archive_end = (uint64_t)out->archive.base_address +
                out->archive.prehistory_ring_bytes +
                (uint64_t)out->archive.slot_bytes * out->archive.slot_count;
  if (archive_end > archive_bytes ||
      (uint64_t)archive_bytes + outbox_bytes != capacity_bytes) {
    memset(out, 0, sizeof(*out));
    return false;
  }

  out->capacity_bytes = capacity_bytes;
  out->erase_block_bytes = erase_block_bytes;
  out->outbox_slot_count = outbox_slot_count;
  out->outbox_base_address = archive_bytes;
  out->outbox_partition_bytes = (uint32_t)outbox_bytes;
  return true;
}

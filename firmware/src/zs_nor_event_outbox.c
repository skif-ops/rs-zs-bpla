#include "zs_nor_event_outbox.h"

#include <string.h>

static bool adapter_valid(const zs_nor_event_outbox_adapter_t *adapter) {
  uint64_t partition_end;
  if (!adapter || !adapter->nor || adapter->slot_count == 0u ||
      !adapter->nor->port.command || !adapter->nor->port.millis ||
      !adapter->nor->port.delay_ms ||
      adapter->nor->geometry.erase_bytes < ZS_EVENT_OUTBOX_SLOT_BYTES ||
      adapter->base_address % adapter->nor->geometry.erase_bytes != 0u)
    return false;
  partition_end = (uint64_t)adapter->base_address +
                  (uint64_t)adapter->slot_count *
                      adapter->nor->geometry.erase_bytes;
  return partition_end <= adapter->nor->geometry.capacity_bytes;
}

static bool slot_range(
    const zs_nor_event_outbox_adapter_t *adapter,
    uint16_t slot,
    uint32_t offset,
    size_t size,
    uint32_t *address) {
  uint64_t absolute;
  if (!adapter_valid(adapter) || slot >= adapter->slot_count || !address ||
      (uint64_t)offset + (uint64_t)size > ZS_EVENT_OUTBOX_SLOT_BYTES)
    return false;
  absolute = (uint64_t)adapter->base_address +
             (uint64_t)slot * adapter->nor->geometry.erase_bytes + offset;
  if (absolute > UINT32_MAX ||
      absolute + size > adapter->nor->geometry.capacity_bytes)
    return false;
  *address = (uint32_t)absolute;
  return true;
}

static bool outbox_read(void *ctx, uint16_t slot, uint32_t offset,
                        uint8_t *data, size_t size) {
  zs_nor_event_outbox_adapter_t *adapter = ctx;
  uint32_t address;
  return data && slot_range(adapter, slot, offset, size, &address) &&
         zs_nor_read(adapter->nor, address, data, size);
}

static bool outbox_erase(void *ctx, uint16_t slot) {
  zs_nor_event_outbox_adapter_t *adapter = ctx;
  uint32_t address;
  return slot_range(adapter, slot, 0u, ZS_EVENT_OUTBOX_SLOT_BYTES,
                    &address) &&
         zs_nor_erase(adapter->nor, address,
                      adapter->nor->geometry.erase_bytes);
}

static bool outbox_write(void *ctx, uint16_t slot, uint32_t offset,
                         const uint8_t *data, size_t size) {
  zs_nor_event_outbox_adapter_t *adapter = ctx;
  uint32_t address;
  return data && slot_range(adapter, slot, offset, size, &address) &&
         zs_nor_program(adapter->nor, address, data, size);
}

bool zs_nor_event_outbox_io_init(
    zs_nor_event_outbox_adapter_t *adapter,
    zs_nor_t *nor,
    uint32_t base_address,
    uint16_t slot_count,
    zs_event_outbox_io_t *out_io) {
  uint64_t partition_end;
  if (adapter) memset(adapter, 0, sizeof(*adapter));
  if (out_io) memset(out_io, 0, sizeof(*out_io));
  if (!adapter || !nor || !out_io || !nor->port.command ||
      !nor->port.millis || !nor->port.delay_ms ||
      nor->geometry.capacity_bytes == 0u || nor->geometry.erase_bytes == 0u ||
      nor->geometry.page_bytes == 0u || slot_count == 0u ||
      nor->geometry.erase_bytes < ZS_EVENT_OUTBOX_SLOT_BYTES ||
      base_address % nor->geometry.erase_bytes != 0u)
    return false;
  partition_end = (uint64_t)base_address +
                  (uint64_t)slot_count * nor->geometry.erase_bytes;
  if (partition_end > nor->geometry.capacity_bytes) return false;
  adapter->nor = nor;
  adapter->base_address = base_address;
  adapter->slot_count = slot_count;
  *out_io = (zs_event_outbox_io_t){
      adapter, slot_count, outbox_read, outbox_erase, outbox_write};
  return true;
}

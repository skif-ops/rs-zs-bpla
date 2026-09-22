#include "zs_nor_slot_store.h"
#include "zs_nor_storage_layout.h"

#include <string.h>

static bool store_valid(const zs_nor_slot_store_t *s) {
  uint64_t end;
  if (!s || !s->nor || s->slot_count < 2u || s->record_bytes == 0u || !s->nor->port.command ||
      s->nor->geometry.erase_bytes == 0u || s->record_bytes > s->nor->geometry.erase_bytes ||
      s->base_address % s->nor->geometry.erase_bytes != 0u)
    return false;
  end = (uint64_t)s->base_address + (uint64_t)s->slot_count * s->nor->geometry.erase_bytes;
  return end <= s->nor->geometry.capacity_bytes;
}

static bool slot_address(const zs_nor_slot_store_t *s, uint8_t slot, uint32_t offset, size_t size, uint32_t *address) {
  uint64_t absolute;
  if (!store_valid(s) || slot >= s->slot_count || (uint64_t)offset + size > s->record_bytes) return false;
  absolute = (uint64_t)s->base_address + (uint64_t)slot * s->nor->geometry.erase_bytes + offset;
  if (absolute + size > UINT32_MAX) return false;
  *address = (uint32_t)absolute;
  return true;
}

static bool slot_read(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size) {
  uint32_t address;
  zs_nor_slot_store_t *s = ctx;
  return data && slot_address(s, slot, offset, size, &address) && zs_nor_read(s->nor, address, data, size);
}

static bool slot_erase(void *ctx, uint8_t slot) {
  uint32_t address;
  zs_nor_slot_store_t *s = ctx;
  return slot_address(s, slot, 0u, 0u, &address) && zs_nor_erase(s->nor, address, s->nor->geometry.erase_bytes);
}

static bool slot_write(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size) {
  uint32_t address;
  zs_nor_slot_store_t *s = ctx;
  return data && slot_address(s, slot, offset, size, &address) && zs_nor_program(s->nor, address, data, size);
}

bool zs_nor_slot_store_init(zs_nor_slot_store_t *store, zs_nor_t *nor, uint32_t base_address, uint8_t slot_count, uint32_t record_bytes) {
  if (!store) return false;
  memset(store, 0, sizeof(*store));
  store->nor = nor; store->base_address = base_address; store->slot_count = slot_count; store->record_bytes = record_bytes;
  if (!store_valid(store)) { memset(store, 0, sizeof(*store)); return false; }
  return true;
}

bool zs_nor_slot_store_config_io(zs_nor_slot_store_t *store, zs_station_config_io_t *out_io) {
  if (!out_io) return false;
  memset(out_io, 0, sizeof(*out_io));
  if (!store_valid(store) || store->slot_count != ZS_STATION_CONFIG_SLOT_COUNT || store->record_bytes < ZS_STATION_CONFIG_SLOT_BYTES) return false;
  out_io->ctx = store; out_io->read = slot_read; out_io->erase = slot_erase; out_io->write = slot_write;
  return true;
}

bool zs_nor_slot_store_installation_io(zs_nor_slot_store_t *store, zs_installation_store_io_t *out_io) {
  if (!out_io) return false;
  memset(out_io, 0, sizeof(*out_io));
  if (!store_valid(store) || store->slot_count != ZS_INSTALLATION_STORE_SLOT_COUNT || store->record_bytes < ZS_INSTALLATION_STORE_SLOT_BYTES) return false;
  out_io->ctx = store; out_io->read = slot_read; out_io->erase = slot_erase; out_io->write = slot_write;
  return true;
}

/* ---- B3 layout binding (declared in zs_nor_storage_layout.h) ----------------------------- */

bool zs_nor_storage_bind_stores(zs_nor_storage_bindings_t *bindings,
                                zs_nor_t *nor,
                                uint16_t command_slot_count,
                                uint16_t outbox_slot_count,
                                zs_archive_storage_t *out_archive_storage,
                                zs_command_journal_io_t *out_command_io,
                                zs_event_outbox_io_t *out_outbox_io,
                                zs_station_config_io_t *out_config_io,
                                zs_installation_store_io_t *out_installation_io) {
  if (bindings) memset(bindings, 0, sizeof(*bindings));
  if (out_archive_storage) memset(out_archive_storage, 0, sizeof(*out_archive_storage));
  if (out_command_io) memset(out_command_io, 0, sizeof(*out_command_io));
  if (out_outbox_io) memset(out_outbox_io, 0, sizeof(*out_outbox_io));
  if (out_config_io) memset(out_config_io, 0, sizeof(*out_config_io));
  if (out_installation_io) memset(out_installation_io, 0, sizeof(*out_installation_io));
  if (!bindings || !nor || !out_archive_storage || !out_command_io || !out_outbox_io ||
      !out_config_io || !out_installation_io)
    return false;

  if (!zs_nor_storage_layout_make_stores(nor->geometry.capacity_bytes, nor->geometry.erase_bytes,
                                         command_slot_count, outbox_slot_count, &bindings->layout) ||
      zs_nor_probe_w25q512jv(nor, &bindings->nor_probe) != ZS_NOR_PROBE_OK ||
      !zs_nor_archive_storage_init(&bindings->archive_adapter, nor, out_archive_storage) ||
      !zs_nor_command_journal_io_init(&bindings->command_adapter, nor,
                                      bindings->layout.command_base_address,
                                      bindings->layout.command_slot_count, out_command_io) ||
      !zs_nor_event_outbox_io_init(&bindings->outbox_adapter, nor,
                                   bindings->layout.outbox_base_address,
                                   bindings->layout.outbox_slot_count, out_outbox_io) ||
      !zs_nor_slot_store_init(&bindings->config_store, nor, bindings->layout.config_base_address,
                              ZS_STATION_CONFIG_SLOT_COUNT, ZS_STATION_CONFIG_SLOT_BYTES) ||
      !zs_nor_slot_store_config_io(&bindings->config_store, out_config_io) ||
      !zs_nor_slot_store_init(&bindings->installation_store, nor, bindings->layout.installation_base_address,
                              ZS_INSTALLATION_STORE_SLOT_COUNT, ZS_INSTALLATION_STORE_SLOT_BYTES) ||
      !zs_nor_slot_store_installation_io(&bindings->installation_store, out_installation_io)) {
    memset(bindings, 0, sizeof(*bindings));
    memset(out_archive_storage, 0, sizeof(*out_archive_storage));
    memset(out_command_io, 0, sizeof(*out_command_io));
    memset(out_outbox_io, 0, sizeof(*out_outbox_io));
    memset(out_config_io, 0, sizeof(*out_config_io));
    memset(out_installation_io, 0, sizeof(*out_installation_io));
    return false;
  }

  out_archive_storage->size_bytes = bindings->layout.command_base_address;
  return true;
}

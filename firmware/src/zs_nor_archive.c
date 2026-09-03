#include "zs_nor_archive.h"

#include <string.h>

static int archive_read(void *ctx, uint32_t address, uint8_t *data, size_t len) {
  zs_nor_archive_adapter_t *adapter = (zs_nor_archive_adapter_t *)ctx;
  return adapter && adapter->nor && zs_nor_read(adapter->nor, address, data, len) ? 0 : -1;
}

static int archive_write(void *ctx, uint32_t address, const uint8_t *data, size_t len) {
  zs_nor_archive_adapter_t *adapter = (zs_nor_archive_adapter_t *)ctx;
  return adapter && adapter->nor && zs_nor_program(adapter->nor, address, data, len) ? 0 : -1;
}

static int archive_erase(void *ctx, uint32_t address, size_t len) {
  zs_nor_archive_adapter_t *adapter = (zs_nor_archive_adapter_t *)ctx;
  return adapter && adapter->nor && zs_nor_erase(adapter->nor, address, len) ? 0 : -1;
}

bool zs_nor_archive_storage_init(zs_nor_archive_adapter_t *adapter,
                                 zs_nor_t *nor,
                                 zs_archive_storage_t *out_storage) {
  if (!adapter || !nor || !out_storage) return false;
  memset(adapter, 0, sizeof(*adapter));
  adapter->nor = nor;
  *out_storage = (zs_archive_storage_t){
      .ctx = adapter,
      .size_bytes = nor->geometry.capacity_bytes,
      .erase_block_bytes = nor->geometry.erase_bytes,
      .read = archive_read,
      .write = archive_write,
      .erase = archive_erase,
  };
  return true;
}

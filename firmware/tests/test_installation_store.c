#include "zs_installation_store.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  uint8_t slots[ZS_INSTALLATION_STORE_SLOT_COUNT][ZS_INSTALLATION_STORE_SLOT_BYTES];
  unsigned write_calls;
  unsigned fail_write_call;
} memory_store_t;

static bool memory_read(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size) {
  memory_store_t *store = ctx;
  if (slot >= ZS_INSTALLATION_STORE_SLOT_COUNT || offset + size > ZS_INSTALLATION_STORE_SLOT_BYTES) return false;
  memcpy(data, &store->slots[slot][offset], size);
  return true;
}

static bool memory_erase(void *ctx, uint8_t slot) {
  memory_store_t *store = ctx;
  if (slot >= ZS_INSTALLATION_STORE_SLOT_COUNT) return false;
  memset(store->slots[slot], 0xff, ZS_INSTALLATION_STORE_SLOT_BYTES);
  return true;
}

static bool memory_write(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size) {
  memory_store_t *store = ctx;
  if (slot >= ZS_INSTALLATION_STORE_SLOT_COUNT || offset + size > ZS_INSTALLATION_STORE_SLOT_BYTES) return false;
  store->write_calls++;
  if (store->fail_write_call != 0u && store->write_calls == store->fail_write_call) return false;
  for (size_t i = 0u; i < size; i++) {
    if ((store->slots[slot][offset + i] & data[i]) != data[i]) return false;
    store->slots[slot][offset + i] = data[i];
  }
  return true;
}

static zs_installation_store_io_t memory_io(memory_store_t *store) {
  zs_installation_store_io_t io = {store, memory_read, memory_erase, memory_write};
  return io;
}

static zs_installation_record_t valid_record(uint32_t version) {
  zs_installation_record_t record;
  memset(&record, 0, sizeof(record));
  record.trust.configured = true;
  record.trust.locked = true;
  record.trust.installation.lat_e7 = 557550000;
  record.trust.installation.lon_e7 = 376150000;
  record.trust.installation.alt_dm = 1800;
  record.trust.installation.pos_accuracy_m = 5u;
  record.trust.installation.altitude_source = 1u;
  record.trust.installation.position_source = ZS_POSITION_SOURCE_CONFIGURED_INSTALL;
  record.trust.warning_distance_m = 25u;
  record.trust.suspect_distance_m = 75u;
  record.trust.gross_jump_distance_m = 250u;
  record.trust.warning_consecutive_fixes = 3u;
  record.trust.suspect_consecutive_fixes = 10u;
  record.version = version;
  record.commissioned_time_us = UINT64_C(2000000000000000) + version;
  record.source = 0u;
  for (size_t i = 0u; i < ZS_INSTALLATION_HASH_BYTES; i++) {
    record.commissioning_hash[i] = (uint8_t)(i + version);
  }
  return record;
}

int main(void) {
  memory_store_t store;
  memset(&store, 0xff, sizeof(store));
  store.write_calls = 0u;
  store.fail_write_call = 0u;
  zs_installation_store_io_t io = memory_io(&store);
  zs_installation_record_t first = valid_record(1u);
  zs_installation_record_t loaded;
  uint8_t slot = 0xffu;

  assert(zs_installation_store_load(&io, &loaded, &slot) == ZS_INSTALLATION_STORE_NOT_FOUND);
  assert(zs_installation_store_commit(&io, &first, false, true, false) == ZS_INSTALLATION_STORE_AUTH_REQUIRED);
  assert(zs_installation_store_commit(&io, &first, true, false, false) == ZS_INSTALLATION_STORE_AUTH_REQUIRED);
  assert(zs_installation_store_commit(&io, &first, true, true, false) == ZS_INSTALLATION_STORE_OK);
  assert(zs_installation_store_load(&io, &loaded, &slot) == ZS_INSTALLATION_STORE_OK);
  assert(slot == 0u && loaded.version == 1u && loaded.storage_generation == 1u);
  assert(loaded.trust.installation.lat_e7 == first.trust.installation.lat_e7);
  assert(memcmp(loaded.commissioning_hash, first.commissioning_hash, ZS_INSTALLATION_HASH_BYTES) == 0);

  assert(zs_installation_store_commit(&io, &first, true, true, false) == ZS_INSTALLATION_STORE_LOCKED);
  assert(zs_installation_store_commit(&io, &first, true, true, true) == ZS_INSTALLATION_STORE_VERSION_REJECTED);

  zs_installation_record_t second = valid_record(2u);
  store.write_calls = 0u;
  store.fail_write_call = 2u; /* Body written, atomic commit marker missing. */
  assert(zs_installation_store_commit(&io, &second, true, true, true) == ZS_INSTALLATION_STORE_IO_ERROR);
  assert(zs_installation_store_load(&io, &loaded, &slot) == ZS_INSTALLATION_STORE_OK);
  assert(slot == 0u && loaded.version == 1u);

  store.write_calls = 0u;
  store.fail_write_call = 0u;
  assert(zs_installation_store_commit(&io, &second, true, true, true) == ZS_INSTALLATION_STORE_OK);
  assert(zs_installation_store_load(&io, &loaded, &slot) == ZS_INSTALLATION_STORE_OK);
  assert(slot == 1u && loaded.version == 2u && loaded.storage_generation == 2u);

  store.slots[1][50] ^= 0x01u; /* Corrupt hash payload without updating CRC. */
  assert(zs_installation_store_load(&io, &loaded, &slot) == ZS_INSTALLATION_STORE_OK);
  assert(slot == 0u && loaded.version == 1u);

  zs_installation_record_t invalid = valid_record(3u);
  invalid.trust.installation.lat_e7 = 900000001;
  assert(zs_installation_store_commit(&io, &invalid, true, true, true) == ZS_INSTALLATION_STORE_INVALID_RECORD);
  invalid = valid_record(3u);
  memset(invalid.commissioning_hash, 0, sizeof(invalid.commissioning_hash));
  assert(zs_installation_store_commit(&io, &invalid, true, true, true) == ZS_INSTALLATION_STORE_INVALID_RECORD);
  invalid = valid_record(3u);
  invalid.source = 4u;
  assert(zs_installation_store_commit(&io, &invalid, true, true, true) == ZS_INSTALLATION_STORE_INVALID_RECORD);

  puts("zs_installation_store_tests: OK");
  return 0;
}

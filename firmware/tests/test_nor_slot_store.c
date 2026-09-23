/* B3: station configuration and installation record on NOR (simulated W25Q-like flash, 4 KiB blocks). */
#include "zs_nor_slot_store.h"
#include "zs_nor_storage_layout.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define MOCK_ERASE_BYTES 4096u
#define MOCK_BYTES (8u * MOCK_ERASE_BYTES)

typedef struct {
  uint8_t memory[MOCK_BYTES];
  uint8_t status;
  uint32_t millis;
  uint32_t erase_commands, program_commands, program_attempts, fail_program_call;
} mock_nor_t;

static uint32_t mock_millis(void *ctx) { return ((mock_nor_t *)ctx)->millis; }
static void mock_delay(void *ctx, uint32_t millis) { ((mock_nor_t *)ctx)->millis += millis; }

static int mock_command(void *ctx, uint8_t opcode, uint32_t address, uint8_t address_bytes,
                        const uint8_t *tx, size_t tx_size, uint8_t *rx, size_t rx_size) {
  mock_nor_t *mock = ctx;
  if (opcode == 0x05u) { if (!rx || rx_size != 1u) return -1; rx[0] = mock->status; return 0; }
  if (opcode == 0x06u) { mock->status |= 0x02u; return 0; }
  if (opcode == 0x13u) {
    if (address_bytes != 4u || !rx || tx || tx_size != 0u || (uint64_t)address + rx_size > MOCK_BYTES) return -1;
    memcpy(rx, &mock->memory[address], rx_size);
    return 0;
  }
  if (opcode == 0x12u) {
    if (address_bytes != 4u || !tx || rx || rx_size != 0u || tx_size == 0u || tx_size > 256u ||
        (mock->status & 0x02u) == 0u || address / 256u != (address + (uint32_t)tx_size - 1u) / 256u ||
        (uint64_t)address + tx_size > MOCK_BYTES)
      return -1;
    ++mock->program_attempts;
    if (mock->program_attempts == mock->fail_program_call) { /* power loss mid-program: half the bytes land */
      for (size_t i = 0u; i < tx_size / 2u; ++i) mock->memory[address + i] &= tx[i];
      mock->status &= (uint8_t)~0x02u;
      return -1;
    }
    for (size_t i = 0u; i < tx_size; ++i) {
      if ((mock->memory[address + i] & tx[i]) != tx[i]) return -1;
      mock->memory[address + i] = tx[i];
    }
    mock->status &= (uint8_t)~0x02u;
    ++mock->program_commands;
    return 0;
  }
  if (opcode == 0x21u) {
    if (address_bytes != 4u || tx || tx_size != 0u || rx || rx_size != 0u || (mock->status & 0x02u) == 0u ||
        address % MOCK_ERASE_BYTES != 0u || (uint64_t)address + MOCK_ERASE_BYTES > MOCK_BYTES)
      return -1;
    memset(&mock->memory[address], 0xff, MOCK_ERASE_BYTES);
    mock->status &= (uint8_t)~0x02u;
    ++mock->erase_commands;
    return 0;
  }
  return -1;
}

static zs_nor_t make_nor(mock_nor_t *mock) {
  const zs_nor_port_t port = {mock, mock_command, mock_millis, mock_delay};
  zs_nor_geometry_t geometry = zs_nor_geometry_64m_4byte();
  zs_nor_t nor;
  geometry.capacity_bytes = MOCK_BYTES;
  assert(zs_nor_init(&nor, &port, &geometry));
  return nor;
}

static zs_station_config_t sample_config(uint32_t version) {
  zs_station_config_t c;
  zs_station_config_defaults(&c, 12u, ZS_STATION_CONFIG_REGION_RU868);
  c.version = version;
  strcpy(c.server_host, "muhoed.example.ru");
  c.mqtt_port = 8883u;
  strcpy(c.ca_reference, "dioneya-root");
  strcpy(c.tenant, "pilot1");
  strcpy(c.topic_prefix, "zs/v1");
  assert(zs_station_config_validate(&c) == 0u && zs_station_config_compute_hash(&c, c.config_hash));
  return c;
}

static zs_installation_record_t sample_record(uint32_t version, int32_t lat) {
  zs_installation_record_t r;
  memset(&r, 0, sizeof(r));
  r.trust.configured = true;
  r.trust.locked = true;
  r.trust.installation.lat_e7 = lat;
  r.trust.installation.lon_e7 = 376173000;
  r.trust.installation.alt_dm = 1564;
  r.trust.installation.pos_accuracy_m = 4u;
  r.trust.installation.altitude_source = 1u;
  r.trust.installation.position_source = 1u;
  r.trust.warning_distance_m = 25u; r.trust.suspect_distance_m = 75u; r.trust.gross_jump_distance_m = 250u;
  r.trust.warning_consecutive_fixes = 3u; r.trust.suspect_consecutive_fixes = 10u;
  r.version = version;
  r.source = 3u;
  r.commissioned_time_us = UINT64_C(1800000000000000);
  assert(zs_installation_record_compute_hash(&r, r.commissioning_hash));
  return r;
}

static void test_adapter_bounds(void) {
  static mock_nor_t mock;
  zs_nor_t nor;
  zs_nor_slot_store_t store;
  zs_station_config_io_t cfg_io;
  zs_installation_store_io_t pos_io;
  uint8_t buf[8];
  memset(&mock, 0, sizeof(mock)); memset(mock.memory, 0xff, sizeof(mock.memory));
  nor = make_nor(&mock);
  assert(!zs_nor_slot_store_init(&store, &nor, 100u, 2u, 320u));                 /* unaligned base */
  assert(!zs_nor_slot_store_init(&store, &nor, 0u, 1u, 320u));                   /* single slot */
  assert(!zs_nor_slot_store_init(&store, &nor, 7u * MOCK_ERASE_BYTES, 2u, 320u)); /* past the end */
  assert(!zs_nor_slot_store_init(&store, &nor, 0u, 2u, MOCK_ERASE_BYTES + 1u));  /* record larger than a block */
  assert(zs_nor_slot_store_init(&store, &nor, 4u * MOCK_ERASE_BYTES, 2u, ZS_STATION_CONFIG_SLOT_BYTES));
  assert(zs_nor_slot_store_config_io(&store, &cfg_io));
  assert(zs_nor_slot_store_installation_io(&store, &pos_io));                    /* 320 B slots also hold the 96 B record */
  {
    zs_nor_slot_store_t small;
    assert(zs_nor_slot_store_init(&small, &nor, 0u, 2u, 64u));
    assert(!zs_nor_slot_store_config_io(&small, &cfg_io) && !zs_nor_slot_store_installation_io(&small, &pos_io)); /* record does not fit */
    assert(zs_nor_slot_store_init(&small, &nor, 0u, 3u, ZS_STATION_CONFIG_SLOT_BYTES));
    assert(!zs_nor_slot_store_config_io(&small, &cfg_io));                       /* the stores are strictly double-slot */
    assert(zs_nor_slot_store_config_io(&store, &cfg_io));
  }
  assert(!cfg_io.read(cfg_io.ctx, 2u, 0u, buf, 1u));                             /* slot out of range */
  assert(!cfg_io.read(cfg_io.ctx, 0u, ZS_STATION_CONFIG_SLOT_BYTES - 4u, buf, 8u)); /* crosses the record end */
  assert(cfg_io.read(cfg_io.ctx, 1u, 0u, buf, 8u) && buf[0] == 0xffu);
  assert(cfg_io.write(cfg_io.ctx, 1u, 0u, (const uint8_t *)"\x12\x34", 2u));
  assert(mock.memory[5u * MOCK_ERASE_BYTES] == 0x12u && mock.memory[5u * MOCK_ERASE_BYTES + 1u] == 0x34u);
  assert(cfg_io.erase(cfg_io.ctx, 1u) && mock.memory[5u * MOCK_ERASE_BYTES] == 0xffu && mock.erase_commands == 1u);
  printf("slot store bounds ok\n");
}

static void test_stores_on_nor(void) {
  static mock_nor_t mock;
  zs_nor_t nor;
  zs_nor_slot_store_t cfg_store, pos_store;
  zs_station_config_io_t cfg_io;
  zs_installation_store_io_t pos_io;
  zs_station_config_t cfg, loaded;
  zs_installation_record_t rec, back;
  uint8_t slot;
  memset(&mock, 0, sizeof(mock)); memset(mock.memory, 0xff, sizeof(mock.memory));
  nor = make_nor(&mock);
  assert(zs_nor_slot_store_init(&cfg_store, &nor, 4u * MOCK_ERASE_BYTES, ZS_STATION_CONFIG_SLOT_COUNT, ZS_STATION_CONFIG_SLOT_BYTES));
  assert(zs_nor_slot_store_init(&pos_store, &nor, 6u * MOCK_ERASE_BYTES, ZS_INSTALLATION_STORE_SLOT_COUNT, ZS_INSTALLATION_STORE_SLOT_BYTES));
  assert(zs_nor_slot_store_config_io(&cfg_store, &cfg_io) && zs_nor_slot_store_installation_io(&pos_store, &pos_io));

  /* empty flash: nothing stored */
  assert(zs_station_config_store_load(&cfg_io, &loaded, &slot) != ZS_STATION_CONFIG_OK);
  assert(zs_installation_store_load(&pos_io, &back, &slot) == ZS_INSTALLATION_STORE_NOT_FOUND);

  /* v1 config, then v2 lands in the other slot; the blocks are independent */
  cfg = sample_config(1u);
  assert(zs_station_config_store_commit(&cfg_io, &cfg, true, true) == ZS_STATION_CONFIG_OK);
  assert(zs_station_config_store_load(&cfg_io, &loaded, &slot) == ZS_STATION_CONFIG_OK && loaded.version == 1u);
  assert(zs_station_config_hash_valid(&loaded) && strcmp(loaded.server_host, "muhoed.example.ru") == 0);
  const uint8_t first_slot = slot;
  cfg = sample_config(2u); cfg.mqtt_port = 8884u; assert(zs_station_config_compute_hash(&cfg, cfg.config_hash));
  assert(zs_station_config_store_commit(&cfg_io, &cfg, true, true) == ZS_STATION_CONFIG_OK);
  assert(zs_station_config_store_load(&cfg_io, &loaded, &slot) == ZS_STATION_CONFIG_OK && loaded.version == 2u && loaded.mqtt_port == 8884u && slot != first_slot);
  cfg = sample_config(2u);
  assert(zs_station_config_store_commit(&cfg_io, &cfg, true, true) == ZS_STATION_CONFIG_VERSION_REJECTED);
  assert(zs_station_config_store_commit(&cfg_io, &cfg, false, true) != ZS_STATION_CONFIG_OK);

  /* power loss while programming v3: the active v2 record survives, v3 is not visible */
  cfg = sample_config(3u);
  mock.fail_program_call = mock.program_attempts + 2u;
  assert(zs_station_config_store_commit(&cfg_io, &cfg, true, true) != ZS_STATION_CONFIG_OK);
  mock.fail_program_call = 0u;
  assert(zs_station_config_store_load(&cfg_io, &loaded, &slot) == ZS_STATION_CONFIG_OK && loaded.version == 2u);
  assert(zs_station_config_store_commit(&cfg_io, &cfg, true, true) == ZS_STATION_CONFIG_OK);      /* retry after the interruption */
  assert(zs_station_config_store_load(&cfg_io, &loaded, &slot) == ZS_STATION_CONFIG_OK && loaded.version == 3u);

  /* installation record: initial commit, lock, recommission; blocks stay within their partition */
  rec = sample_record(1u, 557558000);
  assert(zs_installation_store_commit(&pos_io, &rec, true, true, false) == ZS_INSTALLATION_STORE_OK);
  assert(zs_installation_store_load(&pos_io, &back, &slot) == ZS_INSTALLATION_STORE_OK && back.version == 1u && zs_installation_record_hash_valid(&back));
  rec = sample_record(2u, 557558100);
  assert(zs_installation_store_commit(&pos_io, &rec, true, true, false) == ZS_INSTALLATION_STORE_LOCKED);
  assert(zs_installation_store_commit(&pos_io, &rec, true, true, true) == ZS_INSTALLATION_STORE_OK);
  assert(zs_installation_store_load(&pos_io, &back, &slot) == ZS_INSTALLATION_STORE_OK && back.version == 2u && back.trust.installation.lat_e7 == 557558100);
  for (uint32_t a = 0u; a < 4u * MOCK_ERASE_BYTES; a++) assert(mock.memory[a] == 0xffu);   /* nothing below the config partition */
  printf("stores on nor ok (erase %u program %u)\n", mock.erase_commands, mock.program_commands);
}

static void test_layout_with_stores(void) {
  zs_nor_storage_layout_t v1, v2;
  const uint32_t cap = 64u * 1024u * 1024u, blk = 4096u;
  assert(zs_nor_storage_layout_make(cap, blk, 16u, 256u, &v1));
  assert(zs_nor_storage_layout_make_stores(cap, blk, 16u, 256u, &v2));
  const uint32_t stores = (2u + 2u + ZS_NOR_STORAGE_NRF_IMAGE_BLOCKS) * blk;
  assert(v2.capacity_bytes == cap && v2.stores_partition_bytes == stores);
  assert(v2.outbox_base_address + v2.outbox_partition_bytes == v2.nrf_image_base_address);
  assert(v2.nrf_image_partition_bytes == ZS_NOR_STORAGE_NRF_IMAGE_BLOCKS * blk && v2.nrf_image_partition_bytes >= 472u * 1024u + blk);
  assert(v2.nrf_image_base_address + v2.nrf_image_partition_bytes == v2.config_base_address);
  assert(v2.config_base_address + 2u * blk == v2.installation_base_address);
  assert(v2.installation_base_address + 2u * blk == cap);
  assert(v2.nrf_image_base_address == v1.outbox_base_address + v1.outbox_partition_bytes - stores);
  assert(v2.command_base_address == v1.command_base_address - stores);   /* everything below moves down by the stores */
  assert(v2.archive.base_address == 0u && v2.archive.total_bytes == v2.command_base_address);
  assert(v1.config_base_address == 0u && v1.stores_partition_bytes == 0u); /* v1 map untouched */
  assert(v2.nrf_image_base_address == 0x03f7c000u && v2.config_base_address == 0x03ffc000u && v2.installation_base_address == 0x03ffe000u); /* W25Q512JV map, B3 + C.6 */
  printf("layout with stores ok (nrf image @0x%08x config @0x%08x installation @0x%08x)\n", v2.nrf_image_base_address, v2.config_base_address, v2.installation_base_address);
  assert(!zs_nor_storage_layout_make_stores(stores + blk, blk, 2u, 1u, &v2));  /* no room left for the archive */
}

int main(void) {
  test_adapter_bounds();
  test_stores_on_nor();
  test_layout_with_stores();
  printf("nor slot store tests passed\n");
  return 0;
}

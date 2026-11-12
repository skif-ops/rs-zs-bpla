#include "zs_lora_rf_profile.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t slot[2][128]; bool fail_write; } ram_t;
static bool r_read(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size) {
  ram_t *ram = ctx;
  if (slot > 1u || offset + size > sizeof(ram->slot[slot])) return false;
  memcpy(data, &ram->slot[slot][offset], size); return true;
}
static bool r_erase(void *ctx, uint8_t slot) {
  ram_t *ram = ctx; if (slot > 1u) return false; memset(ram->slot[slot], 0xff, sizeof(ram->slot[slot])); return true;
}
static bool r_write(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size) {
  ram_t *ram = ctx; if (slot > 1u || offset + size > sizeof(ram->slot[slot]) || ram->fail_write) return false;
  memcpy(&ram->slot[slot][offset], data, size); return true;
}
static bool verify(void *ctx, const uint8_t *message, size_t size, const uint8_t signature[64]) {
  (void)ctx;
  return size == 46u && memcmp(message, "DIO-LORA-RF-V1", 14u) == 0 && signature[0] == 0xa5u;
}
static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { for (unsigned i = 0u; i < 4u; i++) p[i] = (uint8_t)(v >> (8u * i)); }
static void make_record(uint8_t record[96], uint32_t version) {
  memset(record, 0, 96u);
  put32(&record[0], UINT32_C(0x46524c44)); record[4] = 1u; record[5] = 2u; record[6] = 1u; record[7] = 9u;
  put16(&record[8], 1u); record[10] = 14u; put32(&record[12], version); put32(&record[16], 868900000u);
  put32(&record[20], 125000u); put32(&record[24], 10000u); put32(&record[28], 2026111201u); record[32] = 0xa5u;
}
int main(void) {
  ram_t ram; uint8_t record[96]; zs_lora_rf_profile_t profile, loaded;
  zs_lora_rf_profile_io_t io = {&ram, r_read, r_erase, r_write};
  memset(&ram, 0xff, sizeof(ram)); ram.fail_write = false; make_record(record, 1u);
  assert(zs_lora_rf_profile_decode(record, 2026111201u, verify, NULL, &profile) == ZS_LORA_RF_PROFILE_OK);
  assert(profile.frequency_hz == 868900000u && profile.tx_dbm == 14 && profile.version == 1u);
  assert(zs_lora_rf_profile_load(&io, 2026111201u, verify, NULL, &loaded) == ZS_LORA_RF_PROFILE_NOT_FOUND);
  assert(zs_lora_rf_profile_commit(&io, record, 2026111201u, verify, NULL, &profile) == ZS_LORA_RF_PROFILE_OK);
  assert(zs_lora_rf_profile_load(&io, 2026111201u, verify, NULL, &loaded) == ZS_LORA_RF_PROFILE_OK && loaded.version == 1u);
  assert(zs_lora_rf_profile_commit(&io, record, 2026111201u, verify, NULL, &profile) == ZS_LORA_RF_PROFILE_ROLLBACK);
  make_record(record, 2u); record[16] = 0u;
  assert(zs_lora_rf_profile_decode(record, 2026111201u, verify, NULL, &profile) == ZS_LORA_RF_PROFILE_INVALID);
  make_record(record, 2u); record[32] = 0u;
  assert(zs_lora_rf_profile_decode(record, 2026111201u, verify, NULL, &profile) == ZS_LORA_RF_PROFILE_INVALID);
  make_record(record, 2u); ram.fail_write = true;
  assert(zs_lora_rf_profile_commit(&io, record, 2026111201u, verify, NULL, &profile) == ZS_LORA_RF_PROFILE_IO_ERROR);
  assert(zs_lora_rf_profile_load(&io, 2026111201u, verify, NULL, &loaded) == ZS_LORA_RF_PROFILE_OK && loaded.version == 1u);
  puts("lora rf profile tests passed");
  return 0;
}

/* Station secrets record on a RAM two-slot store and on the simulated NOR through zs_nor_slot_store. */
#include "zs_station_secrets.h"
#include "zs_nor_slot_store.h"
#include "zs_nor_storage_layout.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  uint8_t slots[ZS_STATION_SECRETS_SLOT_COUNT][ZS_STATION_SECRETS_SLOT_BYTES];
  unsigned writes, fail_write, erases;
} ram_t;

static bool r_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { ram_t *m = c; if (s >= 2u || o + n > ZS_STATION_SECRETS_SLOT_BYTES) return false; memcpy(d, &m->slots[s][o], n); return true; }
static bool r_erase(void *c, uint8_t s) { ram_t *m = c; if (s >= 2u) return false; memset(m->slots[s], 0xff, ZS_STATION_SECRETS_SLOT_BYTES); m->erases++; return true; }
static bool r_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) {
  ram_t *m = c;
  if (s >= 2u || o + n > ZS_STATION_SECRETS_SLOT_BYTES) return false;
  if (++m->writes == m->fail_write) return false;                       /* power loss before this write lands */
  for (size_t i = 0u; i < n; i++) { if ((m->slots[s][o + i] & d[i]) != d[i]) return false; m->slots[s][o + i] = d[i]; }
  return true;
}

#define KEY1 "a0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebf"
#define ICCID1 "89701012345678901234"
#define ICCID2 "89702012345678901234"

static void test_ram(void) {
  static ram_t m;
  const zs_station_secrets_io_t io = {&m, r_read, r_erase, r_write};
  zs_station_secrets_t s, back;
  uint8_t slot = 9u;
  memset(&m, 0xff, sizeof(m)); m.writes = 0u; m.fail_write = 0u; m.erases = 0u;

  assert(zs_station_secrets_load(&io, &back, &slot) == ZS_STATION_SECRETS_NOT_FOUND && !back.engineer_key_set && back.iccid[0][0] == 0);
  assert(zs_station_secrets_load(NULL, &back, &slot) == ZS_STATION_SECRETS_INVALID_ARGUMENT);

  /* first commit: version 1 into slot 0 */
  memset(&s, 0, sizeof(s));
  for (unsigned i = 0u; i < 32u; i++) s.engineer_key[i] = (uint8_t)(0xa0 + i);
  s.engineer_key_set = true;
  strcpy(s.iccid[0], ICCID1);
  assert(zs_station_secrets_commit(&io, &s) == ZS_STATION_SECRETS_OK && s.version == 1u);
  assert(zs_station_secrets_load(&io, &back, &slot) == ZS_STATION_SECRETS_OK && slot == 0u && back.version == 1u);
  assert(back.engineer_key_set && memcmp(back.engineer_key, s.engineer_key, 32u) == 0 && strcmp(back.iccid[0], ICCID1) == 0 && back.iccid[1][0] == 0 && !back.command_key_set);

  /* second commit goes to slot 1 with version 2; the unset key bytes of the caller do not matter */
  strcpy(s.iccid[1], ICCID2);
  memset(s.command_public_key, 0x5a, sizeof(s.command_public_key));   /* garbage, not flagged */
  assert(zs_station_secrets_commit(&io, &s) == ZS_STATION_SECRETS_OK && s.version == 2u);
  assert(zs_station_secrets_load(&io, &back, &slot) == ZS_STATION_SECRETS_OK && slot == 1u && back.version == 2u && strcmp(back.iccid[1], ICCID2) == 0 && !back.command_key_set);

  /* torn third commit (power loss before the CRC): the version-2 record stays active */
  m.fail_write = m.writes + 2u;
  s.command_key_set = true;
  assert(zs_station_secrets_commit(&io, &s) == ZS_STATION_SECRETS_IO_ERROR);
  m.fail_write = 0u;
  assert(zs_station_secrets_load(&io, &back, &slot) == ZS_STATION_SECRETS_OK && slot == 1u && back.version == 2u && !back.command_key_set);
  /* retry lands version 3 in slot 0 */
  assert(zs_station_secrets_commit(&io, &s) == ZS_STATION_SECRETS_OK && s.version == 3u);
  assert(zs_station_secrets_load(&io, &back, &slot) == ZS_STATION_SECRETS_OK && slot == 0u && back.version == 3u && back.command_key_set && back.command_public_key[0] == 0x5a);

  /* a corrupt active slot falls back to the other valid record */
  m.slots[0][20] ^= 0x01u;
  assert(zs_station_secrets_load(&io, &back, &slot) == ZS_STATION_SECRETS_OK && slot == 1u && back.version == 2u);

  /* invalid ICCID is refused before anything is written */
  { unsigned e = m.erases; strcpy(s.iccid[0], "12ab"); assert(zs_station_secrets_commit(&io, &s) == ZS_STATION_SECRETS_INVALID_ARGUMENT && m.erases == e); }

  /* clear: both slots blank */
  assert(zs_station_secrets_clear(&io) == ZS_STATION_SECRETS_OK);
  assert(zs_station_secrets_load(&io, &back, &slot) == ZS_STATION_SECRETS_NOT_FOUND);
  assert(zs_station_secrets_iccid_valid(ICCID1) && !zs_station_secrets_iccid_valid("1234") && !zs_station_secrets_iccid_valid("8970101234567890123x"));
  printf("secrets ram ok\n");
}

/* ---- simulated W25Q NOR through the slot-store adapter ---- */
#define MOCK_ERASE_BYTES 4096u
#define MOCK_BYTES (4u * MOCK_ERASE_BYTES)
typedef struct { uint8_t memory[MOCK_BYTES]; uint8_t status; uint32_t millis; } mock_nor_t;
static uint32_t mock_millis(void *ctx) { return ((mock_nor_t *)ctx)->millis; }
static void mock_delay(void *ctx, uint32_t ms) { ((mock_nor_t *)ctx)->millis += ms; }
static int mock_command(void *ctx, uint8_t opcode, uint32_t address, uint8_t address_bytes, const uint8_t *tx, size_t tx_size, uint8_t *rx, size_t rx_size) {
  mock_nor_t *m = ctx;
  if (opcode == 0x05u) { if (!rx || rx_size != 1u) return -1; rx[0] = m->status; return 0; }
  if (opcode == 0x06u) { m->status |= 0x02u; return 0; }
  if (opcode == 0x13u) { if (address_bytes != 4u || !rx || (uint64_t)address + rx_size > MOCK_BYTES) return -1; memcpy(rx, &m->memory[address], rx_size); return 0; }
  if (opcode == 0x12u) {
    if (address_bytes != 4u || !tx || tx_size == 0u || tx_size > 256u || (m->status & 0x02u) == 0u || address / 256u != (address + (uint32_t)tx_size - 1u) / 256u || (uint64_t)address + tx_size > MOCK_BYTES) return -1;
    for (size_t i = 0u; i < tx_size; i++) { if ((m->memory[address + i] & tx[i]) != tx[i]) return -1; m->memory[address + i] = tx[i]; }
    m->status &= (uint8_t)~0x02u; return 0;
  }
  if (opcode == 0x21u) { if (address_bytes != 4u || (m->status & 0x02u) == 0u || address % MOCK_ERASE_BYTES != 0u || (uint64_t)address + MOCK_ERASE_BYTES > MOCK_BYTES) return -1; memset(&m->memory[address], 0xff, MOCK_ERASE_BYTES); m->status &= (uint8_t)~0x02u; return 0; }
  return -1;
}

static void test_nor(void) {
  static mock_nor_t m;
  const zs_nor_port_t port = {&m, mock_command, mock_millis, mock_delay};
  zs_nor_geometry_t geometry = zs_nor_geometry_64m_4byte();
  zs_nor_t nor;
  zs_nor_slot_store_t store;
  zs_station_secrets_io_t io;
  zs_station_secrets_t s, back;
  uint8_t slot;
  memset(&m, 0, sizeof(m)); memset(m.memory, 0xff, sizeof(m.memory));
  geometry.capacity_bytes = MOCK_BYTES;
  assert(zs_nor_init(&nor, &port, &geometry));
  assert(zs_nor_slot_store_init(&store, &nor, 2u * MOCK_ERASE_BYTES, ZS_STATION_SECRETS_SLOT_COUNT, ZS_STATION_SECRETS_SLOT_BYTES));
  assert(zs_nor_slot_store_secrets_io(&store, &io));
  { zs_nor_slot_store_t small; assert(zs_nor_slot_store_init(&small, &nor, 0u, 2u, 64u)); assert(!zs_nor_slot_store_secrets_io(&small, &io)); assert(zs_nor_slot_store_secrets_io(&store, &io)); }
  memset(&s, 0, sizeof(s));
  strcpy(s.iccid[0], ICCID1); strcpy(s.iccid[1], ICCID2);
  assert(zs_station_secrets_commit(&io, &s) == ZS_STATION_SECRETS_OK);
  assert(zs_station_secrets_commit(&io, &s) == ZS_STATION_SECRETS_OK && s.version == 2u);
  assert(zs_station_secrets_load(&io, &back, &slot) == ZS_STATION_SECRETS_OK && slot == 1u && strcmp(back.iccid[1], ICCID2) == 0);
  assert(memcmp(&m.memory[2u * MOCK_ERASE_BYTES], "ZSSECR01", 8) == 0 && memcmp(&m.memory[3u * MOCK_ERASE_BYTES], "ZSSECR01", 8) == 0);
  for (uint32_t a = 0u; a < 2u * MOCK_ERASE_BYTES; a++) assert(m.memory[a] == 0xffu);     /* nothing outside the partition */
  printf("secrets nor ok\n");
}

int main(void) {
  test_ram();
  test_nor();
  printf("station secrets tests passed\n");
  return 0;
}

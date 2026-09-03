#include "zs_nor.h"
#include "zs_nor_archive.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MOCK_BYTES (18u * 1024u * 1024u)

typedef struct {
  uint8_t *mem;
  size_t size;
  uint8_t status;
  uint32_t ms;
  uint32_t program_commands;
  uint32_t erase_commands;
  uint32_t last_memory_address;
  uint8_t last_memory_address_bytes;
} mock_nor_t;

static uint32_t mock_millis(void *ctx) { return ((mock_nor_t *)ctx)->ms; }
static void mock_delay(void *ctx, uint32_t ms) { ((mock_nor_t *)ctx)->ms += ms; }

static void remember_memory_command(mock_nor_t *m, uint32_t address, uint8_t address_bytes) {
  m->last_memory_address = address;
  m->last_memory_address_bytes = address_bytes;
}

static int mock_command(void *ctx,
                        uint8_t opcode,
                        uint32_t address,
                        uint8_t address_bytes,
                        const uint8_t *tx,
                        size_t tx_len,
                        uint8_t *rx,
                        size_t rx_len) {
  mock_nor_t *m = (mock_nor_t *)ctx;
  if (opcode == 0x9fu) {
    if (!rx || rx_len != 3u) return -1;
    rx[0] = 0xc2u; rx[1] = 0x20u; rx[2] = 0x1au;
    return 0;
  }
  if (opcode == 0x05u) {
    if (!rx || rx_len != 1u) return -1;
    rx[0] = m->status;
    return 0;
  }
  if (opcode == 0x06u) {
    m->status |= 0x02u;
    return 0;
  }
  if (opcode == 0x13u) {
    remember_memory_command(m, address, address_bytes);
    if (address_bytes != 4u || !rx || (uint64_t)address + rx_len > m->size) return -1;
    memcpy(rx, &m->mem[address], rx_len);
    return 0;
  }
  if (opcode == 0x12u) {
    remember_memory_command(m, address, address_bytes);
    if (address_bytes != 4u || !tx || tx_len == 0u || tx_len > 256u) return -1;
    if ((m->status & 0x02u) == 0u) return -1;
    if ((address / 256u) != ((address + (uint32_t)tx_len - 1u) / 256u)) return -1;
    if ((uint64_t)address + tx_len > m->size) return -1;
    for (size_t i = 0; i < tx_len; ++i) m->mem[address + i] &= tx[i];
    m->status &= (uint8_t)~0x02u;
    m->program_commands++;
    return 0;
  }
  if (opcode == 0x21u) {
    remember_memory_command(m, address, address_bytes);
    if (address_bytes != 4u || (m->status & 0x02u) == 0u) return -1;
    if ((address % 4096u) != 0u || (uint64_t)address + 4096u > m->size) return -1;
    memset(&m->mem[address], 0xff, 4096u);
    m->status &= (uint8_t)~0x02u;
    m->erase_commands++;
    return 0;
  }
  return -1;
}

static zs_nor_t make_nor(mock_nor_t *mock) {
  const zs_nor_port_t port = {
      .ctx = mock,
      .command = mock_command,
      .millis = mock_millis,
      .delay_ms = mock_delay,
  };
  zs_nor_geometry_t g = zs_nor_geometry_64m_4byte();
  /* The mocked backing store is smaller, but keep logical 64 MiB geometry. */
  zs_nor_t nor;
  assert(zs_nor_init(&nor, &port, &g));
  return nor;
}

static void test_id_and_addressing(mock_nor_t *mock, zs_nor_t *nor) {
  uint8_t id[3] = {0};
  assert(zs_nor_read_jedec_id(nor, id));
  assert(id[0] == 0xc2u && id[1] == 0x20u && id[2] == 0x1au);

  const uint32_t address = 0x01000010u; /* Above 16 MiB, requires 4-byte address. */
  uint8_t src[32];
  uint8_t dst[32];
  for (unsigned i = 0; i < sizeof(src); ++i) src[i] = (uint8_t)(0xa0u + i);
  assert(zs_nor_program(nor, address, src, sizeof(src)));
  assert(mock->last_memory_address == address);
  assert(mock->last_memory_address_bytes == 4u);
  memset(dst, 0, sizeof(dst));
  assert(zs_nor_read(nor, address, dst, sizeof(dst)));
  assert(mock->last_memory_address == address);
  assert(mock->last_memory_address_bytes == 4u);
  assert(memcmp(src, dst, sizeof(src)) == 0);
}

static void test_page_split(mock_nor_t *mock, zs_nor_t *nor) {
  const uint32_t before = mock->program_commands;
  const uint32_t address = 0x00000ff0u;
  uint8_t data[40];
  memset(data, 0x55, sizeof(data));
  assert(zs_nor_program(nor, address, data, sizeof(data)));
  assert(mock->program_commands - before == 2u);
}

static void test_erase_rules(mock_nor_t *mock, zs_nor_t *nor) {
  assert(!zs_nor_erase(nor, 1u, 4096u));
  assert(!zs_nor_erase(nor, 0u, 4095u));
  const uint32_t before = mock->erase_commands;
  assert(zs_nor_erase(nor, 0x2000u, 8192u));
  assert(mock->erase_commands - before == 2u);
  for (uint32_t a = 0x2000u; a < 0x4000u; ++a) assert(mock->mem[a] == 0xffu);
}

static void test_archive_adapter(zs_nor_t *nor) {
  zs_nor_archive_adapter_t adapter;
  zs_archive_storage_t storage;
  assert(zs_nor_archive_storage_init(&adapter, nor, &storage));
  assert(storage.size_bytes == 64u * 1024u * 1024u);
  assert(storage.erase_block_bytes == 4096u);
  const uint8_t payload[] = {0xfeu, 0xfdu, 0xfbu, 0xf7u};
  uint8_t out[sizeof(payload)] = {0};
  assert(storage.erase(storage.ctx, 0x4000u, 4096u) == 0);
  assert(storage.write(storage.ctx, 0x4010u, payload, sizeof(payload)) == 0);
  assert(storage.read(storage.ctx, 0x4010u, out, sizeof(out)) == 0);
  assert(memcmp(payload, out, sizeof(payload)) == 0);
}

static void test_bounds(zs_nor_t *nor) {
  uint8_t one = 0;
  assert(!zs_nor_read(nor, 64u * 1024u * 1024u, &one, 1u));
  assert(!zs_nor_program(nor, 0xffffffffu, &one, 1u));
}

int main(void) {
  mock_nor_t mock = {0};
  mock.size = MOCK_BYTES;
  mock.mem = (uint8_t *)malloc(mock.size);
  assert(mock.mem != NULL);
  memset(mock.mem, 0xff, mock.size);

  zs_nor_t nor = make_nor(&mock);
  test_id_and_addressing(&mock, &nor);
  test_page_split(&mock, &nor);
  test_erase_rules(&mock, &nor);
  test_archive_adapter(&nor);
  test_bounds(&nor);

  free(mock.mem);
  puts("zs_nor_tests: OK");
  return 0;
}

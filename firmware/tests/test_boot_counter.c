/* B3: monotonic boot counter in one NOR erase block (simulated W25Q-like flash). */
#include "zs_boot_counter.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define MOCK_ERASE_BYTES 4096u
#define MOCK_BYTES (4u * MOCK_ERASE_BYTES)

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
    if (mock->program_attempts == mock->fail_program_call) { /* power loss mid-program: nothing lands */
      mock->status &= (uint8_t)~0x02u;
      return -1;
    }
    for (size_t i = 0u; i < tx_size; ++i) {
      if ((mock->memory[address + i] & tx[i]) != tx[i]) return -1;   /* programming can only clear bits */
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

#define BASE (2u * MOCK_ERASE_BYTES)
#define BITMAP_BITS ((MOCK_ERASE_BYTES - ZS_BOOT_COUNTER_HEADER_BYTES) * 8u)

int main(void) {
  static mock_nor_t mock;
  zs_nor_t nor;
  zs_boot_counter_t c;
  uint32_t id = 0u;

  /* factory flash: unformatted reads as 0, the first boot formats and returns 1 */
  memset(&mock, 0, sizeof(mock)); memset(mock.memory, 0xff, sizeof(mock.memory));
  nor = make_nor(&mock);
  assert(zs_boot_counter_open(&c, &nor, BASE, MOCK_ERASE_BYTES) && !c.formatted && zs_boot_counter_value(&c) == 0u);
  assert(zs_boot_counter_increment(&c, &id) && id == 1u && zs_boot_counter_value(&c) == 1u);
  assert(mock.erase_commands == 1u && memcmp(&mock.memory[BASE], "ZSBOOT01", 8) == 0 && mock.memory[BASE + 16u] == 0xfeu);

  /* every boot is one byte program, no erase; the count survives a re-open */
  for (unsigned i = 2u; i <= 20u; i++) { assert(zs_boot_counter_increment(&c, &id) && id == i); }
  assert(mock.erase_commands == 1u && mock.memory[BASE + 16u] == 0x00u && mock.memory[BASE + 17u] == 0x00u && mock.memory[BASE + 18u] == 0xf0u);
  assert(zs_boot_counter_open(&c, &nor, BASE, MOCK_ERASE_BYTES) && c.formatted && zs_boot_counter_value(&c) == 20u);
  assert(zs_boot_counter_increment(&c, &id) && id == 21u);

  /* a failed program (power loss) leaves the count unchanged; the retry lands the same bit */
  mock.fail_program_call = mock.program_attempts + 1u;
  assert(!zs_boot_counter_increment(&c, &id));
  assert(zs_boot_counter_open(&c, &nor, BASE, MOCK_ERASE_BYTES) && zs_boot_counter_value(&c) == 21u);
  assert(zs_boot_counter_increment(&c, &id) && id == 22u);

  /* bitmap exhaustion carries into the base with one erase; the value keeps counting up */
  while (zs_boot_counter_value(&c) < BITMAP_BITS) assert(zs_boot_counter_increment(&c, &id));
  assert(id == BITMAP_BITS && mock.erase_commands == 1u);
  assert(zs_boot_counter_increment(&c, &id) && id == BITMAP_BITS + 1u && mock.erase_commands == 2u && c.base == BITMAP_BITS && c.used_bits == 1u);
  assert(zs_boot_counter_open(&c, &nor, BASE, MOCK_ERASE_BYTES) && zs_boot_counter_value(&c) == BITMAP_BITS + 1u);

  /* a corrupt header (base / ~base mismatch) is treated as unformatted: value 0, next boot re-formats */
  mock.memory[BASE + 12u] ^= 0x01u;
  assert(zs_boot_counter_open(&c, &nor, BASE, MOCK_ERASE_BYTES) && !c.formatted && zs_boot_counter_value(&c) == 0u);
  assert(zs_boot_counter_increment(&c, &id) && id == 1u && mock.erase_commands == 3u);

  /* bad arguments */
  assert(!zs_boot_counter_open(&c, NULL, BASE, MOCK_ERASE_BYTES));
  assert(!zs_boot_counter_open(&c, &nor, BASE, ZS_BOOT_COUNTER_HEADER_BYTES));
  assert(!zs_boot_counter_increment(NULL, &id));

  printf("boot counter ok (%u boots per block before an erase)\n", (unsigned)BITMAP_BITS);
  printf("boot counter tests passed\n");
  return 0;
}

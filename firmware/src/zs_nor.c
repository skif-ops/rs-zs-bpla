#include "zs_nor.h"

#include <string.h>

#define ZS_NOR_OP_READ_ID 0x9fu
#define ZS_NOR_OP_READ_STATUS 0x05u
#define ZS_NOR_OP_WRITE_ENABLE 0x06u
#define ZS_NOR_OP_READ_4BYTE 0x13u
#define ZS_NOR_OP_PROGRAM_4BYTE 0x12u
#define ZS_NOR_OP_ERASE_4K_4BYTE 0x21u

static bool range_ok(const zs_nor_t *nor, uint32_t address, size_t len) {
  if (!nor) return false;
  if (len == 0u) return true;
  if ((uint64_t)address + (uint64_t)len > (uint64_t)nor->geometry.capacity_bytes) return false;
  return true;
}

zs_nor_geometry_t zs_nor_geometry_64m_4byte(void) {
  const zs_nor_geometry_t g = {
      .capacity_bytes = ZS_NOR_DEFAULT_CAPACITY_BYTES,
      .page_bytes = ZS_NOR_DEFAULT_PAGE_BYTES,
      .erase_bytes = ZS_NOR_DEFAULT_ERASE_BYTES,
      .address_bytes = 4u,
      .read_opcode = ZS_NOR_OP_READ_4BYTE,
      .program_opcode = ZS_NOR_OP_PROGRAM_4BYTE,
      .erase_opcode = ZS_NOR_OP_ERASE_4K_4BYTE,
      .read_status_opcode = ZS_NOR_OP_READ_STATUS,
      .write_enable_opcode = ZS_NOR_OP_WRITE_ENABLE,
      .read_id_opcode = ZS_NOR_OP_READ_ID,
      .status_busy_mask = 0x01u,
      .status_wel_mask = 0x02u,
  };
  return g;
}

bool zs_nor_init(zs_nor_t *nor,
                 const zs_nor_port_t *port,
                 const zs_nor_geometry_t *geometry) {
  if (!nor || !port || !geometry || !port->command || !port->millis || !port->delay_ms) return false;
  if (geometry->capacity_bytes == 0u || geometry->page_bytes == 0u || geometry->erase_bytes == 0u) return false;
  if (geometry->address_bytes != 3u && geometry->address_bytes != 4u) return false;
  memset(nor, 0, sizeof(*nor));
  nor->port = *port;
  nor->geometry = *geometry;
  nor->program_timeout_ms = 1000u;
  nor->erase_timeout_ms = 10000u;
  return true;
}

bool zs_nor_read_jedec_id(zs_nor_t *nor, uint8_t out_id[3]) {
  if (!nor || !out_id) return false;
  return nor->port.command(nor->port.ctx, nor->geometry.read_id_opcode, 0u, 0u,
                           NULL, 0u, out_id, 3u) == 0;
}

bool zs_nor_read_status(zs_nor_t *nor, uint8_t *status) {
  if (!nor || !status) return false;
  return nor->port.command(nor->port.ctx, nor->geometry.read_status_opcode, 0u, 0u,
                           NULL, 0u, status, 1u) == 0;
}

bool zs_nor_wait_ready(zs_nor_t *nor, uint32_t timeout_ms) {
  if (!nor) return false;
  const uint32_t start = nor->port.millis(nor->port.ctx);
  for (;;) {
    uint8_t status = 0xffu;
    if (!zs_nor_read_status(nor, &status)) return false;
    if ((status & nor->geometry.status_busy_mask) == 0u) return true;
    if ((uint32_t)(nor->port.millis(nor->port.ctx) - start) >= timeout_ms) return false;
    nor->port.delay_ms(nor->port.ctx, 1u);
  }
}

bool zs_nor_write_enable(zs_nor_t *nor) {
  if (!nor) return false;
  if (nor->port.command(nor->port.ctx, nor->geometry.write_enable_opcode, 0u, 0u,
                        NULL, 0u, NULL, 0u) != 0) return false;
  uint8_t status = 0u;
  if (!zs_nor_read_status(nor, &status)) return false;
  return (status & nor->geometry.status_wel_mask) != 0u;
}

bool zs_nor_read(zs_nor_t *nor, uint32_t address, uint8_t *data, size_t len) {
  if (!nor || (!data && len != 0u) || !range_ok(nor, address, len)) return false;
  if (len == 0u) return true;
  if (!zs_nor_wait_ready(nor, nor->program_timeout_ms)) return false;
  return nor->port.command(nor->port.ctx, nor->geometry.read_opcode, address,
                           nor->geometry.address_bytes, NULL, 0u, data, len) == 0;
}

bool zs_nor_program(zs_nor_t *nor, uint32_t address, const uint8_t *data, size_t len) {
  if (!nor || (!data && len != 0u) || !range_ok(nor, address, len)) return false;
  size_t remaining = len;
  const uint8_t *p = data;
  uint32_t a = address;
  while (remaining != 0u) {
    const uint32_t page_off = a % nor->geometry.page_bytes;
    const uint32_t room = nor->geometry.page_bytes - page_off;
    const size_t chunk = remaining < room ? remaining : (size_t)room;
    if (!zs_nor_wait_ready(nor, nor->program_timeout_ms)) return false;
    if (!zs_nor_write_enable(nor)) return false;
    if (nor->port.command(nor->port.ctx, nor->geometry.program_opcode, a,
                          nor->geometry.address_bytes, p, chunk, NULL, 0u) != 0) return false;
    if (!zs_nor_wait_ready(nor, nor->program_timeout_ms)) return false;
    a += (uint32_t)chunk;
    p += chunk;
    remaining -= chunk;
  }
  return true;
}

bool zs_nor_erase(zs_nor_t *nor, uint32_t address, size_t len) {
  if (!nor || !range_ok(nor, address, len)) return false;
  if (len == 0u) return true;
  if ((address % nor->geometry.erase_bytes) != 0u || (len % nor->geometry.erase_bytes) != 0u) return false;
  uint32_t a = address;
  size_t remaining = len;
  while (remaining != 0u) {
    if (!zs_nor_wait_ready(nor, nor->erase_timeout_ms)) return false;
    if (!zs_nor_write_enable(nor)) return false;
    if (nor->port.command(nor->port.ctx, nor->geometry.erase_opcode, a,
                          nor->geometry.address_bytes, NULL, 0u, NULL, 0u) != 0) return false;
    if (!zs_nor_wait_ready(nor, nor->erase_timeout_ms)) return false;
    a += nor->geometry.erase_bytes;
    remaining -= nor->geometry.erase_bytes;
  }
  return true;
}

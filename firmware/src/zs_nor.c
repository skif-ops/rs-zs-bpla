#include "zs_nor.h"

#include <string.h>

#define ZS_NOR_OP_READ_ID 0x9fu
#define ZS_NOR_OP_READ_STATUS 0x05u
#define ZS_NOR_OP_WRITE_ENABLE 0x06u
#define ZS_NOR_OP_READ_STATUS_2 0x35u
#define ZS_NOR_OP_WRITE_STATUS_2 0x31u
#define ZS_NOR_OP_READ_SFDP 0x5au
#define ZS_NOR_OP_READ_4BYTE 0x13u
#define ZS_NOR_OP_PROGRAM_4BYTE 0x12u
#define ZS_NOR_OP_ERASE_4K_4BYTE 0x21u
#define ZS_NOR_STATUS_2_QE_MASK 0x02u
#define ZS_NOR_SFDP_HEADER_BYTES 16u

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

static bool read_sfdp(zs_nor_t *nor,
                      uint32_t address,
                      uint8_t *data,
                      size_t len) {
  const uint8_t dummy = 0u;
  if (!nor || !data || len == 0u || address > 0x00ffffffu ||
      (uint64_t)address + len > UINT32_C(0x01000000))
    return false;
  return nor->port.command(nor->port.ctx, ZS_NOR_OP_READ_SFDP, address, 3u,
                           &dummy, 1u, data, len) == 0;
}

static uint32_t get_u32_le(const uint8_t value[4]) {
  return (uint32_t)value[0] | ((uint32_t)value[1] << 8) |
         ((uint32_t)value[2] << 16) | ((uint32_t)value[3] << 24);
}

static bool sfdp_density_bytes(uint32_t raw, uint32_t *bytes) {
  uint64_t bits;
  if (!bytes) return false;
  *bytes = 0u;
  if ((raw & UINT32_C(0x80000000)) == 0u) {
    bits = (uint64_t)raw + 1u;
  } else {
    const uint32_t exponent = raw & UINT32_C(0x7fffffff);
    if (exponent >= 63u) return false;
    bits = UINT64_C(1) << exponent;
  }
  if (bits == 0u || bits % 8u != 0u || bits / 8u > UINT32_MAX)
    return false;
  *bytes = (uint32_t)(bits / 8u);
  return true;
}

static bool read_status_2(zs_nor_t *nor, uint8_t *status) {
  return nor && status &&
         nor->port.command(nor->port.ctx, ZS_NOR_OP_READ_STATUS_2, 0u, 0u,
                           NULL, 0u, status, 1u) == 0;
}

static bool restore_quad_enable(zs_nor_t *nor,
                                uint8_t status_2,
                                bool *restored) {
  uint8_t verified = 0u;
  const uint8_t enabled = status_2 | ZS_NOR_STATUS_2_QE_MASK;
  if (!nor || !restored) return false;
  *restored = false;
  if ((status_2 & ZS_NOR_STATUS_2_QE_MASK) != 0u) return true;
  if (!zs_nor_write_enable(nor) ||
      nor->port.command(nor->port.ctx, ZS_NOR_OP_WRITE_STATUS_2, 0u, 0u,
                        &enabled, 1u, NULL, 0u) != 0 ||
      !zs_nor_wait_ready(nor, nor->program_timeout_ms) ||
      !read_status_2(nor, &verified) ||
      (verified & ZS_NOR_STATUS_2_QE_MASK) == 0u)
    return false;
  *restored = true;
  return true;
}

zs_nor_probe_result_t zs_nor_probe_w25q512jv(
    zs_nor_t *nor, zs_nor_probe_info_t *out_info) {
  uint8_t jedec[3] = {0u};
  uint8_t sfdp[ZS_NOR_SFDP_HEADER_BYTES] = {0u};
  uint8_t density_raw[4] = {0u};
  uint8_t status_2 = 0u;
  uint32_t density_address;
  uint32_t capacity_bytes;
  bool restored = false;

  if (out_info) memset(out_info, 0, sizeof(*out_info));
  if (!nor || !out_info || !nor->port.command || !nor->port.millis ||
      !nor->port.delay_ms)
    return ZS_NOR_PROBE_INVALID_ARGUMENT;
  if (nor->geometry.capacity_bytes != ZS_NOR_DEFAULT_CAPACITY_BYTES ||
      nor->geometry.page_bytes != ZS_NOR_DEFAULT_PAGE_BYTES ||
      nor->geometry.erase_bytes != ZS_NOR_DEFAULT_ERASE_BYTES ||
      nor->geometry.address_bytes != 4u ||
      nor->geometry.read_opcode != ZS_NOR_OP_READ_4BYTE ||
      nor->geometry.program_opcode != ZS_NOR_OP_PROGRAM_4BYTE ||
      nor->geometry.erase_opcode != ZS_NOR_OP_ERASE_4K_4BYTE ||
      nor->geometry.read_status_opcode != ZS_NOR_OP_READ_STATUS ||
      nor->geometry.write_enable_opcode != ZS_NOR_OP_WRITE_ENABLE ||
      nor->geometry.read_id_opcode != ZS_NOR_OP_READ_ID ||
      nor->geometry.status_busy_mask != 0x01u ||
      nor->geometry.status_wel_mask != 0x02u)
    return ZS_NOR_PROBE_GEOMETRY_MISMATCH;
  if (!zs_nor_wait_ready(nor, nor->program_timeout_ms) ||
      !zs_nor_read_jedec_id(nor, jedec))
    return ZS_NOR_PROBE_IO_ERROR;
  if (jedec[0] != ZS_NOR_W25Q512JV_JEDEC_MANUFACTURER ||
      jedec[1] != ZS_NOR_W25Q512JV_JEDEC_MEMORY_TYPE ||
      jedec[2] != ZS_NOR_W25Q512JV_JEDEC_CAPACITY)
    return ZS_NOR_PROBE_JEDEC_MISMATCH;
  if (!read_sfdp(nor, 0u, sfdp, sizeof(sfdp)))
    return ZS_NOR_PROBE_IO_ERROR;
  if (memcmp(sfdp, "SFDP", 4u) != 0 || sfdp[5] == 0u ||
      sfdp[5] == 0xffu || sfdp[8] != 0x00u || sfdp[11] < 2u ||
      sfdp[15] != 0xffu)
    return ZS_NOR_PROBE_SFDP_MISMATCH;
  density_address = (uint32_t)sfdp[12] | ((uint32_t)sfdp[13] << 8) |
                    ((uint32_t)sfdp[14] << 16);
  if (density_address > UINT32_C(0x00fffffb) ||
      !read_sfdp(nor, density_address + 4u, density_raw,
                 sizeof(density_raw)))
    return ZS_NOR_PROBE_IO_ERROR;
  if (!sfdp_density_bytes(get_u32_le(density_raw), &capacity_bytes) ||
      capacity_bytes != nor->geometry.capacity_bytes)
    return ZS_NOR_PROBE_CAPACITY_MISMATCH;
  if (!read_status_2(nor, &status_2)) return ZS_NOR_PROBE_IO_ERROR;
  if (!restore_quad_enable(nor, status_2, &restored))
    return ZS_NOR_PROBE_QUAD_ENABLE_FAILED;
  if (!read_status_2(nor, &status_2) ||
      (status_2 & ZS_NOR_STATUS_2_QE_MASK) == 0u)
    return ZS_NOR_PROBE_QUAD_ENABLE_FAILED;

  memcpy(out_info->jedec_id, jedec, sizeof(jedec));
  out_info->sfdp_minor = sfdp[4];
  out_info->sfdp_major = sfdp[5];
  out_info->capacity_bytes = capacity_bytes;
  out_info->quad_enabled = true;
  out_info->quad_enable_restored = restored;
  return ZS_NOR_PROBE_OK;
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

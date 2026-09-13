#ifndef ZS_NOR_H
#define ZS_NOR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_NOR_DEFAULT_PAGE_BYTES 256u
#define ZS_NOR_DEFAULT_ERASE_BYTES 4096u
#define ZS_NOR_DEFAULT_CAPACITY_BYTES (64u * 1024u * 1024u)
#define ZS_NOR_W25Q512JV_JEDEC_MANUFACTURER 0xefu
#define ZS_NOR_W25Q512JV_JEDEC_MEMORY_TYPE 0x40u
#define ZS_NOR_W25Q512JV_JEDEC_CAPACITY 0x20u

typedef struct {
  void *ctx;
  /*
   * Execute one serial-NOR command. address_bytes is 0, 3, or 4.
   * tx/rx payload follows opcode/address. If both are present, transmit tx
   * first and clock rx under the same chip-select assertion. Return 0 on
   * success.
   */
  int (*command)(void *ctx,
                 uint8_t opcode,
                 uint32_t address,
                 uint8_t address_bytes,
                 const uint8_t *tx,
                 size_t tx_len,
                 uint8_t *rx,
                 size_t rx_len);
  uint32_t (*millis)(void *ctx);
  void (*delay_ms)(void *ctx, uint32_t ms);
} zs_nor_port_t;

typedef struct {
  uint32_t capacity_bytes;
  uint32_t page_bytes;
  uint32_t erase_bytes;
  uint8_t address_bytes;
  uint8_t read_opcode;
  uint8_t program_opcode;
  uint8_t erase_opcode;
  uint8_t read_status_opcode;
  uint8_t write_enable_opcode;
  uint8_t read_id_opcode;
  uint8_t status_busy_mask;
  uint8_t status_wel_mask;
} zs_nor_geometry_t;

typedef struct {
  zs_nor_port_t port;
  zs_nor_geometry_t geometry;
  uint32_t program_timeout_ms;
  uint32_t erase_timeout_ms;
} zs_nor_t;

typedef enum {
  ZS_NOR_PROBE_OK = 0,
  ZS_NOR_PROBE_INVALID_ARGUMENT,
  ZS_NOR_PROBE_GEOMETRY_MISMATCH,
  ZS_NOR_PROBE_IO_ERROR,
  ZS_NOR_PROBE_JEDEC_MISMATCH,
  ZS_NOR_PROBE_SFDP_MISMATCH,
  ZS_NOR_PROBE_CAPACITY_MISMATCH,
  ZS_NOR_PROBE_QUAD_ENABLE_FAILED
} zs_nor_probe_result_t;

typedef struct {
  uint8_t jedec_id[3];
  uint8_t sfdp_major;
  uint8_t sfdp_minor;
  uint32_t capacity_bytes;
  bool quad_enabled;
  bool quad_enable_restored;
} zs_nor_probe_info_t;

/* Conservative 64 MiB serial-NOR profile using explicit 4-byte addresses. */
zs_nor_geometry_t zs_nor_geometry_64m_4byte(void);

bool zs_nor_init(zs_nor_t *nor,
                 const zs_nor_port_t *port,
                 const zs_nor_geometry_t *geometry);

bool zs_nor_read_jedec_id(zs_nor_t *nor, uint8_t out_id[3]);
bool zs_nor_read_status(zs_nor_t *nor, uint8_t *status);
bool zs_nor_wait_ready(zs_nor_t *nor, uint32_t timeout_ms);
bool zs_nor_write_enable(zs_nor_t *nor);

/*
 * Validate the frozen W25Q512JV identity through exact JEDEC ID and SFDP
 * density, then verify or restore Status Register-2 QE via 35h/31h before Quad
 * operation.
 * out_info is zeroed on every failure. Target OCTOSPI setup must call this
 * before exposing archive, command-journal, or event-outbox storage.
 */
zs_nor_probe_result_t zs_nor_probe_w25q512jv(
    zs_nor_t *nor, zs_nor_probe_info_t *out_info);

bool zs_nor_read(zs_nor_t *nor, uint32_t address, uint8_t *data, size_t len);
bool zs_nor_program(zs_nor_t *nor, uint32_t address, const uint8_t *data, size_t len);
bool zs_nor_erase(zs_nor_t *nor, uint32_t address, size_t len);

#endif

#ifndef ZS_NOR_H
#define ZS_NOR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_NOR_DEFAULT_PAGE_BYTES 256u
#define ZS_NOR_DEFAULT_ERASE_BYTES 4096u
#define ZS_NOR_DEFAULT_CAPACITY_BYTES (64u * 1024u * 1024u)

typedef struct {
  void *ctx;
  /*
   * Execute one serial-NOR command. address_bytes is 0, 3, or 4.
   * tx/rx payload follows opcode/address. Return 0 on success.
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

/* Conservative 64 MiB serial-NOR profile using explicit 4-byte addresses. */
zs_nor_geometry_t zs_nor_geometry_64m_4byte(void);

bool zs_nor_init(zs_nor_t *nor,
                 const zs_nor_port_t *port,
                 const zs_nor_geometry_t *geometry);

bool zs_nor_read_jedec_id(zs_nor_t *nor, uint8_t out_id[3]);
bool zs_nor_read_status(zs_nor_t *nor, uint8_t *status);
bool zs_nor_wait_ready(zs_nor_t *nor, uint32_t timeout_ms);
bool zs_nor_write_enable(zs_nor_t *nor);

bool zs_nor_read(zs_nor_t *nor, uint32_t address, uint8_t *data, size_t len);
bool zs_nor_program(zs_nor_t *nor, uint32_t address, const uint8_t *data, size_t len);
bool zs_nor_erase(zs_nor_t *nor, uint32_t address, size_t len);

#endif

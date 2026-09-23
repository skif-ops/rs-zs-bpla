#ifndef ZS_NOR_IMAGE_STORE_H
#define ZS_NOR_IMAGE_STORE_H
/*
 * nRF52840 bridge image slot on the station NOR (B3 layout: zs_nor_storage_layout_t.nrf_image_base_address,
 * addendum C.6).  The first erase block holds the header, the image follows from the second block:
 *   header: magic "ZSNRFIMG", format 1, image version, size, SHA-256, header CRC-16 (XMODEM) — written LAST,
 *   after the image has been programmed and read back against its SHA-256, so a torn transfer or a power
 *   loss leaves the slot invalid (magic missing) rather than half-trusted.
 * Writes are sequential from offset 0 (the writer keeps a running SHA-256); reads are random access for
 * the mcumgr upload client (zs_mcumgr_serial).
 */
#include "zs_nor.h"
#include "zs_sha256.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_NOR_IMAGE_HEADER_BYTES 64u
#define ZS_NOR_IMAGE_FORMAT 1u

typedef struct {
  uint32_t format;
  uint32_t version;       /* image version as the sender declared it (informational) */
  uint32_t size;
  uint8_t sha256[32];
} zs_nor_image_info_t;

typedef struct {
  zs_nor_t *nor;
  uint32_t base, bytes, erase_bytes;
  /* write session */
  bool writing;
  uint32_t write_size, write_version, written;
  uint8_t expected_sha[32];
  zs_sha256_t running;
  /* last opened image */
  bool valid;
  zs_nor_image_info_t info;
} zs_nor_image_store_t;

bool zs_nor_image_store_init(zs_nor_image_store_t *s, zs_nor_t *nor, uint32_t base_address, uint32_t partition_bytes);
uint32_t zs_nor_image_store_capacity(const zs_nor_image_store_t *s);   /* largest image the slot can hold */

/* Erases the slot and opens a write session for an image of `size` bytes with the declared SHA-256. */
bool zs_nor_image_store_begin(zs_nor_image_store_t *s, uint32_t size, uint32_t version, const uint8_t sha256[32]);
/* Appends the next bytes (any length); returns false on programming errors or overflow. */
bool zs_nor_image_store_write(zs_nor_image_store_t *s, const uint8_t *data, size_t len);
/* Verifies the running and the read-back SHA-256 against the declared one and commits the header. */
bool zs_nor_image_store_finish(zs_nor_image_store_t *s);
void zs_nor_image_store_abort(zs_nor_image_store_t *s);

/* Validates the header (and, when verify is set, the image SHA-256); fills info on success. */
bool zs_nor_image_store_open(zs_nor_image_store_t *s, bool verify, zs_nor_image_info_t *info);
/* Random-access read of the stored image (offset within the image). */
bool zs_nor_image_store_read(zs_nor_image_store_t *s, uint32_t offset, uint8_t *dst, size_t len);
/* Reader in the shape zs_mcumgr_upload_init_reader expects (ctx = the store). */
bool zs_nor_image_store_reader(void *ctx, size_t offset, uint8_t *dst, size_t len);

#endif

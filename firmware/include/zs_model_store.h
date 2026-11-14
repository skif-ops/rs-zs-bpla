#ifndef ZS_MODEL_STORE_H
#define ZS_MODEL_STORE_H
/*
 * Two slots for model packages on the station NOR (MQTT ICD addendum I; B3 layout model region).  Each slot is one
 * header block followed by the package area.  A download goes into the slot that is not active: its header block is
 * erased first, the package is written through zs_fw_image_io_t by the addendum F download engine (its validate hook
 * checks the package as a model), and only after the OK ACK the header is programmed:
 *   magic "DIOMSLT1" | seq u32 | version u32 | size u32 | SHA-256 of the package | 8 zero bytes | check u32
 *   (check = first 4 bytes of the SHA-256 of the 60 bytes before it)
 * A torn download or a power loss before the header leaves that slot invalid and the other one (or the built-in
 * model) in use.  At start the valid slot with the highest seq whose package matches its SHA-256 is active.
 */
#include "zs_fw_update.h"
#include "zs_model.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_MODEL_STORE_SLOTS 2u
#define ZS_MODEL_SLOT_HEADER_BYTES 64u
#define ZS_MODEL_SLOT_MAGIC "DIOMSLT1"

typedef struct {
  void *ctx;
  bool (*erase)(void *ctx, uint32_t address, uint32_t size);                       /* erase-block aligned */
  bool (*program)(void *ctx, uint32_t address, const uint8_t *data, size_t size);
  bool (*read)(void *ctx, uint32_t address, uint8_t *data, size_t size);
} zs_model_flash_t;

typedef struct {
  bool valid;
  uint32_t seq;
  uint32_t version;
  uint32_t size;
  uint8_t sha256[ZS_SHA256_DIGEST_BYTES];
} zs_model_slot_info_t;

typedef struct {
  const zs_model_flash_t *flash;
  uint32_t base;                   /* first slot; the second follows it */
  uint32_t slot_bytes;             /* header block + package area */
  uint32_t block_bytes;            /* erase granularity */
  zs_model_slot_info_t slot[ZS_MODEL_STORE_SLOTS];
  int active;                      /* -1: no valid package */
  unsigned target;                 /* slot of the download in progress */
  zs_fw_image_io_t io;             /* package area of the target slot */
} zs_model_store_t;

/* Binds the region and reads both headers (with the package SHA-256); false on bad geometry or a read error. */
bool zs_model_store_init(zs_model_store_t *s, const zs_model_flash_t *flash, uint32_t base, uint32_t slot_bytes, uint32_t block_bytes);
uint32_t zs_model_store_capacity(const zs_model_store_t *s);
/* The package area of the slot that is not active, its header block erased; NULL on an erase error. */
const zs_fw_image_io_t *zs_model_store_begin(zs_model_store_t *s);
/* After a verified download: programs the header of the target slot (seq one above the active one) and makes it
   the active slot. */
bool zs_model_store_commit(zs_model_store_t *s, const zs_fw_manifest_t *manifest);
/* Reader of the active package (ctx = the store) for zs_model_activate; size/version of it, false when none. */
bool zs_model_store_active(const zs_model_store_t *s, uint32_t *size, uint32_t *version);
bool zs_model_store_read_active(void *ctx, uint32_t offset, uint8_t *data, size_t size);

#endif

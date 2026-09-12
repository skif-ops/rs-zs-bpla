#ifndef ZS_INSTALLATION_STORE_H
#define ZS_INSTALLATION_STORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_position_trust.h"

#define ZS_INSTALLATION_STORE_SLOT_COUNT 2u
#define ZS_INSTALLATION_STORE_SLOT_BYTES 96u
#define ZS_INSTALLATION_HASH_BYTES 32u

typedef enum {
  ZS_INSTALLATION_STORE_OK = 0,
  ZS_INSTALLATION_STORE_NOT_FOUND,
  ZS_INSTALLATION_STORE_INVALID_ARGUMENT,
  ZS_INSTALLATION_STORE_AUTH_REQUIRED,
  ZS_INSTALLATION_STORE_INVALID_RECORD,
  ZS_INSTALLATION_STORE_LOCKED,
  ZS_INSTALLATION_STORE_VERSION_REJECTED,
  ZS_INSTALLATION_STORE_IO_ERROR,
  ZS_INSTALLATION_STORE_VERIFY_FAILED
} zs_installation_store_result_t;

typedef struct {
  void *ctx;
  bool (*read)(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size);
  bool (*erase)(void *ctx, uint8_t slot);
  bool (*write)(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size);
} zs_installation_store_io_t;

typedef struct {
  zs_position_trust_config_t trust;
  uint32_t version;
  uint32_t storage_generation;
  uint64_t commissioned_time_us;
  uint8_t source; /* 0 manual, 1 phone, 2 station GNSS snapshot, 3 surveyed */
  uint8_t commissioning_hash[ZS_INSTALLATION_HASH_BYTES];
} zs_installation_record_t;

zs_installation_store_result_t zs_installation_store_load(
    const zs_installation_store_io_t *io,
    zs_installation_record_t *record,
    uint8_t *active_slot);

zs_installation_store_result_t zs_installation_store_commit(
    const zs_installation_store_io_t *io,
    const zs_installation_record_t *record,
    bool physical_service_mode,
    bool authenticated_role,
    bool recommission);

#endif

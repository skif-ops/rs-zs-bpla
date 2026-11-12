#ifndef ZS_LORA_RF_PROFILE_H
#define ZS_LORA_RF_PROFILE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_LORA_RF_PROFILE_PAYLOAD_BYTES 32u
#define ZS_LORA_RF_PROFILE_SIGNATURE_BYTES 64u
#define ZS_LORA_RF_PROFILE_RECORD_BYTES (ZS_LORA_RF_PROFILE_PAYLOAD_BYTES + ZS_LORA_RF_PROFILE_SIGNATURE_BYTES)
#define ZS_LORA_RF_PROFILE_REGION_RU868 1u
#define ZS_LORA_RF_PROFILE_MODE_FIELD 2u

typedef struct {
  uint32_t version;
  uint32_t valid_from_firmware;
  uint32_t frequency_hz;
  uint32_t bandwidth_hz;
  uint32_t duty_cycle_ppm;
  uint16_t profile_id;
  uint8_t spreading_factor;
  int8_t tx_dbm;
} zs_lora_rf_profile_t;

typedef bool (*zs_lora_rf_profile_verify_fn)(void *ctx, const uint8_t *message, size_t message_size,
                                             const uint8_t signature[ZS_LORA_RF_PROFILE_SIGNATURE_BYTES]);

typedef struct {
  void *ctx;
  bool (*read)(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size);
  bool (*erase)(void *ctx, uint8_t slot);
  bool (*write)(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size);
} zs_lora_rf_profile_io_t;

typedef enum {
  ZS_LORA_RF_PROFILE_OK = 0,
  ZS_LORA_RF_PROFILE_NOT_FOUND,
  ZS_LORA_RF_PROFILE_INVALID,
  ZS_LORA_RF_PROFILE_ROLLBACK,
  ZS_LORA_RF_PROFILE_IO_ERROR,
  ZS_LORA_RF_PROFILE_VERIFY_FAILED
} zs_lora_rf_profile_result_t;

zs_lora_rf_profile_result_t zs_lora_rf_profile_decode(
    const uint8_t record[ZS_LORA_RF_PROFILE_RECORD_BYTES], uint32_t running_firmware,
    zs_lora_rf_profile_verify_fn verify, void *verify_ctx, zs_lora_rf_profile_t *out);
zs_lora_rf_profile_result_t zs_lora_rf_profile_load(
    const zs_lora_rf_profile_io_t *io, uint32_t running_firmware,
    zs_lora_rf_profile_verify_fn verify, void *verify_ctx, zs_lora_rf_profile_t *out);
zs_lora_rf_profile_result_t zs_lora_rf_profile_commit(
    const zs_lora_rf_profile_io_t *io, const uint8_t record[ZS_LORA_RF_PROFILE_RECORD_BYTES],
    uint32_t running_firmware, zs_lora_rf_profile_verify_fn verify, void *verify_ctx,
    zs_lora_rf_profile_t *out);
const char *zs_lora_rf_profile_result_name(zs_lora_rf_profile_result_t result);

#endif

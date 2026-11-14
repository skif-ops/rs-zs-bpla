#include "zs_lora_rf_profile.h"

#include <string.h>

#define PROFILE_MAGIC UINT32_C(0x46524c44)
#define PROFILE_FORMAT 1u
#define PROFILE_SIGN_DOMAIN "DIO-LORA-RF-V1"
#define PROFILE_SIGN_DOMAIN_BYTES 14u

static uint16_t get16(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static uint32_t get32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static bool frequency_allowed(uint32_t hz) {
  static const uint32_t allowed[] = {864100000u, 864300000u, 864500000u, 864700000u,
                                     864900000u, 868900000u, 869100000u};
  for (size_t i = 0u; i < sizeof(allowed) / sizeof(allowed[0]); i++) if (allowed[i] == hz) return true;
  return false;
}

zs_lora_rf_profile_result_t zs_lora_rf_profile_decode(
    const uint8_t record[ZS_LORA_RF_PROFILE_RECORD_BYTES], uint32_t running_firmware,
    zs_lora_rf_profile_verify_fn verify, void *verify_ctx, zs_lora_rf_profile_t *out) {
  uint8_t message[PROFILE_SIGN_DOMAIN_BYTES + ZS_LORA_RF_PROFILE_PAYLOAD_BYTES];
  zs_lora_rf_profile_t decoded;
  if (out) memset(out, 0, sizeof(*out));
  if (!record || !verify || !out) return ZS_LORA_RF_PROFILE_INVALID;
  if (get32(&record[0]) != PROFILE_MAGIC || record[4] != PROFILE_FORMAT ||
      record[5] != ZS_LORA_RF_PROFILE_MODE_FIELD || record[6] != ZS_LORA_RF_PROFILE_REGION_RU868 ||
      record[11] != 0u)
    return ZS_LORA_RF_PROFILE_INVALID;
  decoded.spreading_factor = record[7];
  decoded.profile_id = get16(&record[8]);
  decoded.tx_dbm = (int8_t)record[10];
  decoded.version = get32(&record[12]);
  decoded.frequency_hz = get32(&record[16]);
  decoded.bandwidth_hz = get32(&record[20]);
  decoded.duty_cycle_ppm = get32(&record[24]);
  decoded.valid_from_firmware = get32(&record[28]);
  if (decoded.version == 0u || decoded.profile_id == 0u || !frequency_allowed(decoded.frequency_hz) ||
      decoded.bandwidth_hz != 125000u || decoded.spreading_factor < 7u || decoded.spreading_factor > 12u ||
      decoded.tx_dbm < -9 || decoded.tx_dbm > 14 || decoded.duty_cycle_ppm == 0u ||
      decoded.duty_cycle_ppm > 10000u || decoded.valid_from_firmware > running_firmware)
    return ZS_LORA_RF_PROFILE_INVALID;
  memcpy(message, PROFILE_SIGN_DOMAIN, PROFILE_SIGN_DOMAIN_BYTES);
  memcpy(&message[PROFILE_SIGN_DOMAIN_BYTES], record, ZS_LORA_RF_PROFILE_PAYLOAD_BYTES);
  if (!verify(verify_ctx, message, sizeof(message), &record[ZS_LORA_RF_PROFILE_PAYLOAD_BYTES])) {
    memset(message, 0, sizeof(message));
    return ZS_LORA_RF_PROFILE_INVALID;
  }
  memset(message, 0, sizeof(message));
  *out = decoded;
  return ZS_LORA_RF_PROFILE_OK;
}

static int newest(const zs_lora_rf_profile_io_t *io, uint32_t running_firmware,
                  zs_lora_rf_profile_verify_fn verify, void *verify_ctx,
                  zs_lora_rf_profile_t *out, bool *io_error) {
  uint8_t record[ZS_LORA_RF_PROFILE_RECORD_BYTES];
  zs_lora_rf_profile_t candidate;
  int best = -1;
  *io_error = false;
  memset(out, 0, sizeof(*out));
  for (uint8_t slot = 0u; slot < 2u; slot++) {
    if (!io->read(io->ctx, slot, 0u, record, sizeof(record))) { *io_error = true; continue; }
    if (zs_lora_rf_profile_decode(record, running_firmware, verify, verify_ctx, &candidate) == ZS_LORA_RF_PROFILE_OK &&
        (best < 0 || (int32_t)(candidate.version - out->version) > 0)) {
      *out = candidate;
      best = slot;
    }
  }
  memset(record, 0, sizeof(record));
  return best;
}

zs_lora_rf_profile_result_t zs_lora_rf_profile_load(
    const zs_lora_rf_profile_io_t *io, uint32_t running_firmware,
    zs_lora_rf_profile_verify_fn verify, void *verify_ctx, zs_lora_rf_profile_t *out) {
  bool io_error;
  if (out) memset(out, 0, sizeof(*out));
  if (!io || !io->read || !verify || !out) return ZS_LORA_RF_PROFILE_IO_ERROR;
  if (newest(io, running_firmware, verify, verify_ctx, out, &io_error) < 0)
    return io_error ? ZS_LORA_RF_PROFILE_IO_ERROR : ZS_LORA_RF_PROFILE_NOT_FOUND;
  return ZS_LORA_RF_PROFILE_OK;
}

zs_lora_rf_profile_result_t zs_lora_rf_profile_commit(
    const zs_lora_rf_profile_io_t *io, const uint8_t record[ZS_LORA_RF_PROFILE_RECORD_BYTES],
    uint32_t running_firmware, zs_lora_rf_profile_verify_fn verify, void *verify_ctx,
    zs_lora_rf_profile_t *out) {
  uint8_t back[ZS_LORA_RF_PROFILE_RECORD_BYTES];
  zs_lora_rf_profile_t incoming, current;
  bool io_error;
  int active;
  uint8_t target;
  zs_lora_rf_profile_result_t decoded;
  if (out) memset(out, 0, sizeof(*out));
  if (!io || !io->read || !io->erase || !io->write || !record || !verify || !out)
    return ZS_LORA_RF_PROFILE_IO_ERROR;
  decoded = zs_lora_rf_profile_decode(record, running_firmware, verify, verify_ctx, &incoming);
  if (decoded != ZS_LORA_RF_PROFILE_OK) return decoded;
  active = newest(io, running_firmware, verify, verify_ctx, &current, &io_error);
  if (active >= 0 && incoming.version <= current.version) return ZS_LORA_RF_PROFILE_ROLLBACK;
  target = active == 0 ? 1u : 0u;
  if (!io->erase(io->ctx, target) || !io->write(io->ctx, target, 0u, record, ZS_LORA_RF_PROFILE_RECORD_BYTES))
    return ZS_LORA_RF_PROFILE_IO_ERROR;
  if (!io->read(io->ctx, target, 0u, back, sizeof(back)) || memcmp(record, back, sizeof(back)) != 0) {
    memset(back, 0, sizeof(back));
    return ZS_LORA_RF_PROFILE_VERIFY_FAILED;
  }
  memset(back, 0, sizeof(back));
  *out = incoming;
  return ZS_LORA_RF_PROFILE_OK;
}

const char *zs_lora_rf_profile_result_name(zs_lora_rf_profile_result_t result) {
  switch (result) {
    case ZS_LORA_RF_PROFILE_OK: return "ok";
    case ZS_LORA_RF_PROFILE_NOT_FOUND: return "not found";
    case ZS_LORA_RF_PROFILE_INVALID: return "invalid or unsigned";
    case ZS_LORA_RF_PROFILE_ROLLBACK: return "version rollback";
    case ZS_LORA_RF_PROFILE_IO_ERROR: return "storage error";
    case ZS_LORA_RF_PROFILE_VERIFY_FAILED: return "read-back failed";
    default: return "unknown";
  }
}

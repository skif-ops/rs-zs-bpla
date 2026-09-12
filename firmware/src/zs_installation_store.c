#include "zs_installation_store.h"

#include <string.h>

#define RECORD_MAGIC UINT32_C(0x3150535a) /* ZSP1 */
#define RECORD_COMMIT UINT32_C(0x54494d43) /* CMIT */
#define RECORD_FORMAT UINT16_C(1)
#define RECORD_PAYLOAD_BYTES UINT16_C(74)
#define RECORD_CRC_OFFSET 82u
#define RECORD_COMMIT_OFFSET 86u

static uint16_t get_u16(const uint8_t *p) {
  return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t get_u32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t get_u64(const uint8_t *p) {
  uint64_t value = 0u;
  for (unsigned i = 0u; i < 8u; i++) value |= (uint64_t)p[i] << (8u * i);
  return value;
}

static void put_u16(uint8_t *p, uint16_t value) {
  p[0] = (uint8_t)value;
  p[1] = (uint8_t)(value >> 8);
}

static void put_u32(uint8_t *p, uint32_t value) {
  for (unsigned i = 0u; i < 4u; i++) p[i] = (uint8_t)(value >> (8u * i));
}

static void put_u64(uint8_t *p, uint64_t value) {
  for (unsigned i = 0u; i < 8u; i++) p[i] = (uint8_t)(value >> (8u * i));
}

static uint32_t crc32(const uint8_t *data, size_t size) {
  uint32_t crc = UINT32_MAX;
  for (size_t i = 0u; i < size; i++) {
    crc ^= data[i];
    for (unsigned bit = 0u; bit < 8u; bit++) {
      crc = (crc >> 1) ^ (UINT32_C(0xedb88320) & (uint32_t)-(int32_t)(crc & 1u));
    }
  }
  return ~crc;
}

static bool hash_present(const uint8_t hash[ZS_INSTALLATION_HASH_BYTES]) {
  uint8_t combined = 0u;
  for (size_t i = 0u; i < ZS_INSTALLATION_HASH_BYTES; i++) combined |= hash[i];
  return combined != 0u;
}

static bool record_valid(const zs_installation_record_t *record) {
  const zs_position_trust_config_t *trust;
  if (record == NULL) return false;
  trust = &record->trust;
  return trust->configured && trust->locked &&
         trust->installation.lat_e7 >= -900000000 && trust->installation.lat_e7 <= 900000000 &&
         trust->installation.lon_e7 >= -1800000000 && trust->installation.lon_e7 <= 1800000000 &&
         trust->installation.alt_dm >= -50000 && trust->installation.alt_dm <= 100000 &&
         trust->installation.pos_accuracy_m >= 1u && trust->installation.pos_accuracy_m <= 1000u &&
         trust->installation.altitude_source <= 2u &&
         trust->installation.position_source == ZS_POSITION_SOURCE_CONFIGURED_INSTALL &&
         record->source <= 3u && record->version > 0u && record->commissioned_time_us > 0u &&
         trust->warning_distance_m >= 5u && trust->warning_distance_m <= 500u &&
         trust->suspect_distance_m > trust->warning_distance_m && trust->suspect_distance_m <= 2000u &&
         trust->gross_jump_distance_m > trust->suspect_distance_m && trust->gross_jump_distance_m <= 5000u &&
         trust->warning_consecutive_fixes >= 1u && trust->warning_consecutive_fixes <= 60u &&
         trust->suspect_consecutive_fixes >= trust->warning_consecutive_fixes &&
         trust->suspect_consecutive_fixes <= 120u && hash_present(record->commissioning_hash);
}

static void encode_record(
    const zs_installation_record_t *record,
    uint32_t generation,
    uint8_t bytes[ZS_INSTALLATION_STORE_SLOT_BYTES]) {
  memset(bytes, 0xff, ZS_INSTALLATION_STORE_SLOT_BYTES);
  put_u32(&bytes[0], RECORD_MAGIC);
  put_u16(&bytes[4], RECORD_FORMAT);
  put_u16(&bytes[6], RECORD_PAYLOAD_BYTES);
  put_u32(&bytes[8], generation);
  put_u32(&bytes[12], record->version);
  put_u32(&bytes[16], (uint32_t)record->trust.installation.lat_e7);
  put_u32(&bytes[20], (uint32_t)record->trust.installation.lon_e7);
  put_u32(&bytes[24], (uint32_t)record->trust.installation.alt_dm);
  put_u16(&bytes[28], record->trust.installation.pos_accuracy_m);
  bytes[30] = record->trust.installation.altitude_source;
  bytes[31] = record->trust.installation.position_source;
  bytes[32] = record->source;
  bytes[33] = record->trust.locked ? 1u : 0u;
  put_u16(&bytes[34], record->trust.warning_distance_m);
  put_u16(&bytes[36], record->trust.suspect_distance_m);
  put_u16(&bytes[38], record->trust.gross_jump_distance_m);
  bytes[40] = record->trust.warning_consecutive_fixes;
  bytes[41] = record->trust.suspect_consecutive_fixes;
  put_u64(&bytes[42], record->commissioned_time_us);
  memcpy(&bytes[50], record->commissioning_hash, ZS_INSTALLATION_HASH_BYTES);
  put_u32(&bytes[RECORD_CRC_OFFSET], crc32(bytes, RECORD_CRC_OFFSET));
  put_u32(&bytes[RECORD_COMMIT_OFFSET], RECORD_COMMIT);
}

static bool decode_record(
    const uint8_t bytes[ZS_INSTALLATION_STORE_SLOT_BYTES],
    zs_installation_record_t *record) {
  if (get_u32(&bytes[0]) != RECORD_MAGIC || get_u16(&bytes[4]) != RECORD_FORMAT ||
      get_u16(&bytes[6]) != RECORD_PAYLOAD_BYTES ||
      get_u32(&bytes[RECORD_COMMIT_OFFSET]) != RECORD_COMMIT ||
      get_u32(&bytes[RECORD_CRC_OFFSET]) != crc32(bytes, RECORD_CRC_OFFSET)) {
    return false;
  }
  memset(record, 0, sizeof(*record));
  record->storage_generation = get_u32(&bytes[8]);
  record->version = get_u32(&bytes[12]);
  record->trust.configured = true;
  record->trust.locked = bytes[33] == 1u;
  record->trust.installation.lat_e7 = (int32_t)get_u32(&bytes[16]);
  record->trust.installation.lon_e7 = (int32_t)get_u32(&bytes[20]);
  record->trust.installation.alt_dm = (int32_t)get_u32(&bytes[24]);
  record->trust.installation.pos_accuracy_m = get_u16(&bytes[28]);
  record->trust.installation.altitude_source = bytes[30];
  record->trust.installation.position_source = bytes[31];
  record->source = bytes[32];
  record->trust.warning_distance_m = get_u16(&bytes[34]);
  record->trust.suspect_distance_m = get_u16(&bytes[36]);
  record->trust.gross_jump_distance_m = get_u16(&bytes[38]);
  record->trust.warning_consecutive_fixes = bytes[40];
  record->trust.suspect_consecutive_fixes = bytes[41];
  record->commissioned_time_us = get_u64(&bytes[42]);
  memcpy(record->commissioning_hash, &bytes[50], ZS_INSTALLATION_HASH_BYTES);
  return record_valid(record) && record->storage_generation > 0u;
}

static bool generation_newer(uint32_t candidate, uint32_t reference) {
  return candidate != reference && (uint32_t)(candidate - reference) < UINT32_C(0x80000000);
}

zs_installation_store_result_t zs_installation_store_load(
    const zs_installation_store_io_t *io,
    zs_installation_record_t *record,
    uint8_t *active_slot) {
  zs_installation_record_t decoded[ZS_INSTALLATION_STORE_SLOT_COUNT];
  bool valid[ZS_INSTALLATION_STORE_SLOT_COUNT] = {false, false};
  bool read_failed = false;
  uint8_t bytes[ZS_INSTALLATION_STORE_SLOT_BYTES];

  if (io == NULL || record == NULL || io->read == NULL) return ZS_INSTALLATION_STORE_INVALID_ARGUMENT;
  for (uint8_t slot = 0u; slot < ZS_INSTALLATION_STORE_SLOT_COUNT; slot++) {
    if (!io->read(io->ctx, slot, 0u, bytes, sizeof(bytes))) {
      read_failed = true;
      continue;
    }
    valid[slot] = decode_record(bytes, &decoded[slot]);
  }
  if (!valid[0] && !valid[1]) {
    return read_failed ? ZS_INSTALLATION_STORE_IO_ERROR : ZS_INSTALLATION_STORE_NOT_FOUND;
  }
  uint8_t selected = valid[1] && (!valid[0] || generation_newer(decoded[1].storage_generation,
                                                                 decoded[0].storage_generation)) ? 1u : 0u;
  *record = decoded[selected];
  if (active_slot != NULL) *active_slot = selected;
  return ZS_INSTALLATION_STORE_OK;
}

static bool same_record(const zs_installation_record_t *a, const zs_installation_record_t *b) {
  const zs_position_trust_config_t *ta = &a->trust;
  const zs_position_trust_config_t *tb = &b->trust;
  return a->version == b->version && a->commissioned_time_us == b->commissioned_time_us &&
         a->source == b->source && ta->configured == tb->configured && ta->locked == tb->locked &&
         ta->installation.lat_e7 == tb->installation.lat_e7 &&
         ta->installation.lon_e7 == tb->installation.lon_e7 &&
         ta->installation.alt_dm == tb->installation.alt_dm &&
         ta->installation.pos_accuracy_m == tb->installation.pos_accuracy_m &&
         ta->installation.altitude_source == tb->installation.altitude_source &&
         ta->installation.position_source == tb->installation.position_source &&
         ta->warning_distance_m == tb->warning_distance_m &&
         ta->suspect_distance_m == tb->suspect_distance_m &&
         ta->gross_jump_distance_m == tb->gross_jump_distance_m &&
         ta->warning_consecutive_fixes == tb->warning_consecutive_fixes &&
         ta->suspect_consecutive_fixes == tb->suspect_consecutive_fixes &&
         memcmp(a->commissioning_hash, b->commissioning_hash, ZS_INSTALLATION_HASH_BYTES) == 0;
}

zs_installation_store_result_t zs_installation_store_commit(
    const zs_installation_store_io_t *io,
    const zs_installation_record_t *record,
    bool physical_service_mode,
    bool authenticated_role,
    bool recommission) {
  zs_installation_record_t current;
  zs_installation_record_t verified;
  uint8_t current_slot = 0u;
  uint8_t target_slot;
  uint8_t verified_slot = 0u;
  uint8_t bytes[ZS_INSTALLATION_STORE_SLOT_BYTES];
  uint32_t generation = 1u;

  if (io == NULL || record == NULL || io->read == NULL || io->erase == NULL || io->write == NULL) {
    return ZS_INSTALLATION_STORE_INVALID_ARGUMENT;
  }
  if (!physical_service_mode || !authenticated_role) return ZS_INSTALLATION_STORE_AUTH_REQUIRED;
  if (!record_valid(record)) return ZS_INSTALLATION_STORE_INVALID_RECORD;

  const zs_installation_store_result_t loaded = zs_installation_store_load(io, &current, &current_slot);
  if (loaded == ZS_INSTALLATION_STORE_OK) {
    if (!recommission) return ZS_INSTALLATION_STORE_LOCKED;
    if (record->version <= current.version) return ZS_INSTALLATION_STORE_VERSION_REJECTED;
    generation = current.storage_generation + 1u;
    if (generation == 0u) generation = 1u;
    target_slot = (uint8_t)(current_slot ^ 1u);
  } else if (loaded == ZS_INSTALLATION_STORE_NOT_FOUND) {
    if (recommission) return ZS_INSTALLATION_STORE_NOT_FOUND;
    target_slot = 0u;
  } else {
    return loaded;
  }

  encode_record(record, generation, bytes);
  if (!io->erase(io->ctx, target_slot) ||
      !io->write(io->ctx, target_slot, 0u, bytes, RECORD_COMMIT_OFFSET) ||
      !io->write(io->ctx, target_slot, RECORD_COMMIT_OFFSET,
                 &bytes[RECORD_COMMIT_OFFSET], sizeof(uint32_t))) {
    return ZS_INSTALLATION_STORE_IO_ERROR;
  }
  if (zs_installation_store_load(io, &verified, &verified_slot) != ZS_INSTALLATION_STORE_OK ||
      verified_slot != target_slot || verified.storage_generation != generation ||
      !same_record(record, &verified)) {
    return ZS_INSTALLATION_STORE_VERIFY_FAILED;
  }
  return ZS_INSTALLATION_STORE_OK;
}

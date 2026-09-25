#include "zs_command_journal.h"

#include "zs_sha256.h"

#include <string.h>

#define JOURNAL_MAGIC UINT32_C(0x4a43535a) /* ZSCJ */
#define JOURNAL_FORMAT UINT16_C(1)
#define JOURNAL_CRC_OFFSET 76u
#define JOURNAL_COMMIT_OFFSET 80u
#define JOURNAL_COMMIT UINT32_C(0x54494d43) /* CMIT */
#define FINGERPRINT_INPUT_BYTES 64u

typedef struct {
  bool match_found;
  zs_command_journal_record_t match;
  bool target_found;
  uint16_t target_slot;
  bool generation_found;
  uint32_t newest_generation;
} journal_scan_t;

static uint16_t get_u16(const uint8_t *p) {
  return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t get_u32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t get_u64(const uint8_t *p) {
  uint64_t value = 0u;
  for (unsigned i = 0u; i < 8u; ++i) value |= (uint64_t)p[i] << (8u * i);
  return value;
}

static void put_u16(uint8_t *p, uint16_t value) {
  p[0] = (uint8_t)value;
  p[1] = (uint8_t)(value >> 8);
}

static void put_u32(uint8_t *p, uint32_t value) {
  for (unsigned i = 0u; i < 4u; ++i) p[i] = (uint8_t)(value >> (8u * i));
}

static void put_u64(uint8_t *p, uint64_t value) {
  for (unsigned i = 0u; i < 8u; ++i) p[i] = (uint8_t)(value >> (8u * i));
}

static void put_be32(uint8_t *p, uint32_t value) {
  p[0] = (uint8_t)(value >> 24);
  p[1] = (uint8_t)(value >> 16);
  p[2] = (uint8_t)(value >> 8);
  p[3] = (uint8_t)value;
}

static void put_be64(uint8_t *p, uint64_t value) {
  for (unsigned i = 0u; i < 8u; ++i) p[7u - i] = (uint8_t)(value >> (8u * i));
}

static uint32_t crc32(const uint8_t *data, size_t size) {
  uint32_t crc = UINT32_MAX;
  for (size_t i = 0u; i < size; ++i) {
    crc ^= data[i];
    for (unsigned bit = 0u; bit < 8u; ++bit) {
      crc = (crc >> 1) ^
            (UINT32_C(0xedb88320) & (uint32_t)-(int32_t)(crc & 1u));
    }
  }
  return ~crc;
}

static bool generation_newer(uint32_t candidate, uint32_t reference) {
  return candidate != reference &&
         (uint32_t)(candidate - reference) < UINT32_C(0x80000000);
}

static bool all_value(const uint8_t *data, size_t size, uint8_t value) {
  for (size_t i = 0u; i < size; ++i) {
    if (data[i] != value) return false;
  }
  return true;
}

static bool params_valid(const zs_set_params_command_t *p) {
  if (p->count > ZS_COMMAND_PARAMS_MAX || (p->count == 0u && !p->reset_to_defaults)) return false;
  for (uint8_t i = 0u; i < p->count; ++i)
    if (p->id[i] == 0u || (i > 0u && p->id[i] <= p->id[i - 1u])) return false;
  return true;
}

static bool command_valid(const zs_command_t *command, uint64_t now_us) {
  if (!command || command->station_id == 0u ||
      command->created_time_us >= command->expires_time_us ||
      command->expires_time_us - command->created_time_us > ZS_COMMAND_MAX_TTL_US ||
      now_us < command->created_time_us || now_us >= command->expires_time_us ||
      all_value(command->command_id, ZS_COMMAND_UUID_BYTES, 0u)) return false;
  if (command->code == ZS_COMMAND_REBOOT) return command->reboot.delay_s <= ZS_COMMAND_REBOOT_MAX_DELAY_S;
  if (command->code == ZS_COMMAND_SET_PARAMS) return params_valid(&command->params);
  if (command->code != ZS_COMMAND_REQUEST_AUDIO || command->audio.event_id == 0u ||
      (unsigned)command->audio.segment > (unsigned)ZS_AUDIO_SEGMENT_RANGE) return false;
  if (command->audio.segment == ZS_AUDIO_SEGMENT_RANGE) {
    return command->audio.has_range && command->audio.duration_ms > 0u;
  }
  return !command->audio.has_range && command->audio.start_offset_ms == 0 &&
         command->audio.duration_ms == 0u;
}

static bool command_fingerprint(
    const zs_command_t *command,
    uint8_t output[ZS_COMMAND_JOURNAL_FINGERPRINT_BYTES]) {
  static const uint8_t domain[] = {'Z', 'S', '-', 'C', 'M', 'D', '-', 'V', '1'};
  uint8_t input[FINGERPRINT_INPUT_BYTES] = {0};
  uint8_t digest[ZS_SHA256_DIGEST_BYTES];
  _Static_assert(sizeof(domain) == 9u, "command fingerprint domain drift");
  if (!command || !output) return false;
  memcpy(input, domain, sizeof(domain));
  put_be32(&input[9], command->station_id);
  memcpy(&input[13], command->command_id, ZS_COMMAND_UUID_BYTES);
  put_be64(&input[29], command->created_time_us);
  put_be64(&input[37], command->expires_time_us);
  input[45] = (uint8_t)command->code;
  if (command->code == ZS_COMMAND_REQUEST_AUDIO) {        /* layout unchanged: journals on NOR stay valid */
    put_be64(&input[46], command->audio.event_id);
    input[54] = (uint8_t)command->audio.segment;
    put_be32(&input[55], (uint32_t)command->audio.start_offset_ms);
    put_be32(&input[59], command->audio.duration_ms);
    input[63] = command->audio.has_range ? 1u : 0u;
  } else if (command->code == ZS_COMMAND_REBOOT) {
    input[46] = (uint8_t)(command->reboot.delay_s >> 8);
    input[47] = (uint8_t)command->reboot.delay_s;
  } else {                                                /* SET_PARAMS: digest of reset flag and the id/value list */
    uint8_t list[2u + ZS_COMMAND_PARAMS_MAX * 6u];
    size_t n = 0u;
    list[n++] = command->params.reset_to_defaults ? 1u : 0u;
    list[n++] = command->params.count;
    for (uint8_t i = 0u; i < command->params.count && i < ZS_COMMAND_PARAMS_MAX; ++i) {
      list[n++] = (uint8_t)(command->params.id[i] >> 8);
      list[n++] = (uint8_t)command->params.id[i];
      put_be32(&list[n], (uint32_t)command->params.value[i]);
      n += 4u;
    }
    zs_sha256_digest(list, n, digest);
    memcpy(&input[46], digest, 18u);
  }
  zs_sha256_digest(input, sizeof(input), digest);
  memcpy(output, digest, ZS_COMMAND_JOURNAL_FINGERPRINT_BYTES);
  memset(input, 0, sizeof(input));
  memset(digest, 0, sizeof(digest));
  return true;
}

static bool record_valid(const zs_command_journal_record_t *record) {
  if (!record || record->station_id == 0u || record->storage_generation == 0u ||
      record->accepted_time_us == 0u ||
      record->retain_until_us <= record->accepted_time_us ||
      all_value(record->fingerprint, sizeof(record->fingerprint), 0u)) return false;
  if (record->state == ZS_COMMAND_JOURNAL_STATE_ACCEPTED) {
    return record->result == ZS_COMMAND_ACK_OK && record->detail_code == 0u &&
           record->completed_time_us == 0u;
  }
  return record->state == ZS_COMMAND_JOURNAL_STATE_COMPLETED &&
         record->result <= ZS_COMMAND_ACK_EXPIRED &&
         record->completed_time_us >= record->accepted_time_us;
}

static void encode_record(
    const zs_command_journal_record_t *record,
    uint8_t bytes[ZS_COMMAND_JOURNAL_SLOT_BYTES]) {
  memset(bytes, 0xff, ZS_COMMAND_JOURNAL_SLOT_BYTES);
  put_u32(&bytes[0], JOURNAL_MAGIC);
  put_u16(&bytes[4], JOURNAL_FORMAT);
  bytes[6] = (uint8_t)record->state;
  bytes[7] = (uint8_t)record->result;
  put_u32(&bytes[8], record->storage_generation);
  put_u32(&bytes[12], record->station_id);
  memcpy(&bytes[16], record->command_id, ZS_COMMAND_UUID_BYTES);
  memcpy(&bytes[32], record->fingerprint, ZS_COMMAND_JOURNAL_FINGERPRINT_BYTES);
  put_u16(&bytes[48], record->detail_code);
  put_u64(&bytes[52], record->accepted_time_us);
  put_u64(&bytes[60], record->completed_time_us);
  put_u64(&bytes[68], record->retain_until_us);
  put_u32(&bytes[JOURNAL_CRC_OFFSET], crc32(bytes, JOURNAL_CRC_OFFSET));
  put_u32(&bytes[JOURNAL_COMMIT_OFFSET], JOURNAL_COMMIT);
}

static bool decode_record(
    const uint8_t bytes[ZS_COMMAND_JOURNAL_SLOT_BYTES],
    zs_command_journal_record_t *record) {
  if (get_u32(&bytes[0]) != JOURNAL_MAGIC ||
      get_u16(&bytes[4]) != JOURNAL_FORMAT ||
      get_u32(&bytes[JOURNAL_COMMIT_OFFSET]) != JOURNAL_COMMIT ||
      get_u32(&bytes[JOURNAL_CRC_OFFSET]) != crc32(bytes, JOURNAL_CRC_OFFSET))
    return false;
  memset(record, 0, sizeof(*record));
  record->state = (zs_command_journal_state_t)bytes[6];
  record->result = (zs_command_ack_result_t)bytes[7];
  record->storage_generation = get_u32(&bytes[8]);
  record->station_id = get_u32(&bytes[12]);
  memcpy(record->command_id, &bytes[16], ZS_COMMAND_UUID_BYTES);
  memcpy(record->fingerprint, &bytes[32], ZS_COMMAND_JOURNAL_FINGERPRINT_BYTES);
  record->detail_code = get_u16(&bytes[48]);
  record->accepted_time_us = get_u64(&bytes[52]);
  record->completed_time_us = get_u64(&bytes[60]);
  record->retain_until_us = get_u64(&bytes[68]);
  return record_valid(record);
}

static bool same_record(
    const zs_command_journal_record_t *left,
    const zs_command_journal_record_t *right) {
  return left->station_id == right->station_id &&
         left->storage_generation == right->storage_generation &&
         left->state == right->state && left->result == right->result &&
         left->detail_code == right->detail_code &&
         left->accepted_time_us == right->accepted_time_us &&
         left->completed_time_us == right->completed_time_us &&
         left->retain_until_us == right->retain_until_us &&
         memcmp(left->command_id, right->command_id, ZS_COMMAND_UUID_BYTES) == 0 &&
         memcmp(left->fingerprint, right->fingerprint,
                ZS_COMMAND_JOURNAL_FINGERPRINT_BYTES) == 0;
}

static bool incomplete_record(const uint8_t *bytes) {
  return get_u32(&bytes[JOURNAL_COMMIT_OFFSET]) == UINT32_MAX;
}

static zs_command_journal_result_t scan_journal(
    const zs_command_journal_io_t *io,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    uint64_t reclaim_time_us,
    journal_scan_t *scan) {
  uint8_t bytes[ZS_COMMAND_JOURNAL_SLOT_BYTES];
  zs_command_journal_record_t record;
  bool reclaim_found = false;
  uint16_t reclaim_slot = 0u;
  uint32_t reclaim_generation = 0u;
  if (!io || io->slot_count < 2u || !io->read || !scan) {
    return ZS_COMMAND_JOURNAL_INVALID_ARGUMENT;
  }
  memset(scan, 0, sizeof(*scan));
  for (uint16_t slot = 0u; slot < io->slot_count; ++slot) {
    if (!io->read(io->ctx, slot, 0u, bytes, sizeof(bytes)))
      return ZS_COMMAND_JOURNAL_IO_ERROR;
    if (all_value(bytes, sizeof(bytes), 0xffu) || incomplete_record(bytes)) {
      if (!scan->target_found) {
        scan->target_found = true;
        scan->target_slot = slot;
      }
      continue;
    }
    if (!decode_record(bytes, &record)) return ZS_COMMAND_JOURNAL_CORRUPT;
    if (!scan->generation_found ||
        generation_newer(record.storage_generation, scan->newest_generation)) {
      scan->generation_found = true;
      scan->newest_generation = record.storage_generation;
    }
    const bool matches = command_id &&
        memcmp(record.command_id, command_id, ZS_COMMAND_UUID_BYTES) == 0;
    if (matches && (!scan->match_found ||
        generation_newer(record.storage_generation,
                         scan->match.storage_generation))) {
      scan->match_found = true;
      scan->match = record;
    }
    if (!matches && reclaim_time_us > record.retain_until_us &&
        (!reclaim_found || generation_newer(reclaim_generation,
                                             record.storage_generation))) {
      reclaim_found = true;
      reclaim_slot = slot;
      reclaim_generation = record.storage_generation;
    }
  }
  if (!scan->target_found && reclaim_found) {
    scan->target_found = true;
    scan->target_slot = reclaim_slot;
  }
  return ZS_COMMAND_JOURNAL_OK;
}

static zs_command_journal_result_t append_record(
    const zs_command_journal_io_t *io,
    uint16_t slot,
    const zs_command_journal_record_t *record) {
  uint8_t bytes[ZS_COMMAND_JOURNAL_SLOT_BYTES];
  uint8_t verified_bytes[ZS_COMMAND_JOURNAL_SLOT_BYTES];
  zs_command_journal_record_t verified;
  if (!io || slot >= io->slot_count || !io->read || !io->erase || !io->write ||
      !record) return ZS_COMMAND_JOURNAL_INVALID_ARGUMENT;
  encode_record(record, bytes);
  if (!io->erase(io->ctx, slot) ||
      !io->write(io->ctx, slot, 0u, bytes, JOURNAL_COMMIT_OFFSET) ||
      !io->write(io->ctx, slot, JOURNAL_COMMIT_OFFSET,
                 &bytes[JOURNAL_COMMIT_OFFSET], sizeof(uint32_t)))
    return ZS_COMMAND_JOURNAL_IO_ERROR;
  if (!io->read(io->ctx, slot, 0u, verified_bytes, sizeof(verified_bytes)) ||
      !decode_record(verified_bytes, &verified) || !same_record(record, &verified))
    return ZS_COMMAND_JOURNAL_VERIFY_FAILED;
  return ZS_COMMAND_JOURNAL_OK;
}

zs_command_journal_result_t zs_command_journal_load(
    const zs_command_journal_io_t *io,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    zs_command_journal_record_t *record) {
  journal_scan_t scan;
  if (!command_id || !record) return ZS_COMMAND_JOURNAL_INVALID_ARGUMENT;
  memset(record, 0, sizeof(*record));
  const zs_command_journal_result_t result =
      scan_journal(io, command_id, 0u, &scan);
  if (result != ZS_COMMAND_JOURNAL_OK) return result;
  if (!scan.match_found) return ZS_COMMAND_JOURNAL_NOT_FOUND;
  *record = scan.match;
  return ZS_COMMAND_JOURNAL_OK;
}

zs_command_dedup_state_t zs_command_journal_dedup_lookup(
    void *ctx, const uint8_t command_id[ZS_COMMAND_UUID_BYTES]) {
  zs_command_journal_record_t record;
  const zs_command_journal_result_t result = zs_command_journal_load(
      (const zs_command_journal_io_t *)ctx, command_id, &record);
  if (result == ZS_COMMAND_JOURNAL_NOT_FOUND) return ZS_COMMAND_DEDUP_NOT_SEEN;
  return result == ZS_COMMAND_JOURNAL_OK ? ZS_COMMAND_DEDUP_SEEN
                                         : ZS_COMMAND_DEDUP_ERROR;
}

zs_command_journal_result_t zs_command_journal_accept(
    const zs_command_journal_io_t *io,
    const zs_command_t *command,
    uint64_t accepted_time_us) {
  journal_scan_t scan;
  zs_command_journal_record_t record;
  uint8_t fingerprint[ZS_COMMAND_JOURNAL_FINGERPRINT_BYTES];
  if (!io || !io->read || !io->erase || !io->write)
    return ZS_COMMAND_JOURNAL_INVALID_ARGUMENT;
  if (!command_valid(command, accepted_time_us) ||
      !command_fingerprint(command, fingerprint))
    return ZS_COMMAND_JOURNAL_INVALID_COMMAND;
  const zs_command_journal_result_t scanned = scan_journal(
      io, command->command_id, accepted_time_us, &scan);
  if (scanned != ZS_COMMAND_JOURNAL_OK) return scanned;
  if (scan.match_found) {
    if (scan.match.station_id != command->station_id ||
        memcmp(scan.match.fingerprint, fingerprint, sizeof(fingerprint)) != 0)
      return ZS_COMMAND_JOURNAL_CONFLICT;
    return scan.match.state == ZS_COMMAND_JOURNAL_STATE_COMPLETED
               ? ZS_COMMAND_JOURNAL_ALREADY_COMPLETED
               : ZS_COMMAND_JOURNAL_ALREADY_ACCEPTED;
  }
  if (!scan.target_found) return ZS_COMMAND_JOURNAL_FULL;
  memset(&record, 0, sizeof(record));
  memcpy(record.command_id, command->command_id, ZS_COMMAND_UUID_BYTES);
  memcpy(record.fingerprint, fingerprint, sizeof(fingerprint));
  record.station_id = command->station_id;
  record.storage_generation = scan.generation_found
                                  ? scan.newest_generation + 1u
                                  : 1u;
  if (record.storage_generation == 0u) record.storage_generation = 1u;
  record.state = ZS_COMMAND_JOURNAL_STATE_ACCEPTED;
  record.result = ZS_COMMAND_ACK_OK;
  record.accepted_time_us = accepted_time_us;
  record.retain_until_us = command->expires_time_us;
  return append_record(io, scan.target_slot, &record);
}

zs_command_journal_result_t zs_command_journal_complete(
    const zs_command_journal_io_t *io,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    zs_command_ack_result_t result,
    uint16_t detail_code,
    uint64_t completed_time_us) {
  journal_scan_t scan;
  zs_command_journal_record_t completed;
  if (!io || !io->read || !io->erase || !io->write || !command_id ||
      (unsigned)result > (unsigned)ZS_COMMAND_ACK_EXPIRED ||
      completed_time_us == 0u)
    return ZS_COMMAND_JOURNAL_INVALID_ARGUMENT;
  const zs_command_journal_result_t scanned = scan_journal(
      io, command_id, completed_time_us, &scan);
  if (scanned != ZS_COMMAND_JOURNAL_OK) return scanned;
  if (!scan.match_found) return ZS_COMMAND_JOURNAL_NOT_FOUND;
  if (scan.match.state == ZS_COMMAND_JOURNAL_STATE_COMPLETED)
    return ZS_COMMAND_JOURNAL_ALREADY_COMPLETED;
  if (completed_time_us < scan.match.accepted_time_us)
    return ZS_COMMAND_JOURNAL_INVALID_ARGUMENT;
  if (!scan.target_found) return ZS_COMMAND_JOURNAL_FULL;
  completed = scan.match;
  completed.storage_generation = scan.generation_found
                                     ? scan.newest_generation + 1u
                                     : 1u;
  if (completed.storage_generation == 0u) completed.storage_generation = 1u;
  completed.state = ZS_COMMAND_JOURNAL_STATE_COMPLETED;
  completed.result = result;
  completed.detail_code = detail_code;
  completed.completed_time_us = completed_time_us;
  if (completed.retain_until_us < completed_time_us)
    completed.retain_until_us = completed_time_us;
  return append_record(io, scan.target_slot, &completed);
}

size_t zs_command_journal_encode_ack(
    const zs_command_journal_io_t *io,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    uint8_t *output,
    size_t output_size) {
  zs_command_journal_record_t record;
  if (zs_command_journal_load(io, command_id, &record) != ZS_COMMAND_JOURNAL_OK ||
      record.state != ZS_COMMAND_JOURNAL_STATE_COMPLETED) return 0u;
  return zs_command_encode_ack(record.station_id, record.command_id,
                               record.result, record.completed_time_us,
                               record.detail_code, output, output_size);
}

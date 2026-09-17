#ifndef ZS_COMMAND_JOURNAL_H
#define ZS_COMMAND_JOURNAL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_command.h"

#define ZS_COMMAND_JOURNAL_SLOT_BYTES 88u
#define ZS_COMMAND_JOURNAL_FINGERPRINT_BYTES 16u

typedef enum {
  ZS_COMMAND_JOURNAL_STATE_ACCEPTED = 1,
  ZS_COMMAND_JOURNAL_STATE_COMPLETED = 2
} zs_command_journal_state_t;

typedef enum {
  ZS_COMMAND_JOURNAL_OK = 0,
  ZS_COMMAND_JOURNAL_NOT_FOUND,
  ZS_COMMAND_JOURNAL_INVALID_ARGUMENT,
  ZS_COMMAND_JOURNAL_INVALID_COMMAND,
  ZS_COMMAND_JOURNAL_IO_ERROR,
  ZS_COMMAND_JOURNAL_CORRUPT,
  ZS_COMMAND_JOURNAL_FULL,
  ZS_COMMAND_JOURNAL_ALREADY_ACCEPTED,
  ZS_COMMAND_JOURNAL_ALREADY_COMPLETED,
  ZS_COMMAND_JOURNAL_CONFLICT,
  ZS_COMMAND_JOURNAL_VERIFY_FAILED
} zs_command_journal_result_t;

typedef struct {
  void *ctx;
  uint16_t slot_count;
  bool (*read)(void *ctx, uint16_t slot, uint32_t offset,
               uint8_t *data, size_t size);
  bool (*erase)(void *ctx, uint16_t slot);
  bool (*write)(void *ctx, uint16_t slot, uint32_t offset,
                const uint8_t *data, size_t size);
} zs_command_journal_io_t;

typedef struct {
  uint8_t command_id[ZS_COMMAND_UUID_BYTES];
  uint8_t fingerprint[ZS_COMMAND_JOURNAL_FINGERPRINT_BYTES];
  uint32_t station_id;
  uint32_t storage_generation;
  zs_command_journal_state_t state;
  zs_command_ack_result_t result;
  uint16_t detail_code;
  uint64_t accepted_time_us;
  uint64_t completed_time_us;
  uint64_t retain_until_us;
} zs_command_journal_record_t;

zs_command_journal_result_t zs_command_journal_load(
    const zs_command_journal_io_t *io,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    zs_command_journal_record_t *record);

/* Adapter for zs_command_decode_verify(). ctx points to zs_command_journal_io_t. */
zs_command_dedup_state_t zs_command_journal_dedup_lookup(
    void *ctx, const uint8_t command_id[ZS_COMMAND_UUID_BYTES]);

/*
 * Call after decoder OK or DUPLICATE. Persist ACCEPTED before invoking an
 * idempotent command side effect. ALREADY_ACCEPTED means resume by command_id;
 * ALREADY_COMPLETED means reuse the stored ACK; CONFLICT means the same UUID
 * was presented with different signed semantics and must be rejected.
 */
zs_command_journal_result_t zs_command_journal_accept(
    const zs_command_journal_io_t *io,
    const zs_command_t *command,
    uint64_t accepted_time_us);

/* Persist COMPLETED before publishing an ACK. */
zs_command_journal_result_t zs_command_journal_complete(
    const zs_command_journal_io_t *io,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    zs_command_ack_result_t result,
    uint16_t detail_code,
    uint64_t completed_time_us);

/* Returns zero unless a durable COMPLETED record exists. */
size_t zs_command_journal_encode_ack(
    const zs_command_journal_io_t *io,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    uint8_t *output,
    size_t output_size);

#endif

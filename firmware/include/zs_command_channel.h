#ifndef ZS_COMMAND_CHANNEL_H
#define ZS_COMMAND_CHANNEL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_command_journal.h"
#include "zs_command_trust.h"

typedef bool (*zs_command_execute_fn)(
    void *ctx,
    const zs_command_t *command,
    zs_command_ack_result_t *result,
    uint16_t *detail_code);

typedef struct {
  uint32_t station_id;
  zs_command_trust_t *trust;
  const zs_command_journal_io_t *journal;
  zs_command_execute_fn execute;
  void *execute_ctx;
  uint8_t *verify_workspace;
  size_t verify_workspace_size;
} zs_command_channel_t;

typedef enum {
  ZS_COMMAND_CHANNEL_ACK_READY = 0,
  ZS_COMMAND_CHANNEL_REJECTED,
  ZS_COMMAND_CHANNEL_STORAGE_ERROR,
  ZS_COMMAND_CHANNEL_EXECUTION_RETRY,
  ZS_COMMAND_CHANNEL_INVALID_ARGUMENT
} zs_command_channel_result_t;

/*
 * Handles one complete MQTT down payload. ACK_READY is returned only after the
 * completed result has been read back from the durable journal. REJECTED never
 * invokes the executor. EXECUTION_RETRY leaves ACCEPTED durable and emits no ACK.
 */
zs_command_channel_result_t zs_command_channel_handle(
    const zs_command_channel_t *channel,
    const uint8_t *payload,
    size_t payload_size,
    uint64_t now_us,
    bool time_trusted,
    uint8_t *ack,
    size_t ack_capacity,
    size_t *ack_size,
    zs_command_status_t *decode_status);

#endif

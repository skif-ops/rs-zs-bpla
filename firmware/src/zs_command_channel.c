#include "zs_command_channel.h"

static zs_command_channel_result_t encode_durable_ack(
    const zs_command_channel_t *channel,
    const uint8_t command_id[ZS_COMMAND_UUID_BYTES],
    uint8_t *ack,
    size_t ack_capacity,
    size_t *ack_size) {
  *ack_size = zs_command_journal_encode_ack(channel->journal, command_id,
                                             ack, ack_capacity);
  return *ack_size > 0u ? ZS_COMMAND_CHANNEL_ACK_READY
                         : ZS_COMMAND_CHANNEL_STORAGE_ERROR;
}

zs_command_channel_result_t zs_command_channel_handle(
    const zs_command_channel_t *channel,
    const uint8_t *payload,
    size_t payload_size,
    uint64_t now_us,
    bool time_trusted,
    uint8_t *ack,
    size_t ack_capacity,
    size_t *ack_size,
    zs_command_status_t *decode_status) {
  zs_command_t command;
  zs_command_status_t decoded;
  zs_command_journal_result_t journal_result;
  zs_command_ack_result_t execution_result = ZS_COMMAND_ACK_FAILED;
  uint16_t detail_code = 0u;
  if (ack_size) *ack_size = 0u;
  if (decode_status) *decode_status = ZS_COMMAND_STATUS_INVALID_ARGUMENT;
  if (!channel || channel->station_id == 0u || !channel->trust ||
      !channel->journal || !channel->execute || !channel->verify_workspace ||
      channel->verify_workspace_size == 0u || !payload || payload_size == 0u ||
      !ack || ack_capacity < ZS_COMMAND_ACK_MAX_BYTES || !ack_size ||
      !decode_status) return ZS_COMMAND_CHANNEL_INVALID_ARGUMENT;

  decoded = zs_command_decode_verify(
      payload, payload_size, channel->station_id, now_us, time_trusted,
      zs_command_trust_verify, channel->trust, zs_command_journal_dedup_lookup,
      (void *)channel->journal, channel->verify_workspace,
      channel->verify_workspace_size, &command);
  *decode_status = decoded;
  if (decoded == ZS_COMMAND_STATUS_DEDUP_STORAGE_ERROR ||
      decoded == ZS_COMMAND_STATUS_DEDUP_REQUIRED)
    return ZS_COMMAND_CHANNEL_STORAGE_ERROR;
  if (decoded != ZS_COMMAND_STATUS_OK && decoded != ZS_COMMAND_STATUS_DUPLICATE)
    return ZS_COMMAND_CHANNEL_REJECTED;

  journal_result = zs_command_journal_accept(channel->journal, &command, now_us);
  if (journal_result == ZS_COMMAND_JOURNAL_ALREADY_COMPLETED) {
    return encode_durable_ack(channel, command.command_id, ack, ack_capacity,
                              ack_size);
  }
  if (journal_result == ZS_COMMAND_JOURNAL_CONFLICT ||
      journal_result == ZS_COMMAND_JOURNAL_INVALID_COMMAND)
    return ZS_COMMAND_CHANNEL_REJECTED;
  if (journal_result != ZS_COMMAND_JOURNAL_OK &&
      journal_result != ZS_COMMAND_JOURNAL_ALREADY_ACCEPTED)
    return ZS_COMMAND_CHANNEL_STORAGE_ERROR;

  if (!channel->execute(channel->execute_ctx, &command, &execution_result,
                        &detail_code) ||
      (unsigned)execution_result > (unsigned)ZS_COMMAND_ACK_EXPIRED)
    return ZS_COMMAND_CHANNEL_EXECUTION_RETRY;
  journal_result = zs_command_journal_complete(
      channel->journal, command.command_id, execution_result, detail_code, now_us);
  if (journal_result != ZS_COMMAND_JOURNAL_OK &&
      journal_result != ZS_COMMAND_JOURNAL_ALREADY_COMPLETED)
    return ZS_COMMAND_CHANNEL_STORAGE_ERROR;
  return encode_durable_ack(channel, command.command_id, ack, ack_capacity,
                            ack_size);
}

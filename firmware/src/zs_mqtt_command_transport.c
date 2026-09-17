#include "zs_mqtt_command_transport.h"

#include <string.h>

static bool is_ascii_alnum(uint8_t value) {
  return (value >= (uint8_t)'A' && value <= (uint8_t)'Z') ||
         (value >= (uint8_t)'a' && value <= (uint8_t)'z') ||
         (value >= (uint8_t)'0' && value <= (uint8_t)'9');
}

static bool tenant_is_valid(const uint8_t *tenant, size_t tenant_size) {
  if (!tenant || tenant_size == 0u ||
      tenant_size > ZS_MQTT_COMMAND_TENANT_MAX_BYTES ||
      !is_ascii_alnum(tenant[0]))
    return false;
  for (size_t i = 1u; i < tenant_size; ++i) {
    if (!is_ascii_alnum(tenant[i]) && tenant[i] != (uint8_t)'_' &&
        tenant[i] != (uint8_t)'-')
      return false;
  }
  return true;
}

static size_t write_station_id(uint32_t station_id, uint8_t *output) {
  uint8_t reverse[10];
  size_t size = 0u;
  do {
    reverse[size++] = (uint8_t)('0' + station_id % 10u);
    station_id /= 10u;
  } while (station_id != 0u);
  for (size_t i = 0u; i < size; ++i) output[i] = reverse[size - i - 1u];
  return size;
}

static bool build_topic(uint8_t *topic, size_t *topic_size,
                        const uint8_t *tenant, size_t tenant_size,
                        uint32_t station_id, const char *kind,
                        size_t kind_size) {
  static const uint8_t prefix[] = {'z', 's', '/', 'v', '1', '/'};
  size_t offset = 0u;
  if (sizeof(prefix) + tenant_size + 1u + 10u + 1u + kind_size >
      ZS_MQTT_COMMAND_TOPIC_MAX_BYTES)
    return false;
  memcpy(&topic[offset], prefix, sizeof(prefix));
  offset += sizeof(prefix);
  memcpy(&topic[offset], tenant, tenant_size);
  offset += tenant_size;
  topic[offset++] = (uint8_t)'/';
  offset += write_station_id(station_id, &topic[offset]);
  topic[offset++] = (uint8_t)'/';
  memcpy(&topic[offset], kind, kind_size);
  offset += kind_size;
  *topic_size = offset;
  return true;
}

bool zs_mqtt_command_transport_init(
    zs_mqtt_command_transport_t *transport,
    const zs_command_channel_t *channel,
    const uint8_t *tenant,
    size_t tenant_size) {
  if (!transport) return false;
  memset(transport, 0, sizeof(*transport));
  if (!channel || channel->station_id == 0u ||
      !tenant_is_valid(tenant, tenant_size))
    return false;
  if (!build_topic(transport->down_topic, &transport->down_topic_size, tenant,
                   tenant_size, channel->station_id, "down", 4u) ||
      !build_topic(transport->ack_topic, &transport->ack_topic_size, tenant,
                   tenant_size, channel->station_id, "ack", 3u)) {
    memset(transport, 0, sizeof(*transport));
    return false;
  }
  transport->channel = channel;
  return true;
}

static void clear_publication(zs_mqtt_command_message_t *publication) {
  if (publication) memset(publication, 0, sizeof(*publication));
}

zs_mqtt_command_transport_result_t zs_mqtt_command_transport_handle(
    const zs_mqtt_command_transport_t *transport,
    const zs_mqtt_command_message_t *message,
    uint64_t now_us,
    bool time_trusted,
    uint8_t *ack_buffer,
    size_t ack_capacity,
    zs_mqtt_command_message_t *publication,
    zs_command_status_t *decode_status) {
  zs_command_channel_result_t channel_result;
  size_t ack_size = 0u;
  clear_publication(publication);
  if (decode_status) *decode_status = ZS_COMMAND_STATUS_INVALID_ARGUMENT;
  if (!transport || !transport->channel || transport->down_topic_size == 0u ||
      transport->down_topic_size > sizeof(transport->down_topic) ||
      transport->ack_topic_size == 0u ||
      transport->ack_topic_size > sizeof(transport->ack_topic) || !message ||
      !message->topic ||
      message->topic_size == 0u || !message->payload ||
      message->payload_size == 0u || !ack_buffer ||
      ack_capacity < ZS_COMMAND_ACK_MAX_BYTES || !publication ||
      !decode_status)
    return ZS_MQTT_COMMAND_INVALID_ARGUMENT;
  if (message->topic_size != transport->down_topic_size ||
      memcmp(message->topic, transport->down_topic,
             transport->down_topic_size) != 0)
    return ZS_MQTT_COMMAND_REJECTED_TOPIC;
  if (message->qos != ZS_MQTT_COMMAND_QOS || message->retained)
    return ZS_MQTT_COMMAND_REJECTED_DELIVERY;

  channel_result = zs_command_channel_handle(
      transport->channel, message->payload, message->payload_size, now_us,
      time_trusted, ack_buffer, ack_capacity, &ack_size, decode_status);
  switch (channel_result) {
    case ZS_COMMAND_CHANNEL_ACK_READY:
      publication->topic = transport->ack_topic;
      publication->topic_size = transport->ack_topic_size;
      publication->payload = ack_buffer;
      publication->payload_size = ack_size;
      publication->qos = ZS_MQTT_COMMAND_QOS;
      publication->retained = false;
      return ZS_MQTT_COMMAND_ACK_READY;
    case ZS_COMMAND_CHANNEL_REJECTED:
      return ZS_MQTT_COMMAND_REJECTED_COMMAND;
    case ZS_COMMAND_CHANNEL_STORAGE_ERROR:
      return ZS_MQTT_COMMAND_STORAGE_ERROR;
    case ZS_COMMAND_CHANNEL_EXECUTION_RETRY:
      return ZS_MQTT_COMMAND_EXECUTION_RETRY;
    case ZS_COMMAND_CHANNEL_INVALID_ARGUMENT:
    default:
      return ZS_MQTT_COMMAND_INVALID_ARGUMENT;
  }
}

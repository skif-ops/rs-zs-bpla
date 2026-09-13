#include "zs_mqtt_event_transport.h"

#include <string.h>

static bool is_ascii_alnum(uint8_t value) {
  return (value >= (uint8_t)'A' && value <= (uint8_t)'Z') ||
         (value >= (uint8_t)'a' && value <= (uint8_t)'z') ||
         (value >= (uint8_t)'0' && value <= (uint8_t)'9');
}

static bool tenant_is_valid(const uint8_t *tenant, size_t tenant_size) {
  if (!tenant || tenant_size == 0u ||
      tenant_size > ZS_MQTT_EVENT_TENANT_MAX_BYTES ||
      !is_ascii_alnum(tenant[0]))
    return false;
  for (size_t i = 1u; i < tenant_size; ++i) {
    if (!is_ascii_alnum(tenant[i]) && tenant[i] != (uint8_t)'_' &&
        tenant[i] != (uint8_t)'-')
      return false;
  }
  return true;
}

static bool outbox_is_valid(const zs_event_outbox_io_t *outbox) {
  return outbox && outbox->slot_count > 0u && outbox->read && outbox->erase &&
         outbox->write;
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

static bool build_up_topic(uint8_t *topic, size_t *topic_size,
                           const uint8_t *tenant, size_t tenant_size,
                           uint32_t station_id) {
  static const uint8_t prefix[] = {'z', 's', '/', 'v', '1', '/'};
  static const uint8_t suffix[] = {'/', 'u', 'p'};
  size_t offset = 0u;
  if (sizeof(prefix) + tenant_size + 1u + 10u + sizeof(suffix) >
      ZS_MQTT_EVENT_TOPIC_MAX_BYTES)
    return false;
  memcpy(&topic[offset], prefix, sizeof(prefix));
  offset += sizeof(prefix);
  memcpy(&topic[offset], tenant, tenant_size);
  offset += tenant_size;
  topic[offset++] = (uint8_t)'/';
  offset += write_station_id(station_id, &topic[offset]);
  memcpy(&topic[offset], suffix, sizeof(suffix));
  offset += sizeof(suffix);
  *topic_size = offset;
  return true;
}

bool zs_mqtt_event_transport_init(
    zs_mqtt_event_transport_t *transport,
    const zs_event_outbox_io_t *outbox,
    uint32_t station_id,
    const uint8_t *tenant,
    size_t tenant_size) {
  if (!transport) return false;
  memset(transport, 0, sizeof(*transport));
  if (!outbox_is_valid(outbox) || station_id == 0u ||
      !tenant_is_valid(tenant, tenant_size) ||
      !build_up_topic(transport->up_topic, &transport->up_topic_size,
                      tenant, tenant_size, station_id) ||
      !zs_event_receipt_transport_init(&transport->receipt, station_id, tenant,
                                       tenant_size)) {
    memset(transport, 0, sizeof(*transport));
    return false;
  }
  transport->outbox = outbox;
  transport->station_id = station_id;
  return true;
}

static void clear_message(zs_mqtt_event_message_t *message) {
  if (message) memset(message, 0, sizeof(*message));
}

zs_mqtt_event_prepare_result_t zs_mqtt_event_transport_prepare(
    zs_mqtt_event_transport_t *transport,
    zs_mqtt_event_message_t *publication) {
  zs_event_outbox_result_t result;
  clear_message(publication);
  if (!transport || !outbox_is_valid(transport->outbox) ||
      transport->station_id == 0u || transport->up_topic_size == 0u ||
      transport->up_topic_size > sizeof(transport->up_topic) || !publication)
    return ZS_MQTT_EVENT_INVALID_ARGUMENT;

  memset(&transport->publication_item, 0,
         sizeof(transport->publication_item));
  result = zs_event_outbox_peek(transport->outbox,
                                &transport->publication_item);
  if (result == ZS_EVENT_OUTBOX_EMPTY) return ZS_MQTT_EVENT_EMPTY;
  if (result == ZS_EVENT_OUTBOX_INVALID_ARGUMENT)
    return ZS_MQTT_EVENT_INVALID_ARGUMENT;
  if (result != ZS_EVENT_OUTBOX_OK) return ZS_MQTT_EVENT_STORAGE_ERROR;
  if (transport->publication_item.station_id != transport->station_id)
    return ZS_MQTT_EVENT_STATION_MISMATCH;

  result = zs_event_outbox_note_attempt(transport->outbox,
                                        &transport->publication_item);
  if (result == ZS_EVENT_OUTBOX_RETRY_EXHAUSTED)
    return ZS_MQTT_EVENT_RETRY_EXHAUSTED;
  if (result == ZS_EVENT_OUTBOX_INVALID_ARGUMENT)
    return ZS_MQTT_EVENT_INVALID_ARGUMENT;
  if (result != ZS_EVENT_OUTBOX_OK) return ZS_MQTT_EVENT_STORAGE_ERROR;

  publication->topic = transport->up_topic;
  publication->topic_size = transport->up_topic_size;
  publication->payload = transport->publication_item.payload;
  publication->payload_size = transport->publication_item.payload_size;
  publication->qos = ZS_MQTT_EVENT_QOS;
  publication->retained = false;
  return ZS_MQTT_EVENT_PUBLICATION_READY;
}

zs_event_receipt_result_t zs_mqtt_event_transport_handle_receipt(
    zs_mqtt_event_transport_t *transport,
    const zs_mqtt_event_message_t *message,
    zs_event_receipt_status_t *decode_status) {
  zs_event_receipt_result_t result;
  if (decode_status) *decode_status = ZS_EVENT_RECEIPT_STATUS_INVALID_ARGUMENT;
  if (!transport || !outbox_is_valid(transport->outbox) ||
      transport->station_id == 0u || !message || !message->topic ||
      message->topic_size == 0u || !message->payload ||
      message->payload_size == 0u || !decode_status)
    return ZS_EVENT_RECEIPT_INVALID_ARGUMENT;
  result = zs_event_receipt_transport_handle(
      &transport->receipt, transport->outbox, message->topic,
      message->topic_size, message->payload, message->payload_size,
      message->qos, message->retained, decode_status);
  if (result == ZS_EVENT_RECEIPT_APPLIED ||
      result == ZS_EVENT_RECEIPT_ALREADY_APPLIED)
    memset(&transport->publication_item, 0,
           sizeof(transport->publication_item));
  return result;
}

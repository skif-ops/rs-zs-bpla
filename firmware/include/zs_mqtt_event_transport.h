#ifndef ZS_MQTT_EVENT_TRANSPORT_H
#define ZS_MQTT_EVENT_TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_event_receipt.h"

#define ZS_MQTT_EVENT_TENANT_MAX_BYTES 32u
#define ZS_MQTT_EVENT_TOPIC_MAX_BYTES 64u
#define ZS_MQTT_EVENT_QOS 1u

typedef struct {
  const uint8_t *topic;
  size_t topic_size;
  const uint8_t *payload;
  size_t payload_size;
  uint8_t qos;
  bool retained;
} zs_mqtt_event_message_t;

typedef struct {
  const zs_event_outbox_io_t *outbox;
  uint32_t station_id;
  uint8_t up_topic[ZS_MQTT_EVENT_TOPIC_MAX_BYTES];
  size_t up_topic_size;
  zs_event_receipt_transport_t receipt;
  zs_event_outbox_item_t publication_item;
} zs_mqtt_event_transport_t;

typedef enum {
  ZS_MQTT_EVENT_PUBLICATION_READY = 0,
  ZS_MQTT_EVENT_EMPTY,
  ZS_MQTT_EVENT_RETRY_EXHAUSTED,
  ZS_MQTT_EVENT_STATION_MISMATCH,
  ZS_MQTT_EVENT_STORAGE_ERROR,
  ZS_MQTT_EVENT_INVALID_ARGUMENT
} zs_mqtt_event_prepare_result_t;

/* Build exact station `up` and `receipt` topics from bounded binary tenant bytes. */
bool zs_mqtt_event_transport_init(
    zs_mqtt_event_transport_t *transport,
    const zs_event_outbox_io_t *outbox,
    uint32_t station_id,
    const uint8_t *tenant,
    size_t tenant_size);

/*
 * Persist one retry attempt before returning the exact pending CBOR as a QoS-1,
 * non-retained publication. Each call is an explicit initial/retry attempt;
 * MQTT PUBACK does not alter outbox state. The returned view remains valid until
 * the next call that mutates `transport`.
 */
zs_mqtt_event_prepare_result_t zs_mqtt_event_transport_prepare(
    zs_mqtt_event_transport_t *transport,
    zs_mqtt_event_message_t *publication);

/* Apply a complete binary receipt publication to its matching durable slot. */
zs_event_receipt_result_t zs_mqtt_event_transport_handle_receipt(
    zs_mqtt_event_transport_t *transport,
    const zs_mqtt_event_message_t *message,
    zs_event_receipt_status_t *decode_status);

#endif

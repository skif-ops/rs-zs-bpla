#ifndef ZS_MQTT_COMMAND_TRANSPORT_H
#define ZS_MQTT_COMMAND_TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_command_channel.h"

#define ZS_MQTT_COMMAND_TENANT_MAX_BYTES 32u
#define ZS_MQTT_COMMAND_TOPIC_MAX_BYTES 64u
#define ZS_MQTT_COMMAND_QOS 1u

typedef struct {
  const uint8_t *topic;
  size_t topic_size;
  const uint8_t *payload;
  size_t payload_size;
  uint8_t qos;
  bool retained;
} zs_mqtt_command_message_t;

typedef struct {
  const zs_command_channel_t *channel;
  uint8_t down_topic[ZS_MQTT_COMMAND_TOPIC_MAX_BYTES];
  size_t down_topic_size;
  uint8_t ack_topic[ZS_MQTT_COMMAND_TOPIC_MAX_BYTES];
  size_t ack_topic_size;
} zs_mqtt_command_transport_t;

typedef enum {
  ZS_MQTT_COMMAND_ACK_READY = 0,
  ZS_MQTT_COMMAND_REJECTED_TOPIC,
  ZS_MQTT_COMMAND_REJECTED_DELIVERY,
  ZS_MQTT_COMMAND_REJECTED_COMMAND,
  ZS_MQTT_COMMAND_STORAGE_ERROR,
  ZS_MQTT_COMMAND_EXECUTION_RETRY,
  ZS_MQTT_COMMAND_INVALID_ARGUMENT
} zs_mqtt_command_transport_result_t;

/*
 * Builds canonical station topics from a bounded tenant identifier and the
 * channel station ID. Tenant bytes are not treated as a NUL-terminated string.
 */
bool zs_mqtt_command_transport_init(
    zs_mqtt_command_transport_t *transport,
    const zs_command_channel_t *channel,
    const uint8_t *tenant,
    size_t tenant_size);

/*
 * Handles one complete binary MQTT publication. The caller must preserve the
 * exact topic and payload lengths supplied by the MQTT client. Only a QoS 1,
 * non-retained publication on the exact canonical down topic reaches the
 * command channel. ACK_READY returns a QoS 1, non-retained binary ACK view;
 * all other results return an empty publication.
 */
zs_mqtt_command_transport_result_t zs_mqtt_command_transport_handle(
    const zs_mqtt_command_transport_t *transport,
    const zs_mqtt_command_message_t *message,
    uint64_t now_us,
    bool time_trusted,
    uint8_t *ack_buffer,
    size_t ack_capacity,
    zs_mqtt_command_message_t *publication,
    zs_command_status_t *decode_status);

#endif

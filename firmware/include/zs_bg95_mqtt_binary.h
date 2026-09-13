#ifndef ZS_BG95_MQTT_BINARY_H
#define ZS_BG95_MQTT_BINARY_H

#include "zs_bg95.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
  unsigned client;
  unsigned message_id;
  const uint8_t *topic;
  size_t topic_size;
  const uint8_t *payload;
  size_t payload_size;
} zs_bg95_mqtt_receive_frame_t;

typedef enum {
  ZS_BG95_MQTT_RECEIVE_FRAME_OK = 0,
  ZS_BG95_MQTT_RECEIVE_NOT_FRAME,
  ZS_BG95_MQTT_RECEIVE_MALFORMED
} zs_bg95_mqtt_receive_parse_result_t;

/* Accept HAL conventions returning either zero or the complete byte count. */
bool zs_bg95_mqtt_uart_write_all(zs_bg95_t *modem,
                                 const uint8_t *data,
                                 size_t size);

bool zs_bg95_mqtt_topic_is_at_safe(const uint8_t *topic, size_t size,
                                   size_t maximum_size);

void zs_bg95_mqtt_invalidate(zs_bg95_t *modem);

bool zs_bg95_mqtt_parse_subscribe_result(const char *line,
                                         unsigned *client,
                                         unsigned *message_id,
                                         unsigned *result,
                                         unsigned *granted_qos);

bool zs_bg95_mqtt_parse_publish_result(const char *line,
                                       unsigned *client,
                                       unsigned *message_id,
                                       unsigned *result);

/* Parse one complete quoted +QMTRECV URC using its explicit payload length. */
zs_bg95_mqtt_receive_parse_result_t zs_bg95_mqtt_parse_receive_frame(
    const uint8_t *frame,
    size_t frame_size,
    zs_bg95_mqtt_receive_frame_t *received);

#endif

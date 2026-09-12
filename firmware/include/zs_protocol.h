#ifndef ZS_PROTOCOL_H
#define ZS_PROTOCOL_H

#include "zs_types.h"
#include <stddef.h>
#include <stdint.h>

size_t zs_protocol_encode_detection(const zs_detection_t *m, uint8_t *out, size_t cap);
size_t zs_protocol_encode_detection_summary(const zs_detection_t *m, uint8_t *out, size_t cap);
size_t zs_protocol_encode_heartbeat(const zs_heartbeat_t *m, uint8_t *out, size_t cap);
uint16_t zs_float_to_f16(float f);

#endif

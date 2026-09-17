#ifndef ZS_EVENT_RECEIPT_H
#define ZS_EVENT_RECEIPT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_event_outbox.h"

#define ZS_EVENT_RECEIPT_MAX_BYTES 128u
#define ZS_EVENT_RECEIPT_TENANT_MAX_BYTES 32u
#define ZS_EVENT_RECEIPT_TOPIC_MAX_BYTES 64u
#define ZS_EVENT_RECEIPT_QOS 1u

typedef struct {
  uint32_t station_id;
  uint32_t boot_id;
  uint32_t seq_no;
  uint64_t event_id;
  uint8_t payload_sha256[ZS_SHA256_DIGEST_BYTES];
} zs_event_receipt_t;

typedef enum {
  ZS_EVENT_RECEIPT_STATUS_OK = 0,
  ZS_EVENT_RECEIPT_STATUS_INVALID_ARGUMENT,
  ZS_EVENT_RECEIPT_STATUS_INVALID_SIZE,
  ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR,
  ZS_EVENT_RECEIPT_STATUS_UNSUPPORTED_SCHEMA,
  ZS_EVENT_RECEIPT_STATUS_STATION_MISMATCH,
  ZS_EVENT_RECEIPT_STATUS_ITEM_MISMATCH,
  ZS_EVENT_RECEIPT_STATUS_SHA256_MISMATCH
} zs_event_receipt_status_t;

typedef struct {
  uint32_t station_id;
  uint8_t topic[ZS_EVENT_RECEIPT_TOPIC_MAX_BYTES];
  size_t topic_size;
} zs_event_receipt_transport_t;

typedef enum {
  ZS_EVENT_RECEIPT_APPLIED = 0,
  ZS_EVENT_RECEIPT_ALREADY_APPLIED,
  ZS_EVENT_RECEIPT_REJECTED_TOPIC,
  ZS_EVENT_RECEIPT_REJECTED_DELIVERY,
  ZS_EVENT_RECEIPT_REJECTED_RECEIPT,
  ZS_EVENT_RECEIPT_STORAGE_ERROR,
  ZS_EVENT_RECEIPT_INVALID_ARGUMENT
} zs_event_receipt_result_t;

zs_event_receipt_status_t zs_event_receipt_decode(
    const uint8_t *payload,
    size_t payload_size,
    uint32_t expected_station_id,
    zs_event_receipt_t *receipt);

bool zs_event_receipt_transport_init(
    zs_event_receipt_transport_t *transport,
    uint32_t station_id,
    const uint8_t *tenant,
    size_t tenant_size);

/*
 * Accept only the exact station receipt topic at QoS 1 with retain=false,
 * verify all event metadata and SHA-256, then mark the outbox item delivered.
 */
zs_event_receipt_result_t zs_event_receipt_transport_handle(
    const zs_event_receipt_transport_t *transport,
    const zs_event_outbox_io_t *outbox,
    const uint8_t *topic,
    size_t topic_size,
    const uint8_t *payload,
    size_t payload_size,
    uint8_t qos,
    bool retained,
    zs_event_receipt_status_t *decode_status);

#endif

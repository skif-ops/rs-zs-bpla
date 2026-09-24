#ifndef ZS_EVENT_OUTBOX_H
#define ZS_EVENT_OUTBOX_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_sha256.h"
#include "zs_types.h"

#define ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES 512u
#define ZS_EVENT_OUTBOX_SLOT_BYTES 616u
#define ZS_EVENT_OUTBOX_MAX_RETRIES 128u
#define ZS_EVENT_OUTBOX_PRIORITY_MAX 3u

/* All operations on one physical outbox must be serialized by the target. */

typedef enum {
  ZS_EVENT_OUTBOX_OK = 0,
  ZS_EVENT_OUTBOX_EMPTY,
  ZS_EVENT_OUTBOX_INVALID_ARGUMENT,
  ZS_EVENT_OUTBOX_INVALID_EVENT,
  ZS_EVENT_OUTBOX_IO_ERROR,
  ZS_EVENT_OUTBOX_CORRUPT,
  ZS_EVENT_OUTBOX_FULL,
  ZS_EVENT_OUTBOX_ALREADY_PENDING,
  ZS_EVENT_OUTBOX_ALREADY_ACKED,
  ZS_EVENT_OUTBOX_CONFLICT,
  ZS_EVENT_OUTBOX_RETRY_EXHAUSTED,
  ZS_EVENT_OUTBOX_STALE_ITEM,
  ZS_EVENT_OUTBOX_VERIFY_FAILED
} zs_event_outbox_result_t;

typedef struct {
  void *ctx;
  uint16_t slot_count;
  bool (*read)(void *ctx, uint16_t slot, uint32_t offset,
               uint8_t *data, size_t size);
  bool (*erase)(void *ctx, uint16_t slot);
  bool (*write)(void *ctx, uint16_t slot, uint32_t offset,
                const uint8_t *data, size_t size);
} zs_event_outbox_io_t;

typedef struct {
  uint32_t station_id;
  uint32_t boot_id;
  uint32_t seq_no;
  uint64_t event_id;
  int64_t event_time_us;
  uint8_t priority;
  const uint8_t *payload;
  size_t payload_size;
} zs_event_outbox_event_t;

typedef struct {
  uint16_t storage_slot;
  uint32_t storage_generation;
  uint32_t station_id;
  uint32_t boot_id;
  uint32_t seq_no;
  uint64_t event_id;
  int64_t event_time_us;
  uint8_t priority;
  uint16_t retry_count;
  uint16_t payload_size;
  uint8_t payload_sha256[ZS_SHA256_DIGEST_BYTES];
  uint8_t payload[ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES];
} zs_event_outbox_item_t;

/*
 * Atomically enqueue one complete binary event. A committed duplicate with
 * identical metadata and payload is idempotent; reuse of station_id/event_id
 * with different semantics is a conflict. Delivered slots may be reclaimed,
 * but pending events are never evicted.
 */
zs_event_outbox_result_t zs_event_outbox_enqueue(
    const zs_event_outbox_io_t *io,
    const zs_event_outbox_event_t *event);

/* Encode schema-4 detection CBOR and bind its metadata in one operation. */
zs_event_outbox_result_t zs_event_outbox_enqueue_detection(
    const zs_event_outbox_io_t *io,
    const zs_detection_t *detection,
    uint8_t priority,
    uint8_t *workspace,
    size_t workspace_size);

/* Highest priority first, FIFO by durable storage generation within priority. */
zs_event_outbox_result_t zs_event_outbox_peek(
    const zs_event_outbox_io_t *io,
    zs_event_outbox_item_t *item);

/* Number of stored events not yet acknowledged by the server (heartbeat detector map). */
zs_event_outbox_result_t zs_event_outbox_pending_count(
    const zs_event_outbox_io_t *io,
    uint16_t *pending);

/*
 * Find a committed event by station/event identity, including an already
 * delivered slot. This allows a queued QoS-1 application receipt to be applied
 * safely after a station restart without relying on volatile in-flight state.
 */
zs_event_outbox_result_t zs_event_outbox_lookup(
    const zs_event_outbox_io_t *io,
    uint32_t station_id,
    uint64_t event_id,
    zs_event_outbox_item_t *item,
    bool *delivered);

/* Persistently count an attempted transmission before submitting the payload. */
zs_event_outbox_result_t zs_event_outbox_note_attempt(
    const zs_event_outbox_io_t *io,
    const zs_event_outbox_item_t *item);

/*
 * Mark delivered only after a verified server application ACK, never merely
 * after an MQTT PUBACK. Interrupted marker writes leave the item pending, so
 * recovery is at-least-once and may redeliver the same event_id.
 */
zs_event_outbox_result_t zs_event_outbox_mark_application_acked(
    const zs_event_outbox_io_t *io,
    const zs_event_outbox_item_t *item);

#endif

#ifndef ZS_BEARING_BATCH_H
#define ZS_BEARING_BATCH_H
/*
 * Bearing stream while tracking (MQTT ICD addendum H): the bearings of the CONFIRMED windows after a detection event
 * are queued in RAM and published about once a second as one batch on zs/v1/{tenant}/{station_id}/bearing.
 *
 * Batch, canonical CBOR map, message type 7, schema 1:
 *   0 schema (1)   1 message type (7)   2 station_id   3 boot_id   4 track event_id (the event of the rising edge)
 *   5 base_time_us (int64, time of the first sample)   6 time_trust (zs_time_trust_t of the samples)
 *   7 geometry_id (1 = the locked 3+1 array)
 *   8 samples: array of [dt_ms (uint, from base_time_us), azimuth_cdeg (uint 0..35999), elevation_cdeg (int),
 *                        sigma_cdeg (uint), confidence_u8 (uint), frames (uint)]
 * A batch holds the samples of one track and one time trust; the stream is best effort (QoS 1 to the broker, never
 * stored in NOR, dropped when the session cannot take it): the durable record of the track is the detection events.
 *
 * The queue keeps the newest ZS_BEARING_QUEUE_DEPTH records (the oldest is dropped and counted when it is full,
 * e.g. while the modem is still coming up).  No locking inside: the target wraps push/take in a critical section.
 */
#include "zs_bearing.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_BEARING_BATCH_SCHEMA 1u
#define ZS_BEARING_BATCH_MESSAGE_TYPE 7u
#define ZS_BEARING_BATCH_MAX_SAMPLES 16u
#define ZS_BEARING_BATCH_MAX_BYTES 384u      /* 16 samples at their widest fit (checked by the tests) */
#define ZS_BEARING_QUEUE_DEPTH 32u

typedef struct {
  uint64_t track_event_id;
  int64_t time_us;            /* wall time of the window end (0 when the station time is not trusted yet) */
  uint16_t azimuth_cdeg;      /* 0..35999, clockwise from north */
  int16_t elevation_cdeg;
  uint16_t sigma_cdeg;
  uint8_t confidence_u8;
  uint8_t frames;
  uint8_t time_trust;
} zs_bearing_record_t;

typedef struct {
  uint32_t dt_ms;
  uint16_t azimuth_cdeg;
  int16_t elevation_cdeg;
  uint16_t sigma_cdeg;
  uint8_t confidence_u8;
  uint8_t frames;
} zs_bearing_sample_t;

typedef struct {
  uint32_t station_id, boot_id;
  uint64_t track_event_id;
  int64_t base_time_us;
  uint8_t time_trust;
  uint8_t geometry_id;
  uint8_t count;
  zs_bearing_sample_t sample[ZS_BEARING_BATCH_MAX_SAMPLES];
} zs_bearing_batch_t;

typedef struct {
  zs_bearing_record_t item[ZS_BEARING_QUEUE_DEPTH];
  uint8_t head, count;
  uint32_t pushed, dropped, taken;
} zs_bearing_queue_t;

/* A valid bearing as a record (azimuth wrapped into 0..35999, angles in hundredths, sigma saturated). */
bool zs_bearing_record_from(zs_bearing_record_t *r, uint64_t track_event_id, int64_t time_us, uint8_t time_trust, const zs_bearing_t *b);

/* Canonical CBOR of a batch (1..ZS_BEARING_BATCH_MAX_SAMPLES samples); 0 on a bad batch or a short buffer. */
size_t zs_bearing_batch_encode(const zs_bearing_batch_t *b, uint8_t *out, size_t cap);

void zs_bearing_queue_init(zs_bearing_queue_t *q);
void zs_bearing_queue_push(zs_bearing_queue_t *q, const zs_bearing_record_t *r);
uint8_t zs_bearing_queue_count(const zs_bearing_queue_t *q);
void zs_bearing_queue_clear(zs_bearing_queue_t *q);
/* Moves up to `max` oldest records into `batch`: the oldest record's track and time trust, in order, while the time
   offset fits; returns the number taken (0 = empty queue). */
uint8_t zs_bearing_queue_take(zs_bearing_queue_t *q, uint32_t station_id, uint32_t boot_id, uint8_t geometry_id, uint8_t max,
                              zs_bearing_batch_t *batch);

#endif

#include "zs_bearing_batch.h"
#include "zs_cbor.h"

#include <math.h>
#include <string.h>

bool zs_bearing_record_from(zs_bearing_record_t *r, uint64_t track_event_id, int64_t time_us, uint8_t time_trust, const zs_bearing_t *b) {
  long az, el, sigma;
  if (!r || !b || !b->valid) return false;
  az = lroundf(b->azimuth_deg * 100.0f) % 36000L;
  if (az < 0) az += 36000L;
  el = lroundf(b->elevation_deg * 100.0f);
  sigma = lroundf(b->sigma_deg * 100.0f);
  memset(r, 0, sizeof(*r));
  r->track_event_id = track_event_id;
  r->time_us = time_us;
  r->azimuth_cdeg = (uint16_t)az;
  r->elevation_cdeg = (int16_t)(el > 9000L ? 9000L : (el < -9000L ? -9000L : el));
  r->sigma_cdeg = (uint16_t)(sigma < 0L ? 0L : (sigma > 65535L ? 65535L : sigma));
  r->confidence_u8 = (uint8_t)lroundf((b->confidence < 0.0f ? 0.0f : (b->confidence > 1.0f ? 1.0f : b->confidence)) * 255.0f);
  r->frames = b->frames_used;
  r->time_trust = time_trust;
  {
    const long f0 = b->f0_hz > 0.0f ? lroundf(b->f0_hz * 10.0f) : 0L;
    r->f0_dhz = (uint16_t)(f0 > 65535L ? 65535L : f0);
  }
  return true;
}

size_t zs_bearing_batch_encode(const zs_bearing_batch_t *b, uint8_t *out, size_t cap) {
  zs_cbor_t c;
  bool sources = false;
  if (!b || !out || b->count == 0u || b->count > ZS_BEARING_BATCH_MAX_SAMPLES || b->station_id == 0u) return 0u;
  for (unsigned i = 0u; i < b->count; i++) sources = sources || b->sample[i].f0_dhz != 0u;
  zs_cbor_init(&c, out, cap);
  zs_cbor_map(&c, 9u);
  zs_cbor_uint(&c, 0u); zs_cbor_uint(&c, sources ? ZS_BEARING_BATCH_SCHEMA_SOURCES : ZS_BEARING_BATCH_SCHEMA);
  zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, ZS_BEARING_BATCH_MESSAGE_TYPE);
  zs_cbor_uint(&c, 2u); zs_cbor_uint(&c, b->station_id);
  zs_cbor_uint(&c, 3u); zs_cbor_uint(&c, b->boot_id);
  zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, b->track_event_id);
  zs_cbor_uint(&c, 5u); zs_cbor_int(&c, b->base_time_us);
  zs_cbor_uint(&c, 6u); zs_cbor_uint(&c, b->time_trust);
  zs_cbor_uint(&c, 7u); zs_cbor_uint(&c, b->geometry_id);
  zs_cbor_uint(&c, 8u); zs_cbor_array(&c, b->count);
  for (unsigned i = 0u; i < b->count; i++) {
    const zs_bearing_sample_t *s = &b->sample[i];
    zs_cbor_array(&c, sources ? 7u : 6u);
    zs_cbor_uint(&c, s->dt_ms);
    zs_cbor_uint(&c, s->azimuth_cdeg);
    zs_cbor_int(&c, s->elevation_cdeg);
    zs_cbor_uint(&c, s->sigma_cdeg);
    zs_cbor_uint(&c, s->confidence_u8);
    zs_cbor_uint(&c, s->frames);
    if (sources) zs_cbor_uint(&c, s->f0_dhz);
  }
  return c.error ? 0u : c.len;
}

void zs_bearing_queue_init(zs_bearing_queue_t *q) { if (q) memset(q, 0, sizeof(*q)); }
void zs_bearing_queue_clear(zs_bearing_queue_t *q) { if (q) { q->head = 0u; q->count = 0u; } }
uint8_t zs_bearing_queue_count(const zs_bearing_queue_t *q) { return q ? q->count : 0u; }

void zs_bearing_queue_push(zs_bearing_queue_t *q, const zs_bearing_record_t *r) {
  if (!q || !r) return;
  if (q->count == ZS_BEARING_QUEUE_DEPTH) {                  /* full: the oldest goes */
    q->head = (uint8_t)((q->head + 1u) % ZS_BEARING_QUEUE_DEPTH);
    q->count--;
    q->dropped++;
  }
  q->item[(q->head + q->count) % ZS_BEARING_QUEUE_DEPTH] = *r;
  q->count++;
  q->pushed++;
}

uint8_t zs_bearing_queue_take(zs_bearing_queue_t *q, uint32_t station_id, uint32_t boot_id, uint8_t geometry_id, uint8_t max,
                              zs_bearing_batch_t *batch) {
  const zs_bearing_record_t *first;
  uint8_t n = 0u;
  if (!q || !batch || q->count == 0u) return 0u;
  if (max == 0u || max > ZS_BEARING_BATCH_MAX_SAMPLES) max = ZS_BEARING_BATCH_MAX_SAMPLES;
  first = &q->item[q->head];
  memset(batch, 0, sizeof(*batch));
  batch->station_id = station_id;
  batch->boot_id = boot_id;
  batch->geometry_id = geometry_id;
  batch->track_event_id = first->track_event_id;
  batch->base_time_us = first->time_us;
  batch->time_trust = first->time_trust;
  while (n < max && q->count > 0u) {
    const zs_bearing_record_t *r = &q->item[q->head];
    int64_t dt;
    if (r->track_event_id != batch->track_event_id || r->time_trust != batch->time_trust) break;
    dt = (r->time_us - batch->base_time_us) / 1000;
    if (dt < 0 || dt > (int64_t)UINT32_MAX) break;         /* time went back or jumped: next batch */
    batch->sample[n] = (zs_bearing_sample_t){(uint32_t)dt, r->azimuth_cdeg, r->elevation_cdeg, r->sigma_cdeg, r->confidence_u8, r->frames, r->f0_dhz};
    n++;
    q->head = (uint8_t)((q->head + 1u) % ZS_BEARING_QUEUE_DEPTH);
    q->count--;
  }
  batch->count = n;
  q->taken += n;
  return n;
}

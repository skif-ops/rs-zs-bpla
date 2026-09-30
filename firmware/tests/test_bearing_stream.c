/* Bearing stream while tracking (MQTT ICD addendum H): batch encoding against the server's golden vector, the RAM
   queue (order, track/trust boundaries, overflow), records from bearings, the tracking window. */
#include "zs_bearing_batch.h"
#include "zs_track_window.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

/* server/tests/test_bearing_stream.py decodes the same bytes (cbor2 canonical encoding of the batch below) */
static const char *const GOLDEN =
    "a90001010702110305041b0000000500000001051b0006651729573c2006010701088386001931561907d018b418e608861901f419319e19"
    "07c118af18e508861903e81931cf3895190384188005";

static void hex(const uint8_t *b, size_t n, char *out) { for (size_t i = 0u; i < n; i++) sprintf(out + 2u * i, "%02x", b[i]); }

static zs_bearing_record_t rec(uint64_t track, int64_t t, uint16_t az, int16_t el, uint16_t sigma, uint8_t conf, uint8_t frames, uint8_t trust) {
  zs_bearing_record_t r = {track, t, az, el, sigma, conf, frames, trust};
  return r;
}

static void push(zs_bearing_queue_t *q, zs_bearing_record_t r) { zs_bearing_queue_push(q, &r); }

static void test_golden_batch(void) {
  zs_bearing_queue_t q;
  zs_bearing_batch_t b;
  uint8_t buf[ZS_BEARING_BATCH_MAX_BYTES];
  char text[2u * ZS_BEARING_BATCH_MAX_BYTES + 1u];
  const uint64_t track = ((uint64_t)5u << 32) | 1u;
  size_t n;
  zs_bearing_queue_init(&q);
  zs_bearing_queue_push(&q, &(zs_bearing_record_t){track, 1800000012500000LL, 12630u, 2000, 180u, 230u, 8u, 1u});
  zs_bearing_queue_push(&q, &(zs_bearing_record_t){track, 1800000013000000LL, 12702u, 1985, 175u, 229u, 8u, 1u});
  zs_bearing_queue_push(&q, &(zs_bearing_record_t){track, 1800000013500000LL, 12751u, -150, 900u, 128u, 5u, 1u});
  assert(zs_bearing_queue_take(&q, 17u, 5u, 1u, 16u, &b) == 3u && zs_bearing_queue_count(&q) == 0u);
  assert(b.base_time_us == 1800000012500000LL && b.sample[2].dt_ms == 1000u && b.track_event_id == track);
  n = zs_bearing_batch_encode(&b, buf, sizeof(buf));
  hex(buf, n, text);
  assert(n > 0u && strcmp(text, GOLDEN) == 0);
  assert(zs_bearing_batch_encode(&b, buf, 20u) == 0u);                       /* short buffer */
  b.count = 0u; assert(zs_bearing_batch_encode(&b, buf, sizeof(buf)) == 0u);  /* empty batch */
}

static void test_worst_case_size(void) {
  zs_bearing_batch_t b;
  uint8_t buf[ZS_BEARING_BATCH_MAX_BYTES];
  memset(&b, 0, sizeof(b));
  b.station_id = UINT32_MAX; b.boot_id = UINT32_MAX; b.track_event_id = UINT64_MAX; b.base_time_us = INT64_MIN;
  b.time_trust = 255u; b.geometry_id = 255u; b.count = ZS_BEARING_BATCH_MAX_SAMPLES;
  for (unsigned i = 0u; i < ZS_BEARING_BATCH_MAX_SAMPLES; i++) b.sample[i] = (zs_bearing_sample_t){UINT32_MAX, 35999u, INT16_MIN, UINT16_MAX, 255u, 255u};
  printf("bearing batch worst case %zu bytes\n", zs_bearing_batch_encode(&b, buf, sizeof(buf)));
  assert(zs_bearing_batch_encode(&b, buf, sizeof(buf)) > 0u);
}

static void test_queue_boundaries_and_overflow(void) {
  zs_bearing_queue_t q;
  zs_bearing_batch_t b;
  zs_bearing_queue_init(&q);
  push(&q, rec(7u, 1000000, 100u, 0, 50u, 200u, 8u, 1u));
  push(&q, rec(7u, 1500000, 110u, 0, 50u, 200u, 8u, 1u));
  push(&q, rec(7u, 2000000, 120u, 0, 50u, 200u, 8u, 2u));   /* trust changed */
  push(&q, rec(9u, 2500000, 130u, 0, 50u, 200u, 8u, 2u));   /* next track */
  push(&q, rec(9u, 1000000, 140u, 0, 50u, 200u, 8u, 2u));   /* time went back */
  assert(zs_bearing_queue_take(&q, 1u, 1u, 1u, 16u, &b) == 2u && b.track_event_id == 7u && b.time_trust == 1u && b.sample[1].dt_ms == 500u);
  assert(zs_bearing_queue_take(&q, 1u, 1u, 1u, 16u, &b) == 1u && b.time_trust == 2u);
  assert(zs_bearing_queue_take(&q, 1u, 1u, 1u, 16u, &b) == 1u && b.track_event_id == 9u);
  assert(zs_bearing_queue_take(&q, 1u, 1u, 1u, 16u, &b) == 1u && b.sample[0].azimuth_cdeg == 140u);
  assert(zs_bearing_queue_take(&q, 1u, 1u, 1u, 16u, &b) == 0u);
  /* overflow: the newest ZS_BEARING_QUEUE_DEPTH stay, the oldest are counted */
  for (unsigned i = 0u; i < ZS_BEARING_QUEUE_DEPTH + 5u; i++) push(&q, rec(3u, (int64_t)i * 500000, (uint16_t)i, 0, 1u, 1u, 4u, 1u));
  assert(zs_bearing_queue_count(&q) == ZS_BEARING_QUEUE_DEPTH && q.dropped == 5u);
  assert(zs_bearing_queue_take(&q, 1u, 1u, 1u, 4u, &b) == 4u && b.sample[0].azimuth_cdeg == 5u && b.sample[3].dt_ms == 1500u);
  zs_bearing_queue_clear(&q);
  assert(zs_bearing_queue_count(&q) == 0u);
}

static void test_record_from_bearing(void) {
  zs_bearing_record_t r;
  zs_bearing_t b = {.azimuth_deg = 359.996f, .elevation_deg = 95.0f, .sigma_deg = 1000.0f, .confidence = 1.2f, .frames_used = 7u, .valid = true};
  assert(zs_bearing_record_from(&r, 11u, 123456, 1u, &b));
  assert(r.azimuth_cdeg == 0u && r.elevation_cdeg == 9000 && r.sigma_cdeg == 65535u && r.confidence_u8 == 255u && r.frames == 7u && r.time_trust == 1u);
  b.azimuth_deg = -0.5f; b.elevation_deg = -12.34f; b.sigma_deg = 2.25f; b.confidence = 0.5f;
  assert(zs_bearing_record_from(&r, 11u, 123456, 1u, &b) && r.azimuth_cdeg == 35950u && r.elevation_cdeg == -1234 && r.sigma_cdeg == 225u && r.confidence_u8 == 128u);
  b.valid = false;
  assert(!zs_bearing_record_from(&r, 11u, 123456, 1u, &b));
}

static void test_track_window(void) {
  zs_track_window_t t;
  zs_track_window_init(&t, 120000u, 6u);
  assert(!zs_track_window_on_event(&t, 5u, false, 1000u) && t.refused_link == 1u && !zs_track_window_active(&t));   /* LTE only */
  assert(zs_track_window_on_event(&t, 5u, true, 1000u) && zs_track_window_active(&t));
  assert(!zs_track_window_on_event(&t, 5u, true, 5000u));                                  /* keep-alive update: same track */
  for (unsigned i = 0u; i < 5u; i++) assert(zs_track_window_on_window(&t, false, 2000u + i * 500u) == ZS_TRACK_END_NONE);
  assert(zs_track_window_on_window(&t, true, 5000u) == ZS_TRACK_END_NONE);                  /* a CONFIRMED window resets the count */
  for (unsigned i = 0u; i < 5u; i++) assert(zs_track_window_on_window(&t, false, 5500u + i * 500u) == ZS_TRACK_END_NONE);
  assert(zs_track_window_on_window(&t, false, 8000u) == ZS_TRACK_END_LOST && !zs_track_window_active(&t) && t.windows == 12u);
  assert(zs_track_window_on_window(&t, true, 8500u) == ZS_TRACK_END_NONE);                  /* closed: ignored */
  /* the next track: the time limit */
  assert(zs_track_window_on_event(&t, 6u, true, 10000u));
  assert(zs_track_window_on_window(&t, true, 129999u) == ZS_TRACK_END_NONE);
  assert(zs_track_window_on_window(&t, true, 130000u) == ZS_TRACK_END_MAX && t.ended_max == 1u);
  assert(!zs_track_window_on_event(&t, 6u, true, 131000u));                                /* same track after the limit: stays closed */
  assert(zs_track_window_on_event(&t, 8u, true, 132000u));
  zs_track_window_end(&t);
  assert(!zs_track_window_active(&t) && t.ended_mode == 1u && t.last_end == ZS_TRACK_END_MODE && t.tracks == 3u);
  /* disabled */
  zs_track_window_init(&t, 0u, 6u);
  assert(!zs_track_window_on_event(&t, 7u, true, 0u));
  assert(strcmp(zs_track_end_name(ZS_TRACK_END_LOST), "target lost") == 0);
}

int main(void) {
  test_golden_batch();
  test_worst_case_size();
  test_queue_boundaries_and_overflow();
  test_record_from_bearing();
  test_track_window();
  puts("bearing stream tests passed");
  return 0;
}

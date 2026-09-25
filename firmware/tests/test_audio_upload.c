/* zs_audio_upload (addendum B §3): windows around the event, contiguous-run selection, SHA-256 of the exact record
   concatenation, chunking, waiting for the window, and the refusals/failures (no audio, bad range, CRC, overwrite). */
#include "zs_audio_chunk.h"
#include "zs_audio_upload.h"
#include "zs_prehistory.h"
#include "zs_sha256.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ERASE 4096u
#define RECORDS 64u
#define FLASH_BYTES (RECORDS * 16384u)
#define RATE 32000u
#define S 1000000LL

static uint8_t flash[FLASH_BYTES];
static int st_read(void *c, uint32_t a, uint8_t *d, size_t n) { (void)c; if ((uint64_t)a + n > FLASH_BYTES) return -1; memcpy(d, flash + a, n); return 0; }
static int st_write(void *c, uint32_t a, const uint8_t *d, size_t n) { (void)c; if ((uint64_t)a + n > FLASH_BYTES) return -1; for (size_t i = 0u; i < n; i++) flash[a + i] &= d[i]; return 0; }
static int st_erase(void *c, uint32_t a, size_t n) { (void)c; if (a % ERASE || n % ERASE || (uint64_t)a + n > FLASH_BYTES) return -1; memset(flash + a, 0xff, n); return 0; }
static const zs_archive_storage_t storage = {NULL, FLASH_BYTES, ERASE, st_read, st_write, st_erase};
static zs_prehistory_t ring;
static const int64_t T0 = 1800000000000000LL;
static const uint8_t CMD[16] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};

static void record_second(int64_t start_us, unsigned salt) {
  static int16_t pcm[RATE];
  for (uint32_t i = 0u; i < RATE; i++) pcm[i] = (int16_t)((int)((i * 37u + salt * 1013u) % 20000u) - 10000);
  assert(zs_prehistory_begin_frame(&ring, start_us) && zs_prehistory_push_pcm(&ring, pcm, RATE) && zs_prehistory_finalize_frame(&ring));
}
static void fresh_ring(void) { memset(flash, 0xff, sizeof(flash)); assert(zs_prehistory_init(&ring, &storage, 0u, FLASH_BYTES, RATE)); }
static uint64_t oldest(void) { return ring.next_sequence - ring.available_records; }

/* Runs a job to the end; returns the concatenated segment data of the last segment and checks every chunk. */
typedef struct { unsigned chunks, segments; uint8_t kinds[2]; uint32_t bytes[2]; uint64_t first[2]; uint32_t records[2]; } run_t;
static run_t run_job(zs_audio_upload_t *u, int64_t now_us, bool recording) {
  static uint8_t out[ZS_AUDIO_CHUNK_MAX_BYTES], seg[200u * 16004u];
  run_t r;
  uint32_t seg_len = 0u;
  memset(&r, 0, sizeof(r));
  for (unsigned guard = 0u; guard < 100000u; guard++) {
    const zs_audio_upload_step_t st = zs_audio_upload_step(u, now_us, recording, oldest(), ring.next_sequence);
    if (st == ZS_AUDIO_UPLOAD_STEP_FINISHED || st == ZS_AUDIO_UPLOAD_STEP_IDLE) return r;
    if (st != ZS_AUDIO_UPLOAD_STEP_CHUNK_READY) continue;
    {
      const zs_audio_upload_segment_t *s = &u->seg[u->seg_index];
      const uint32_t off = (uint32_t)u->chunk_index * ZS_AUDIO_CHUNK_DATA_MAX;
      const uint32_t len = s->bytes - off < ZS_AUDIO_CHUNK_DATA_MAX ? s->bytes - off : ZS_AUDIO_CHUNK_DATA_MAX;
      const size_t n = zs_audio_upload_chunk(u, out, sizeof(out));
      if (n == 0u) continue;                                                    /* storage failure: finished */
      assert(n <= ZS_AUDIO_CHUNK_MAX_BYTES && memcmp(out + n - len, u->data, len) == 0);   /* data is the bstr tail */
      if (u->chunk_index == 0u) seg_len = 0u;
      memcpy(seg + seg_len, u->data, len);
      seg_len += len;
      if (u->chunk_index + 1u == s->chunk_count) {
        /* the whole segment = the records' payloads back to back; its SHA-256 is the one every chunk carries */
        uint8_t digest[32];
        static uint8_t expect[200u * 16004u];
        for (uint32_t k = 0u; k < s->records; k++) assert(zs_prehistory_read_payload(&ring, s->first_seq + k, 0u, expect + k * 16004u, 16004u));
        assert(seg_len == s->bytes && s->bytes == s->records * 16004u && memcmp(seg, expect, seg_len) == 0);
        zs_sha256_digest(seg, seg_len, digest);
        assert(memcmp(digest, s->sha256, 32) == 0);
        r.kinds[r.segments] = s->kind; r.bytes[r.segments] = s->bytes; r.first[r.segments] = s->first_seq; r.records[r.segments] = s->records;
        r.segments++;
      }
      r.chunks++;
      zs_audio_upload_chunk_sent(u);
    }
  }
  assert(0 && "job did not finish");
  return r;
}

int main(void) {
  zs_audio_upload_t u;
  zs_audio_request_command_t req;
  uint16_t detail;
  run_t r;
  const int64_t event = T0 + 25 * S + 300000;                 /* 25.3 s */

  /* 40 s recorded without a break: records 0..39 start at T0 + k s */
  fresh_ring();
  for (unsigned k = 0u; k < 40u; k++) record_second(T0 + (int64_t)k * S, k);
  memset(&req, 0, sizeof(req));
  req.event_id = 77u;

  /* pre: [event-30 s, event) -> records 0..25 (record 25 starts at 25.0 s, before the event) */
  req.segment = ZS_AUDIO_SEGMENT_PRE;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, event, &detail));
  assert(zs_audio_upload_step(&u, event, true, oldest(), ring.next_sequence) == ZS_AUDIO_UPLOAD_STEP_IDLE);   /* window not over */
  r = run_job(&u, event + 2 * S, true);
  assert(u.state == ZS_AUDIO_UPLOAD_FINISHED && u.result == ZS_COMMAND_ACK_OK);
  assert(r.segments == 1u && r.kinds[0] == 0u && r.first[0] == 0u && r.records[0] == 26u);
  assert(r.chunks == zs_audio_chunk_count(26u * 16004u) && u.detail == r.chunks);

  /* post: [event, event+30 s) -> records 25..39 (all that exists); it waits for the window unless the capture stopped */
  req.segment = ZS_AUDIO_SEGMENT_POST;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, event, &detail));
  assert(zs_audio_upload_step(&u, event + 20 * S, true, oldest(), ring.next_sequence) == ZS_AUDIO_UPLOAD_STEP_IDLE);
  r = run_job(&u, event + 20 * S, false);                     /* capture stopped: nothing more will come */
  assert(u.result == ZS_COMMAND_ACK_OK && r.segments == 1u && r.kinds[0] == 1u && r.first[0] == 25u && r.records[0] == 15u);

  /* both: two segments, the ACK detail counts every chunk */
  req.segment = ZS_AUDIO_SEGMENT_BOTH;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, event, &detail));
  r = run_job(&u, event + 40 * S, true);
  assert(u.result == ZS_COMMAND_ACK_OK && r.segments == 2u && r.kinds[0] == 0u && r.kinds[1] == 1u);
  assert(u.detail == zs_audio_chunk_count(26u * 16004u) + zs_audio_chunk_count(15u * 16004u));

  /* range: 5 s from 2 s after the event -> records 27..31 (27.0..31.0 overlap [27.3, 32.3)) plus 32 */
  req.segment = ZS_AUDIO_SEGMENT_RANGE; req.has_range = true; req.start_offset_ms = 2000; req.duration_ms = 5000u;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, event, &detail));
  r = run_job(&u, event + 60 * S, true);
  assert(u.result == ZS_COMMAND_ACK_OK && r.first[0] == 27u && r.records[0] == 6u && r.kinds[0] == 1u);
  req.duration_ms = ZS_AUDIO_UPLOAD_MAX_RANGE_MS + 1u;
  assert(!zs_audio_upload_start(&u, &ring, 901u, CMD, &req, event, &detail) && detail == ZS_AUDIO_UPLOAD_DETAIL_RANGE);
  req.duration_ms = 0u;
  assert(!zs_audio_upload_start(&u, &ring, 901u, CMD, &req, event, &detail) && detail == ZS_AUDIO_UPLOAD_DETAIL_RANGE);
  req.has_range = false; req.start_offset_ms = 0; req.duration_ms = 0u;

  /* no audio of the event (long overwritten / never recorded) -> REJECTED 2 */
  req.segment = ZS_AUDIO_SEGMENT_BOTH;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, T0 + 3600 * S, &detail));
  r = run_job(&u, T0 + 4000 * S, true);
  assert(u.result == ZS_COMMAND_ACK_REJECTED && u.detail == ZS_AUDIO_UPLOAD_DETAIL_NO_AUDIO && r.chunks == 0u);

  /* a gap (capture off 10 s): pre picks the run right before the event, not the older one; post the first after */
  fresh_ring();
  for (unsigned k = 0u; k < 20u; k++) record_second(T0 + (int64_t)k * S, k);          /* 0..19 s */
  for (unsigned k = 0u; k < 20u; k++) record_second(T0 + (int64_t)(30u + k) * S, k);   /* 30..49 s */
  req.segment = ZS_AUDIO_SEGMENT_PRE;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, T0 + 35 * S, &detail));
  r = run_job(&u, T0 + 60 * S, true);
  assert(u.result == ZS_COMMAND_ACK_OK && r.first[0] == 20u && r.records[0] == 5u);    /* 30..34 s, not 5..19 s */
  req.segment = ZS_AUDIO_SEGMENT_POST;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, T0 + 12 * S, &detail));
  r = run_job(&u, T0 + 60 * S, true);
  assert(u.result == ZS_COMMAND_ACK_OK && r.first[0] == 12u && r.records[0] == 8u);    /* 12..19 s: the run in the window's start */

  /* a corrupted record payload -> FAILED 1 while hashing, nothing sent */
  flash[23u * 16384u + ZS_PREHISTORY_HEADER_BYTES + 100u] ^= 0x01u;   /* seq 23 = 33 s */
  req.segment = ZS_AUDIO_SEGMENT_PRE;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, T0 + 35 * S, &detail));
  r = run_job(&u, T0 + 60 * S, true);
  (void)r;
  assert(u.result == ZS_COMMAND_ACK_FAILED && u.detail == ZS_AUDIO_UPLOAD_DETAIL_STORAGE);

  /* a record overwritten between the hash and its chunk -> FAILED 1 (never a chunk of other audio) */
  fresh_ring();
  for (unsigned k = 0u; k < 10u; k++) record_second(T0 + (int64_t)k * S, k);
  req.segment = ZS_AUDIO_SEGMENT_PRE;
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, T0 + 10 * S, &detail));
  while (zs_audio_upload_step(&u, T0 + 20 * S, true, oldest(), ring.next_sequence) != ZS_AUDIO_UPLOAD_STEP_CHUNK_READY) {}
  memset(flash + 3u * 16384u, 0xff, ZS_PREHISTORY_HEADER_BYTES);                          /* record 3 gone */
  {
    static uint8_t out[ZS_AUDIO_CHUNK_MAX_BYTES];
    unsigned sent = 0u;
    while (u.state == ZS_AUDIO_UPLOAD_SEND && zs_audio_upload_chunk(&u, out, sizeof(out)) > 0u) { zs_audio_upload_chunk_sent(&u); sent++; }
    assert(u.state == ZS_AUDIO_UPLOAD_FINISHED && u.result == ZS_COMMAND_ACK_FAILED && sent == (3u * 16004u) / ZS_AUDIO_CHUNK_DATA_MAX);
  }

  /* abort leaves the job idle (a redelivered command starts over) */
  assert(zs_audio_upload_start(&u, &ring, 901u, CMD, &req, T0 + 10 * S, &detail) && zs_audio_upload_active(&u));
  zs_audio_upload_abort(&u);
  assert(!zs_audio_upload_active(&u));
  puts("zs_audio_upload_tests: OK");
  return 0;
}

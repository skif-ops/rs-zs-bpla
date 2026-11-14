/* zs_audio_recorder: capture ring -> NOR prehistory ring (addendum B).  Complete seconds only, time-stamped by the
   first sample; stop and overrun drop the partial second; storage errors never wedge the recorder; the records
   carry exactly the channel's samples (the ADPCM payload equals an independent encode of the same second). */
#include "zs_adpcm.h"
#include "zs_audio.h"
#include "zs_audio_recorder.h"
#include "zs_prehistory.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ERASE 4096u
#define FLASH_BYTES (32u * 16384u)            /* the minimum ring: 30 s prehistory + 1 record */
#define RATE 32000u
#define RING_FRAMES 36000u                 /* the target's 1.125 s capture ring */
#define TICK 640u                          /* 20 ms of audio per tick */

static uint8_t flash[FLASH_BYTES];
static int fail_erase;
static int st_read(void *c, uint32_t a, uint8_t *d, size_t n) { (void)c; if ((uint64_t)a + n > FLASH_BYTES) return -1; memcpy(d, flash + a, n); return 0; }
static int st_write(void *c, uint32_t a, const uint8_t *d, size_t n) {
  (void)c; if ((uint64_t)a + n > FLASH_BYTES) return -1;
  for (size_t i = 0u; i < n; i++) { if ((flash[a + i] & d[i]) != d[i]) return -2; flash[a + i] &= d[i]; }
  return 0;
}
static int st_erase(void *c, uint32_t a, size_t n) { (void)c; if (fail_erase) return -1; if (a % ERASE || n % ERASE || (uint64_t)a + n > FLASH_BYTES) return -1; memset(flash + a, 0xff, n); return 0; }
static const zs_archive_storage_t storage = {NULL, FLASH_BYTES, ERASE, st_read, st_write, st_erase};

static int16_t ring_mem[RING_FRAMES * ZS_AUDIO_CHANNELS];
static zs_audio_ring_t ring;
static uint64_t produced;
static int64_t t_base = 1800000000000000LL;
static int64_t sample_time(void *ctx, uint64_t s) { (void)ctx; return t_base + (int64_t)(s * 1000000u / RATE); }
static int16_t sample_at(uint64_t n, unsigned ch) { return (int16_t)(8000.0 * sin(2.0 * 3.14159265 * (200.0 + 100.0 * ch) * (double)n / RATE)); }
static void produce(uint32_t frames) {
  for (uint32_t i = 0u; i < frames; i++, produced++) {
    int16_t f[ZS_AUDIO_CHANNELS];
    for (unsigned c = 0u; c < ZS_AUDIO_CHANNELS; c++) f[c] = sample_at(produced, c);
    zs_audio_ring_push(&ring, f);
  }
}
static void run_ticks(zs_audio_recorder_t *r, unsigned ticks) {
  for (unsigned t = 0u; t < ticks; t++) { produce(TICK); (void)zs_audio_recorder_step(r, &ring, ring.total_frames, 4096u); }
}

int main(void) {
  zs_prehistory_t pre;
  zs_audio_recorder_t rec;
  zs_prehistory_record_info_t info;
  memset(flash, 0xff, sizeof(flash));
  zs_audio_ring_init(&ring, ring_mem, RING_FRAMES, RATE);
  assert(zs_prehistory_init(&pre, &storage, 0u, FLASH_BYTES, RATE) && pre.record_count == 32u);
  assert(!zs_audio_recorder_init(&rec, &pre, NULL, NULL));
  assert(zs_audio_recorder_init(&rec, &pre, sample_time, NULL));
  rec.channel = 2u;

  /* not capturing: nothing recorded */
  produce(RATE);
  assert(zs_audio_recorder_step(&rec, &ring, ring.total_frames, 100000u) == 0u && pre.next_sequence == 0u);

  /* 3.5 s of capture from sample 32000: three complete seconds, the fourth in progress */
  zs_audio_recorder_start(&rec, ring.total_frames);
  run_ticks(&rec, 175u);
  assert(rec.frames_committed == 3u && pre.active && pre.current_samples == RATE / 2u);
  for (uint64_t s = 0u; s < 3u; s++) {
    assert(zs_prehistory_read_record_info(&pre, s, &info));
    assert(info.sample_count == RATE && info.payload_bytes == zs_ima_adpcm_block_bytes_for_samples(RATE));
    assert(info.start_time_us == t_base + (int64_t)(1u + s) * 1000000);          /* capture sample 32000 * (1 + s) */
  }
  /* the payload is exactly the chosen channel's second, encoded independently */
  {
    static int16_t second[RATE];
    static uint8_t expect[16100], got[16100];
    size_t n = 0u;
    for (uint32_t i = 0u; i < RATE; i++) second[i] = sample_at(RATE * 2u + i, 2u);   /* record 1 = capture second 2 */
    assert(zs_ima_adpcm_encode_block(second, RATE, expect, sizeof(expect), &n) && n == info.payload_bytes);
    assert(st_read(NULL, 1u * 16384u + ZS_PREHISTORY_HEADER_BYTES, got, n) == 0 && memcmp(got, expect, n) == 0);
  }

  /* stop drops the half second; restart continues with a fresh, correctly stamped second */
  zs_audio_recorder_stop(&rec);
  assert(rec.frames_aborted == 1u && !pre.active);
  produce(RATE * 5u);                                         /* capture off: nothing recorded, time moves on */
  assert(zs_audio_recorder_step(&rec, &ring, ring.total_frames, 100000u) == 0u);
  zs_audio_recorder_start(&rec, ring.total_frames);
  {
    const uint64_t first = ring.total_frames;
    run_ticks(&rec, 50u);                                     /* exactly one second */
    assert(rec.frames_committed == 4u && !pre.active);
    assert(zs_prehistory_read_record_info(&pre, 3u, &info) && info.start_time_us == sample_time(NULL, first));
  }

  /* overrun: the recorder is starved for 2 s (longer than the RAM ring) -> partial dropped, resync, next second ok */
  run_ticks(&rec, 10u);
  produce(RATE * 2u);
  assert(zs_audio_recorder_step(&rec, &ring, ring.total_frames, 100000u) == 0u);
  assert(rec.overruns == 1u && rec.frames_aborted == 2u && rec.cursor == ring.total_frames);
  run_ticks(&rec, 50u);
  assert(rec.frames_committed == 5u);

  /* bounded work per call */
  produce(3000u);
  assert(zs_audio_recorder_step(&rec, &ring, ring.total_frames, 1000u) == 1000u);
  assert(zs_audio_recorder_step(&rec, &ring, ring.total_frames, 100000u) == 2000u);

  /* storage error on the record start: counted, the backlog skipped, recording resumes once the flash works */
  zs_audio_recorder_stop(&rec);
  zs_audio_recorder_start(&rec, ring.total_frames);
  fail_erase = 1;
  run_ticks(&rec, 5u);
  assert(rec.storage_errors >= 1u && !pre.active);
  fail_erase = 0;
  {
    const uint32_t committed = rec.frames_committed;
    run_ticks(&rec, 51u);
    assert(rec.frames_committed == committed + 1u);
  }

  /* the ring survives a reboot: recover finds the latest sequence and the next record continues it */
  {
    zs_prehistory_t again;
    const uint64_t next = pre.next_sequence;
    assert(zs_prehistory_init(&again, &storage, 0u, FLASH_BYTES, RATE) && zs_prehistory_recover(&again));
    assert(again.next_sequence == next && again.available_records == (uint32_t)next);
  }

  /* wrong channel is refused, not recorded */
  rec.channel = ZS_AUDIO_CHANNELS;
  produce(TICK);
  assert(zs_audio_recorder_step(&rec, &ring, ring.total_frames, 100000u) == 0u);

  printf("zs_audio_recorder_tests: OK (committed %u aborted %u overruns %u storage errors %u)\n",
         rec.frames_committed, rec.frames_aborted, rec.overruns, rec.storage_errors);
  return 0;
}

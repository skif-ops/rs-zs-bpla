#include "zs_audio_upload.h"

#include "zs_archive.h"

#include <string.h>

#define SECOND_US 1000000

static void finish(zs_audio_upload_t *u, zs_command_ack_result_t result, uint16_t detail) {
  u->result = result;
  u->detail = detail;
  u->state = ZS_AUDIO_UPLOAD_FINISHED;
}

static uint32_t payload_bytes(const zs_audio_upload_t *u) { return (uint32_t)zs_ima_adpcm_block_bytes_for_samples(u->ring->sample_rate); }

static void add_window(zs_audio_upload_t *u, uint8_t kind, int64_t start_us, int64_t end_us) {
  zs_audio_upload_segment_t *s = &u->seg[u->seg_count++];
  memset(s, 0, sizeof(*s));
  s->kind = kind;
  s->window_start_us = start_us;
  s->window_end_us = end_us;
  if (end_us + ZS_AUDIO_UPLOAD_SETTLE_US > u->not_before_us) u->not_before_us = end_us + ZS_AUDIO_UPLOAD_SETTLE_US;
}

bool zs_audio_upload_start(zs_audio_upload_t *u, const zs_prehistory_t *ring, uint32_t station_id,
                           const uint8_t command_id[ZS_COMMAND_UUID_BYTES], const zs_audio_request_command_t *req,
                           int64_t event_time_us, uint16_t *detail) {
  const int64_t window_us = (int64_t)ZS_AUDIO_UPLOAD_WINDOW_MS * 1000;
  if (!u || !ring || !command_id || !req || !detail || ring->record_count == 0u) return false;
  *detail = 0u;
  memset(u, 0, sizeof(*u));
  u->ring = ring;
  u->station_id = station_id;
  memcpy(u->command_id, command_id, ZS_COMMAND_UUID_BYTES);
  u->event_id = req->event_id;
  u->not_before_us = INT64_MIN;
  switch (req->segment) {
    case ZS_AUDIO_SEGMENT_PRE: add_window(u, ZS_AUDIO_SEGMENT_PRE, event_time_us - window_us, event_time_us); break;
    case ZS_AUDIO_SEGMENT_POST: add_window(u, ZS_AUDIO_SEGMENT_POST, event_time_us, event_time_us + window_us); break;
    case ZS_AUDIO_SEGMENT_BOTH:
      add_window(u, ZS_AUDIO_SEGMENT_PRE, event_time_us - window_us, event_time_us);
      add_window(u, ZS_AUDIO_SEGMENT_POST, event_time_us, event_time_us + window_us);
      break;
    case ZS_AUDIO_SEGMENT_RANGE:
      if (!req->has_range || req->duration_ms == 0u || req->duration_ms > ZS_AUDIO_UPLOAD_MAX_RANGE_MS) { *detail = ZS_AUDIO_UPLOAD_DETAIL_RANGE; return false; }
      add_window(u, req->start_offset_ms < 0 ? ZS_AUDIO_SEGMENT_PRE : ZS_AUDIO_SEGMENT_POST,
                 event_time_us + (int64_t)req->start_offset_ms * 1000,
                 event_time_us + (int64_t)req->start_offset_ms * 1000 + (int64_t)req->duration_ms * 1000);
      break;
    default:
      *detail = ZS_AUDIO_UPLOAD_DETAIL_RANGE;
      return false;
  }
  u->state = ZS_AUDIO_UPLOAD_WAIT;
  return true;
}

/* ---- select: backward scan of the record headers, one contiguous run per window ---- */
static void begin_select(zs_audio_upload_t *u, uint64_t oldest_seq, uint64_t next_seq) {
  u->scan_seq = next_seq;
  u->scan_oldest = oldest_seq;
  u->run_open = false;
  u->chosen = false;
  u->state = ZS_AUDIO_UPLOAD_SELECT;
}

/* A run is closed: pre keeps the first one met (the latest before the event), post / later windows the last one
   met (the earliest in the window). */
static void close_run(zs_audio_upload_t *u) {
  zs_audio_upload_segment_t *s = &u->seg[u->seg_index];
  if (!u->run_open) return;
  u->run_open = false;
  if (s->kind == ZS_AUDIO_SEGMENT_PRE && u->chosen) return;
  s->first_seq = u->run_lo;
  s->records = (uint32_t)(u->run_hi - u->run_lo + 1u);
  s->start_time_us = u->run_lo_time;
  u->chosen = true;
}

static void end_select(zs_audio_upload_t *u) {
  zs_audio_upload_segment_t *s = &u->seg[u->seg_index];
  close_run(u);
  if (!u->chosen || s->records == 0u) {
    /* nothing of this window: skip it; the job fails only when no window has audio */
    s->records = 0u;
    if (++u->seg_index < u->seg_count) { u->state = ZS_AUDIO_UPLOAD_WAIT; return; }
    if (u->segments_sent == 0u) finish(u, ZS_COMMAND_ACK_REJECTED, ZS_AUDIO_UPLOAD_DETAIL_NO_AUDIO);
    else finish(u, ZS_COMMAND_ACK_OK, (uint16_t)(u->chunks_sent > 0xffffu ? 0xffffu : u->chunks_sent));
    return;
  }
  s->bytes = s->records * payload_bytes(u);
  s->chunk_count = zs_audio_chunk_count(s->bytes);
  if (s->chunk_count == 0u) { finish(u, ZS_COMMAND_ACK_FAILED, ZS_AUDIO_UPLOAD_DETAIL_STORAGE); return; }
  u->hash_record = 0u;
  zs_sha256_init(&u->sha);
  u->state = ZS_AUDIO_UPLOAD_HASH;
}

static void select_step(zs_audio_upload_t *u) {
  const zs_audio_upload_segment_t *s = &u->seg[u->seg_index];
  for (unsigned n = 0u; n < ZS_AUDIO_UPLOAD_SCAN_PER_STEP; n++) {
    zs_prehistory_record_info_t info;
    if (u->scan_seq <= u->scan_oldest) { end_select(u); return; }
    const uint64_t seq = --u->scan_seq;
    if (!zs_prehistory_read_record_info(u->ring, seq, &info)) { close_run(u); continue; }   /* a gap */
    if (info.start_time_us >= s->window_end_us) { close_run(u); continue; }                /* newer than the window */
    if (info.start_time_us + SECOND_US <= s->window_start_us) { end_select(u); return; }   /* older: done */
    if (u->run_open && seq + 1u == u->run_lo) {
      const int64_t step = u->run_lo_time - info.start_time_us;
      if (step >= SECOND_US - ZS_AUDIO_UPLOAD_CONTIGUITY_US && step <= SECOND_US + ZS_AUDIO_UPLOAD_CONTIGUITY_US) {
        u->run_lo = seq;
        u->run_lo_time = info.start_time_us;
        continue;
      }
    }
    close_run(u);
    if (s->kind == ZS_AUDIO_SEGMENT_PRE && u->chosen) { end_select(u); return; }
    u->run_open = true;
    u->run_lo = u->run_hi = seq;
    u->run_lo_time = info.start_time_us;
  }
}

/* ---- hash: one record per step, its payload CRC checked on the way ---- */
static void hash_step(zs_audio_upload_t *u) {
  zs_audio_upload_segment_t *s = &u->seg[u->seg_index];
  zs_prehistory_record_info_t info;
  const uint64_t seq = s->first_seq + u->hash_record;
  uint32_t off = 0u, crc = 0xffffffffu;
  if (!zs_prehistory_read_record_info(u->ring, seq, &info)) { finish(u, ZS_COMMAND_ACK_FAILED, ZS_AUDIO_UPLOAD_DETAIL_STORAGE); return; }
  while (off < info.payload_bytes) {
    const uint32_t n = info.payload_bytes - off < sizeof(u->data) ? info.payload_bytes - off : (uint32_t)sizeof(u->data);
    if (!zs_prehistory_read_payload(u->ring, seq, off, u->data, n)) { finish(u, ZS_COMMAND_ACK_FAILED, ZS_AUDIO_UPLOAD_DETAIL_STORAGE); return; }
    crc = zs_archive_crc32_update(crc, u->data, n);
    zs_sha256_update(&u->sha, u->data, n);
    off += n;
  }
  if ((crc ^ 0xffffffffu) != info.payload_crc32) { finish(u, ZS_COMMAND_ACK_FAILED, ZS_AUDIO_UPLOAD_DETAIL_STORAGE); return; }
  if (++u->hash_record < s->records) return;
  zs_sha256_final(&u->sha, s->sha256);
  u->chunk_index = 0u;
  u->state = ZS_AUDIO_UPLOAD_SEND;
}

zs_audio_upload_step_t zs_audio_upload_step(zs_audio_upload_t *u, int64_t now_us, bool recording, uint64_t oldest_seq, uint64_t next_seq) {
  if (!u) return ZS_AUDIO_UPLOAD_STEP_IDLE;
  switch (u->state) {
    case ZS_AUDIO_UPLOAD_WAIT:
      if (recording && now_us < u->not_before_us) return ZS_AUDIO_UPLOAD_STEP_IDLE;
      begin_select(u, oldest_seq, next_seq);
      return ZS_AUDIO_UPLOAD_STEP_BUSY;
    case ZS_AUDIO_UPLOAD_SELECT: select_step(u); break;
    case ZS_AUDIO_UPLOAD_HASH: hash_step(u); break;
    case ZS_AUDIO_UPLOAD_SEND: return ZS_AUDIO_UPLOAD_STEP_CHUNK_READY;
    case ZS_AUDIO_UPLOAD_FINISHED: return ZS_AUDIO_UPLOAD_STEP_FINISHED;
    case ZS_AUDIO_UPLOAD_IDLE:
    default: return ZS_AUDIO_UPLOAD_STEP_IDLE;
  }
  return u->state == ZS_AUDIO_UPLOAD_FINISHED ? ZS_AUDIO_UPLOAD_STEP_FINISHED
       : u->state == ZS_AUDIO_UPLOAD_SEND ? ZS_AUDIO_UPLOAD_STEP_CHUNK_READY : ZS_AUDIO_UPLOAD_STEP_BUSY;
}

/* Segment bytes [offset, offset + len) span consecutive records; every record touched must still be the one hashed. */
static bool read_segment(zs_audio_upload_t *u, const zs_audio_upload_segment_t *s, uint32_t offset, uint32_t len) {
  const uint32_t per = payload_bytes(u);
  uint32_t done = 0u;
  while (done < len) {
    zs_prehistory_record_info_t info;
    const uint32_t rec = (offset + done) / per, in = (offset + done) % per;
    const uint32_t n = len - done < per - in ? len - done : per - in;
    if (rec >= s->records || !zs_prehistory_read_payload(u->ring, s->first_seq + rec, in, u->data + done, n) ||
        !zs_prehistory_read_record_info(u->ring, s->first_seq + rec, &info)) return false;   /* overwritten meanwhile */
    done += n;
  }
  return true;
}

size_t zs_audio_upload_chunk(zs_audio_upload_t *u, uint8_t *out, size_t cap) {
  zs_audio_chunk_t c;
  const zs_audio_upload_segment_t *s;
  uint32_t offset, len;
  size_t n;
  if (!u || u->state != ZS_AUDIO_UPLOAD_SEND || !out) return 0u;
  s = &u->seg[u->seg_index];
  offset = (uint32_t)u->chunk_index * ZS_AUDIO_CHUNK_DATA_MAX;
  len = s->bytes - offset < ZS_AUDIO_CHUNK_DATA_MAX ? s->bytes - offset : ZS_AUDIO_CHUNK_DATA_MAX;
  if (!read_segment(u, s, offset, len)) { finish(u, ZS_COMMAND_ACK_FAILED, ZS_AUDIO_UPLOAD_DETAIL_STORAGE); return 0u; }
  memset(&c, 0, sizeof(c));
  c.station_id = u->station_id;
  memcpy(c.command_id, u->command_id, sizeof(c.command_id));
  c.event_id = u->event_id;
  c.segment = s->kind;
  c.chunk_index = u->chunk_index;
  c.chunk_count = s->chunk_count;
  c.codec = ZS_AUDIO_CODEC_IMA_ADPCM_1S;
  c.sample_rate = u->ring->sample_rate;
  c.segment_start_time_us = s->start_time_us;
  memcpy(c.segment_sha256, s->sha256, sizeof(c.segment_sha256));
  c.data = u->data;
  c.data_len = len;
  n = zs_audio_chunk_encode(&c, out, cap);
  if (n == 0u) finish(u, ZS_COMMAND_ACK_FAILED, ZS_AUDIO_UPLOAD_DETAIL_STORAGE);
  return n;
}

void zs_audio_upload_chunk_sent(zs_audio_upload_t *u) {
  if (!u || u->state != ZS_AUDIO_UPLOAD_SEND) return;
  u->chunks_sent++;
  if (++u->chunk_index < u->seg[u->seg_index].chunk_count) return;
  u->segments_sent++;
  if (++u->seg_index < u->seg_count) { u->state = ZS_AUDIO_UPLOAD_WAIT; return; }
  finish(u, ZS_COMMAND_ACK_OK, (uint16_t)(u->chunks_sent > 0xffffu ? 0xffffu : u->chunks_sent));
}

void zs_audio_upload_abort(zs_audio_upload_t *u) { if (u) u->state = ZS_AUDIO_UPLOAD_IDLE; }

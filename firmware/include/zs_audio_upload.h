#ifndef ZS_AUDIO_UPLOAD_H
#define ZS_AUDIO_UPLOAD_H
/*
 * Answer to CMD_REQUEST_AUDIO (MQTT ICD addendum B §3): picks the event's audio out of the NOR prehistory ring and
 * cuts it into audio chunks (zs_audio_chunk).  Transport-neutral: the caller publishes each chunk and reports the
 * broker ACK; the command journal and the ACK stay with the caller.
 *
 *   start (windows from the request) -> WAIT (until the window has been recorded) -> SELECT (backward header scan,
 *   contiguous run) -> HASH (SHA-256 + record CRC, one record per step) -> SEND (chunk by chunk) -> next segment ...
 *   -> FINISHED (result + detail: OK / number of chunks, REJECTED 2 no audio, FAILED 1 NOR/CRC)
 *
 * Every step does bounded work (a few header reads, one record, or one chunk) so the comms task keeps servicing
 * the modem between them.
 */
#include "zs_audio_chunk.h"
#include "zs_command.h"
#include "zs_prehistory.h"
#include "zs_sha256.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_AUDIO_UPLOAD_WINDOW_MS 30000        /* pre / post segment length */
#define ZS_AUDIO_UPLOAD_MAX_RANGE_MS 120000u   /* longest RANGE request */
#define ZS_AUDIO_UPLOAD_SETTLE_US 1500000      /* the record covering the window end commits ~1 s after its start */
#define ZS_AUDIO_UPLOAD_CONTIGUITY_US 5000     /* consecutive records start 1 s apart within this (time re-anchoring) */
#define ZS_AUDIO_UPLOAD_SCAN_PER_STEP 32u      /* record headers read per step while selecting */

/* ACK detail codes (addendum B) */
#define ZS_AUDIO_UPLOAD_DETAIL_NO_AUDIO 2u     /* REJECTED: nothing of the event left in the ring / event unknown */
#define ZS_AUDIO_UPLOAD_DETAIL_TIME 3u         /* REJECTED: the event time is not trusted */
#define ZS_AUDIO_UPLOAD_DETAIL_BUSY 4u         /* REJECTED: another upload is running; ask again later */
#define ZS_AUDIO_UPLOAD_DETAIL_RANGE 5u        /* REJECTED: RANGE longer than ZS_AUDIO_UPLOAD_MAX_RANGE_MS or empty */
#define ZS_AUDIO_UPLOAD_DETAIL_STORAGE 1u      /* FAILED: NOR read / record CRC / record overwritten */

typedef enum {
  ZS_AUDIO_UPLOAD_IDLE = 0,
  ZS_AUDIO_UPLOAD_WAIT,
  ZS_AUDIO_UPLOAD_SELECT,
  ZS_AUDIO_UPLOAD_HASH,
  ZS_AUDIO_UPLOAD_SEND,
  ZS_AUDIO_UPLOAD_FINISHED
} zs_audio_upload_state_t;

typedef enum {
  ZS_AUDIO_UPLOAD_STEP_IDLE = 0,      /* nothing to do (idle, or waiting for the window) */
  ZS_AUDIO_UPLOAD_STEP_BUSY,          /* work done; call again */
  ZS_AUDIO_UPLOAD_STEP_CHUNK_READY,   /* zs_audio_upload_chunk() has the next chunk */
  ZS_AUDIO_UPLOAD_STEP_FINISHED       /* result/detail final */
} zs_audio_upload_step_t;

typedef struct {
  uint8_t kind;                /* chunk key 5: 0 pre, 1 post */
  int64_t window_start_us, window_end_us;
  uint64_t first_seq;
  uint32_t records;
  int64_t start_time_us;
  uint32_t bytes;
  uint16_t chunk_count;
  uint8_t sha256[ZS_SHA256_DIGEST_BYTES];
} zs_audio_upload_segment_t;

typedef struct {
  const zs_prehistory_t *ring;
  zs_audio_upload_state_t state;
  uint32_t station_id;
  uint8_t command_id[ZS_COMMAND_UUID_BYTES];
  uint64_t event_id;
  int64_t not_before_us;
  zs_audio_upload_segment_t seg[2];
  uint8_t seg_count, seg_index, segments_sent;
  /* select */
  uint64_t scan_seq, scan_oldest;
  bool run_open, chosen;
  uint64_t run_lo, run_hi;
  int64_t run_lo_time;
  /* hash */
  uint32_t hash_record;
  zs_sha256_t sha;
  /* send */
  uint16_t chunk_index;
  uint32_t chunks_sent;
  /* result */
  zs_command_ack_result_t result;
  uint16_t detail;
  uint8_t data[ZS_AUDIO_CHUNK_DATA_MAX];
} zs_audio_upload_t;

/* Starts a job for a verified CMD_REQUEST_AUDIO whose event happened at event_time_us (station time base).
   Returns false with *detail set (REJECTED) when the request cannot be served at all. */
bool zs_audio_upload_start(zs_audio_upload_t *u, const zs_prehistory_t *ring, uint32_t station_id,
                           const uint8_t command_id[ZS_COMMAND_UUID_BYTES], const zs_audio_request_command_t *req,
                           int64_t event_time_us, uint16_t *detail);

/* One bounded step.  now_us: the station's current sample time; recording: the capture still runs (a stopped
   capture adds nothing more, so the job need not wait for the window end); [oldest_seq, next_seq): records the
   ring holds right now. */
zs_audio_upload_step_t zs_audio_upload_step(zs_audio_upload_t *u, int64_t now_us, bool recording, uint64_t oldest_seq, uint64_t next_seq);

/* Encodes the current chunk (state SEND); 0 = storage error (the job then finishes FAILED 1). */
size_t zs_audio_upload_chunk(zs_audio_upload_t *u, uint8_t *out, size_t cap);
/* The broker acknowledged the current chunk: move on. */
void zs_audio_upload_chunk_sent(zs_audio_upload_t *u);
/* Abandons the job (session lost): the command stays ACCEPTED, a redelivery starts over. */
void zs_audio_upload_abort(zs_audio_upload_t *u);

static inline bool zs_audio_upload_active(const zs_audio_upload_t *u) { return u && u->state != ZS_AUDIO_UPLOAD_IDLE && u->state != ZS_AUDIO_UPLOAD_FINISHED; }

#endif

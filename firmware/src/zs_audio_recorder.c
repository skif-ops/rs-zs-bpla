#include "zs_audio_recorder.h"

#include <string.h>

bool zs_audio_recorder_init(zs_audio_recorder_t *r, zs_prehistory_t *ring, zs_audio_recorder_time_fn sample_time, void *ctx) {
  if (!r || !ring || !sample_time || ring->sample_rate == 0u) return false;
  memset(r, 0, sizeof(*r));
  r->ring = ring;
  r->sample_time = sample_time;
  r->ctx = ctx;
  return true;
}

static void drop_partial(zs_audio_recorder_t *r) {
  if (!r->ring->active) return;
  zs_prehistory_abort_frame(r->ring);   /* the slot stays erased; the next record reuses it */
  r->frames_aborted++;
}

void zs_audio_recorder_start(zs_audio_recorder_t *r, uint64_t total_frames) {
  if (!r) return;
  drop_partial(r);
  r->cursor = total_frames;
  r->capturing = true;
}

void zs_audio_recorder_stop(zs_audio_recorder_t *r) {
  if (!r) return;
  drop_partial(r);
  r->capturing = false;
}

uint32_t zs_audio_recorder_step(zs_audio_recorder_t *r, const zs_audio_ring_t *audio, uint64_t total_frames, uint32_t max_samples) {
  uint32_t done = 0u;
  if (!r || !audio || !r->capturing || r->channel >= ZS_AUDIO_CHANNELS) return 0u;
  const uint32_t rate = r->ring->sample_rate;
  if (total_frames < r->cursor) {                       /* the capture ring was reset under us */
    drop_partial(r);
    r->cursor = total_frames;
    return 0u;
  }
  if (audio->frames_capacity <= ZS_AUDIO_RECORDER_MARGIN_SAMPLES) return 0u;
  if (total_frames - r->cursor > audio->frames_capacity - ZS_AUDIO_RECORDER_MARGIN_SAMPLES) {
    /* fell behind: the samples at the cursor are (about to be) overwritten; resume at the live position */
    drop_partial(r);
    r->overruns++;
    r->cursor = total_frames;
    return 0u;
  }
  while (done < max_samples && r->cursor < total_frames) {
    uint64_t avail;
    uint32_t n = ZS_AUDIO_RECORDER_CHUNK;
    if (!r->ring->active && !zs_prehistory_begin_frame(r->ring, r->sample_time(r->ctx, r->cursor))) {
      r->storage_errors++;
      r->cursor = total_frames;                          /* skip the backlog, try again with the next samples */
      return done;
    }
    avail = total_frames - r->cursor;
    if (n > avail) n = (uint32_t)avail;
    if (n > max_samples - done) n = max_samples - done;
    if (n > rate - r->ring->current_samples) n = rate - r->ring->current_samples;
    if (!zs_audio_ring_copy_mono(audio, r->cursor + n, n, r->pcm, r->channel) || !zs_prehistory_push_pcm(r->ring, r->pcm, n)) {
      drop_partial(r);
      r->storage_errors++;
      r->cursor = total_frames;
      return done;
    }
    r->cursor += n;
    done += n;
    if (r->ring->current_samples == rate) {
      if (zs_prehistory_finalize_frame(r->ring)) r->frames_committed++;
      else { drop_partial(r); r->storage_errors++; }
    }
  }
  return done;
}

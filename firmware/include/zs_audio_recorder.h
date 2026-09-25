#ifndef ZS_AUDIO_RECORDER_H
#define ZS_AUDIO_RECORDER_H
/*
 * Audio recorder (MQTT ICD addendum B): keeps the NOR prehistory ring (zs_prehistory) filled with the station's
 * mono audio while the capture runs, so CMD_REQUEST_AUDIO can be answered later.
 *
 *   capture ring (RAM, ~1 s, written by the audio task) --zs_audio_recorder_step--> 1-second IMA-ADPCM records
 *
 * One record = exactly sample_rate consecutive capture samples, stamped with the time of its first sample.  A
 * record is only committed when it is complete and continuous: a capture stop (the scheduler turned the PDM clock
 * off) or an overrun (the recorder fell behind the RAM ring) drops the partial second and restarts at the live
 * position, so the ring never holds a second that stitches two moments together.
 *
 * Runs in its own task on the target (a record start erases 4 NOR blocks, ~180 ms typical), never in the audio task.
 */
#include "zs_audio.h"
#include "zs_prehistory.h"

#include <stdbool.h>
#include <stdint.h>

#define ZS_AUDIO_RECORDER_CHUNK 256u             /* samples converted per ring read */
#define ZS_AUDIO_RECORDER_MARGIN_SAMPLES 3200u   /* 100 ms at 32 kHz: lagging closer than this to the ring's end = overrun */

/* Time of a capture sample index (the same mapping the pipeline uses for event times). */
typedef int64_t (*zs_audio_recorder_time_fn)(void *ctx, uint64_t sample);

typedef struct {
  zs_prehistory_t *ring;
  zs_audio_recorder_time_fn sample_time;
  void *ctx;
  uint8_t channel;              /* microphone channel recorded (mic_channel parameter) */
  bool capturing;
  uint64_t cursor;              /* next capture sample to record */
  uint32_t frames_committed, frames_aborted, overruns, storage_errors;
  int16_t pcm[ZS_AUDIO_RECORDER_CHUNK];
} zs_audio_recorder_t;

bool zs_audio_recorder_init(zs_audio_recorder_t *r, zs_prehistory_t *ring, zs_audio_recorder_time_fn sample_time, void *ctx);

/* The capture (re)started with the ring at `total_frames`: record from here on. */
void zs_audio_recorder_start(zs_audio_recorder_t *r, uint64_t total_frames);

/* The capture stops: the partial second is dropped (the ring keeps only complete, continuous seconds). */
void zs_audio_recorder_stop(zs_audio_recorder_t *r);

/* Records what the capture ring holds past the cursor, at most max_samples per call (bounds the time one call
   holds the caller); `total_frames` is the ring's write position read once by the caller.  Returns the number of
   samples consumed. */
uint32_t zs_audio_recorder_step(zs_audio_recorder_t *r, const zs_audio_ring_t *audio, uint64_t total_frames, uint32_t max_samples);

#endif

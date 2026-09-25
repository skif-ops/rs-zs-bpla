#ifndef APP_AUDIO_REC_H
#define APP_AUDIO_REC_H
/*
 * Audio prehistory recorder task (MQTT ICD addendum B): zs_audio_recorder from the capture ring into the NOR
 * prehistory ring (the archive region of the B3 NOR map), so CMD_REQUEST_AUDIO can be answered later.  The
 * supervisor tells it when the PDM capture starts and stops; the audio task wakes it after each block.
 */
#include "zs_audio.h"
#include "zs_audio_recorder.h"
#include "zs_prehistory.h"

#include <stdbool.h>
#include <stdint.h>

/* The ring lives in [base, base + ring_bytes) of `storage`; recovers the latest sequence (headers only). */
bool app_audio_rec_bind(const zs_archive_storage_t *storage, uint32_t base, uint32_t ring_bytes, const zs_audio_ring_t *capture,
                        zs_audio_recorder_time_fn sample_time, void (*log)(const char *fmt, ...));
/* Capture on/off (supervisor): the recorder task applies it before its next step. */
void app_audio_rec_capture(bool on);
void app_audio_rec_set_channel(uint8_t channel);
void app_audio_rec_notify(void);                  /* audio task, after a capture block */
void app_audio_rec_task(void *arg);
void app_audio_rec_status(void (*print)(const char *fmt, ...));
/* The ring for readers (the audio upload); NULL until bound. */
const zs_prehistory_t *app_audio_rec_ring(void);

#endif

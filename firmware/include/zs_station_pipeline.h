#ifndef ZS_STATION_PIPELINE_H
#define ZS_STATION_PIPELINE_H
/*
 * Station audio pipeline (S2 detection duty): pulls 1 s windows at a 0.5 s hop from the capture ring,
 * runs the feature extractor (zs_dsp_mcu on the target, zs_dsp on the host), the centroid classifier
 * with its 4..8-window consensus, the AIR gate and the level-1 fusion (zs_presence), and turns the
 * level-1 decision into detection events:
 *   - a detection is emitted when level 1 becomes CONFIRMED (rising edge), and again every
 *     `update_period_windows` while it stays CONFIRMED (the server keeps the track alive on updates);
 *   - SUSPECT / ENGINE_UNCONFIRMED are counted and exposed for diagnostics, never sent as detections;
 *   - the event carries the last window's 43 features, the consensus classification/hierarchy, the
 *     level-1 confidence and the detector profile (piston / reactive / generic) of the consensus family.
 * The module is portable: the extractor, the clock, the identity and the event sink are ports, the
 * 1 s mono window and the 64 KB gate scratch are caller-provided (the target overlays them on DSP memory).
 */
#include "zs_air_gate.h"
#include "zs_audio.h"
#include "zs_classifier_consensus.h"
#include "zs_dsp.h"
#include "zs_presence.h"
#include "zs_types.h"

#define ZS_PIPELINE_WINDOW_SAMPLES 32000u
#define ZS_PIPELINE_HOP_SAMPLES 16000u
#define ZS_PIPELINE_DEFAULT_UPDATE_WINDOWS 10u   /* 5 s at the 0.5 s hop */

typedef struct {
  void *ctx;
  /* 43 features of one 32000-sample window (zs_dsp_mcu_extract_1s / zs_dsp_extract_1s). */
  bool (*extract)(void *ctx, const int16_t *pcm, size_t n, float out[ZS_FEATURE_COUNT]);
  /* Wall time of a sample-counter position (zs_time); 0 when time is not yet trusted. */
  int64_t (*sample_time_us)(void *ctx, uint64_t sample);
  /* Event sink: encode + enqueue (zs_event_outbox_enqueue_detection). Returns false when not accepted. */
  bool (*emit)(void *ctx, const zs_detection_t *detection);
  uint32_t station_id;
  uint32_t boot_id;
  uint8_t channel;                 /* ring channel analysed (0..ZS_AUDIO_CHANNELS-1) */
  uint8_t update_period_windows;   /* 0 = ZS_PIPELINE_DEFAULT_UPDATE_WINDOWS */
} zs_station_pipeline_port_t;

typedef struct {
  const zs_station_pipeline_port_t *port;
  zs_complex_t *scratch;           /* >= ZS_AIR_SCRATCH_COMPLEX complex */
  int16_t *window;                 /* >= ZS_PIPELINE_WINDOW_SAMPLES */
  zs_classifier_consensus_t votes;
  zs_air_gate_t gate;
  zs_classification_t classification;
  zs_hier_classification_t hierarchy;
  zs_classifier_result_t last_window;
  zs_air_gate_result_t last_gate;
  zs_presence_t presence;
  float features[ZS_FEATURE_COUNT];
  uint64_t next_window_end;        /* sample counter at which the next window ends */
  uint64_t pending_end;            /* window copied into `window`, not yet analysed (fetch/run split) */
  bool pending;
  uint32_t windows;                /* windows processed */
  uint32_t windows_dropped;        /* ring overran the analysis (hops skipped) */
  uint32_t confirmed_windows, suspect_windows, engine_windows;
  uint32_t events_emitted, events_refused;
  uint32_t seq_no;
  uint16_t windows_since_event;    /* while CONFIRMED */
  bool confirmed;                  /* current level-1 state */
} zs_station_pipeline_t;

bool zs_station_pipeline_init(zs_station_pipeline_t *p, const zs_station_pipeline_port_t *port,
                              zs_complex_t *scratch, int16_t *window);
/* Copies the next complete window out of the ring into `window` (a few ms) and marks it pending; false when
   no new window is complete or one is still pending. Windows the ring has already overwritten are skipped
   and counted as dropped. On the target the capture task calls this so the copy happens while the samples
   are still in the ring; the analysis runs in the DSP task via zs_station_pipeline_run_pending(). */
bool zs_station_pipeline_fetch(zs_station_pipeline_t *p, const zs_audio_ring_t *ring);
/* Analyses the pending window (extractor, votes, gate, level 1, events); false when nothing is pending. */
bool zs_station_pipeline_run_pending(zs_station_pipeline_t *p);
/* fetch + run until the ring is drained (host tools, single-task use); returns windows processed. */
unsigned zs_station_pipeline_poll(zs_station_pipeline_t *p, const zs_audio_ring_t *ring);
/* One window straight from a PCM buffer (host tools, tests); `end_sample` labels the window. */
bool zs_station_pipeline_push_window(zs_station_pipeline_t *p, const int16_t *pcm, uint64_t end_sample);
/* Fills a detection from the current state (what emit() receives). */
void zs_station_pipeline_fill_detection(const zs_station_pipeline_t *p, uint64_t end_sample, zs_detection_t *d);

#endif

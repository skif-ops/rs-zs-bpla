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
 *     level-1 confidence and the detector profile (piston / reactive / generic) of the consensus family;
 *   - while CONFIRMED every window also gets a bearing of the 3+1 array (zs_bearing, the last 0.5 s of the window
 *     from the 4-channel ring): the event carries it as DOA (key 11) and the reference TDOAs (key 14), and the
 *     bearing port, when set, receives each one (the bearing stream while tracking);
 *   - when the AIR gate hears other sources beside the main one (a mixture, up to three), every source is followed
 *     as a source track (its fundamental from window to window, within ZS_PIPELINE_SOURCE_F0_STEP) with votes of its
 *     own: each mixture window classifies one source in turn with all the others suppressed, the main one included
 *     (one feature extraction per window, as before), and the source's presence is level 1 over its own votes with
 *     the gate's comb evidence.  The station is CONFIRMED when the main stream or any source track is; the event then
 *     names the confirming source's class.  Every CONFIRMED source gets its own bearing from the bins of its
 *     harmonics (zs_comb_bearing): the port receives each one with its fundamental (f0_hz), so the server follows
 *     several targets heard by one station; the event carries the first one.  The bearings of a mixture are taken in
 *     every window: two combs heard from one direction for ZS_PIPELINE_TOGETHER_WINDOWS windows are one target (a
 *     multirotor's rotors at different speeds), classified and reported as one, the main one; a new comb starts as
 *     one target with those heard already, and becomes a target of its own once its bearings disagree with theirs
 *     (two windows).
 *   - several targets by direction first (zs_doa_sep.h): from the first sign of a target (the gate's comb or any level
 *     above none) the newest 0.5 s of every window
 *     gives every spectral bin its own direction, the directions are counted over windows, and up to three direction
 *     tracks follow where many bins point (the comb cannot split two targets whose fundamentals are in a small integer
 *     ratio, nor hear one masked by a louder one).  When at least two direction tracks are confirmed and have their
 *     label (fundamental), and the caller lent a stash (zs_station_pipeline_set_stash), each one is classified on its
 *     own window: a window spends its newest 0.5 s on the next direction (the bins its plane wave fits best, soft mask)
 *     into the stash and is classified as it is (the main stream); the next window completes that direction's 1 s
 *     from the stash and its own newest 0.5 s and is classified as that direction (the 4-channel ring keeps only the
 *     newest 0.5 s of a window for the DSP task, one mask per window keeps the load).  A direction is a target when
 *     its own votes alone have a UAV majority of at least ZS_CLASSIFICATION_MIN_WINDOWS windows, or a majority of weak
 *     UAV votes with its own comb (its label) and almost no ground votes (no votes of the main stream, no comb of the
 *     gate: a tractor heard beside a UAV is a direction, never a target).  A target once confirmed stays so while its
 *     direction track lives (confirmed, labelled) and none of its own windows is a ground engine even at the weak
 *     threshold: its own window weakens as the targets close in (the mask leaves more of the others, twin 2026-10-01:
 *     an electric UAV's own windows fell from 72..134 to 0..38) and its bearings must not stop for it; with one direction
 *     left (the others gone, or come into its direction) a held target keeps its own bearing until a ground vote of
 *     the main stream lets it go; the station is
 *     CONFIRMED when the main stream or a target is.  The confirmed targets then replace the comb bearings: one
 *     bearing each with its label as f0_hz (the gate's fundamental when the label is an integer multiple of exactly
 *     one of the gate's combs, so the detections and the bearings name the same source).  While two directions or
 *     more are confirmed (also before they are labelled and classified) nothing else is delivered: the full-band
 *     bearing follows the louder of them, and the gate's main comb may be the one that is no UAV (a tractor's beside a
 *     UAV the main stream confirms).  Without a stash, or with fewer than two confirmed
 *     directions, everything is as above.
 * The module is portable: the extractor, the clock, the identity and the event sink are ports, the
 * 1 s mono window (4-byte aligned: the comb bearings borrow it as floats) and the gate scratch are caller-provided
 * (the target overlays them on DSP memory).
 */
#include "zs_air_gate.h"
#include "zs_audio.h"
#include "zs_bearing.h"
#include "zs_comb_bearing.h"
#include "zs_classifier_consensus.h"
#include "zs_doa_sep.h"
#include "zs_dsp.h"
#include "zs_presence.h"
#include "zs_types.h"

#define ZS_PIPELINE_WINDOW_SAMPLES 32000u
#define ZS_PIPELINE_HOP_SAMPLES 16000u
#define ZS_PIPELINE_DEFAULT_UPDATE_WINDOWS 10u   /* 5 s at the 0.5 s hop */
#define ZS_PIPELINE_BEARING_SPAN ZS_PIPELINE_HOP_SAMPLES   /* the newest 0.5 s of a window, still in a 1.125 s ring */
#define ZS_PIPELINE_SOURCES (1u + ZS_AIR_MAX_SECONDARY)     /* source tracks of a mixture */
#define ZS_PIPELINE_SOURCE_F0_STEP 0.06f                  /* a source's fundamental moves less than this per window */
#define ZS_PIPELINE_SOURCE_HOLD_WINDOWS 8u                /* a source track not heard this long is free again */
#define ZS_PIPELINE_TOGETHER_DEG 6.0f                     /* two combs from one direction (or 2 sigma) ...          */
#define ZS_PIPELINE_TOGETHER_WINDOWS 3u                   /* ... for this many windows are one target (its rotors) */
#define ZS_PIPELINE_LABEL_RATIO 0.04f                     /* a direction's label within 4 % of k x a gate comb (k 1..6) */
#define ZS_PIPELINE_DOA_BEARING_AGE 4u                    /* a direction's own window is masked by a bearing this recent */

/* One source of a mixture followed from window to window. */
typedef struct {
  float f0_hz;                     /* last fundamental; 0 = free */
  uint32_t last_window;            /* the window it was last heard in */
  zs_classifier_consensus_t votes; /* its own windows, classified with the other sources suppressed */
  zs_classification_t classification;
  zs_hier_classification_t hierarchy;
  zs_presence_t presence;
  bool heard;                      /* in the current window */
  bool with_others;                /* the gate reported it beside another source at least once (a mixture) */
} zs_pipeline_source_t;

/* A target found by direction (zs_doa_sep) with votes of its own (classified on its own window). */
typedef struct {
  uint16_t id;                     /* the direction track; 0 = free slot */
  zs_classifier_consensus_t votes;
  zs_classification_t classification;
  zs_hier_classification_t hierarchy;
  zs_presence_t presence;
  zs_bearing_t bearing;            /* its last bearing (valid once it had one); f0_hz = its label */
  uint8_t bearing_age;             /* windows since that bearing (0: this window) */
  float strength;                  /* the direction memory's peak */
  bool confirmed_direction;
  bool held;                       /* its own votes confirmed it once: it stays CONFIRMED while its track lives (see doa_evaluate) */
  uint8_t absent;                  /* windows its track has been gone (it may come back, zs_doa_sep recall) */
} zs_pipeline_target_t;

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
  /* Optional: air temperature for the speed of sound (NULL = 15 C; azimuth barely depends on it). */
  float (*temperature_c)(void *ctx);
  /* Optional: every valid bearing of a CONFIRMED window (end_sample = the window's last sample); with several
     sources one call per source, bearing->f0_hz telling which (0 for the full-band bearing of a single source). */
  void (*bearing)(void *ctx, const zs_bearing_t *bearing, uint64_t end_sample, uint64_t track_event_id);
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
  uint32_t separated_windows;      /* windows classified with other sources suppressed (zs_air_gate.h) */
  uint32_t events_emitted, events_refused;
  uint32_t seq_no;
  uint16_t windows_since_event;    /* while CONFIRMED */
  bool confirmed;                  /* current level-1 state */
  const zs_audio_ring_t *ring;     /* set by fetch: the 4-channel source of the bearings */
  zs_bearing_ctx_t bearing_ctx;
  zs_bearing_t last_bearing;       /* of the window ending at last_bearing_end (the main source's) */
  zs_comb_bearing_stats_t comb_stats;   /* bearings of several sources (zs_comb_bearing) */
  uint32_t comb_windows;           /* windows whose bearings came from the sources' combs */
  zs_pipeline_source_t sources[ZS_PIPELINE_SOURCES];
  uint8_t source_of[ZS_PIPELINE_SOURCES];   /* this window's sources (main first) -> source track, 0xff = none */
  float source_f0[ZS_PIPELINE_SOURCES];     /* this window's fundamentals, main first */
  uint8_t source_count;            /* this window's sources (0 = not a mixture) */
  uint8_t mixture_turn;            /* which source of a mixture the next window classifies */
  uint32_t source_confirmed_windows; /* windows CONFIRMED by a source track while the main stream was not */
  uint8_t together[ZS_PIPELINE_SOURCES][ZS_PIPELINE_SOURCES];   /* source tracks heard from one direction: windows */
  bool same_target[ZS_PIPELINE_SOURCES][ZS_PIPELINE_SOURCES];   /* ... and the decision (one target, e.g. a quadcopter
                                                                   whose rotors run at different speeds) */
  uint32_t merged_windows;         /* mixture windows whose combs all came from one target */
  uint64_t last_bearing_end;
  uint64_t track_event_id;         /* event id of the rising edge of the current CONFIRMED run */
  zs_doa_sep_t doa;                /* direction tracks (zs_doa_sep.h) */
  zs_pipeline_target_t doa_targets[ZS_DOA_MAX_TRACKS];
  int16_t *stash;                  /* ZS_PIPELINE_HOP_SAMPLES: a direction's masked 0.5 s between two windows (NULL: none) */
  uint16_t stash_target;           /* whose 0.5 s the stash holds (0: none) */
  uint64_t stash_end;              /* the window it was taken from */
  uint8_t doa_turn;                /* which direction the next stash takes */
  uint32_t doa_windows;            /* windows with the direction tracks running */
  uint32_t doa_mixture_windows;    /* windows with two or more confirmed directions (labelled) */
  uint32_t doa_classified_windows; /* windows classified as one direction's own window */
  uint32_t doa_confirmed_windows;  /* windows CONFIRMED by a direction target while the main stream was not */
  uint32_t doa_bearings;           /* bearings delivered from direction targets */
  uint32_t doa_mask_failed;        /* masks not made: the ring no longer held the span */
} zs_station_pipeline_t;

bool zs_station_pipeline_init(zs_station_pipeline_t *p, const zs_station_pipeline_port_t *port,
                              zs_complex_t *scratch, int16_t *window);
/* Lends a buffer of ZS_PIPELINE_HOP_SAMPLES int16 that nothing else touches between two windows (the target: the DSP
   magnitude buffer, idle between two feature extractions).  Without it the directions are tracked but not classified
   and their bearings never delivered. */
void zs_station_pipeline_set_stash(zs_station_pipeline_t *p, int16_t *stash);
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

#ifndef ZS_DOA_SEP_H
#define ZS_DOA_SEP_H
/*
 * Several targets by direction first (2026-10-01).  The comb of each source (zs_air_gate, zs_comb_bearing) cannot
 * tell apart targets whose fundamentals are in a small integer ratio (a DJI Mavic 3 Pro at 174 Hz and a Mini 3 Pro
 * at 261 Hz are exactly 2:3: one comb of 87 Hz) nor a quiet target whose lines drown among another's.  Here every
 * spectral bin finds its own direction, the directions are counted, and the targets are where many bins point:
 *
 *   - per 0.5 s span (the comb bearing's: decimated to 8 kHz, 7 Hann frames of 1024, hop 496, zs_comb_bearing.h):
 *     bins 80..1400 Hz (below the array's spatial aliasing) at least ZS_DOA_MIN_EXCESS_DB over the median of the
 *     31 bins around them; for each, the cross spectra to mic 1 normalised per frame and averaged over the frames
 *     give three phases -> three delays (the vertical pair's phase may wrap above 1 kHz: the delay candidates are
 *     tried and the best plane wave kept) -> the 3+1 solver (zs_spatial); the bin's coherence is the weakest pair's
 *     |mean| (one source in the bin: 1; two or noise: less);
 *   - a histogram of the window's bins over azimuth (2 degree cells, Gaussian 3 degrees): weight (coherence above
 *     ZS_DOA_MIN_COHERENCE, scaled to 0..1) x excess dB (at most 20); a memory decays by ZS_DOA_DECAY per window
 *     and adds the window's histogram, so a target whose bins are rare in one window (masked by a louder one) adds
 *     up over a few;
 *   - up to ZS_DOA_MAX_TRACKS peaks of the memory (ZS_DOA_PEAK_SEP_DEG apart, ZS_DOA_PEAK_REL of the strongest,
 *     at least ZS_DOA_PEAK_ABS) are followed as direction tracks: a track is where its last bearing plus its rate of
 *     turn says (the decaying memory lags behind a fast pass), a peak within ZS_DOA_GATE_DEG of that (wider by the
 *     turn) continues it, so does the window's own support there; a peak near a live track starts no other one; a
 *     track lost (a target fading for a few windows) comes back under its id, label and turn when a new peak appears
 *     where it would be now, within ZS_DOA_RECALL_WINDOWS;
 *     a track is confirmed when its own window histogram near it reached ZS_DOA_SUPPORT in at least
 *     ZS_DOA_CONFIRM_M of the last ZS_DOA_CONFIRM_N windows, and stays confirmed until none of them did (a target
 *     whose bins drop out for a window or two): the memory alone keeps a one-window burst (a horn, a bird) for several
 *     windows, its own support does not;
 *   - each track's bearing of the window is the weighted circular mean of its bins: those within ZS_DOA_ASSIGN_DEG of
 *     it and nearer to it than to any other track (at least ZS_DOA_MIN_BINS of them, otherwise no bearing this
 *     window); sigma from their spread.  The memory peaks and the window's support go to the tracks the same way
 *     (nearest pair first, each on its own side), so a louder target nearing a quiet one does not pull the quiet one's
 *     track onto itself (twin, 2026-10-01: three targets, the group's track of 121 Hz followed the 186 Hz one and its
 *     own target was lost);
 *   - a crossing: two tracks closer than ZS_DOA_CROSS_DEG see one blob of bins.  With both labels known and not in an
 *     integer ratio, frequency tells them apart: each takes the blob's bins on its own harmonics and on none of the
 *     other's and goes on as usual (two targets in one direction are two harmonic series, also when they stay
 *     together).  Otherwise both report the blob's bearing but coast on their own last bearing and rate of turn (no
 *     turn, no label from the blob), so each comes out where its own turn puts it and finds its own bins again.  A
 *     pair that cannot part is one target: a track that coasted ZS_DOA_COAST_MAX windows, or (no frequency) rates of
 *     turn that do not part it within that; the track whose label the blob's lines name stays (else the one with bins
 *     of its own, else the older), the other ends;
 *   - each track's label: the fundamental (100..400 Hz) of a harmonic sieve over its bins' local maxima; fixed by
 *     the median of its first estimates, then followed slowly (an estimate in an integer ratio to the label within
 *     6 % is folded onto it; others are ignored), so the label does not slip from window to window.
 *
 * A target's own window for the classifier (zs_doa_sep_mask_window): the 1 s window from the 4-channel ring in
 * 1024-point sqrt-Hann frames at 32 kHz, 50 % overlap; every bin goes to the tracks by how well their plane wave
 * fits the four phases (weight 1 / (misfit + 0.02)^2); a bin goes to another track only when that track's weight is
 * twice the target's, so noise and bins no direction explains stay (like the comb notch, only the other targets'
 * lines go); the target's share of mic 1 is resynthesised.
 *
 * Measured on recordings as plane waves on the 3+1 array (host prototype, docs/STATION_DIRECTION_SEPARATION_2026-10-01.md):
 * three real UAVs at once found in 19..21 of 21 windows, the 2:3 pair in 21 of 21, no confirmed track in diffuse
 * city noise or birds.  Portable, no allocation: the caller lends the decimated span and a zs_doa_workspace_t.
 */
#include "zs_audio.h"
#include "zs_bearing.h"
#include "zs_comb_bearing.h"
#include "zs_fft.h"
#include "zs_spatial.h"

#include <stdbool.h>
#include <stdint.h>

#define ZS_DOA_MAX_TRACKS 3u
#define ZS_DOA_CELLS 180u                 /* 2 degree azimuth cells */
#define ZS_DOA_FMIN_HZ 80.0f
#define ZS_DOA_FMAX_HZ 1400.0f
#define ZS_DOA_MIN_EXCESS_DB 3.0f
#define ZS_DOA_MIN_COHERENCE 0.75f
#define ZS_DOA_DECAY 0.7f
#define ZS_DOA_PEAK_SEP_DEG 20.0f
#define ZS_DOA_PEAK_REL 0.10f
#define ZS_DOA_PEAK_ABS 3.0f
#define ZS_DOA_GATE_DEG 6.0f
#define ZS_DOA_SUPPORT 2.0f
#define ZS_DOA_CONFIRM_M 2u
#define ZS_DOA_CONFIRM_N 4u
#define ZS_DOA_MISS_MAX 2u                /* a track not continued for more windows than this ends */
#define ZS_DOA_ASSIGN_DEG 10.0f
#define ZS_DOA_RECALL_WINDOWS 10u         /* a track lost this recently comes back under its id where it went */
#define ZS_DOA_CROSS_DEG 6.0f             /* two tracks closer than this are crossing (one blob of bins) */
#define ZS_DOA_COAST_MAX 24u              /* windows a crossing may last; longer, the two are one target: one track ends */
#define ZS_DOA_MIN_BINS 3u
#define ZS_DOA_LABEL_MIN_HZ 100.0f
#define ZS_DOA_LABEL_MAX_HZ 400.0f
#define ZS_DOA_LABEL_START 3u             /* estimates whose median fixes the label */
#define ZS_DOA_MAX_BINS 192u              /* bins 80..1400 Hz at 7.8 Hz: 169 */
#define ZS_DOA_MASK_N 1024u               /* 32 kHz frames of the target's own window */
#define ZS_DOA_MASK_HOP (ZS_DOA_MASK_N / 2u)

typedef struct {
  uint16_t k;              /* bin */
  float az_deg, el_deg;
  float coherence;
  float excess_db;
  float power;
} zs_doa_bin_t;

typedef struct {
  zs_complex_t spectrum[ZS_SPATIAL_MIC_COUNT][ZS_COMB_BEARING_N];
  zs_complex_t cross[ZS_SPATIAL_REF_TDOA_COUNT][ZS_COMB_BEARING_BINS];   /* sum of normalised cross spectra */
  float power[ZS_COMB_BEARING_BINS];                                    /* mean power over frames and mics */
  zs_doa_bin_t bins[ZS_DOA_MAX_BINS];
  float window_hist[ZS_DOA_CELLS];
  float line_hz[ZS_DOA_MAX_BINS], line_w[ZS_DOA_MAX_BINS];             /* a track's lines for its label */
} zs_doa_workspace_t;

typedef struct {
  zs_complex_t spectrum[ZS_SPATIAL_MIC_COUNT][ZS_DOA_MASK_N];
  float carry[ZS_DOA_MASK_HOP];                                          /* overlap-add of the previous frame */
} zs_doa_mask_workspace_t;

typedef struct {
  float az_deg;            /* where the track is (memory peak) */
  float label_hz;          /* stable fundamental label, 0 until fixed */
  float label_start[ZS_DOA_LABEL_START];
  uint8_t label_count;
  float last_az_deg;       /* its last bearing */
  float rate_deg;          /* azimuth change per window (from its bearings) */
  uint8_t since_bearing;   /* windows since that bearing (255: none yet) */
  uint8_t support;         /* own window support, newest in bit 0 */
  uint8_t misses;
  uint8_t age;             /* windows since it started (saturates) */
  uint8_t crossing;        /* windows it has coasted through a crossing (0: not crossing) */
  uint16_t id;             /* never 0 for a live track */
  bool live;
  bool confirmed;          /* ZS_DOA_CONFIRM_M of the last ZS_DOA_CONFIRM_N windows supported it; stays until none of them do */
} zs_doa_track_t;

typedef struct {
  uint16_t id;             /* 0: empty */
  float last_az_deg, rate_deg, label_hz;
  uint32_t last_bearing_window;
} zs_doa_recent_t;

typedef struct {
  float memory[ZS_DOA_CELLS];
  zs_doa_track_t track[ZS_DOA_MAX_TRACKS];
  zs_doa_recent_t recent[ZS_DOA_MAX_TRACKS];   /* tracks lost lately (a target fading for a few windows) */
  uint16_t next_id;
  uint32_t windows;
  uint32_t bins_used;      /* bins that entered a histogram (diagnostics) */
} zs_doa_sep_t;

/* A track's result for the window. */
typedef struct {
  uint16_t id;             /* the track (stable while it lives) */
  bool confirmed;
  bool has_bearing;        /* enough of its bins this window: bearing below */
  zs_bearing_t bearing;    /* azimuth, elevation, sigma, confidence; f0_hz = the label (0 until fixed) */
  float strength;          /* memory peak height */
  uint8_t bins;            /* its bins this window */
} zs_doa_target_t;

void zs_doa_sep_init(zs_doa_sep_t *s);
/* Forget all tracks and the memory (the station went quiet). */
void zs_doa_sep_reset(zs_doa_sep_t *s);
/* One window from the decimated span (zs_comb_bearing_decimate_ring / _channels).  out[] gets the live tracks in slot
   order; returns their number.  `ctx` gives the geometry. */
unsigned zs_doa_sep_push(zs_doa_sep_t *s, const zs_bearing_ctx_t *ctx, const float *memory, float temperature_c,
                         zs_doa_workspace_t *ws, zs_doa_target_t out[ZS_DOA_MAX_TRACKS]);
/* Target `which` of the tracks given (their bearings: azimuth and elevation of each, count 1..ZS_DOA_MAX_TRACKS) as a
   32 kHz mono window of `samples` samples ending at end_sample, from the 4-channel ring: the bins each track's plane
   wave fits clearly better go to it, the target's share of mic 1 is resynthesised into out[].  `ws` is scratch.
   False when the ring does not hold the span (and the 512 samples before it) or on bad arguments. */
bool zs_doa_sep_mask_window(const zs_bearing_ctx_t *ctx, const zs_audio_ring_t *ring, uint64_t end_sample, uint32_t samples,
                            const zs_bearing_t *tracks, unsigned count, unsigned which, float temperature_c,
                            zs_doa_mask_workspace_t *ws, int16_t *out);

#endif

#ifndef ZS_BEARING_H
#define ZS_BEARING_H
/*
 * On-board bearing (DOA) of the 3+1 microphone array from the 4-channel capture ring.
 *
 * One bearing = ZS_BEARING_FRAMES frames of ZS_SPATIAL_GCC_N samples spread evenly over a span of the ring; every
 * frame gives the three reference delays t_j - t_1 (GCC-PHAT, one reference transform); frames whose weakest
 * PHAT peak is below min_quality are dropped; the median of each delay over the accepted frames goes to the
 * closed-form 3+1 solver (zs_spatial).  Accuracy of this scheme with the locked geometry (DEC-005): median
 * azimuth error ~1-2 deg at 0 dB band SNR over 8 frames (tools/array_bearing_mc.py,
 * docs/ARRAY_BEARING_EVALUATION_2026-09-30.md).
 *
 * Portable, no allocation: the caller lends 4 x ZS_SPATIAL_GCC_N int16 of frame memory and a GCC workspace (the
 * station pipeline lends its 1 s window and the AIR gate scratch, both idle once a window is analysed).
 */
#include "zs_audio.h"
#include "zs_spatial.h"

#include <stdbool.h>
#include <stdint.h>

#define ZS_BEARING_FRAMES 8u
#define ZS_BEARING_MIN_FRAMES 4u                 /* fewer accepted frames: no bearing */
#define ZS_BEARING_FRAME_MEMORY (ZS_SPATIAL_MIC_COUNT * ZS_SPATIAL_GCC_N)   /* int16 */
#define ZS_BEARING_DEFAULT_FMIN_HZ 80.0f
#define ZS_BEARING_DEFAULT_FMAX_HZ 3000.0f
#define ZS_BEARING_DEFAULT_MIN_QUALITY 0.25f    /* PHAT coherence (independent noise ~0.1-0.2) */

typedef struct {
  float azimuth_deg;         /* 0..360, clockwise from north */
  float elevation_deg;       /* -90..90 */
  float sigma_deg;           /* 1-sigma angular uncertainty estimate */
  float residual_us;         /* solver residual */
  float tdoa_us[ZS_SPATIAL_REF_TDOA_COUNT];   /* median t_j - t_1, j = 2..4 */
  float confidence;          /* 0..1 */
  uint8_t frames_used;
  bool valid;
} zs_bearing_t;

typedef struct {
  zs_spatial_geometry_t geometry;
  float fmin_hz, fmax_hz, min_quality;
  uint32_t attempts;         /* bearings asked for */
  uint32_t computed;         /* valid bearings */
  uint32_t no_audio;         /* span no longer (or not yet) in the ring */
  uint32_t weak;             /* too few frames above min_quality */
  uint32_t unsolved;         /* solver rejected the delays */
} zs_bearing_ctx_t;

/* geometry NULL = the locked 3+1 geometry (zs_spatial_geometry_3p1_default). */
void zs_bearing_init(zs_bearing_ctx_t *ctx, const zs_spatial_geometry_t *geometry);

/* Bearing of the ring span [end_sample - span_samples, end_sample) (span >= ZS_SPATIAL_GCC_N).  `frames` holds
   ZS_BEARING_FRAME_MEMORY int16, `workspace` a GCC workspace.  Returns out->valid. */
bool zs_bearing_from_ring(zs_bearing_ctx_t *ctx, const zs_audio_ring_t *ring, uint64_t end_sample, uint32_t span_samples,
                          float temperature_c, int16_t *frames, zs_spatial_gcc_workspace_t *workspace, zs_bearing_t *out);

/* Same from four caller-provided channel buffers of `count` samples each (host tools, tests). */
bool zs_bearing_from_channels(zs_bearing_ctx_t *ctx, const int16_t *const channels[ZS_SPATIAL_MIC_COUNT], uint32_t count,
                              uint32_t sample_rate_hz, float temperature_c, zs_spatial_gcc_workspace_t *workspace,
                              zs_bearing_t *out);

#endif

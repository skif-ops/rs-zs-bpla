#ifndef ZS_COMB_BEARING_H
#define ZS_COMB_BEARING_H
/*
 * Bearings of several sources heard at once: one bearing per propulsion comb, from the bins of its own harmonics.
 *
 * The full-band GCC-PHAT bearing (zs_bearing) follows whatever dominates the band: with two targets of about the same
 * level it lands between them or comes out with a wide sigma, with three it rarely gives a usable bearing.  The AIR
 * gate already knows each source's fundamental (zs_air_gate.h, several sources); here every source gets its own
 * cross spectrum restricted to the bins of its harmonics, minus the bins near any other source's harmonics:
 *
 *   - the span (the newest 0.5 s of the window) of all four channels is low-passed and decimated 32 -> 8 kHz
 *     (63-tap Hamming sinc, identical on all channels, so the inter-channel phase is untouched), 7 Hann frames of
 *     1024 samples at a 496-sample hop (7.8 Hz bins up to 3.1 kHz);
 *   - bins of source s: within max(1 bin, 1.2 % of the frequency) of a harmonic h * f0_s (80 Hz .. 3.1 kHz, the
 *     Doppler drift over the span and the f0 estimate), excluding those within the same tolerance of any other
 *     source's harmonic; fewer than ZS_COMB_BEARING_MIN_BINS bins: no bearing for that source;
 *   - per microphone pair (j vs 1) the PHAT-normalised cross spectra of the source's bins are summed over the frames
 *     and the delay is the maximum of their correlation R(tau) = sum Re(C_k e^{i w_k tau}) over the physical lag range
 *     (5 us grid, then 0.5 us); the coherence R(tau)/count gates it (each pair >= min_quality);
 *   - a second pass finds each frame's delay near that maximum: their spread (MAD) and the solver residual give the
 *     sigma, as in zs_bearing; the three delays go to the 3+1 solver (zs_spatial).
 *
 * Portable, no allocation: the caller lends ZS_COMB_BEARING_MEMORY floats (the decimated span) and a
 * zs_comb_bearing_workspace_t (spectra, accumulators, masks); the station pipeline lends its 1 s window and the AIR
 * gate scratch, both idle once a window is analysed.
 */
#include "zs_audio.h"
#include "zs_bearing.h"
#include "zs_fft.h"
#include "zs_spatial.h"

#include <stdbool.h>
#include <stdint.h>

#define ZS_COMB_BEARING_MAX_SOURCES 3u
#define ZS_COMB_BEARING_DECIM 4u
#define ZS_COMB_BEARING_N 1024u
#define ZS_COMB_BEARING_FRAMES 7u
#define ZS_COMB_BEARING_HOP 496u
#define ZS_COMB_BEARING_TAPS 63u
#define ZS_COMB_BEARING_SPAN_DECIMATED (ZS_COMB_BEARING_N + (ZS_COMB_BEARING_FRAMES - 1u) * ZS_COMB_BEARING_HOP)   /* 4000 */
#define ZS_COMB_BEARING_SPAN (ZS_COMB_BEARING_SPAN_DECIMATED * ZS_COMB_BEARING_DECIM)                            /* 16000 at 32 kHz */
#define ZS_COMB_BEARING_MEMORY (ZS_SPATIAL_MIC_COUNT * ZS_COMB_BEARING_SPAN_DECIMATED)                               /* floats */
#define ZS_COMB_BEARING_BINS (ZS_COMB_BEARING_N / 2u + 1u)
#define ZS_COMB_BEARING_MIN_BINS 8u
#define ZS_COMB_BEARING_FMIN_HZ 80.0f
#define ZS_COMB_BEARING_FMAX_HZ 3100.0f

typedef struct {
  zs_complex_t spectrum[ZS_SPATIAL_MIC_COUNT][ZS_COMB_BEARING_N];
  zs_complex_t acc[ZS_COMB_BEARING_MAX_SOURCES][ZS_SPATIAL_REF_TDOA_COUNT][ZS_COMB_BEARING_BINS];
  uint8_t mask[ZS_COMB_BEARING_MAX_SOURCES][ZS_COMB_BEARING_BINS];
} zs_comb_bearing_workspace_t;

typedef struct {
  uint32_t attempts;         /* sources asked for */
  uint32_t computed;         /* valid bearings */
  uint32_t no_audio;         /* span not in the ring */
  uint32_t few_bins;         /* the source's own bins (after the others are excluded) too few */
  uint32_t weak;             /* coherence below min_quality */
  uint32_t unsolved;         /* solver rejected the delays */
} zs_comb_bearing_stats_t;

/* Bearings of `count` sources (fundamentals f0_hz[], 30..1000 Hz) heard in the ring span [end_sample - 16000,
   end_sample) at 32 kHz.  out[s].valid tells which succeeded, out[s].f0_hz is set for each.  `ctx` gives the geometry
   and min_quality (zs_bearing_init).  Returns the number of valid bearings. */
unsigned zs_comb_bearings_from_ring(const zs_bearing_ctx_t *ctx, zs_comb_bearing_stats_t *stats, const zs_audio_ring_t *ring,
                                    uint64_t end_sample, const float *f0_hz, unsigned count, float temperature_c, float *memory,
                                    zs_comb_bearing_workspace_t *ws, zs_bearing_t *out);

/* Same from four caller-provided channel buffers at 32 kHz of at least ZS_COMB_BEARING_SPAN + ZS_COMB_BEARING_TAPS - 1
   samples each (the span is the last ZS_COMB_BEARING_SPAN samples; the filter reads the taps before it). */
unsigned zs_comb_bearings_from_channels(const zs_bearing_ctx_t *ctx, zs_comb_bearing_stats_t *stats,
                                        const int16_t *const channels[ZS_SPATIAL_MIC_COUNT], uint32_t count_samples,
                                        const float *f0_hz, unsigned count, float temperature_c, float *memory,
                                        zs_comb_bearing_workspace_t *ws, zs_bearing_t *out);

#endif

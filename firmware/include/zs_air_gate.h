#ifndef ZS_AIR_GATE_H
#define ZS_AIR_GATE_H
/*
 * Station AIR-target gate: "is there a steady propulsion comb" — level 1 of the hierarchy, the
 * same evidence the server's DroneSeparator uses (server/audio/separation.py) with its thresholds
 * (server/config.py): harmonic comb with f0 in 12..180 Hz inside the 18..2400 Hz band, per-window
 * harmonic SNR, persistence over windows, steadiness of the dominant line, mains veto.
 *
 * Per 1 s window: decimate 32 kHz -> 6.4 kHz (9-tap triangle), Hann, 8192-point FFT (0.78 Hz bins),
 * 1.2 Hz notches on 50/60 Hz harmonics up to 200 Hz, power spectrum of the band.  The comb is fitted
 * on the running log-average spectrum of the last windows (the server fits it on the median spectrum
 * of the recording), then every window is measured at that comb (f0 refined ±10 % per window): harmonic
 * SNR with the server definition (harmonic peaks over the median band floor) plus a contrast guard
 * (harmonic peaks over half-order maxima, which cancels the max-over-bins bias of noise), harmonic count.
 * Over the history (0.5 s hop, 8 windows = 4 s): persistence, coefficient of variation of the per-window
 * fundamental (folded by integer ratios so an octave slip of the fit does not count as motion; all teeth
 * of a comb move with f0, so this is the server's line steadiness), decision as in
 * DroneSeparator._build_findings.
 * Scratch is caller-provided (ZS_AIR_SCRATCH_COMPLEX: the 8192-point FFT plus the per-window work areas,
 * ~105 KB) so the target can overlay it on the DSP work buffer; the gate itself keeps two band spectra (2 x 12 KB).
 */
#include "zs_fft.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_AIR_SAMPLE_RATE 32000u
#define ZS_AIR_WINDOW_SAMPLES 32000u
#define ZS_AIR_DECIMATION 5u
#define ZS_AIR_FFT 8192u
#define ZS_AIR_BINS 3074u        /* bins up to 2400 Hz at 0.78125 Hz */
#define ZS_AIR_HISTORY 8u
/* scratch for zs_air_gate_push: the FFT plus three band-sized float work areas and a byte mask (~105 KB) */
#define ZS_AIR_SCRATCH_COMPLEX (ZS_AIR_FFT + (3u * ZS_AIR_BINS * 4u + ZS_AIR_BINS + 7u) / 8u)

typedef struct {
  float snr_db;         /* server definition: mean harmonic peak / median of the band floor (harmonic bins excluded) */
  float contrast_db;    /* anti-noise guard: mean harmonic peak / mean half-order maximum (white noise ~0..1 dB) */
  float f0_hz;          /* fundamental refined on this window (0 when no comb was fitted) */
  float dominant_hz;    /* strongest tooth of the average comb followed at this window's f0 */
  float integer_order_ratio;
  uint8_t harmonic_count;
  uint8_t low_teeth;    /* prominent teeth among the first four (a propulsion comb is strong at the bottom) */
  bool comb;            /* snr_db >= 6 dB (server), contrast_db >= 3 dB, >= 2 harmonics, low_teeth >= 2 */
} zs_air_window_t;

typedef struct {
  float spectrum[ZS_AIR_BINS];     /* power spectrum of the last window */
  float avg_log[ZS_AIR_BINS];      /* running mean of log power over the history (geometric mean) */
  zs_air_window_t hist[ZS_AIR_HISTORY];
  uint8_t next, count;
  float f0_hz;                     /* comb fundamental fitted on avg_log, 0 = no line */
  float anchor_hz;                 /* strongest tooth of that comb on avg_log */
} zs_air_gate_t;

typedef struct {
  bool present;         /* AIR target confirmed by the gate */
  bool mains;           /* rejected as 50/60 Hz hum / grid-locked genset */
  float persistence;    /* share of history windows with a comb */
  float median_snr_db;      /* server-definition SNR, report only */
  float median_contrast_db; /* the gate's SNR (half-order contrast) */
  float steadiness_cv;  /* std/mean of the folded per-window fundamental over comb windows */
  float f0_hz;          /* folded median fundamental of the comb windows (fit value when none) */
  uint8_t harmonic_count;
  uint8_t confidence_u8; /* server _confidence blend without the separation-gain term */
} zs_air_gate_result_t;

void zs_air_gate_init(zs_air_gate_t *g);
/* Analyses one 32000-sample window (any channel), pushes it into the history and evaluates the gate.
   scratch >= ZS_AIR_SCRATCH_COMPLEX complex.  Returns false only on bad arguments. */
bool zs_air_gate_push(zs_air_gate_t *g, const int16_t *pcm, size_t n, zs_complex_t *scratch, zs_air_gate_result_t *out);
/* Evaluates the current history (diagnostics). */
zs_air_gate_result_t zs_air_gate_evaluate(const zs_air_gate_t *g);
/* The last window's measurement (diagnostics). */
const zs_air_window_t *zs_air_gate_last(const zs_air_gate_t *g);

#endif

# B1: porting zs_dsp to the MCU - plan and first step (2026-09-21)

## Why the host zs_dsp.c cannot run on the STM32U585 as is

- static memory ~430 KB: g_fft 32000 complex (256 KB), g_mag (64 KB), g_peaks int[16001] (64 KB),
  g_peak_state (16 KB), g_mel 63x128 floats (32 KB);
- the recursive mixed-radix FFT calls cosf/sinf per (k, node): about 5e5 trig evaluations per
  32000-point transform, seconds on a Cortex-M33 at 160 MHz;
- double-precision accumulations (means, energies) run in software on the M33 (no double FPU);
- recursion depth and stack use are fine (radix 4/5 over 7 levels).

The feature definitions themselves (43 features, golden acceptance: median normalized error
<= 3 %, p95 <= 5 %) stay exactly as on the host; only the implementation changes.

## Step 1 (done): float32 mixed-radix FFT with twiddle recurrence

`zs_fft_mixed` keeps the host decimation structure (radix 4, then 5, then 2) so the bin
definition is identical, generates twiddles by rotation with a sincos re-sync every 32 steps,
uses hard-coded radix-4/5 butterflies and a packed real transform (16000-point complex FFT
for the 32000-sample window).

Host results (test_fft_mixed):
- vs double-precision reference: max error 9.6e-7 of the peak, mean relative error 1.7e-6;
- vs the host zs_dsp global spectrum on the same preprocessing: max diff 3e-5 of the peak
  (the host's own float accumulation noise), 7x faster on x86; on the M33 the gain is larger
  because trig calls dominate there;
- memory for the global spectrum: work (128 KB) + mag/packed input (128 KB) = 256 KB, host 320 KB.
  An in-place iterative variant (128 KB total) is a follow-up.

## Remaining steps

2. `zs_dsp_mcu.c`: same 43 features on top of zs_fft_mixed, all accumulations in float or int64,
   peak search without the int[16001] array (bit-set state + streaming peak list, ~4 KB),
   STFT 2048/512 and YIN 8192 through zs_fft_mixed_complex (8192 = 2^13, radix 4/2),
   scratch overlay: mag (64 KB) persists while YIN/STFT reuse the second 64 KB of `work`.
3. Golden check: `zs_eval_golden` run on the 100 windows (PCM inputs are outside the repository:
   the customer audio must be present locally) with the acceptance thresholds above; a host
   A/B test zs_dsp vs zs_dsp_mcu on synthetic signals is added to ctest as a proxy.
4. Target: link zs_dsp_mcu into the app, measure S2 window time and audio task CPU share on the
   NUCLEO-U575; target budget for one 1 s window < 250 ms at 160 MHz.
5. Retire zs_fft.c / zs_dsp.c from the target library once 3-4 pass; keep them for the host tools.

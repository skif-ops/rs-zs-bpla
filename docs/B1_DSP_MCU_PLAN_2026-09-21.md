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

## Step 2 (done): `zs_dsp_mcu` - the 43 features on the MCU

Same definitions, band limits, thresholds and ordering as zs_dsp.c; float32 only (chunked
accumulation, int64 for the DC sum); YIN 8192 and STFT 2048 through zs_fft_mixed_complex
(inverse via conj/FFT/1/N); MFCC DCT and STFT window as tables built once; peaks as uint16 list
+ byte state overlaid on the tail of the magnitude buffer, mel matrix overlaid there after the
harmonics; median scratch in the FFT work buffer. Static scratch 278 KB (work 128 + mag 128 +
tables/small arrays).

Host A/B test (test_dsp_mcu, 16 synthetic windows x 43 features vs zs_dsp): median normalized
error 0.0000, p95 0.0000, max 3e-4 (fundamental_variation) - the two implementations agree far
inside the golden acceptance. Host time per window 26 ms vs 28 ms (x86 hides the trig cost that
dominates on the M33).

Target: linked into the B1 app behind the console command `dsp` (last 1 s of channel 0, DWT
cycle count). Image: 68 KB flash, 708 KB RAM (90 % of SRAM1-3: audio ring 256 KB, DSP 278 KB,
1 s mono copy 64 KB, heap 64 KB, DMA 10 KB). RAM relief for later: feed the extractor from the
ring without the 64 KB copy, in-place FFT (-128 KB), prehistory to NOR (B3).

## Step 3 (done 2026-09-22): golden check on customer audio

The «Лютый» recording of 2026-09-20 (three 32 kHz WAVs, confirmed by video) replaces the missing June
archive: `server/tools/generate_golden_vectors.py` cut 100 windows and computed the server reference,
`server/tools/check_golden_vectors.py` ran both firmware extractors (`zs_eval_golden`, new
`zs_eval_golden_mcu`) over them. Result: `zs_dsp_mcu` median/p95 normalized error 0.0000/0.0000, max
0.0034; F0, harmonic step and harmonic count exact in 100 % of windows (`server/tools/golden_lyuty/`).
The MCU port reproduces the server features on real drone audio; what remains is the time budget.

## Remaining steps

4. Target: link zs_dsp_mcu into the app, measure S2 window time and audio task CPU share on the
   NUCLEO-U575; target budget for one 1 s window < 250 ms at 160 MHz.
5. Retire zs_fft.c / zs_dsp.c from the target library once 3-4 pass; keep them for the host tools.

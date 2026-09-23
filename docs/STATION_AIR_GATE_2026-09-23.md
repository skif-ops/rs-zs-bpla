# Station AIR gate (level 1 on the station) — 2026-09-23

`firmware/src/zs_air_gate.c` ports the evidence of the server's `DroneSeparator` (server/audio/separation.py,
thresholds from server/config.py) to the station as a second level-1 signal next to the centroid classifier:
a *steady propulsion comb* over several seconds.

* Per 1 s window: decimate 32 kHz -> 6.4 kHz (9-tap triangle), Hann, 8192-point FFT (0.78 Hz), 1.2 Hz notches on
  50/60 Hz harmonics up to 200 Hz; the comb (f0 12..180 Hz, band 18..2400 Hz, up to 16 teeth) is fitted on the
  running geometric-mean spectrum of the last 8 windows (the server fits on the median spectrum of the recording),
  anchored on the most *prominent* line (power over ±32 Hz surroundings) so wind rumble cannot anchor it, with the
  server's missing-fundamental descent (a lower f0 needs 3 of its first 4 teeth incl. the 1st or 2nd) and ±5 % fine grid.
* Per window at that comb (f0 refined ±10 %): harmonic count (teeth >= floor + 6 dB), the server SNR (teeth over
  the median band floor, report only) and the **contrast** = mean tooth maximum / mean half-order maximum. The
  contrast cancels the max-over-bins bias of the server definition: white noise gives 0..1 dB of contrast but
  4..8 dB of server SNR, and on a distant windy recording the server SNR reads 20..30 dB with < 0 dB contrast.
  Gate thresholds are therefore re-calibrated on contrast: comb >= 3 dB, strong >= 8 dB, steadiness relaxed >= 12 dB.
* Over 8 windows (4 s at 0.5 s hop): persistence >= 0.35, median contrast >= 3 dB, steadiness cv of the per-window
  fundamental <= 0.12 (0.24 when loud; exact ×2/×3 slips of the fit are folded, glides are not), >= 4 teeth
  (2 when strong), mains veto (f0 within 2 Hz of 50/60 with cv <= 0.02 or a pure integer-order comb), the comb
  must be present in the current or the previous window (no "present" hangover after the source stops), and the
  folded median f0 must be airborne-plausible: **30..300 Hz** (station-only; a ground engine idles below 30 Hz — the
  APC on the Muhoed recording sits at 15 Hz — and a cicada chorus combs at 500+ Hz, UAV props/engines in between).
  Confidence = the server blend without the separation-gain term.
* Cost: one 8192-point float FFT per window (64 KB scratch, caller-provided), two 12 KB band spectra in the state.

Host test (`firmware/tests/test_air_gate.c`): synthetic comb with Doppler drift and a high blade-pass quadcopter
pass; white noise, bird-like chirp, gunfire-like impulses, 50 Hz hum and a siren-like glide are rejected.
Golden windows of the «Лютый» recording (server/tools/golden_lyuty): file 1 (close pass) present in 12/14 windows,
file 2 (maneuvering, f0 wobbling 25 %) 10/14, file 3 (55 s, distant, windy) 0/66 — the third file has no comb the
gate can see (contrast < 3 dB); whether the drone is audible there is to be confirmed by ear.

Muhoed recordings (`server/tools/eval_air_gate_wavs.py`, dataset.zip of 2026-09-23; share of windows with the gate
confirmed, 1 s windows at 0.5 s hop, 2 warm-up windows excluded):

| label | files / windows | present |
|---|---|---|
| DJI Mini 3 Pro | 1 / 161 | 57 % (f0 128..260 Hz, contrast ~10 dB, 12 teeth; misses where the fit alternates between 128 and 256 Hz) |
| Лютый (2026-09-20) | 3 / 135 | 21 % (86 % / 71 % / 3 % per file, see above) |
| природный фон | 1 / 357 | 0 % |
| цикады и насекомые | 2 / 93 | 0 % (a 520..540 Hz chorus comb, rejected by the airborne f0 range) |
| стрельба из бронетранспортера | 1 / 22 | 0 % (idling APC engine: 15 Hz comb, 15 teeth, rejected by the airborne f0 range) |
| стрельба | 1 / 24 | 25 % (a rock-steady 100..105 Hz comb with 12..15 teeth, cv 0.002, in 5 s of the sample: an engine or a synthetic tone in the library sound — to be checked by ear; a comb this steady on a non-mains f0 is the remaining false-positive shape) |
| птицы, трактор, городской транспорт | — | the archive's WAVs are empty placeholders; not measured |

Next: combine with the centroid classifier in `zs_classifier_consensus` (gate-confirmed comb raises presence,
background-class + no comb lowers it); re-run the eval once the empty labels are provided.

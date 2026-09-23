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
  the median band floor, report only), the **contrast** = mean tooth maximum / mean half-order maximum, and the
  number of *prominent* teeth among the first four (`low_teeth`: >= 3 dB over ±32 Hz surroundings). The
  contrast cancels the max-over-bins bias of the server definition: white noise gives 0..1 dB of contrast but
  4..8 dB of server SNR, and on a distant windy recording the server SNR reads 20..30 dB with < 0 dB contrast.
  Gate thresholds are therefore re-calibrated on contrast: comb >= 3 dB, strong >= 8 dB, steadiness relaxed >= 12 dB.
  A window is a comb only with >= 2 prominent low teeth: a propulsion comb is strong at the bottom, whereas a bird
  trill at 1.5 kHz fitted as a 16th harmonic (MP3 bird recordings have almost nothing below 400 Hz) has none.
  The same prominence rule guards the missing-fundamental descent (wind rumble is above the global floor
  everywhere below 40 Hz and used to pull the fit to 12 Hz on Mavic recordings).
* Over 8 windows (4 s at 0.5 s hop): persistence >= 0.35, median contrast >= 3 dB, steadiness cv of the per-window
  fundamental <= 0.12 (0.20 when loud — the server caps at 0.25, a 30 %/s glide reaches 0.24; exact ×2/×3 slips of
  the fit are folded, glides are not), >= 3 comb windows, >= 4 teeth (2 when strong), mains veto (f0 within 2 Hz of 50/60 with cv <= 0.02 or a pure integer-order comb), the comb
  must be present in the current or the previous window (no "present" hangover after the source stops), and the
  folded median f0 must be airborne-plausible: **30..300 Hz** (station-only; a ground engine idles below 30 Hz — the
  APC on the Muhoed recording sits at 15 Hz — and a cicada chorus combs at 500+ Hz, UAV props/engines in between).
  Confidence = the server blend without the separation-gain term.
* Cost: one 8192-point float FFT per window (64 KB scratch, caller-provided), two 12 KB band spectra in the state.

Host test (`firmware/tests/test_air_gate.c`): synthetic comb with Doppler drift and a high blade-pass quadcopter
pass; white noise, bird-like chirp, gunfire-like impulses, 50 Hz hum and a +15 %/s glide are rejected.
Golden windows of the «Лютый» recording (server/tools/golden_lyuty): file 1 (close pass) present in 14/14 windows,
file 2 (maneuvering, f0 wobbling 25 %) 10/14, file 3 (55 s) 0/66. The owner confirms the drone is audible in all
three files: file 3 is a *distant* target with speech over it and no comb the gate can see (contrast < 3 dB) —
the range limit of the comb evidence; level 1 there rests on the centroid classifier.

Muhoed recordings and field uploads (`server/tools/eval_air_gate_wavs.py`; share of windows with the gate confirmed,
1 s windows at 0.5 s hop, 2 warm-up windows excluded; dataset.zip of 2026-09-23 plus the uploads of the same day):

| label | files / windows | present |
|---|---|---|
| DJI Mini 3 Pro | 1 / 161 | 63 % (f0 128..260 Hz, contrast ~10 dB, 12 teeth) |
| DJI Mavic 3 Pro (field, 2026-09-09) | 4 / 332 | 34 % — 98 % and 72 % on the two close passes (f0 ~172 Hz, 13 teeth, contrast 10..19 dB), 27 % and 3 % on the two distant/hovering recordings (contrast <= 3 dB) |
| Лютый (2026-09-20) | 3 / 135 | 20 % (100 % / 71 % / 0 % per file, see above) |
| природный фон | 1 / 357 | 0 % |
| цикады и насекомые | 2 / 93 | 0 % (a 520..540 Hz chorus comb, rejected by the airborne f0 range) |
| птицы (5 MP3s, 856 windows) | 5 / 856 | 10 % — 63 of the 88 windows are an *engine-like* comb (f0 90..110 Hz, 8..14 teeth, contrast up to 15 dB, cv 0.01..0.03) in the three 2-minute field recordings, i.e. background machinery in the "bird" downloads (43eb: 36..40 s, 60..68 s, 76..102 s; 46dd: 14..22 s, 65..68 s, 86..118 s; 7af6: 97..102 s); 7 windows are a 290..310 Hz line (cooing-like, inside the airborne range); 18 are scattered singles |
| стрельба из бронетранспортера | 1 / 22 | 14 % (APC engine: 15 Hz idle rejected; 3 windows at 45..48 Hz while it revs — a ground engine inside the airborne range) |
| стрельба | 1 / 24 | 17 % (the 100..105 Hz comb in seconds 7..10 is, per the owner, the APC again) |

The remaining false-positive shape is therefore one thing: **a ground engine (APC, generator, tractor) whose firing
or blade-pass line falls into 30..300 Hz**. The comb evidence cannot separate it from a UAV engine by itself — that
is the classifier's job (families), and the reason the gate is combined with the centroid classifier rather than
replacing it.

Next: combine with the centroid classifier in `zs_classifier_consensus` (gate-confirmed comb raises presence,
background-class + no comb lowers it; a comb with a ground-vehicle class stays "engine, not confirmed airborne").

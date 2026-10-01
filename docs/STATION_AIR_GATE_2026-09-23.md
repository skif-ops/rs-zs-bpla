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

## Several sources at once (2026-10-01)

Two targets heard at once broke the single-comb fit: 185 Hz + 120 Hz are both near multiples of 61 Hz, the fit took
that common sub-harmonic, the gate rejected it as mains and the classifier saw a ground engine.  The gate now
separates sources (`zs_air_gate.h`, `separate_sources` in `zs_air_gate.c`):

- a mixture is suspected only when the fit lands on a sub-harmonic of the strongest line *below* that line's own
  comb (the lowest dominant/k with five of six real teeth): a single source whose fit is its true fundamental (the
  APC at 104 Hz with its 5th harmonic strongest) is never split;
- the own comb is notched out (a fixed notch of 4 % of each harmonic: the Doppler smear on the 4 s average) and
  the rest searched line by line: a comb with at least three real teeth among its first six known positions (teeth
  inside notched bands count neither way), at least a twentieth (`SECONDARY_MIN_POWER` 0.05) of the main comb's
  power, present in the current window too, and in no integer ratio (within 6 %) to a known comb - a leftover of a
  smeared line is the known comb's harmonic - is another source; after the own comb is known, 3:2 is another source;
- a comb starts a source track only in a fit that shows a mixture and counts once it is found in three fits more
  than missed (+1 found, -1 missed, max 6, 4 % drift); the common sub-harmonic of two counting sources is not one;
- the stronger comb is the gate's line (the other must be 1 dB stronger to take over, so two sources of about the
  same level do not swap from fit to fit); up to two others are reported, only beside a present source, and the
  pipeline notches them out of the window before the classifier (`zs_air_gate_suppress_secondary`, IIR comb with
  fractional delay, about 10 dB on the other comb's teeth, under 1 dB on the tracked one).

Twin recordings of station 17 (`presence_eval`, 358 windows, the same synthetic sources as the field run):

| Sound at the station | confirmed before | confirmed now | gate present now | separated windows |
|---|---|---|---|---|
| one target, 185 Hz | 314 | 314 | 356 | 0 |
| 120 Hz alone / 290 Hz alone | 218 / 261 | 218 / 261 | 356 / 356 | 0 |
| two targets, 185 + 120 Hz | 64 (gate 100) | 153 | 318 | 315 |
| three targets, 185 + 120 + 290 Hz | 18 (gate 98) | 66 | 287 | 284 |

The remaining loss is the classifier: the synthetic 120 Hz source alone is called agricultural (class 14) in 27 %
of its windows, and the three-target windows keep one of the other sources partly (184 of 287 windows class 14).

Real recordings (38 files, `presence_eval` before/after): confirmed windows unchanged on every non-UAV file
(birds 3, gunfire 2, tractors 0, city 0); suspect windows birds 230 -> 231, tractors 44 -> 37, city traffic 16 -> 9;
DJI Mavic 3 Pro 296 -> 296 confirmed; DJI Mini 3 Pro 150 -> 149.  Test: `firmware/tests/test_air_gate.c`
(`test_two_sources`: 120 + 183 Hz separated in 14 of 14 windows, single sources get no secondary comb, the
suppression takes about 10 dB off the other comb).

## Each source its own target (2026-10-01)

The gate finds the sources; the station pipeline (`zs_station_pipeline.h`) now follows each of them as a target of
its own instead of classifying the strongest one only:

- source tracks (`ZS_PIPELINE_SOURCES` 3): the gate's main comb and its secondary combs are matched to tracks by
  fundamental (at most 6 % per window; `window_f0_hz`, the main comb on the last window, folded like `f0_hz`); a track
  missed by the gate is kept for 8 windows if it was heard together with another source and is not of the same
  harmonic family as one heard now (a single engine's further combs never become remembered sources);
- one classification per window as before (the feature extraction is the costly part, 37 ms on the host): a window
  of a mixture classifies one target in turn, with the combs of all the others suppressed (`zs_air_gate_suppress_combs`,
  the main one included when it is not the turn's); each track keeps its own consensus votes and presence; the station
  is CONFIRMED when the main stream or any source is;
- bearings of every source of a mixture in every window (`zs_comb_bearing.h`): the bins within max(1 bin, 1.2 %) of
  the source's harmonics (80-3100 Hz, minus a twice wider guard around the other sources' harmonics), decimated to
  8 kHz, 7 Hann frames of 1024, PHAT cross-spectra summed over the frames, the delay from the correlation maximum
  (5 us then 0.5 us steps and a parabola), a coherence gate, per-frame delays for sigma; 3.1 ms on the host for three
  sources;
- combs whose bearings agree (within max(6 deg, 2 sigma)) for 3 windows are one target (an agreeing window counts
  +1 up to 6, a disagreeing one -2; apart again at 0, after 2-3 windows of disagreement): a multirotor's rotors at
  different speeds and an engine's further combs are classified and reported as one, without rotation (the window is
  classified as one sound, the other combs not suppressed); a new comb starts merged with the known ones until its
  bearings disagree;
- each bearing carries its source's fundamental (bearing batch schema 2, ICD addendum H §1.1, §3); the server splits
  a station track into segments by fundamental as well as by direction.

The gate itself is unchanged.  Changes to the gate's own search for three sources at once (the highest real
sub-fundamental instead of the most powerful, a two-tooth "complete" own comb, a looser per-window check when two
other sources crowd the window, wider removal of a no-comb line) gave about 20 % more bearings of the third target in
the twin field but split a tracked tractor's 34 Hz comb into "sources" (suspect windows 24 -> 34, city traffic 4 -> 11)
and were dropped.

Real recordings (38 files, 5312 windows, `presence_eval`, which now runs the pipeline through the capture ring with
the recording on channel 1 and the other channels delayed as a plane wave from one direction): confirmed windows
unchanged on every file; the level changed in 5 windows (tractor moving: suspect 4 -> 6, street noise: suspect
5 -> 2) and the class in 4, all at or just after windows where the gate reports a second comb from the same direction,
which is no longer suppressed (the votes carry it over a few windows); the sum of UAV votes over the DJI Mini 3 Pro
windows 916 -> 972.  Tests: `firmware/tests/test_comb_bearing.c`,
`firmware/tests/test_pipeline_sources.c` (two directions: both sources confirmed, bearings with mean error about
1 deg; one direction: one target, no rotation).  Field results with two and three targets:
`docs/STATION_TWIN_FIELD_2026-10-01.md` §5.

Limits: the gate separates combs by pitch only.  Two sources with fundamentals in a small integer ratio (DJI Mavic 3
Pro 174 Hz and Mini 3 Pro 261 Hz are 2:3) look like one comb of 87 Hz, and two of the same type within 4 % are not
separated at all.  Done next (2026-10-01): separation by direction before pitch, each direction classified on its own
window (`docs/STATION_DIRECTION_SEPARATION_2026-10-01.md`, `firmware/include/zs_doa_sep.h`).

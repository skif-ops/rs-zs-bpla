# Station level 1: centroid votes + AIR gate, and the dataset rate fix — 2026-09-23

## Fusion (`firmware/src/zs_presence.c`)
Per window the station has two independent pieces of evidence: the centroid classifier vote (kept for 4..8 windows
by `zs_classifier_consensus`) and the AIR gate (`zs_air_gate`: a steady, airborne-plausible propulsion comb over
the last 4 s). `zs_presence_evaluate` turns them into one level-1 verdict:

| evidence | verdict |
|---|---|
| UAV majority (5/8 votes at conf >= 128) | CONFIRMED — with or without the comb (distant target: Lyuty file 3, Mavic far away) |
| comb + >= 2 UAV votes | CONFIRMED |
| comb + ground-engine majority (road traffic, agricultural, generator) | ENGINE_UNCONFIRMED — the one false-positive shape the gate cannot resolve alone |
| comb, no classifier support | SUSPECT |
| >= 2 UAV votes, no comb | SUSPECT |
| otherwise | NONE |

Family/type stay with the consensus and the server hierarchy. Host test `firmware/tests/test_presence.c`;
`firmware/tools/presence_eval.c` + `server/tools/eval_presence_wavs.py` run the whole chain
(zs_dsp -> centroids -> consensus, zs_air_gate -> zs_presence) over WAV directories.

## What the end-to-end run exposed: the dataset was not at the station's rate
`server/dataset/features.csv` held rows extracted at each recording's *native* rate (44.1 kHz birds/tractor/nature,
48 kHz DJI Mini 3 Pro/FP-1, 32 kHz Lyuty) while the station always computes the 43 features on 32 kHz audio.
The features are rate-dependent (YIN, MFCC, mel bank): on the DJI Mini 3 Pro file the dataset had f0 ~76 Hz and
mfcc_mean_0 = -88 where the station computes f0 ~230 Hz and mfcc_mean_0 = -1 — so the station classified the
same file as low-confidence "piston" (0 % confirmed, 63 % suspect) although the dataset test showed DJI recall 1.00.
Loading the same file at 32 kHz makes server and firmware features identical again (max normalized error 3e-4).

Fixes (server):
* `settings.target_analysis_sample_rate_hz = 32000` (was declared but unused): `AudioLoader` resamples every
  recording to the station rate on load (soxr_hq); `tests/test_loader.py`.
* `settings.ml_window_peak_normalize = True`: dataset windows are DC-removed and peak-normalized individually
  before extraction (`normalize_window_like_station`), as the station does per window (the file-level peak made
  rms/average_energy/mfcc_mean_0 file-dependent: DJI rms 0.11 in the dataset vs 0.23 on the station for the same audio).
* `tools/rebuild_dataset_at_station_rate.py`: re-extracts every recording of the dataset from `dataset/raw`
  with the metadata kept, backs the old CSV up and replaces it. **To be run on the Muhoed server, where all raw
  recordings are** (here only the DJI file was available); then `tools/export_station_model.py` regenerates the
  station table and `tests/test_station_presence_model.py` re-validates it.

Preview with only the DJI recording rebuilt (in-sample for DJI, out-of-sample for everything else):

| label | confirmed / suspect before | after the DJI rebuild |
|---|---|---|
| DJI Mini 3 Pro | 0 % / 63 % | **94 % / 6 %** |
| DJI Mavic 3 Pro (not in the dataset) | 35 % / 42 % | **73 % / 20 %** |
| Лютый | 90 % / 9 % | 87 % / 10 % |
| natural background, cicadas | 0 % | 0 % |
| birds (MP3, engines in the background) | 0 % / 11 % | 0 % / 11 % |

`tests/test_station_presence_model.py::test_dataset_rows_are_at_the_station_rate` prints how much of the dataset
still predates the rebuild.

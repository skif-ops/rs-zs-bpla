# Station audio pipeline (S2 detection duty) — 2026-09-23

`firmware/src/zs_station_pipeline.c` closes the chain on the station: capture ring → 1 s windows at a
0.5 s hop → `zs_dsp_mcu` (43 features) → centroid classifier + 4..8-window consensus → `zs_air_gate` →
`zs_presence` (level 1) → detection events (schema 4) into the NOR event outbox.

## Event policy

| level 1 (`zs_presence`) | action |
|---|---|
| CONFIRMED, rising edge | detection event (priority 2) |
| CONFIRMED, every 10 windows (5 s) | detection event (keep-alive; the server keeps the track alive on updates) |
| SUSPECT / ENGINE_UNCONFIRMED / NONE | counted only (`dsp` console line); no event |

The event carries the last window's features, the consensus classification and hierarchy, the level-1
confidence in `classification.confidence_u8`, and `detector_profile` from the consensus family (1 piston,
2 reactive, 0 generic). When level 1 confirms before the 5/8 type consensus (comb + ≥ 2 UAV votes) the
event names the leading UAV class among the votes with `unknown` still set and `family_status = CANDIDATE`.
Time is `zs_time_for_sample(window_end)` (0 until PPS trust); `event_id = boot_id << 32 | seq_no`.

## Target layout (B1 app)

- audio task (prio 6): after each MDF block, `zs_station_pipeline_fetch` copies the next complete window
  out of the ring (channel 0, ~1 ms) while it is still there and notifies the dsp task; a window that is
  still pending when the next completes is skipped and counted (`windows_dropped`).
- dsp task (prio 2): `zs_station_pipeline_run_pending` — extractor, votes, gate, level 1, event; the time
  of the last/longest window is on the `dsp` console line.
- RAM: the AIR gate scratch (`ZS_AIR_SCRATCH_COMPLEX` ≈ 105 KB: FFT + per-window work areas, which used
  to be statics in zs_air_gate.c) overlays the DSP work buffer (`zs_dsp_mcu_borrow_work`), the 1 s mono
  window is the former `dsp_pcm`; the ring grew to 1.125 s (288 KB) to cover the fetch latency; heap 40 KB.
  Image: 114 KB flash, 754 KB RAM (95.9 % of SRAM1-3) at merge; with the B2 comms task 763 KB (97.0 %).
  2026-09-23 RAM relief (after #48): in-place global FFT in zs_dsp_mcu (`zs_fft_mixed_real_magnitude_inplace`,
  the magnitude buffer shrinks to 64 KB and the peak/mel tail moves into the upper half of the work buffer),
  the AIR gate keeps only its running average (the window spectrum lives in the scratch tail), the channel-lag
  self-test correlates straight out of the ring, and one 2 KB quarter-wave cosine table replaces the Hann
  window and DCT tables: 658 KB RAM (83.6 %), 140 KB flash. Remaining relief if needed: 2-channel ring outside
  the spatial duty, heap trim after the bench `heap` reading.
- `zs_fft.c` (float radix-2) is now part of the target library for the gate; `zs_dsp.c` stays host-only.
- Ring range check fixed in `zs_audio.c`: a copy whose *start* the ring has already overwritten is refused.

## Host results

`test_station_pipeline` (stub extractor returning de-normalized dataset centroids, synthetic 94 Hz comb /
noise): rising edge on comb + 4 UAV votes, keep-alive cadence, refusal accounting, drop after departure and
a new edge on return, ring-overrun accounting. Host time per window: `zs_dsp_mcu` 27.6 ms, AIR gate 0.6 ms,
classifier + fusion < 0.1 ms (x86); the M33 figure for the whole window is the acceptance measurement
(`dsp` line, target < 250 ms at 160 MHz).

## Open

- boot_id from a NOR boot counter (B3) — the bench uses `APP_BOOT_ID = 1`;
- ~~outbox drain to the BG95 uplink (B2)~~ — done in #48 (`zs_station_comms`, `app_comms`);
- heartbeat with the pipeline counters (SUSPECT/ENGINE shares) for the server.

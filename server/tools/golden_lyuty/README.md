# Golden vectors — «Лютый», 2026-09-20 (confirmed customer recording)

100 windows of 1.0 s cut on the production 0.5 s grid from the three 32 kHz mono WAVs of
`lyuty_confirmed_2026-09-20` (dataset package, 8.7 s + 9.0 s + 55.4 s, phone video AAC -> PCM16):
`lyuty_2026-09-20_1.wav`, `_2.wav`, `_3.wav`. Reference features: server `audio.features.FeatureExtractor`
through `tools/generate_golden_vectors.py --count 100`; PCM windows are regenerated from the WAVs
(`pcm16le/vec_NNN.bin`, not committed).

Result 2026-09-22 (`tools/check_golden_vectors.py`, host builds of both firmware extractors):

| extractor | normalized error median / p95 / max | fundamental_hz | harmonic_step_hz | harmonic_count |
|---|---|---|---|---|
| `zs_dsp` (host reference port) | 0.0000 / 0.0000 / 0.0060 | ±2 Hz in 100 % | ±2 Hz in 100 % | ±1 in 100 % |
| `zs_dsp_mcu` (float32, MCU port) | 0.0000 / 0.0000 / 0.0034 | ±2 Hz in 100 % | ±2 Hz in 100 % | ±1 in 100 % |

Both are far inside the acceptance (median <= 3 %, p95 <= 5 %); the largest deviations are in
`mfcc_mean_10` / `spectral_flatness` / `noise_floor` at the 1e-4 level. Host time per window: 30 ms
(`zs_dsp`) vs 27 ms (`zs_dsp_mcu`); the MCU gain is in the removed double math and trig, not visible on x86.

Reproduce:

    cd server && PYTHONPATH=. python tools/generate_golden_vectors.py --src <dir with the 3 WAVs> --out /tmp/golden --count 100
    cmake -S firmware -B build && cmake --build build --target zs_eval_golden zs_eval_golden_mcu
    python server/tools/check_golden_vectors.py --golden /tmp/golden --binary build/zs_eval_golden --binary build/zs_eval_golden_mcu

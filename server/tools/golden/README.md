# Golden vectors

Generated from the non-empty original audio files recovered from the supplied June 2026 archive.

- Count: 100 windows
- Input: mono PCM16LE, 32000 Hz, exactly 1.0 s
- Feature vector: 43 values in `feature_order.txt`
- Server reference: current `audio.features.FeatureExtractor`
- MCU acceptance: median normalized error <=3%, p95 <=5%, with separate absolute tolerances for F0/harmonic features.

The windows are a regression fixture, not a statistically representative training dataset.

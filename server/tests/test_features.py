import numpy as np

from audio.features import FeatureExtractor
from audio.preprocessing import adaptive_window_rms_threshold


def test_feature_extractor_finds_drone_like_tone():
    sample_rate = 24_000
    duration = 1.2
    fundamental = 94.0
    time = np.arange(int(sample_rate * duration)) / sample_rate
    signal = np.zeros_like(time)
    for harmonic in range(1, 12):
        signal += (1.0 / harmonic) * np.sin(2 * np.pi * fundamental * harmonic * time)
    signal += 0.02 * np.sin(2 * np.pi * 7_200 * time)
    signal = signal / np.max(np.abs(signal))

    result = FeatureExtractor().extract(signal.astype(np.float32), sample_rate)

    assert 80.0 <= result.features.fundamental_hz <= 110.0
    assert result.features.harmonic_count >= 6
    assert result.features.rms > 0.1


def test_adaptive_rms_gate_ignores_one_clipping_impulse():
    sample_rate = 1_000
    signal = np.full(20 * sample_rate, 0.0012, dtype=np.float64)
    signal[2 * sample_rate] = 1.0

    threshold = adaptive_window_rms_threshold(
        signal,
        window_size=sample_rate,
        hop_size=sample_rate // 2,
        configured_threshold=0.005,
    )

    assert 0.0005 <= threshold < 0.0012


def test_adaptive_rms_gate_keeps_normal_configured_threshold():
    signal = np.full(10_000, 0.1, dtype=np.float64)

    threshold = adaptive_window_rms_threshold(
        signal,
        window_size=1_000,
        hop_size=500,
        configured_threshold=0.005,
    )

    assert threshold == 0.005

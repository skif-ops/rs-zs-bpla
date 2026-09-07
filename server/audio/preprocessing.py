"""Audio preprocessing utilities."""

from __future__ import annotations

import numpy as np

from config import settings


class AudioPreprocessor:
    """Normalize audio and collect quality warnings."""

    def prepare(self, signal: np.ndarray, sample_rate: int) -> tuple[np.ndarray, list[str]]:
        """Remove DC offset, normalize amplitude and validate sample rate."""

        warnings: list[str] = []
        prepared = np.asarray(signal, dtype=np.float64)

        if prepared.size == 0:
            raise ValueError("Audio file is empty.")

        if sample_rate < settings.min_sample_rate_hz:
            warnings.append(
                "Sample rate is below 20 kHz; high-frequency drone noise "
                "features may be unreliable."
            )

        if not np.all(np.isfinite(prepared)):
            warnings.append("Audio contained NaN/Inf values; they were replaced by zero.")
            prepared = np.nan_to_num(prepared)

        prepared = self.remove_dc(prepared)
        prepared = self.normalize_peak(prepared, warnings)
        return prepared.astype(np.float32), warnings

    @staticmethod
    def remove_dc(signal: np.ndarray) -> np.ndarray:
        """Remove DC component from a signal."""

        return signal - float(np.mean(signal))

    @staticmethod
    def normalize_peak(signal: np.ndarray, warnings: list[str]) -> np.ndarray:
        """Normalize signal to the [-1, 1] range using peak amplitude."""

        peak = float(np.max(np.abs(signal)))
        if peak < 1e-12:
            warnings.append("Audio is silent or near-silent after DC removal.")
            return signal
        return signal / peak


def common_duration_seconds(signals: list[np.ndarray], sample_rate: int) -> float:
    """Return duration shared by all signals."""

    if not signals:
        return 0.0
    min_samples = min(len(signal) for signal in signals)
    return min_samples / float(sample_rate)


def adaptive_window_rms_threshold(
    signal: np.ndarray,
    window_size: int,
    hop_size: int,
    configured_threshold: float,
) -> float:
    """Protect window selection from one isolated peak or clipping impulse.

    Peak normalization can leave most of a valid flyover below a fixed RMS
    gate when one short handling impulse defines the file peak. The adaptive
    floor retains the configured threshold for ordinary recordings and lowers
    it only when the median window level proves that most of the file is quieter.
    """

    x = np.asarray(signal, dtype=np.float64).reshape(-1)
    if x.size == 0:
        return float(configured_threshold)
    window_size = max(int(window_size), 1)
    hop_size = max(int(hop_size), 1)
    if len(x) < window_size:
        starts = [0]
    else:
        starts = range(0, len(x) - window_size + 1, hop_size)
    levels = []
    for start in starts:
        window = x[start : start + window_size]
        if window.size:
            levels.append(float(np.sqrt(np.mean(np.square(window)))))
    finite = np.asarray([value for value in levels if np.isfinite(value) and value > 0.0])
    if finite.size == 0:
        return float(configured_threshold)
    robust = 0.25 * float(np.median(finite))
    floor = 0.10 * float(configured_threshold)
    return float(min(configured_threshold, max(floor, robust)))

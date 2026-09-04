"""GCC-PHAT delay estimation for the 3+1 microphone array.

The function gcc_phat_delay_us(reference, other) returns t_other - t_reference
in microseconds. Positive means the signal arrives later at ``other``.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .geometry import (
    DEFAULT_GEOMETRY_3P1,
    SpatialGeometry,
    SpatialSolution,
    direction_from_reference_tdoas_us,
    speed_of_sound_mps,
)


@dataclass(frozen=True)
class SpatialAudioEstimate:
    reference_tdoas_us: tuple[float, float, float]
    pair_quality: tuple[float, float, float]
    solution: SpatialSolution


def _next_pow2(value: int) -> int:
    n = 1
    while n < value:
        n <<= 1
    return n


def gcc_phat_delay_us(
    reference: np.ndarray,
    other: np.ndarray,
    *,
    sample_rate_hz: int,
    max_tau_s: float,
    interp: int = 16,
    fmin_hz: float = 80.0,
    fmax_hz: float = 5000.0,
) -> tuple[float, float]:
    """Estimate t_other - t_reference using frequency-limited GCC-PHAT.

    Returns (delay_us, quality). Quality is a peak-to-median statistic and is
    intentionally not a probability.
    """
    ref = np.asarray(reference, dtype=float)
    sig = np.asarray(other, dtype=float)
    if ref.ndim != 1 or sig.ndim != 1 or len(ref) != len(sig) or len(ref) < 64:
        raise ValueError("reference and other must be equal-length 1-D arrays")
    if sample_rate_hz <= 0 or interp < 1:
        raise ValueError("invalid sample rate/interpolation")

    # Remove DC and taper to reduce edge leakage.
    window = np.hanning(len(ref))
    ref = (ref - float(np.mean(ref))) * window
    sig = (sig - float(np.mean(sig))) * window

    n = _next_pow2(len(ref) + len(sig))
    ref_fft = np.fft.rfft(ref, n=n)
    sig_fft = np.fft.rfft(sig, n=n)
    cross = sig_fft * np.conj(ref_fft)

    freqs = np.fft.rfftfreq(n, d=1.0 / float(sample_rate_hz))
    mask = (freqs >= float(fmin_hz)) & (freqs <= float(fmax_hz))
    mag = np.abs(cross)
    phat = np.zeros_like(cross)
    good = mask & (mag > 1e-12)
    phat[good] = cross[good] / mag[good]

    cc = np.fft.irfft(phat, n=n * interp)
    max_shift = min(int(round(max_tau_s * sample_rate_hz * interp)), len(cc) // 2 - 1)
    if max_shift < 1:
        raise ValueError("max_tau_s too small")
    local = np.concatenate((cc[-max_shift:], cc[: max_shift + 1]))
    abs_local = np.abs(local)
    peak_index = int(np.argmax(abs_local))
    shift = peak_index - max_shift

    # Three-point parabolic interpolation around the oversampled peak.
    frac = 0.0
    if 0 < peak_index < len(abs_local) - 1:
        y0, y1, y2 = (float(abs_local[peak_index - 1]), float(abs_local[peak_index]), float(abs_local[peak_index + 1]))
        denom = y0 - 2.0 * y1 + y2
        if abs(denom) > 1e-15:
            frac = 0.5 * (y0 - y2) / denom
            frac = max(-0.5, min(0.5, frac))

    delay_s = (shift + frac) / float(interp * sample_rate_hz)
    median = float(np.median(abs_local)) + 1e-12
    quality = float(abs_local[peak_index] / median)
    return delay_s * 1e6, quality


def estimate_spatial_from_channels(
    channels: np.ndarray,
    *,
    sample_rate_hz: int = 32000,
    temperature_c: float = 20.0,
    geometry: SpatialGeometry = DEFAULT_GEOMETRY_3P1,
    interp: int = 16,
    fmin_hz: float = 80.0,
    fmax_hz: float = 5000.0,
) -> SpatialAudioEstimate:
    """Estimate 3+1 direction from four synchronous PCM channels.

    Firmware and compact protocol use three independent reference delays
    (1-2, 1-3, 1-4). The remaining pair delays are derived on the server.
    """
    x = np.asarray(channels, dtype=float)
    if x.ndim != 2 or x.shape[0] != 4:
        raise ValueError("channels must be shaped (4, samples)")

    c = speed_of_sound_mps(temperature_c)
    max_tau = geometry.max_baseline_m / c + 2.0 / sample_rate_hz
    delays: list[float] = []
    qualities: list[float] = []
    for channel in (1, 2, 3):
        delay_us, q = gcc_phat_delay_us(
            x[0],
            x[channel],
            sample_rate_hz=sample_rate_hz,
            max_tau_s=max_tau,
            interp=interp,
            fmin_hz=fmin_hz,
            fmax_hz=fmax_hz,
        )
        delays.append(delay_us)
        qualities.append(q)

    solution = direction_from_reference_tdoas_us(
        delays[0], delays[1], delays[2], geometry=geometry, temperature_c=temperature_c
    )
    return SpatialAudioEstimate(tuple(delays), tuple(qualities), solution)

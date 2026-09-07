"""Gain-invariant raw-audio temporal diagnostics for v0.7 research.

These features are intentionally *diagnostic only* until both type labels have
confirmed independent sources.  They are useful for studying envelope
modulation and high-band structure that cannot be reconstructed from the 1 s /
0.5 s 43-feature stream (notably the 1-3 Hz envelope band).
"""
from __future__ import annotations

import numpy as np
from scipy import signal

RAW_DIAGNOSTIC_COLUMNS = (
    "raw_band_80_160_ratio",
    "raw_band_160_320_ratio",
    "raw_band_4000_8000_ratio",
    "raw_band_8000_12000_ratio",
    "raw_spectral_flatness",
    "raw_spectral_crest",
    "raw_envmod_0p3_1_ratio",
    "raw_envmod_1_3_ratio",
    "raw_envmod_3_8_ratio",
    "raw_envmod_peak_hz",
)


def _bandpower(freq: np.ndarray, power: np.ndarray, low: float, high: float) -> float:
    mask = (freq >= low) & (freq < high)
    if int(np.sum(mask)) < 2:
        return 0.0
    return float(np.trapezoid(power[mask], freq[mask]))


def raw_temporal_diagnostics(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    x = np.asarray(samples, dtype=float).reshape(-1)
    if x.size < max(64, int(sample_rate)) or sample_rate < 2_000:
        return {name: 0.0 for name in RAW_DIAGNOSTIC_COLUMNS}
    x = x - float(np.mean(x))
    nperseg = min(x.size, max(1024, int(round(sample_rate * 0.25))))
    freq, power = signal.welch(x, fs=sample_rate, window="hann", nperseg=nperseg, noverlap=nperseg // 2, scaling="density")
    upper = min(12_000.0, sample_rate / 2.0 - 1.0)
    total = _bandpower(freq, power, 20.0, upper) + 1e-30
    out = {
        "raw_band_80_160_ratio": _bandpower(freq, power, 80.0, 160.0) / total,
        "raw_band_160_320_ratio": _bandpower(freq, power, 160.0, 320.0) / total,
        "raw_band_4000_8000_ratio": _bandpower(freq, power, 4_000.0, min(8_000.0, upper)) / total,
        "raw_band_8000_12000_ratio": _bandpower(freq, power, 8_000.0, upper) / total if upper > 8_000.0 else 0.0,
    }
    mask = (freq >= 40.0) & (freq <= min(10_000.0, upper))
    band = power[mask]
    if band.size:
        mean = float(np.mean(band)) + 1e-30
        out["raw_spectral_flatness"] = float(np.exp(np.mean(np.log(np.maximum(band, 1e-30)))) / mean)
        out["raw_spectral_crest"] = float(np.max(band) / mean)
    else:
        out["raw_spectral_flatness"] = 0.0
        out["raw_spectral_crest"] = 0.0

    # Low-band amplitude envelope. Downsample after Hilbert so the modulation PSD
    # resolves 0.3-8 Hz without tying the result to the original sample rate.
    high = min(500.0, sample_rate * 0.45)
    env_values = {
        "raw_envmod_0p3_1_ratio": 0.0,
        "raw_envmod_1_3_ratio": 0.0,
        "raw_envmod_3_8_ratio": 0.0,
        "raw_envmod_peak_hz": 0.0,
    }
    if high > 45.0:
        sos = signal.butter(4, [40.0, high], btype="bandpass", fs=sample_rate, output="sos")
        try:
            low_band = signal.sosfiltfilt(sos, x)
        except ValueError:
            low_band = signal.sosfilt(sos, x)
        envelope = np.abs(signal.hilbert(low_band))
        envelope = envelope - float(np.mean(envelope))
        divisor = max(1, int(round(sample_rate / 50.0)))
        env = signal.resample_poly(envelope, 1, divisor)
        env_sr = sample_rate / divisor
        if env.size >= 32:
            nenv = min(env.size, 256)
            ef, ep = signal.welch(env, fs=env_sr, nperseg=nenv, noverlap=nenv // 2)
            env_total = _bandpower(ef, ep, 0.3, min(8.0, env_sr / 2.0 - 1e-6)) + 1e-30
            env_values["raw_envmod_0p3_1_ratio"] = _bandpower(ef, ep, 0.3, 1.0) / env_total
            env_values["raw_envmod_1_3_ratio"] = _bandpower(ef, ep, 1.0, min(3.0, env_sr / 2.0 - 1e-6)) / env_total
            env_values["raw_envmod_3_8_ratio"] = _bandpower(ef, ep, 3.0, min(8.0, env_sr / 2.0 - 1e-6)) / env_total
            peak_mask = (ef >= 0.5) & (ef <= min(5.0, env_sr / 2.0 - 1e-6))
            if np.any(peak_mask):
                env_values["raw_envmod_peak_hz"] = float(ef[peak_mask][int(np.argmax(ep[peak_mask]))])
    out.update(env_values)
    return {name: float(out.get(name, 0.0)) for name in RAW_DIAGNOSTIC_COLUMNS}

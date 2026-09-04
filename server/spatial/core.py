"""Spatial processing primitives for the ZS-BPLA 3+1 microphone array.

Coordinate convention:
- x: East
- y: North
- z: Up
- azimuth: 0 deg North, clockwise positive
- elevation: 0 deg horizon, +90 deg zenith

TDOA convention for pair (i, j): t_j - t_i, seconds.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import asin, atan2, cos, degrees, radians, sin, sqrt
from typing import Mapping, Sequence

import numpy as np

Pair = tuple[int, int]


@dataclass(frozen=True)
class SpatialEstimate:
    valid: bool
    azimuth_deg: float | None
    elevation_deg: float | None
    residual_us: float
    direction_norm: float
    condition_number: float
    confidence: float
    reason: str = "ok"


def default_geometry_3plus1(horizontal_side_m: float = 0.12,
                            vertical_m: float = 0.15) -> np.ndarray:
    """Return a symmetric 3+1 array centered at the origin."""
    if not (0.05 <= horizontal_side_m <= 0.30):
        raise ValueError("horizontal_side_m outside supported design range")
    if not (0.05 <= vertical_m <= 0.40):
        raise ValueError("vertical_m outside supported design range")
    radius = horizontal_side_m / sqrt(3.0)
    return np.asarray([
        [0.0, radius, 0.0],
        [-horizontal_side_m / 2.0, -radius / 2.0, 0.0],
        [horizontal_side_m / 2.0, -radius / 2.0, 0.0],
        [0.0, 0.0, vertical_m],
    ], dtype=float)


def _unit_from_angles(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    az = radians(azimuth_deg)
    el = radians(elevation_deg)
    c = cos(el)
    return np.asarray([sin(az) * c, cos(az) * c, sin(el)], dtype=float)


def direction_to_pair_tdoa(geometry_m: np.ndarray,
                           azimuth_deg: float,
                           elevation_deg: float,
                           speed_of_sound_mps: float = 343.0) -> dict[Pair, float]:
    """Generate ideal far-field pair TDOAs for tests/simulation."""
    g = _validate_geometry(geometry_m)
    if speed_of_sound_mps <= 250.0 or speed_of_sound_mps >= 400.0:
        raise ValueError("speed_of_sound_mps outside supported range")
    u = _unit_from_angles(azimuth_deg, elevation_deg)
    out: dict[Pair, float] = {}
    for i, j in combinations(range(g.shape[0]), 2):
        out[(i, j)] = -float(np.dot(g[j] - g[i], u)) / speed_of_sound_mps
    return out


def estimate_direction_from_tdoa(geometry_m: np.ndarray,
                                 pair_tdoa_s: Mapping[Pair, float],
                                 speed_of_sound_mps: float = 343.0,
                                 max_residual_us: float = 80.0,
                                 min_direction_norm: float = 0.65,
                                 max_direction_norm: float = 1.35) -> SpatialEstimate:
    """Estimate far-field azimuth/elevation from pair TDOAs."""
    g = _validate_geometry(geometry_m)
    if speed_of_sound_mps <= 250.0 or speed_of_sound_mps >= 400.0:
        raise ValueError("speed_of_sound_mps outside supported range")

    rows: list[np.ndarray] = []
    rhs: list[float] = []
    for pair, tau in pair_tdoa_s.items():
        if len(pair) != 2:
            continue
        i, j = int(pair[0]), int(pair[1])
        if i == j or i < 0 or j < 0 or i >= len(g) or j >= len(g):
            continue
        if not np.isfinite(tau):
            continue
        rows.append(g[j] - g[i])
        rhs.append(-speed_of_sound_mps * float(tau))

    if len(rows) < 3:
        return SpatialEstimate(False, None, None, float("inf"), 0.0,
                               float("inf"), 0.0, "insufficient_pairs")

    a = np.vstack(rows)
    b = np.asarray(rhs, dtype=float)
    if int(np.linalg.matrix_rank(a, tol=1e-9)) < 3:
        return SpatialEstimate(False, None, None, float("inf"), 0.0,
                               float("inf"), 0.0, "rank_deficient_geometry")

    u_raw, _, _, singular = np.linalg.lstsq(a, b, rcond=None)
    norm = float(np.linalg.norm(u_raw))
    if not np.isfinite(norm) or norm < 1e-9:
        return SpatialEstimate(False, None, None, float("inf"), norm,
                               float("inf"), 0.0, "degenerate_solution")

    condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else float("inf")
    residual_s = (a @ u_raw - b) / speed_of_sound_mps
    residual_us = float(np.sqrt(np.mean(np.square(residual_s))) * 1e6)

    if norm < min_direction_norm or norm > max_direction_norm:
        return SpatialEstimate(False, None, None, residual_us, norm, condition,
                               0.0, "physically_inconsistent_tdoa")
    if residual_us > max_residual_us:
        return SpatialEstimate(False, None, None, residual_us, norm, condition,
                               0.0, "residual_gate")

    u = u_raw / norm
    elevation = degrees(asin(float(np.clip(u[2], -1.0, 1.0))))
    azimuth = degrees(atan2(float(u[0]), float(u[1]))) % 360.0

    residual_score = max(0.0, 1.0 - residual_us / max(max_residual_us, 1e-9))
    norm_score = max(0.0, 1.0 - abs(norm - 1.0) / max(1.0 - min_direction_norm,
                                                    max_direction_norm - 1.0))
    condition_score = 1.0 / (1.0 + max(0.0, condition - 1.0) / 8.0)
    confidence = float(np.clip(0.55 * residual_score + 0.30 * norm_score +
                               0.15 * condition_score, 0.0, 1.0))
    return SpatialEstimate(True, azimuth, elevation, residual_us, norm,
                           condition, confidence, "ok")


def gcc_phat_pair_tdoa(channel_i: Sequence[float],
                       channel_j: Sequence[float],
                       sample_rate_hz: int,
                       max_tau_s: float,
                       band_hz: tuple[float, float] = (80.0, 5000.0),
                       interp: int = 8) -> float:
    """Estimate t_j - t_i using band-limited GCC-PHAT.

    Interpolation is applied to the correlation function, not by computing the
    source spectra on a longer zero-padded grid. This preserves the physical
    lag scale while providing sub-sample peak resolution.
    """
    xi = np.asarray(channel_i, dtype=float)
    xj = np.asarray(channel_j, dtype=float)
    if xi.ndim != 1 or xj.ndim != 1 or len(xi) != len(xj) or len(xi) < 64:
        raise ValueError("channels must be equal-length 1D arrays with >=64 samples")
    if sample_rate_hz < 8000:
        raise ValueError("sample_rate_hz too low")
    if interp < 1 or interp > 32:
        raise ValueError("interp outside supported range")

    xi = xi - float(np.mean(xi))
    xj = xj - float(np.mean(xj))
    window = np.hanning(len(xi))
    xi *= window
    xj *= window

    base_nfft = 1
    while base_nfft < len(xi) * 2:
        base_nfft <<= 1

    fi = np.fft.rfft(xi, n=base_nfft)
    fj = np.fft.rfft(xj, n=base_nfft)
    freq = np.fft.rfftfreq(base_nfft, d=1.0 / sample_rate_hz)
    lo, hi = band_hz
    if lo < 0 or hi <= lo or hi > sample_rate_hz / 2:
        raise ValueError("invalid band_hz")

    cross = fi * np.conj(fj)
    denom = np.abs(cross)
    good = (freq >= lo) & (freq <= hi) & (denom > 1e-12)
    phat = np.zeros_like(cross)
    phat[good] = cross[good] / denom[good]

    corr_n = base_nfft * interp
    cc = np.fft.irfft(phat, n=corr_n)
    max_shift = int(round(max_tau_s * sample_rate_hz * interp))
    max_shift = min(max_shift, corr_n // 2 - 1)
    if max_shift < 1:
        raise ValueError("max_tau_s too small")
    search = np.concatenate((cc[-max_shift:], cc[:max_shift + 1]))
    shift = int(np.argmax(np.abs(search))) - max_shift
    return -float(shift) / (sample_rate_hz * interp)


def pairwise_gcc_phat(channels: Sequence[Sequence[float]],
                      geometry_m: np.ndarray,
                      sample_rate_hz: int,
                      speed_of_sound_mps: float = 343.0,
                      band_hz: tuple[float, float] = (80.0, 5000.0),
                      interp: int = 8) -> dict[Pair, float]:
    """Compute all pair TDOAs for the configured array."""
    g = _validate_geometry(geometry_m)
    if len(channels) != len(g):
        raise ValueError("number of channels must match geometry")
    out: dict[Pair, float] = {}
    for i, j in combinations(range(len(g)), 2):
        distance = float(np.linalg.norm(g[j] - g[i]))
        max_tau = distance / speed_of_sound_mps * 1.10
        out[(i, j)] = gcc_phat_pair_tdoa(
            channels[i], channels[j], sample_rate_hz, max_tau,
            band_hz=band_hz, interp=interp,
        )
    return out


def _validate_geometry(geometry_m: np.ndarray) -> np.ndarray:
    g = np.asarray(geometry_m, dtype=float)
    if g.ndim != 2 or g.shape[1] != 3 or g.shape[0] < 4:
        raise ValueError("geometry must be Nx3 with at least four microphones")
    if not np.all(np.isfinite(g)):
        raise ValueError("geometry contains non-finite values")
    return g

"""Geometry and far-field TDOA solver for the approved 3+1 array.

Coordinate convention:
- x: east/right on the station drawing;
- y: north/forward;
- z: up;
- azimuth: 0 deg north, 90 deg east;
- elevation: 0 deg horizon, +90 deg zenith;
- tau_ij = t_j - t_i.

The default geometry is an equilateral 120 mm horizontal triangle centered at
(0, 0, 0), with microphone 4 located 150 mm above its centroid.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


def speed_of_sound_mps(temperature_c: float = 20.0) -> float:
    return 331.3 + 0.606 * float(temperature_c)


@dataclass(frozen=True)
class SpatialGeometry:
    positions_m: np.ndarray
    geometry_id: int = 1
    name: str = "3p1_120mm_150mm_v1"

    def __post_init__(self) -> None:
        p = np.asarray(self.positions_m, dtype=float)
        if p.shape != (4, 3):
            raise ValueError("positions_m must be shaped (4, 3)")
        if np.linalg.matrix_rank(p[1:] - p[0]) < 3:
            raise ValueError("3+1 geometry must be non-coplanar")
        object.__setattr__(self, "positions_m", p)

    @property
    def max_baseline_m(self) -> float:
        return max(
            float(np.linalg.norm(self.positions_m[j] - self.positions_m[i]))
            for i in range(4)
            for j in range(i + 1, 4)
        )


def _default_geometry() -> SpatialGeometry:
    side = 0.120
    h = math.sqrt(3.0) * side / 2.0
    # Centroid of the horizontal triangle is the origin.
    p = np.array(
        [
            [-side / 2.0, -h / 3.0, 0.0],
            [ side / 2.0, -h / 3.0, 0.0],
            [0.0, 2.0 * h / 3.0, 0.0],
            [0.0, 0.0, 0.150],
        ],
        dtype=float,
    )
    return SpatialGeometry(p)


DEFAULT_GEOMETRY_3P1 = _default_geometry()


@dataclass(frozen=True)
class SpatialSolution:
    azimuth_deg: float
    elevation_deg: float
    residual_us: float
    confidence: float
    valid: bool
    unit_vector_enu: tuple[float, float, float]
    raw_vector_norm: float


def direction_unit_vector(azimuth_deg: float, elevation_deg: float) -> np.ndarray:
    az = math.radians(float(azimuth_deg))
    el = math.radians(float(elevation_deg))
    ce = math.cos(el)
    return np.array([ce * math.sin(az), ce * math.cos(az), math.sin(el)], dtype=float)


def reference_tdoas_us_from_direction(
    azimuth_deg: float,
    elevation_deg: float,
    *,
    geometry: SpatialGeometry = DEFAULT_GEOMETRY_3P1,
    temperature_c: float = 20.0,
) -> tuple[float, float, float]:
    """Return (tau12, tau13, tau14) in microseconds.

    tau1j is t_j - t_1. For a source above the array, mic 4 is closer, so
    tau14 is negative.
    """
    u = direction_unit_vector(azimuth_deg, elevation_deg)
    c = speed_of_sound_mps(temperature_c)
    baselines = geometry.positions_m[1:] - geometry.positions_m[0]
    tau_s = -(baselines @ u) / c
    return tuple(float(v * 1e6) for v in tau_s)


def full_pair_tdoas_us(reference_tdoas_us: tuple[float, float, float]) -> dict[str, float]:
    t12, t13, t14 = (float(v) for v in reference_tdoas_us)
    return {
        "tdoa12_us": t12,
        "tdoa13_us": t13,
        "tdoa14_us": t14,
        "tdoa23_us": t13 - t12,
        "tdoa24_us": t14 - t12,
        "tdoa34_us": t14 - t13,
    }


def direction_from_reference_tdoas_us(
    tdoa12_us: float,
    tdoa13_us: float,
    tdoa14_us: float,
    *,
    geometry: SpatialGeometry = DEFAULT_GEOMETRY_3P1,
    temperature_c: float = 20.0,
    max_residual_us: float = 35.0,
) -> SpatialSolution:
    """Solve far-field direction from the three independent TDOAs.

    The unnormalized solution should have norm close to one for physically
    consistent far-field measurements. It is normalized before azimuth and
    elevation are computed, while norm error contributes to confidence.
    """
    tau_us = np.array([tdoa12_us, tdoa13_us, tdoa14_us], dtype=float)
    if not np.all(np.isfinite(tau_us)):
        return SpatialSolution(0.0, 0.0, math.inf, 0.0, False, (0.0, 0.0, 0.0), 0.0)

    c = speed_of_sound_mps(temperature_c)
    baselines = geometry.positions_m[1:] - geometry.positions_m[0]
    max_tdoa_us = geometry.max_baseline_m / c * 1e6 + 5.0
    if np.any(np.abs(tau_us) > max_tdoa_us):
        return SpatialSolution(0.0, 0.0, math.inf, 0.0, False, (0.0, 0.0, 0.0), 0.0)

    rhs = -c * tau_us * 1e-6
    try:
        raw = np.linalg.solve(baselines, rhs)
    except np.linalg.LinAlgError:
        return SpatialSolution(0.0, 0.0, math.inf, 0.0, False, (0.0, 0.0, 0.0), 0.0)

    raw_norm = float(np.linalg.norm(raw))
    if raw_norm < 1e-9:
        return SpatialSolution(0.0, 0.0, math.inf, 0.0, False, (0.0, 0.0, 0.0), raw_norm)

    u = raw / raw_norm
    predicted_us = -(baselines @ u) / c * 1e6
    residual_us = float(np.sqrt(np.mean((predicted_us - tau_us) ** 2)))

    az = math.degrees(math.atan2(float(u[0]), float(u[1]))) % 360.0
    el = math.degrees(math.asin(float(np.clip(u[2], -1.0, 1.0))))

    norm_error = abs(raw_norm - 1.0)
    residual_score = math.exp(-((residual_us / 15.0) ** 2))
    norm_score = math.exp(-((norm_error / 0.15) ** 2))
    confidence = float(max(0.0, min(1.0, residual_score * norm_score)))
    valid = bool(residual_us <= max_residual_us and norm_error <= 0.45)

    return SpatialSolution(
        azimuth_deg=az,
        elevation_deg=el,
        residual_us=residual_us,
        confidence=confidence if valid else min(confidence, 0.25),
        valid=valid,
        unit_vector_enu=(float(u[0]), float(u[1]), float(u[2])),
        raw_vector_norm=raw_norm,
    )

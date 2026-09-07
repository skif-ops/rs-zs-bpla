"""Feature vector conversion for local ML classifiers."""

from __future__ import annotations

import numpy as np

from models.schemas import AudioFeatureSet


SCALAR_FEATURE_COLUMNS: tuple[str, ...] = (
    "fundamental_hz",
    "harmonic_count",
    "harmonic_step_hz",
    "harmonic_stability",
    "average_energy",
    "rms",
    "zero_crossing_rate",
    "spectral_centroid_hz",
    "spectral_flatness",
    "spectral_bandwidth_hz",
    "noise_floor",
    "high_band_energy_6_10khz",
    "fundamental_variation",
    "harmonic_variation",
    "frequency_modulation_index",
    "spectral_roughness",
    "doppler_stability",
)

MFCC_MEAN_COLUMNS: tuple[str, ...] = tuple(f"mfcc_mean_{index}" for index in range(13))
MFCC_STD_COLUMNS: tuple[str, ...] = tuple(f"mfcc_std_{index}" for index in range(13))

FEATURE_COLUMNS: tuple[str, ...] = (
    *SCALAR_FEATURE_COLUMNS,
    *MFCC_MEAN_COLUMNS,
    *MFCC_STD_COLUMNS,
)


def feature_set_to_row(features: AudioFeatureSet) -> dict[str, float]:
    """Convert extracted audio features to a flat numeric row."""

    row: dict[str, float] = {}
    for column in SCALAR_FEATURE_COLUMNS:
        row[column] = float(getattr(features, column))

    for index, column in enumerate(MFCC_MEAN_COLUMNS):
        row[column] = _safe_index(features.mfcc_mean, index)
    for index, column in enumerate(MFCC_STD_COLUMNS):
        row[column] = _safe_index(features.mfcc_std, index)
    return row


def row_to_vector(row: dict[str, float] | object) -> np.ndarray:
    """Return a finite vector from a mapping or dataframe row-like object."""

    values = []
    for column in FEATURE_COLUMNS:
        if isinstance(row, dict):
            value = row.get(column, 0.0)
        else:
            value = getattr(row, column, 0.0)
        values.append(float(value) if np.isfinite(float(value)) else 0.0)
    return np.asarray(values, dtype=np.float64)


def feature_set_to_vector(features: AudioFeatureSet) -> np.ndarray:
    """Convert extracted features directly to a numeric vector."""

    return row_to_vector(feature_set_to_row(features))


def _safe_index(values: list[float], index: int) -> float:
    """Return a finite list item or zero."""

    if index >= len(values):
        return 0.0
    value = float(values[index])
    return value if np.isfinite(value) else 0.0

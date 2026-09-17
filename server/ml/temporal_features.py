"""Rolling temporal features built from the existing 43 station features.

The v0.6 type classifier deliberately reuses the 1 s / 0.5 s feature stream so
it can run online on the station without changing the compact 43-feature uplink.
Absolute recording amplitude is not used as a type feature because phone/video
AGC and compression make it non-portable between recordings.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

BASE_TEMPORAL_COLUMNS = (
    "fundamental_hz",
    "harmonic_count",
    "harmonic_step_hz",
    "harmonic_stability",
    "spectral_centroid_hz",
    "spectral_flatness",
    "spectral_bandwidth_hz",
    "high_band_energy_6_10khz",
    "fundamental_variation",
    "harmonic_variation",
    "frequency_modulation_index",
    "spectral_roughness",
    "doppler_stability",
)

_IQR_COLUMNS = {
    "fundamental_hz",
    "harmonic_count",
    "harmonic_step_hz",
    "spectral_centroid_hz",
    "spectral_bandwidth_hz",
    "high_band_energy_6_10khz",
    "spectral_roughness",
}
_SLOPE_COLUMNS = {
    "fundamental_hz",
    "spectral_centroid_hz",
    "high_band_energy_6_10khz",
    "spectral_roughness",
}

TEMPORAL_FEATURE_COLUMNS = tuple(
    [f"{name}_median" for name in BASE_TEMPORAL_COLUMNS]
    + [f"{name}_iqr_rel" for name in BASE_TEMPORAL_COLUMNS if name in _IQR_COLUMNS]
    + [f"{name}_slope" for name in BASE_TEMPORAL_COLUMNS if name in _SLOPE_COLUMNS]
    + ["harmonic_persistence", "f0_step_mad_hz"]
)


def _slope(times: np.ndarray, values: np.ndarray) -> float:
    if values.size < 2:
        return 0.0
    t = times - float(np.mean(times))
    x = values - float(np.mean(values))
    denominator = float(np.dot(t, t))
    if denominator <= 1e-12:
        return 0.0
    return float(np.dot(t, x) / denominator)


def temporal_vector(rows: pd.DataFrame) -> dict[str, float]:
    """Aggregate overlapping 1 s feature rows into a robust temporal vector."""

    if rows.empty:
        return {name: 0.0 for name in TEMPORAL_FEATURE_COLUMNS}
    times = pd.to_numeric(rows.get("start_seconds", 0.0), errors="coerce").fillna(0.0).to_numpy(float) + 0.5
    out: dict[str, float] = {}
    values_by_name: dict[str, np.ndarray] = {}
    for name in BASE_TEMPORAL_COLUMNS:
        if name in rows.columns:
            values = pd.to_numeric(rows[name], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(float)
        else:
            values = np.zeros(len(rows), dtype=float)
        values_by_name[name] = values
        median = float(np.median(values)) if values.size else 0.0
        out[f"{name}_median"] = median
        if name in _IQR_COLUMNS:
            q25, q75 = np.percentile(values, [25.0, 75.0]) if values.size else (0.0, 0.0)
            scale = max(abs(median), 1e-6)
            out[f"{name}_iqr_rel"] = float((q75 - q25) / scale)
        if name in _SLOPE_COLUMNS:
            out[f"{name}_slope"] = _slope(times, values)

    harmonic_count = values_by_name["harmonic_count"]
    harmonic_stability = values_by_name["harmonic_stability"]
    out["harmonic_persistence"] = float(np.mean((harmonic_count >= 4.0) & (harmonic_stability >= 0.25)))
    f0 = values_by_name["fundamental_hz"]
    out["f0_step_mad_hz"] = float(np.median(np.abs(np.diff(f0)))) if f0.size >= 2 else 0.0
    return {name: float(out.get(name, 0.0)) for name in TEMPORAL_FEATURE_COLUMNS}


@dataclass(slots=True)
class TemporalFeatureBuilder:
    """Build configurable rolling vectors from a station feature stream."""

    hop_seconds: float = 1.0

    def build(self, frame: pd.DataFrame, window_seconds: float) -> pd.DataFrame:
        if frame.empty or "source_file" not in frame.columns or "label" not in frame.columns:
            return pd.DataFrame(columns=["label", "source_file", "start_seconds", "window_seconds", *TEMPORAL_FEATURE_COLUMNS])
        results: list[dict[str, object]] = []
        for (label, source), group in frame.groupby(["label", "source_file"], sort=False):
            g = group.sort_values("start_seconds").reset_index(drop=True)
            results.extend(self._build_one(g, str(label), str(source), float(window_seconds)))
        return pd.DataFrame(results)

    def build_one_source(self, frame: pd.DataFrame, window_seconds: float) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=["start_seconds", "window_seconds", *TEMPORAL_FEATURE_COLUMNS])
        label = str(frame["label"].iloc[0]) if "label" in frame.columns else "UNKNOWN"
        source = str(frame["source_file"].iloc[0]) if "source_file" in frame.columns else "source"
        return pd.DataFrame(self._build_one(frame.sort_values("start_seconds").reset_index(drop=True), label, source, float(window_seconds)))

    def _build_one(self, g: pd.DataFrame, label: str, source: str, window_seconds: float) -> list[dict[str, object]]:
        if g.empty:
            return []
        row_duration = float(pd.to_numeric(g.get("duration_seconds", 1.0), errors="coerce").fillna(1.0).median()) if "duration_seconds" in g.columns else 1.0
        end_seconds = float(pd.to_numeric(g["start_seconds"], errors="coerce").fillna(0.0).max()) + max(row_duration, 0.5)
        if end_seconds + 1e-9 < window_seconds:
            return []
        centers = pd.to_numeric(g["start_seconds"], errors="coerce").fillna(0.0).to_numpy(float) + row_duration / 2.0
        starts = np.arange(0.0, max(end_seconds - window_seconds, 0.0) + 1e-9, max(self.hop_seconds, 0.1))
        min_rows = max(3, int(round(window_seconds)))
        out: list[dict[str, object]] = []
        for start in starts:
            mask = (centers >= start) & (centers <= start + window_seconds)
            segment = g.loc[mask]
            if len(segment) < min_rows:
                continue
            row: dict[str, object] = {
                "label": label,
                "source_file": source,
                "start_seconds": round(float(start), 3),
                "window_seconds": float(window_seconds),
            }
            for meta in (
                "meta_dataset_role",
                "meta_recording_quality",
                "meta_recording_quality_score",
                "meta_label_confidence",
                "meta_label_confidence_score",
            ):
                if meta in segment.columns:
                    values = segment[meta].dropna()
                    if not values.empty:
                        row[meta] = values.iloc[0]
            row.update(temporal_vector(segment))
            out.append(row)
        return out

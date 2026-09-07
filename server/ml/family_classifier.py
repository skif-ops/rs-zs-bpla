"""Source-balanced v0.8 acoustic family classifier.

This layer intentionally sits between generic UAV detection and specific type
identity.  It learns only from the existing 43-feature contract, so station
firmware does not need a new uplink format.  Weak labels may contribute with a
reduced weight but cannot by themselves establish validation readiness.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import settings
from ml.acoustic_family import AcousticFamily, family_for_label, known_family_labels
from ml.feature_vector import FEATURE_COLUMNS, feature_set_to_row
from ml.online_type_classifier import source_training_weight
from models.schemas import AudioFeatureSet, FamilyClassificationResult, FamilyClassificationScore
from utils.serialization import write_json

_TRAIN_ROLES = {"training", "training_provisional", "training_provisional_weak"}


def _source_balanced_rows(frame: pd.DataFrame, *, spacing_seconds: float = 2.0, max_rows: int = 24) -> pd.DataFrame:
    """Decorrelate overlapping windows so one recording cannot dominate."""

    selected: list[pd.DataFrame] = []
    if frame.empty:
        return frame.copy()
    for _, group in frame.groupby("source_file", sort=False):
        g = group.sort_values("start_seconds").reset_index(drop=True)
        keep: list[int] = []
        last = -1e12
        for idx, row in g.iterrows():
            start = float(row.get("start_seconds", 0.0))
            if start - last + 1e-9 >= spacing_seconds:
                keep.append(idx)
                last = start
            if len(keep) >= max_rows:
                break
        if keep:
            selected.append(g.loc[keep])
    return pd.concat(selected, ignore_index=True) if selected else frame.iloc[0:0].copy()


@dataclass(slots=True)
class AcousticFamilyClassifier:
    dataset_path: Path = settings.feature_dataset_path
    model_path: Path = settings.base_dir / "models" / "acoustic_family_model_v08.json"
    min_score: float = 0.48
    min_margin: float = 0.08

    def train(self, frame: pd.DataFrame | None = None) -> dict[str, Any]:
        source = frame.copy() if frame is not None else pd.read_csv(self.dataset_path)
        if source.empty or "label" not in source.columns or "source_file" not in source.columns:
            raise ValueError("Family training requires a non-empty labelled source dataset.")
        if "meta_dataset_role" in source.columns:
            roles = source["meta_dataset_role"].fillna("training").astype(str).str.strip().str.lower()
            source = source[roles.isin(_TRAIN_ROLES)].copy()
        source["family"] = source["label"].map(lambda value: family_for_label(str(value)).value)
        source = source[source["family"] != AcousticFamily.UNKNOWN.value].copy()
        training = _source_balanced_rows(source)
        if training.empty:
            raise ValueError("No supported family rows remain after source balancing.")

        matrix = training.loc[:, list(FEATURE_COLUMNS)].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(float)
        mean = np.mean(matrix, axis=0)
        std = np.std(matrix, axis=0)
        std = np.where(std < 1e-9, 1.0, std)
        z = (matrix - mean) / std
        training = training.reset_index(drop=True)

        source_items: list[dict[str, Any]] = []
        for (family, source_file), indices in training.groupby(["family", "source_file"], sort=False).groups.items():
            idx = np.asarray(list(indices), dtype=int)
            group = training.loc[idx]
            source_items.append({
                "family": str(family),
                "source_file": str(source_file),
                "centroid": np.median(z[idx], axis=0),
                "weight": source_training_weight(group),
                "confirmed": self._source_confirmed(group),
                "validation_eligible": self._source_validation_eligible(group),
                "windows": int(len(idx)),
            })

        classes: dict[str, Any] = {}
        readiness: dict[str, Any] = {}
        for family in sorted({item["family"] for item in source_items}):
            items = [item for item in source_items if item["family"] == family]
            weights = np.asarray([max(float(item["weight"]), 0.05) for item in items], dtype=float)
            centroids = np.asarray([item["centroid"] for item in items], dtype=float)
            centroid = np.average(centroids, axis=0, weights=weights)
            distances = np.linalg.norm(centroids - centroid, axis=1)
            radius = max(float(np.percentile(distances, 85)) if len(distances) > 1 else 1.0, 1.0)
            classes[family] = {
                "centroid": centroid.tolist(),
                "radius": radius,
                "sources": len(items),
                "confirmed_sources": int(sum(bool(item["confirmed"]) for item in items)),
                "validation_sources": int(sum(bool(item["validation_eligible"]) for item in items)),
                "training_weight_sum": float(np.sum(weights)),
            }
            readiness[family] = {
                "research_ready": len(items) >= 2,
                "operational_validation_ready": sum(bool(item["validation_eligible"]) for item in items) >= 2,
            }

        payload = {
            "model_type": "source_balanced_acoustic_family_centroid_v08",
            "version": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "feature_contract": "FEATURES_43_V1",
            "feature_columns": list(FEATURE_COLUMNS),
            "mean": mean.tolist(),
            "std": std.tolist(),
            "label_to_family": known_family_labels(),
            "classes": classes,
            "readiness": readiness,
            "unsupported_families": [AcousticFamily.TURBINE_JET.value],
            "training": {
                "source_balanced": True,
                "spacing_seconds": 2.0,
                "max_rows_per_source": 24,
                "rows": int(len(training)),
                "sources": int(training["source_file"].nunique()),
            },
        }
        write_json(self.model_path, payload)
        return payload

    def load_model(self) -> dict[str, Any] | None:
        if not self.model_path.exists():
            return None
        import json
        return json.loads(self.model_path.read_text(encoding="utf-8"))

    def predict_features(
        self,
        features: list[AudioFeatureSet],
        *,
        air_target_confirmed: bool = False,
    ) -> FamilyClassificationResult | None:
        if not features:
            return None
        rows = pd.DataFrame([feature_set_to_row(item) for item in features])
        return self.predict_rows(rows, air_target_confirmed=air_target_confirmed)

    def predict_rows(
        self,
        rows: pd.DataFrame,
        model: dict[str, Any] | None = None,
        *,
        air_target_confirmed: bool = False,
    ) -> FamilyClassificationResult | None:
        model = model or self.load_model()
        if model is None or rows.empty:
            return None
        matrix = rows.loc[:, list(FEATURE_COLUMNS)].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(float)
        vector = np.median(matrix, axis=0)
        mean = np.asarray(model["mean"], dtype=float)
        std = np.asarray(model["std"], dtype=float)
        std = np.where(std < 1e-9, 1.0, std)
        z = (vector - mean) / std

        raw: list[tuple[str, float, float, dict[str, Any]]] = []
        allowed_air = {
            AcousticFamily.PROP_PISTON.value,
            AcousticFamily.ROTOR_ELECTRIC.value,
            AcousticFamily.TURBINE_JET.value,
        }
        for family, data in model.get("classes", {}).items():
            if air_target_confirmed and family not in allowed_air:
                continue
            centroid = np.asarray(data["centroid"], dtype=float)
            radius = max(float(data.get("radius", 1.0)), 1.0)
            distance = float(np.linalg.norm(z - centroid))
            score = float(np.exp(-0.5 * (distance / radius) ** 2))
            raw.append((family, score, distance, data))
        if not raw:
            return None
        total = max(sum(item[1] for item in raw), 1e-12)
        scores = [
            FamilyClassificationScore(
                family=family,
                score=float(score / total),
                distance=distance,
                sources=int(data.get("sources", 0)),
            )
            for family, score, distance, data in raw
        ]
        scores.sort(key=lambda item: item.score, reverse=True)
        best = scores[0]
        runner = scores[1].score if len(scores) > 1 else 0.0
        margin = float(best.score - runner)
        raw_best = next(item[1] for item in raw if item[0] == best.family)
        absolute_fit = float(np.clip(raw_best, 0.0, 1.0))
        confidence = float(best.score * (0.45 + 0.55 * absolute_fit))
        best_family = best.family if confidence >= self.min_score and margin >= self.min_margin else AcousticFamily.UNKNOWN.value
        readiness = model.get("readiness", {}).get(best.family, {})
        operational_ready = bool(readiness.get("operational_validation_ready", False))
        if best_family == AcousticFamily.UNKNOWN.value:
            status = "unknown"
        elif operational_ready:
            status = "validated_family"
        else:
            status = "provisional_family"
        return FamilyClassificationResult(
            best_family=best_family,
            confidence=confidence,
            absolute_fit=absolute_fit,
            margin=margin,
            status=status,
            conditional_on_air_target=bool(air_target_confirmed),
            operational_validation_ready=operational_ready,
            scores=scores,
            model_version=str(model.get("version", "unknown")),
            explanation=(
                ("Семейство определено условно после независимого AIR_TARGET detector gate."
                 if air_target_confirmed else "Семейство определено по source-balanced модели 43 признаков.")
                if best_family != AcousticFamily.UNKNOWN.value
                else "Отрыв между семействами недостаточен, результат оставлен UNKNOWN."
            ),
        )

    @staticmethod
    def _source_confirmed(group: pd.DataFrame) -> bool:
        if "meta_label_confidence" in group.columns:
            values = group["meta_label_confidence"].dropna().astype(str).str.strip().str.lower()
            if not values.empty:
                return values.iloc[0] == "confirmed"
        role = str(group.get("meta_dataset_role", pd.Series(["training"])).dropna().iloc[0]).lower()
        return role != "training_provisional_weak"

    @staticmethod
    def _source_validation_eligible(group: pd.DataFrame) -> bool:
        if "meta_validation_eligible" not in group.columns:
            return False
        values = group["meta_validation_eligible"].dropna().astype(str).str.strip().str.lower()
        return bool(not values.empty and values.iloc[0] in {"1", "true", "yes"})

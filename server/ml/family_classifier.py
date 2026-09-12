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
    min_evidence_windows: int = settings.hierarchy_min_evidence_windows
    max_evidence_windows: int = settings.hierarchy_max_evidence_windows
    min_consensus_ratio: float = settings.hierarchy_min_consensus_ratio

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
        ordered = rows.sort_values("start_seconds") if "start_seconds" in rows.columns else rows
        bounded = ordered.tail(self.max_evidence_windows)
        evidence_windows = int(len(bounded))
        if evidence_windows < self.min_evidence_windows:
            return FamilyClassificationResult(
                status="warming_up",
                conditional_on_air_target=bool(air_target_confirmed),
                evidence_windows=evidence_windows,
                required_windows=self.min_evidence_windows,
                max_windows=self.max_evidence_windows,
                model_version=str(model.get("version", "unknown")),
                explanation=(
                    f"Для решения по семейству требуется не менее {self.min_evidence_windows} "
                    f"окон; получено {evidence_windows}."
                ),
            )
        matrix = bounded.loc[:, list(FEATURE_COLUMNS)].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(float)
        mean = np.asarray(model["mean"], dtype=float)
        std = np.asarray(model["std"], dtype=float)
        std = np.where(std < 1e-9, 1.0, std)
        allowed_air = {
            AcousticFamily.PROP_PISTON.value,
            AcousticFamily.ROTOR_ELECTRIC.value,
            AcousticFamily.TURBINE_JET.value,
        }
        classes = {
            str(family): data
            for family, data in model.get("classes", {}).items()
            if not air_target_confirmed or family in allowed_air
        }
        if not classes:
            return None

        window_results: list[dict[str, Any]] = []
        for vector in matrix:
            z = (vector - mean) / std
            raw_scores: dict[str, float] = {}
            distances: dict[str, float] = {}
            for family, data in classes.items():
                centroid = np.asarray(data["centroid"], dtype=float)
                radius = max(float(data.get("radius", 1.0)), 1.0)
                distance = float(np.linalg.norm(z - centroid))
                distances[family] = distance
                raw_scores[family] = float(np.exp(-0.5 * (distance / radius) ** 2))
            total = max(sum(raw_scores.values()), 1e-12)
            normalized = {family: score / total for family, score in raw_scores.items()}
            ranking = sorted(normalized.items(), key=lambda item: item[1], reverse=True)
            best_family, relative = ranking[0]
            runner = ranking[1][1] if len(ranking) > 1 else 0.0
            margin = float(relative - runner)
            absolute_fit = float(np.clip(raw_scores[best_family], 0.0, 1.0))
            confidence = float(relative * (0.45 + 0.55 * absolute_fit))
            vote = best_family if confidence >= self.min_score and margin >= self.min_margin else AcousticFamily.UNKNOWN.value
            window_results.append({
                "vote": vote,
                "scores": normalized,
                "distances": distances,
                "confidence": confidence,
                "absolute_fit": absolute_fit,
            })

        aggregate_scores = {
            family: float(np.mean([item["scores"][family] for item in window_results]))
            for family in classes
        }
        vote_counts = {
            family: sum(item["vote"] == family for item in window_results)
            for family in classes
        }
        winning_family = max(classes, key=lambda family: (vote_counts[family], aggregate_scores[family], family))
        winning_votes = int(vote_counts[winning_family])
        consensus_ratio = float(winning_votes / evidence_windows)
        support = [item for item in window_results if item["vote"] == winning_family]
        absolute_fit = float(np.mean([item["absolute_fit"] for item in support])) if support else 0.0
        support_confidence = float(np.mean([item["confidence"] for item in support])) if support else 0.0
        confidence = float(support_confidence * (0.75 + 0.25 * consensus_ratio))
        ranking = sorted(aggregate_scores.items(), key=lambda item: item[1], reverse=True)
        runner = ranking[1][1] if len(ranking) > 1 else 0.0
        margin = float(aggregate_scores[winning_family] - runner)
        accepted = (
            consensus_ratio >= self.min_consensus_ratio
            and confidence >= self.min_score
            and margin >= self.min_margin
        )
        best_family = winning_family if accepted else AcousticFamily.UNKNOWN.value

        scores = [
            FamilyClassificationScore(
                family=family,
                score=aggregate_scores[family],
                distance=float(np.median([item["distances"][family] for item in window_results])),
                sources=int(data.get("sources", 0)),
            )
            for family, data in classes.items()
        ]
        scores.sort(key=lambda item: item.score, reverse=True)
        readiness = model.get("readiness", {}).get(winning_family, {})
        operational_ready = bool(readiness.get("operational_validation_ready", False))
        if best_family == AcousticFamily.UNKNOWN.value:
            status = "unknown"
        elif best_family in set(model.get("unsupported_families", [])):
            status = "unsupported"
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
            evidence_windows=evidence_windows,
            required_windows=self.min_evidence_windows,
            max_windows=self.max_evidence_windows,
            consensus_ratio=consensus_ratio,
            scores=scores,
            model_version=str(model.get("version", "unknown")),
            explanation=(
                (f"Семейство подтверждено в {winning_votes}/{evidence_windows} последних окон "
                 + ("после независимого AIR_TARGET detector gate."
                    if air_target_confirmed else "source-balanced моделью 43 признаков."))
                if best_family != AcousticFamily.UNKNOWN.value
                else (
                    f"Серия {evidence_windows} окон не достигла порога согласия "
                    f"{self.min_consensus_ratio:.3f}; результат оставлен UNKNOWN."
                )
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

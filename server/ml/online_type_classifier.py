"""Conservative online UAV type classifier for 40-60 s acoustic fly-overs.

v0.7 separates detection from type identity. Detection may trigger immediately;
type identity uses rolling 4 s, 6 s and 8 s aggregates of the existing 43
features, so no final hierarchy is inferred from a single acoustic window.
Weakly labelled FP-1 data may shape a provisional prototype but can never create
an operational type lock. Confirmed Lutyi recordings are also provisional until
a separately frozen, representative validation set exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import settings
from ml.temporal_features import TEMPORAL_FEATURE_COLUMNS, TemporalFeatureBuilder
from ml.type_readiness import assess_type_readiness
from models.schemas import OnlineTypeReplay, OnlineTypeSnapshot
from utils.serialization import write_json

TRAIN_ROLES = {"training", "training_provisional", "training_provisional_weak"}


def _numeric_score(value: object, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return float(np.clip(number, 0.0, 1.0)) if np.isfinite(number) else fallback


def source_training_weight(group: pd.DataFrame) -> float:
    """Independent quality x label-trust weight for one recording."""

    role = str(group.get("meta_dataset_role", pd.Series(["training"])).dropna().iloc[0] if "meta_dataset_role" in group else "training").strip().lower()
    quality = 0.70
    if "meta_recording_quality_score" in group.columns:
        vals = pd.to_numeric(group["meta_recording_quality_score"], errors="coerce").dropna()
        if not vals.empty:
            quality = _numeric_score(vals.iloc[0], 0.70)
    label_conf = 1.0
    if role == "training_provisional_weak":
        label_conf = 0.40
    if "meta_label_confidence_score" in group.columns:
        vals = pd.to_numeric(group["meta_label_confidence_score"], errors="coerce").dropna()
        if not vals.empty:
            label_conf = _numeric_score(vals.iloc[0], label_conf)
    return max(0.05, quality * label_conf)


@dataclass(slots=True)
class OnlineTemporalTypeClassifier:
    model_path: Path = settings.base_dir / "models" / "temporal_type_model_v07.json"
    builder: TemporalFeatureBuilder | None = None
    # v0.7 scope. Additional UAV types are added only after their source policy
    # and independent recordings are defined.
    target_labels: tuple[str, ...] = ("Лютый", "FP-1")

    def __post_init__(self) -> None:
        self.builder = self.builder or TemporalFeatureBuilder(settings.temporal_type_hop_seconds)

    def train(self, frame: pd.DataFrame) -> dict[str, Any]:
        """Train source-balanced temporal prototypes from labelled feature rows."""

        source = frame.copy()
        if "meta_dataset_role" in source.columns:
            roles = source["meta_dataset_role"].fillna("training").astype(str).str.strip().str.lower()
            source = source[roles.isin(TRAIN_ROLES)].copy()
        target_labels = set(self.target_labels)
        source = source[source["label"].astype(str).isin(target_labels)].copy()
        labels = sorted(set(source["label"].astype(str)))
        if len(labels) < 2:
            raise ValueError("Temporal type training needs at least two UAV type labels.")

        horizons: dict[str, Any] = {}
        label_policy: dict[str, str] = {}
        for label, group in source.groupby("label"):
            roles = set(group.get("meta_dataset_role", pd.Series(["training"])).fillna("training").astype(str).str.lower())
            source_count = int(group["source_file"].astype(str).nunique()) if "source_file" in group.columns else 0
            if "training_provisional_weak" in roles or label in settings.ml_weak_labels:
                label_policy[str(label)] = "weak"
            elif "training_provisional" in roles or label in settings.ml_provisional_labels or source_count < 2:
                # Even a formally confirmed class cannot create a hard type lock
                # from a single physical recording.
                label_policy[str(label)] = "provisional"
            else:
                label_policy[str(label)] = "validated"

        for horizon in settings.temporal_type_window_seconds:
            temporal = self.builder.build(source, horizon)
            temporal = self._balance_temporal_windows(temporal)
            if temporal.empty:
                continue
            X = temporal.loc[:, list(TEMPORAL_FEATURE_COLUMNS)].to_numpy(float)
            mean = np.mean(X, axis=0)
            std = np.std(X, axis=0)
            std = np.where(std < 1e-9, 1.0, std)
            Z = (X - mean) / std
            temporal = temporal.reset_index(drop=True)
            source_centroids: dict[str, dict[str, Any]] = {}
            for (label, src), indices in temporal.groupby(["label", "source_file"]).groups.items():
                idx = np.asarray(list(indices), dtype=int)
                group = temporal.loc[idx]
                centroid = np.median(Z[idx], axis=0)
                source_centroids[str(src)] = {
                    "label": str(label),
                    "centroid": centroid.tolist(),
                    "weight": source_training_weight(group),
                    "role": str(group.get("meta_dataset_role", pd.Series(["training"])).dropna().iloc[0] if "meta_dataset_role" in group else "training"),
                    "windows": int(len(idx)),
                }

            classes: dict[str, Any] = {}
            for label in labels:
                items = [item for item in source_centroids.values() if item["label"] == label]
                if not items:
                    continue
                vectors = np.asarray([item["centroid"] for item in items], dtype=float)
                weights = np.asarray([float(item["weight"]) for item in items], dtype=float)
                weights = weights / max(float(weights.sum()), 1e-12)
                centroid = np.average(vectors, axis=0, weights=weights)
                d = np.linalg.norm(vectors - centroid, axis=1)
                radius = max(float(np.percentile(d, 90)) if d.size > 1 else float(np.sqrt(len(TEMPORAL_FEATURE_COLUMNS))), 1.0)
                classes[label] = {
                    "centroid": centroid.tolist(),
                    "radius": radius,
                    "sources": len(items),
                    "source_ids": [src for src, item in source_centroids.items() if item["label"] == label],
                }
            horizons[str(float(horizon))] = {
                "mean": mean.tolist(),
                "std": std.tolist(),
                "classes": classes,
                "source_centroids": source_centroids,
                "windows": int(len(temporal)),
            }

        readiness = assess_type_readiness(source, self.target_labels)
        payload = {
            "model_type": "online_temporal_source_prototype_v07",
            "version": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "feature_columns": list(TEMPORAL_FEATURE_COLUMNS),
            "horizons": horizons,
            "label_policy": label_policy,
            "type_readiness": readiness.to_dict(),
            "type_lock_policy": {
                "validated_only": True,
                "provisional_labels": sorted([k for k, v in label_policy.items() if v == "provisional"]),
                "weak_labels": sorted([k for k, v in label_policy.items() if v == "weak"]),
            },
            "timing": {
                "candidate_target_seconds": settings.temporal_candidate_seconds,
                "first_type_target_seconds": settings.temporal_first_type_target_seconds,
                "stable_type_target_seconds": settings.temporal_stable_type_target_seconds,
                "evidence_window_range": [
                    settings.hierarchy_min_evidence_windows,
                    settings.hierarchy_max_evidence_windows,
                ],
                "flyover_design_seconds": [40.0, 60.0],
            },
        }
        write_json(self.model_path, payload)
        return payload

    def load(self) -> dict[str, Any] | None:
        if not self.model_path.exists():
            return None
        payload = json.loads(self.model_path.read_text(encoding="utf-8"))
        if tuple(payload.get("feature_columns", ())) != TEMPORAL_FEATURE_COLUMNS:
            return None
        expected_horizons = {str(float(value)) for value in settings.temporal_type_window_seconds}
        if set(payload.get("horizons", {})) != expected_horizons:
            return None
        return payload

    def predict_window(self, vector: dict[str, float], horizon: float, model: dict[str, Any] | None = None) -> dict[str, Any]:
        model = model or self.load()
        if not model:
            return {"best_label": "UNKNOWN", "confidence": 0.0, "margin": 0.0, "scores": {}}
        data = model.get("horizons", {}).get(str(float(horizon)))
        if not data:
            return {"best_label": "UNKNOWN", "confidence": 0.0, "margin": 0.0, "scores": {}}
        x = np.asarray([float(vector.get(name, 0.0)) for name in TEMPORAL_FEATURE_COLUMNS], dtype=float)
        mean = np.asarray(data["mean"], dtype=float)
        std = np.asarray(data["std"], dtype=float)
        z = (x - mean) / np.where(std < 1e-9, 1.0, std)
        raw: dict[str, float] = {}
        distances: dict[str, float] = {}
        source_bank = data.get("source_centroids", {})
        feature_scale = max(float(np.sqrt(len(TEMPORAL_FEATURE_COLUMNS))), 1.0)
        for label, item in data.get("classes", {}).items():
            # Use the closest independent source prototypes rather than a single
            # class centroid. This is essential for weak/heterogeneous labels:
            # their diversity should lower the type margin, not manufacture a
            # distant average that makes another class look falsely certain.
            source_vectors = [
                np.asarray(source_item["centroid"], dtype=float)
                for source_item in source_bank.values()
                if str(source_item.get("label")) == str(label)
            ]
            if source_vectors:
                bank = np.stack(source_vectors)
                source_distances = np.linalg.norm(bank - z[None, :], axis=1)
                k = min(2, len(source_distances))
                distance = float(np.mean(np.sort(source_distances)[:k]))
                scale = feature_scale
            else:
                centroid = np.asarray(item["centroid"], dtype=float)
                distance = float(np.linalg.norm(z - centroid))
                scale = max(float(item.get("radius", feature_scale)), 1.0)
            distances[label] = distance
            raw[label] = float(np.exp(-0.5 * (distance / scale) ** 2))
        if not raw:
            return {"best_label": "UNKNOWN", "confidence": 0.0, "margin": 0.0, "scores": {}}
        total = max(float(sum(raw.values())), 1e-12)
        normalized = {label: score / total for label, score in raw.items()}
        ranking = sorted(normalized.items(), key=lambda item: item[1], reverse=True)
        raw_best_label, relative = ranking[0]
        runner = ranking[1][1] if len(ranking) > 1 else 0.0
        absolute_fit = float(np.clip(raw[raw_best_label], 0.0, 1.0))
        confidence = float(relative * (0.45 + 0.55 * absolute_fit))
        margin = float(relative - runner)
        # A single temporal horizon is not allowed to create a type decision by
        # itself at low confidence.  Keep the raw nearest label nevertheless so
        # the 4 s, 6 s and 8 s horizons can be fused without destroying evidence.
        # The operational decision remains gated later by combined 4/6/8-window
        # confidence, margin, label policy and stability.
        best_label = raw_best_label if confidence >= 0.50 else "UNKNOWN"
        return {
            "best_label": best_label,
            "raw_best_label": raw_best_label,
            "confidence": confidence,
            "margin": margin,
            "scores": normalized,
            "distances": distances,
            "absolute_fit": absolute_fit,
        }

    def replay(self, frame: pd.DataFrame, *, source_file: str | None = None, candidate_detection_seconds: float | None = None, model: dict[str, Any] | None = None) -> OnlineTypeReplay:
        """Replay one recording and measure time to conservative type hypotheses."""

        model = model or self.load()
        if not model:
            raise ValueError("Temporal type model is not trained.")
        g = frame.sort_values("start_seconds").copy()
        if source_file is None:
            source_file = str(g["source_file"].iloc[0]) if "source_file" in g.columns and not g.empty else "source"
        end = float(pd.to_numeric(g["start_seconds"], errors="coerce").fillna(0.0).max() + 1.0) if not g.empty else 0.0
        snapshots: list[OnlineTypeSnapshot] = []
        first_hypothesis: float | None = None
        stable_time: float | None = None
        streak_label: str | None = None
        streak = 0
        final_label = "UNKNOWN"
        final_status = "unknown"
        final_lock = False
        policy = model.get("label_policy", {})

        horizon_total = max(sum(float(value) for value in settings.temporal_type_window_seconds), 1.0)
        start_time = min(settings.temporal_type_window_seconds)
        operational_ready = bool(model.get("type_readiness", {}).get("operational_validation_ready", False))
        for t in np.arange(start_time, end + 1e-9, settings.temporal_type_hop_seconds):
            predictions: list[tuple[float, dict[str, Any]]] = []
            for horizon in settings.temporal_type_window_seconds:
                weight = float(horizon) / horizon_total
                if t + 1e-9 < horizon:
                    continue
                start = t - horizon
                row_duration = 1.0
                centers = pd.to_numeric(g["start_seconds"], errors="coerce").fillna(0.0).to_numpy(float) + row_duration / 2.0
                segment = g.loc[(centers >= start) & (centers <= t)]
                if len(segment) < max(3, int(round(horizon))):
                    continue
                from ml.temporal_features import temporal_vector
                pred = self.predict_window(temporal_vector(segment), horizon, model)
                predictions.append((weight, pred))
            if not predictions:
                continue
            labels = sorted({label for _, pred in predictions for label in pred.get("scores", {})})
            combined = {label: 0.0 for label in labels}
            total_weight = sum(weight for weight, _ in predictions)
            for weight, pred in predictions:
                for label in labels:
                    combined[label] += weight * float(pred.get("scores", {}).get(label, 0.0))
            if total_weight > 0:
                combined = {k: v / total_weight for k, v in combined.items()}
            ranking = sorted(combined.items(), key=lambda item: item[1], reverse=True)
            best_label = ranking[0][0] if ranking else "UNKNOWN"
            relative = ranking[0][1] if ranking else 0.0
            runner = ranking[1][1] if len(ranking) > 1 else 0.0
            # Require individual horizons to support the same label. Contradicting
            # horizons are evidence of uncertainty, not a reason to average into a
            # confident-looking binary probability.
            support = [pred for _, pred in predictions if pred.get("raw_best_label", pred.get("best_label")) == best_label]
            support_weight = sum(weight for weight, pred in predictions if pred in support) / max(total_weight, 1e-12)
            absolute = float(np.mean([pred.get("absolute_fit", 0.0) for pred in support])) if support else 0.0
            confidence = float(relative * (0.45 + 0.55 * absolute) * (0.55 + 0.45 * support_weight))
            margin = float(relative - runner)
            if confidence < settings.temporal_min_hypothesis_score or margin < settings.temporal_min_hypothesis_margin:
                best_label = "UNKNOWN"

            if t < 8.0:
                phase = "early_type"
            elif t < 20.0:
                phase = "temporal"
            else:
                phase = "refinement"

            if best_label != "UNKNOWN":
                if first_hypothesis is None:
                    first_hypothesis = float(t)
                if best_label == streak_label and confidence >= settings.temporal_min_stable_score and margin >= settings.temporal_min_stable_margin:
                    streak += 1
                elif confidence >= settings.temporal_min_stable_score and margin >= settings.temporal_min_stable_margin:
                    streak_label = best_label
                    streak = 1
                else:
                    streak_label = best_label
                    streak = 0
            else:
                # Contradictory/insufficient evidence removes any pending type lock.
                streak_label = None
                streak = 0

            label_policy = policy.get(best_label, "validated") if best_label != "UNKNOWN" else "unknown"
            lock_allowed = operational_ready and label_policy == "validated"
            if best_label == "UNKNOWN":
                status = "unknown"
            elif label_policy == "weak":
                status = "weak_candidate"
            else:
                status = "provisional_candidate"
            if streak >= settings.temporal_stable_updates and stable_time is None:
                stable_time = float(t)
                status = "research_stable" if not lock_allowed else "research_stable"
            final_label = best_label
            final_status = status
            final_lock = lock_allowed and streak >= settings.temporal_stable_updates
            snapshots.append(OnlineTypeSnapshot(
                time_seconds=float(round(t, 3)),
                phase=phase,
                best_label=best_label,
                confidence=float(round(confidence, 4)),
                margin=float(round(margin, 4)),
                status=status,
                type_lock_allowed=bool(lock_allowed),
                evidence_seconds=float(round(t - (candidate_detection_seconds or 0.0), 3)),
            ))

        return OnlineTypeReplay(
            source_file=str(source_file),
            candidate_detection_seconds=candidate_detection_seconds,
            first_type_hypothesis_seconds=first_hypothesis,
            research_stable_seconds=stable_time,
            final_label=final_label,
            final_status=final_status,
            type_lock_allowed=final_lock,
            snapshots=snapshots,
        )

    @staticmethod
    def _balance_temporal_windows(frame: pd.DataFrame, max_per_source: int = 8) -> pd.DataFrame:
        parts: list[pd.DataFrame] = []
        for _, group in frame.groupby(["label", "source_file"], sort=False):
            g = group.sort_values("start_seconds")
            if len(g) > max_per_source:
                positions = np.linspace(0, len(g) - 1, max_per_source)
                g = g.iloc[sorted(set(int(round(v)) for v in positions))]
            parts.append(g)
        return pd.concat(parts, ignore_index=True) if parts else frame.iloc[0:0].copy()

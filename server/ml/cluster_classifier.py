"""Offline KNN/prototype classifier for labeled acoustic feature clusters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import settings
from ml.feature_vector import FEATURE_COLUMNS, feature_set_to_vector
from models.schemas import (
    AudioFeatureSet,
    MLClassificationResult,
    MLClassificationScore,
    ModelTrainingResult,
)
from utils.serialization import write_json


@dataclass(slots=True)
class CentroidAudioClassifier:
    """Train and run a compact local model from extracted audio features."""

    dataset_path: Path = settings.feature_dataset_path
    model_path: Path = settings.ml_model_path
    unknown_threshold: float = settings.ml_unknown_threshold

    def train(self) -> ModelTrainingResult:
        """Train local class prototypes from the labeled feature dataset."""

        if not self.dataset_path.exists():
            return ModelTrainingResult(
                trained=False,
                model_path=str(self.model_path),
                labels=0,
                samples=0,
                message="Нет dataset/features.csv. Сначала добавьте размеченные записи.",
            )

        dataset = pd.read_csv(self.dataset_path)
        if dataset.empty or "label" not in dataset.columns:
            return ModelTrainingResult(
                trained=False,
                model_path=str(self.model_path),
                labels=0,
                samples=0,
                message="Датасет пустой или не содержит метки классов.",
            )

        dataset = self._clean_dataset(dataset)
        label_counts = dataset["label"].value_counts().sort_index()
        provisional_labels: list[str] = []
        weak_labels: list[str] = []
        if "meta_dataset_role" in dataset.columns:
            roles = dataset["meta_dataset_role"].fillna("training").astype(str).str.strip().str.lower()
            provisional_labels = sorted(set(dataset.loc[roles == "training_provisional", "label"].astype(str).tolist()))
            weak_labels = sorted(set(dataset.loc[roles == "training_provisional_weak", "label"].astype(str).tolist()))
        if len(label_counts) < 2:
            return ModelTrainingResult(
                trained=False,
                model_path=str(self.model_path),
                labels=int(len(label_counts)),
                samples=int(len(dataset)),
                message="Для разделения нужны минимум два класса звуков.",
            )

        # Do not let hundreds of overlapping windows from one long recording
        # outweigh another class/source. Training uses a decorrelated,
        # source-balanced prototype frame. Raw windows remain in features.csv
        # for audit/visualization, but are not all copied into KNN.
        training = self._source_balanced_rows(dataset)
        feature_columns = list(FEATURE_COLUMNS)
        matrix = training.loc[:, feature_columns].to_numpy(dtype=np.float64)
        mean = np.mean(matrix, axis=0)
        std = np.std(matrix, axis=0)
        std = np.where(std < 1e-9, 1.0, std)
        normalized = (matrix - mean) / std

        classes: dict[str, dict[str, Any]] = {}
        source_counts: dict[str, int] = {}
        train_labels = training["label"].astype(str).to_numpy()
        for label in sorted(label_counts.index):
            label_mask = train_labels == label
            vectors = normalized[label_mask]
            if "source_file" in training.columns:
                sources = training.loc[label_mask, "source_file"].astype(str).to_numpy()
                unique_sources = sorted(set(sources.tolist()))
                source_counts[str(label)] = len(unique_sources)
                source_centroids = np.asarray([vectors[sources == src].mean(axis=0) for src in unique_sources])
                centroid = np.mean(source_centroids, axis=0)
            else:
                source_counts[str(label)] = 0
                centroid = np.mean(vectors, axis=0)
            distances = np.linalg.norm(vectors - centroid, axis=1)
            radius = float(np.percentile(distances, 80)) if distances.size else 1.0
            classes[str(label)] = {
                "centroid": centroid.tolist(),
                "radius": max(radius, 0.75),
                "samples": int(label_counts[label]),
                "prototype_samples": int(np.sum(label_mask)),
                "sources": int(source_counts[str(label)]),
            }

        payload = {
            "model_type": "source_balanced_knn_centroid_v2",
            "version": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "feature_columns": list(FEATURE_COLUMNS),
            "mean": mean.tolist(),
            "std": std.tolist(),
            "classes": classes,
            "prototypes": {
                "labels": training["label"].astype(str).tolist(),
                "vectors": normalized.tolist(),
                "source_files": training["source_file"].astype(str).tolist() if "source_file" in training.columns else [],
            },
            "training_guard": {
                "source_balanced": True,
                "max_prototypes_per_source": int(settings.ml_max_prototypes_per_source),
                "min_prototype_spacing_seconds": float(settings.ml_min_prototype_spacing_seconds),
                "sources_per_label": source_counts,
                "provisional_labels": provisional_labels,
                "weak_labels": weak_labels,
                "independent_validation_ready": bool(
                    source_counts
                    and all(
                        count >= 2
                        for label, count in source_counts.items()
                        if label not in set(provisional_labels) | set(weak_labels)
                    )
                ),
            },
            "samples_total": int(len(dataset)),
            "prototype_samples_total": int(len(training)),
            "labels_total": int(len(classes)),
        }
        write_json(self.model_path, payload)
        return ModelTrainingResult(
            trained=True,
            model_path=str(self.model_path),
            labels=int(len(classes)),
            samples=int(len(dataset)),
            message="Модель классов обучена.",
        )

    def predict(self, features: AudioFeatureSet) -> MLClassificationResult | None:
        """Predict a label for one extracted feature set, if a model exists."""

        model = self.load_model()
        if model is None:
            return None

        vector = feature_set_to_vector(features)
        return self._predict_vector(vector, model, status="single")

    def predict_many(self, features: list[AudioFeatureSet]) -> MLClassificationResult | None:
        """Predict one label by averaging class scores over many windows."""

        model = self.load_model()
        if model is None or not features:
            return None

        predictions = [
            self._predict_vector(feature_set_to_vector(item), model, status="window")
            for item in features
        ]
        predictions = [item for item in predictions if item is not None]
        if not predictions:
            return None

        labels = sorted({
            score.label
            for prediction in predictions
            for score in prediction.scores
        })
        class_samples = {
            score.label: score.samples
            for prediction in predictions
            for score in prediction.scores
        }
        votes = {label: 0 for label in labels}
        for prediction in predictions:
            votes[prediction.scores[0].label] += 1

        averaged_scores: list[MLClassificationScore] = []
        for label in labels:
            distance_values = [
                next(score.distance for score in prediction.scores if score.label == label)
                for prediction in predictions
                if any(score.label == label for score in prediction.scores)
            ]
            averaged_scores.append(
                MLClassificationScore(
                    label=label,
                    score=float(votes[label] / len(predictions)),
                    distance=float(np.mean(distance_values)) if distance_values else float("inf"),
                    samples=int(class_samples.get(label, 0)),
                )
            )

        averaged_scores.sort(key=lambda item: item.score, reverse=True)
        best = averaged_scores[0]
        best_label = best.label if best.score >= self.unknown_threshold else "UNKNOWN"
        explanation = self._explain(best_label, best, averaged_scores)
        explanation += f" Оценка усреднена по {len(predictions)} аудио-окнам."
        status_out, explanation = self._apply_provisional_status(best_label, "windowed", explanation, model)
        return MLClassificationResult(
            best_label=best_label,
            confidence=float(best.score),
            scores=averaged_scores,
            model_version=str(model.get("version", "unknown")),
            samples_total=int(model.get("samples_total", 0)),
            labels_total=int(model.get("labels_total", len(labels))),
            status=status_out,
            explanation=explanation,
        )

    def _predict_vector(
        self,
        vector: np.ndarray,
        model: dict[str, Any],
        status: str,
    ) -> MLClassificationResult | None:
        """Predict from a prepared vector and loaded model."""

        mean = np.asarray(model["mean"], dtype=np.float64)
        std = np.asarray(model["std"], dtype=np.float64)
        std = np.where(std < 1e-9, 1.0, std)
        normalized = (vector - mean) / std

        knn_scores = self._knn_scores(normalized, model)
        if knn_scores is not None:
            best = knn_scores[0]
            best_label = best.label if best.score >= self.unknown_threshold else "UNKNOWN"
            explanation = self._explain(best_label, best, knn_scores)
            status_out, explanation = self._apply_provisional_status(best_label, status, explanation, model)
            return MLClassificationResult(
                best_label=best_label,
                confidence=float(best.score),
                scores=knn_scores,
                model_version=str(model.get("version", "unknown")),
                samples_total=int(model.get("samples_total", 0)),
                labels_total=int(model.get("labels_total", len(knn_scores))),
                status=status_out,
                explanation=explanation,
            )

        scores: list[MLClassificationScore] = []
        raw_scores: list[float] = []
        classes: dict[str, Any] = model.get("classes", {})
        for label, class_data in classes.items():
            centroid = np.asarray(class_data["centroid"], dtype=np.float64)
            radius = max(float(class_data.get("radius", 1.0)), 0.75)
            distance = float(np.linalg.norm(normalized - centroid))
            raw = float(np.exp(-0.5 * (distance / radius) ** 2))
            raw_scores.append(raw)
            scores.append(
                MLClassificationScore(
                    label=label,
                    score=raw,
                    distance=distance,
                    samples=int(class_data.get("samples", 0)),
                )
            )

        if not scores:
            return None

        total_raw = max(float(np.sum(raw_scores)), 1e-12)
        normalized_scores = [
            score.model_copy(update={"score": float(score.score / total_raw)})
            for score in scores
        ]
        normalized_scores.sort(key=lambda item: item.score, reverse=True)
        best = normalized_scores[0]
        best_label = best.label if best.score >= self.unknown_threshold else "UNKNOWN"
        explanation = self._explain(best_label, best, normalized_scores)
        status_out, explanation = self._apply_provisional_status(best_label, status, explanation, model)
        return MLClassificationResult(
            best_label=best_label,
            confidence=float(best.score),
            scores=normalized_scores,
            model_version=str(model.get("version", "unknown")),
            samples_total=int(model.get("samples_total", 0)),
            labels_total=int(model.get("labels_total", len(classes))),
            status=status_out,
            explanation=explanation,
        )

    @staticmethod
    def _knn_scores(
        normalized: np.ndarray,
        model: dict[str, Any],
    ) -> list[MLClassificationScore] | None:
        """Return label scores from nearest stored training windows."""

        prototypes = model.get("prototypes")
        if not prototypes:
            return None

        vectors = np.asarray(prototypes.get("vectors", []), dtype=np.float64)
        labels = [str(label) for label in prototypes.get("labels", [])]
        if vectors.ndim != 2 or vectors.shape[0] == 0 or vectors.shape[0] != len(labels):
            return None

        distances = np.linalg.norm(vectors - normalized, axis=1)
        neighbor_count = min(settings.ml_knn_neighbors, len(distances))
        if neighbor_count <= 0:
            return None

        nearest = np.argpartition(distances, neighbor_count - 1)[:neighbor_count]
        nearest = nearest[np.argsort(distances[nearest])]
        weights: dict[str, float] = {}
        nearest_distance: dict[str, float] = {}
        for index in nearest:
            label = labels[int(index)]
            distance = float(distances[int(index)])
            weight = 1.0 / max(distance, 1e-6)
            weights[label] = weights.get(label, 0.0) + weight
            nearest_distance[label] = min(nearest_distance.get(label, distance), distance)

        total_weight = max(float(sum(weights.values())), 1e-12)
        class_samples = {
            label: int(class_data.get("samples", 0))
            for label, class_data in model.get("classes", {}).items()
        }
        scores = [
            MLClassificationScore(
                label=label,
                score=float(weight / total_weight),
                distance=float(nearest_distance.get(label, np.inf)),
                samples=int(class_samples.get(label, 0)),
            )
            for label, weight in weights.items()
        ]
        scores.sort(key=lambda item: item.score, reverse=True)
        return scores

    def load_model(self) -> dict[str, Any] | None:
        """Load the model JSON if it exists and matches the feature schema."""

        if not self.model_path.exists():
            return None
        payload = json.loads(self.model_path.read_text(encoding="utf-8"))
        if tuple(payload.get("feature_columns", ())) != FEATURE_COLUMNS:
            return None
        return payload

    def model_info(self) -> dict[str, Any]:
        """Return compact model metadata for the web interface."""

        model = self.load_model()
        if model is None:
            return {
                "exists": False,
                "labels": 0,
                "samples": 0,
                "version": None,
            }
        return {
            "exists": True,
            "labels": int(model.get("labels_total", 0)),
            "samples": int(model.get("samples_total", 0)),
            "version": model.get("version"),
            "provisional_labels": list(model.get("training_guard", {}).get("provisional_labels", [])),
            "independent_validation_ready": bool(model.get("training_guard", {}).get("independent_validation_ready", False)),
        }

    @staticmethod
    def _source_balanced_rows(dataset: pd.DataFrame) -> pd.DataFrame:
        """Return decorrelated rows with bounded, equal influence per source."""

        if "source_file" not in dataset.columns:
            return dataset.copy().reset_index(drop=True)
        selected: list[pd.DataFrame] = []
        max_per_source = max(int(settings.ml_max_prototypes_per_source), 1)
        min_spacing = max(float(settings.ml_min_prototype_spacing_seconds), 0.0)
        for _, group in dataset.groupby(["label", "source_file"], sort=False):
            g = group.copy()
            if "start_seconds" in g.columns:
                g = g.sort_values("start_seconds")
                keep = []
                last = -float("inf")
                for idx, row in g.iterrows():
                    t = float(row.get("start_seconds", 0.0))
                    if t - last + 1e-9 >= min_spacing:
                        keep.append(idx)
                        last = t
                g = g.loc[keep]
            if len(g) > max_per_source:
                positions = np.linspace(0, len(g) - 1, max_per_source)
                g = g.iloc[sorted(set(int(round(x)) for x in positions))]
            selected.append(g)
        if not selected:
            return dataset.copy().reset_index(drop=True)
        return pd.concat(selected, ignore_index=True)

    @staticmethod
    def _clean_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
        """Keep only finite feature rows with non-empty labels."""

        for column in FEATURE_COLUMNS:
            if column not in dataset.columns:
                dataset[column] = 0.0
        dataset["label"] = dataset["label"].astype(str).str.strip()
        dataset = dataset[dataset["label"] != ""]
        # Research/validation recordings are deliberately excluded from model fitting.
        if "meta_dataset_role" in dataset.columns:
            roles = dataset["meta_dataset_role"].fillna("training").astype(str).str.strip().str.lower()
            dataset = dataset[roles.isin({"training", "training_provisional", "training_provisional_weak"})]
        feature_columns = list(FEATURE_COLUMNS)
        dataset.loc[:, feature_columns] = dataset.loc[:, feature_columns].apply(
            pd.to_numeric,
            errors="coerce",
        )
        dataset.loc[:, feature_columns] = dataset.loc[:, feature_columns].replace(
            [np.inf, -np.inf],
            np.nan,
        )
        dataset.loc[:, feature_columns] = dataset.loc[:, feature_columns].fillna(0.0)
        return dataset.reset_index(drop=True)

    @staticmethod
    def _apply_provisional_status(
        best_label: str,
        status: str,
        explanation: str,
        model: dict[str, Any],
    ) -> tuple[str, str]:
        """Mark provisional training classes without removing them from inference."""

        guard = model.get("training_guard", {})
        weak = set(guard.get("weak_labels", []))
        provisional = set(guard.get("provisional_labels", []))
        if best_label in weak:
            return (
                "weak_candidate",
                explanation
                + " Метка этого класса в текущей базе считается слабой/неподтверждённой; "
                  "результат нельзя использовать как жёсткую идентификацию типа.",
            )
        if best_label in provisional:
            return (
                "provisional_candidate",
                explanation
                + " Класс используется в обучении как предварительный и пока не является "
                  "эталонным/валидационным классом; результат требует подтверждения.",
            )
        return status, explanation

    @staticmethod
    def _explain(
        best_label: str,
        best: MLClassificationScore,
        scores: list[MLClassificationScore],
    ) -> str:
        """Build a concise Russian explanation of the cluster decision."""

        if best_label == "UNKNOWN":
            return (
                "Локальная модель не нашла достаточно близкий обученный кластер. "
                f"Ближайший класс: {best.label} ({best.score:.0%})."
            )

        runner_up = scores[1] if len(scores) > 1 else None
        if runner_up is None:
            return f"Ближайший обученный кластер: {best.label} ({best.score:.0%})."
        return (
            f"Ближайший обученный кластер: {best.label} ({best.score:.0%}); "
            f"следующий: {runner_up.label} ({runner_up.score:.0%})."
        )

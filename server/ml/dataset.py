"""Management of the local labeled acoustic dataset."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from audio.features import FeatureExtractor
from audio.loader import AudioLoader
from audio.preprocessing import adaptive_window_rms_threshold
from config import settings
from ml.cluster_classifier import CentroidAudioClassifier
from ml.feature_vector import FEATURE_COLUMNS, feature_set_to_row
from ml.label_registry import load_registry, remove_label, upsert_label
from models.schemas import (
    DatasetAddResult,
    DatasetDeleteResult,
    DatasetLabelSummary,
    DatasetSummary,
    EvaluationResult,
    RecordingMetadata,
    UploadedFileInfo,
)
from utils.logging_utils import logger

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass(slots=True)
class SoundDatasetManager:
    """Store labeled recordings and extract windowed features for training."""

    dataset_dir: Path = settings.dataset_dir
    feature_dataset_path: Path = settings.feature_dataset_path
    loader: AudioLoader | None = None
    extractor: FeatureExtractor | None = None
    classifier: CentroidAudioClassifier | None = None

    def __post_init__(self) -> None:
        self.loader = self.loader or AudioLoader()
        self.extractor = self.extractor or FeatureExtractor()
        self.classifier = self.classifier or CentroidAudioClassifier(
            dataset_path=self.feature_dataset_path,
            model_path=settings.ml_model_path,
        )

    def add_recording(
        self,
        label: str,
        source_file: UploadedFileInfo,
        window_seconds: float = settings.ml_window_seconds,
        hop_seconds: float = settings.ml_hop_seconds,
        min_window_rms: float = settings.ml_min_window_rms,
        max_windows_per_file: int = settings.ml_max_windows_per_file,
        metadata: RecordingMetadata | None = None,
        include_intervals: list[tuple[float, float]] | None = None,
    ) -> DatasetAddResult:
        """Extract labeled feature windows (and optional metadata) from one file."""

        clean_label = self.normalize_label(label)
        if not clean_label:
            raise ValueError("Label is required.")
        if window_seconds <= 0:
            raise ValueError("Window length must be positive.")
        if hop_seconds <= 0:
            raise ValueError("Hop length must be positive.")

        path = Path(source_file.stored_path)
        # Store the source path RELATIVE to the project root so the dataset is
        # portable and never bakes in an absolute machine path with a username.
        try:
            stored_source = str(path.resolve().relative_to(settings.base_dir.resolve()))
        except ValueError:
            stored_source = path.name
        loaded = self.loader.load_audio(path)
        window_size = max(int(round(window_seconds * loaded.sample_rate)), 1)
        hop_size = max(int(round(hop_seconds * loaded.sample_rate)), 1)
        if len(loaded.signal) < window_size:
            starts = [0]
            window_size = len(loaded.signal)
        else:
            starts = list(range(0, len(loaded.signal) - window_size + 1, hop_size))
        if max_windows_per_file > 0 and len(starts) > max_windows_per_file:
            selected = np.linspace(0, len(starts) - 1, max_windows_per_file)
            starts = [starts[int(round(index))] for index in selected]
        effective_min_window_rms = adaptive_window_rms_threshold(
            loaded.signal, window_size, hop_size, min_window_rms
        )

        rows: list[dict[str, object]] = []
        warnings = list(loaded.warnings)
        intervals = self._normalize_intervals(include_intervals, loaded.duration_seconds)
        if include_intervals and not intervals:
            warnings.append("Заданные интервалы цели не пересекаются с записью; окна не добавлены.")
        for window_index, start in enumerate(starts):
            center_seconds = (start + window_size / 2.0) / loaded.sample_rate
            if intervals and not any(left <= center_seconds <= right for left, right in intervals):
                continue
            if include_intervals and not intervals:
                continue
            segment = loaded.signal[start:start + window_size]
            rms = float(np.sqrt(np.mean(np.square(segment)))) if segment.size else 0.0
            if rms < effective_min_window_rms:
                continue
            extraction = self.extractor.extract(segment.astype(np.float32), loaded.sample_rate)
            row: dict[str, object] = {
                "record_id": uuid.uuid4().hex,
                "label": clean_label,
                "source_file": stored_source,
                "original_name": source_file.original_name,
                "window_index": window_index,
                "start_seconds": round(start / loaded.sample_rate, 4),
                "duration_seconds": round(len(segment) / loaded.sample_rate, 4),
                "sample_rate": loaded.sample_rate,
                "channels": loaded.channels,
            }
            row.update(feature_set_to_row(extraction.features))
            if metadata is not None:
                row.update(metadata.to_row())
            rows.append(row)

        if not rows:
            warnings.append("No windows were added: all windows were too quiet or unreadable.")
            return DatasetAddResult(
                label=clean_label,
                files_added=1,
                windows_added=0,
                warnings=warnings,
            )

        self._append_rows(rows)
        if metadata is not None:
            upsert_label(
                clean_label,
                category=metadata.category,
                is_drone=metadata.is_drone or metadata.category == "drone",
                last_metadata=metadata,
            )
        logger.info(
            "Added %s dataset windows for label %s from %s",
            len(rows),
            clean_label,
            path.name,
        )
        return DatasetAddResult(
            label=clean_label,
            files_added=1,
            windows_added=len(rows),
            warnings=warnings,
        )

    def summary(self) -> DatasetSummary:
        """Return current dataset and model statistics."""

        dataset = self._read_dataset()
        registry = load_registry()
        labels: list[DatasetLabelSummary] = []
        total_windows = 0
        total_files = 0
        if not dataset.empty and "label" in dataset.columns:
            grouped = dataset.groupby("label", sort=True)
            for label, group in grouped:
                file_count = int(group["source_file"].nunique()) if "source_file" in group else 0
                window_count = int(len(group))
                meta = registry.labels.get(str(label))
                labels.append(
                    DatasetLabelSummary(
                        label=str(label),
                        windows=window_count,
                        files=file_count,
                        category=meta.category if meta else "background",
                        is_drone=bool(meta.is_drone) if meta else False,
                        # Raw image path here; the web route converts it to a URL.
                        image_url=meta.image_path if (meta and meta.image_path) else None,
                        description=meta.description if meta else None,
                    )
                )
            total_windows = int(len(dataset))
            total_files = int(dataset["source_file"].nunique()) if "source_file" in dataset else 0

        model_info = self.classifier.model_info() if self.classifier else {}
        return DatasetSummary(
            total_windows=total_windows,
            total_files=total_files,
            labels=labels,
            feature_dataset_path=str(self.feature_dataset_path),
            model_path=str(settings.ml_model_path),
            model_exists=bool(model_info.get("exists", False)),
            model_labels=int(model_info.get("labels", 0)),
            model_samples=int(model_info.get("samples", 0)),
            model_version=model_info.get("version"),
        )

    # ------------------------------------------------------------------ #
    # Management: delete, image attachment, accuracy estimate            #
    # ------------------------------------------------------------------ #

    def _backup_csv(self, suffix: str) -> Path | None:
        """Copy features.csv into dataset/_backups/ before a destructive op."""

        if not self.feature_dataset_path.exists():
            return None
        backups = self.dataset_dir / "_backups"
        backups.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = backups / f"features.before_{suffix}_{ts}.csv"
        shutil.copy2(self.feature_dataset_path, dest)
        return dest

    def delete_label(self, label: str) -> DatasetDeleteResult:
        """Remove a whole class: CSV rows, raw audio/image, registry entry."""

        clean = self.normalize_label(label)
        backup = self._backup_csv(f"delete_{self._label_dir_name(clean)}")
        rows_removed = 0
        files_removed = 0
        df = self._read_dataset()
        if not df.empty and "label" in df.columns:
            mask = df["label"].astype(str) == clean
            rows_removed = int(mask.sum())
            if "source_file" in df.columns:
                files_removed = int(df.loc[mask, "source_file"].nunique())
            df = df[~mask]
            if df.empty:
                self.feature_dataset_path.unlink(missing_ok=True)
            else:
                df.to_csv(self.feature_dataset_path, index=False)

        raw = self.dataset_dir / "raw" / self._label_dir_name(clean)
        image_removed = False
        if raw.exists():
            image_removed = any(raw.glob("_image.*"))
            shutil.rmtree(raw, ignore_errors=True)
        remove_label(clean)
        return DatasetDeleteResult(
            label=clean,
            rows_removed=rows_removed,
            files_removed=files_removed,
            image_removed=image_removed,
            backup_path=str(backup) if backup else None,
            message=f"Класс «{clean}» удалён: окон {rows_removed}, файлов {files_removed}.",
        )

    def delete_source(self, label: str, source_file: str) -> DatasetDeleteResult:
        """Remove a single recording (all windows of one source file)."""

        clean = self.normalize_label(label)
        backup = self._backup_csv("delete_source")
        rows_removed = 0
        df = self._read_dataset()
        if not df.empty and "source_file" in df.columns:
            mask = df["source_file"].astype(str) == str(source_file)
            rows_removed = int(mask.sum())
            df = df[~mask]
            if df.empty:
                self.feature_dataset_path.unlink(missing_ok=True)
            else:
                df.to_csv(self.feature_dataset_path, index=False)
        try:
            candidate = Path(source_file)
            source_path = (
                candidate.resolve()
                if candidate.is_absolute()
                else (settings.base_dir / candidate).resolve()
            )
            raw_root = (self.dataset_dir / "raw").resolve()
            if source_path.exists() and raw_root in source_path.parents:
                shutil.rmtree(source_path.parent, ignore_errors=True)
        except Exception:
            logger.exception("Could not remove raw recording folder for %s", source_file)
        return DatasetDeleteResult(
            label=clean,
            rows_removed=rows_removed,
            files_removed=1 if rows_removed else 0,
            backup_path=str(backup) if backup else None,
            message=f"Запись удалена: окон {rows_removed}.",
        )

    def add_label_image(self, label: str, image: UploadedFileInfo) -> str:
        """Store one reference image per class as a canonical _image.<ext>."""

        clean = self.normalize_label(label)
        src = Path(image.stored_path)
        # Take the extension from the original name: safe_filename() strips
        # Cyrillic, which can leave the stored copy without a usable suffix.
        ext = Path(image.original_name or src.name).suffix.lower()
        if ext not in SUPPORTED_IMAGE_EXTENSIONS:
            allowed = ", ".join(sorted(e[1:].upper() for e in SUPPORTED_IMAGE_EXTENSIONS))
            raise ValueError(f"{src.name}: формат изображения не поддерживается ({allowed}).")
        raw = self.raw_label_dir(clean)
        for old in raw.glob("_image.*"):
            old.unlink(missing_ok=True)
        dest = raw / f"_image{ext}"
        shutil.copy2(src, dest)
        upsert_label(clean, image_path=str(dest))
        return str(dest)

    def evaluate(self, method: str = "leave_one_file_out", k: int = 5) -> EvaluationResult:
        """Estimate model accuracy with nearest-centroid cross-validation.

        Leave-one-file-out is the default because windows from the same recording
        are correlated; it falls back to stratified k-fold over windows when a
        class has too few files to hold one out.
        """

        df = self._read_dataset()
        if df.empty or "label" not in df.columns:
            return EvaluationResult(message="Недостаточно данных для оценки.")
        if "meta_dataset_role" in df.columns:
            roles = df["meta_dataset_role"].fillna("training").astype(str).str.strip().str.lower()
            df = df[roles == "training"].reset_index(drop=True)
        if df.empty:
            return EvaluationResult(message="Нет записей со статусом training для оценки.")
        for column in FEATURE_COLUMNS:
            if column not in df.columns:
                df[column] = 0.0
        X = np.nan_to_num(df[list(FEATURE_COLUMNS)].to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        y = df["label"].astype(str).to_numpy()
        classes = sorted(set(y.tolist()))
        if len(classes) < 2:
            return EvaluationResult(
                labels_total=len(classes),
                message="Нужно минимум 2 класса для оценки точности.",
            )
        groups = (
            df["source_file"].astype(str).to_numpy()
            if "source_file" in df.columns
            else None
        )
        files_per_label = {}
        if groups is not None:
            for label in classes:
                files_per_label[label] = len(set(groups[y == label].tolist()))
        can_lofo = (
            method == "leave_one_file_out"
            and groups is not None
            and all(count >= 2 for count in files_per_label.values())
        )
        if can_lofo:
            return self._evaluate_lofo(X, y, groups, classes)

        # Never report window-level k-fold as model accuracy when windows from
        # the same physical recording can appear in train and test. With a
        # 1.0 s window / 0.5 s hop this is severe leakage and can turn the
        # recording background into an apparent class signature.
        missing = [f"{label}: {files_per_label.get(label, 0)}" for label in classes if files_per_label.get(label, 0) < 2]
        if method == "leave_one_file_out":
            return EvaluationResult(
                method="independent_recordings_required",
                folds=0,
                accuracy=0.0,
                per_label_accuracy={},
                samples_evaluated=0,
                labels_total=len(classes),
                message=(
                    "Независимая оценка не выполнена: для LOFO нужно минимум 2 исходные записи "
                    "на каждый класс. Недостаточно: " + ", ".join(missing) + ". "
                    "Оконный k-fold намеренно отключён, так как он даёт утечку соседних окон одного файла."
                ),
            )
        return self._evaluate_kfold(X, y, classes, k)

    @staticmethod
    def _centroid_predict(train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray) -> np.ndarray:
        """Standardize on the train split and predict each test row's class."""

        mean = train_x.mean(axis=0)
        std = train_x.std(axis=0)
        std[std == 0] = 1.0
        train_n = (train_x - mean) / std
        test_n = (test_x - mean) / std
        classes = sorted(set(train_y.tolist()))
        centroids = np.array([train_n[train_y == c].mean(axis=0) for c in classes])
        distances = np.linalg.norm(test_n[:, None, :] - centroids[None, :, :], axis=2)
        nearest = distances.argmin(axis=1)
        return np.array([classes[i] for i in nearest])

    def _evaluate_lofo(self, X, y, groups, classes) -> EvaluationResult:
        files = sorted(set(groups.tolist()))
        correct = 0
        total = 0
        per_correct = {c: 0 for c in classes}
        per_total = {c: 0 for c in classes}
        for held in files:
            test_mask = groups == held
            train_mask = ~test_mask
            true_label = str(y[test_mask][0])
            if true_label not in set(y[train_mask].tolist()):
                continue
            preds = self._centroid_predict(X[train_mask], y[train_mask], X[test_mask])
            values, counts = np.unique(preds, return_counts=True)
            pred_label = str(values[counts.argmax()])
            total += 1
            per_total[true_label] += 1
            if pred_label == true_label:
                correct += 1
                per_correct[true_label] += 1
        if total == 0:
            return self._evaluate_kfold(X, y, classes, k=5)
        per_label = {
            c: round(per_correct[c] / per_total[c], 3)
            for c in classes
            if per_total[c] > 0
        }
        return EvaluationResult(
            method="leave_one_file_out",
            folds=total,
            accuracy=round(correct / total, 3),
            per_label_accuracy=per_label,
            samples_evaluated=total,
            labels_total=len(classes),
            message=f"Точность по записям (LOFO): {correct}/{total}.",
        )

    def _evaluate_kfold(self, X, y, classes, k: int) -> EvaluationResult:
        smallest = min(int(np.sum(y == c)) for c in classes)
        folds = max(2, min(k, smallest))
        if smallest < 2:
            return EvaluationResult(
                labels_total=len(classes),
                message="Слишком мало записей в классе для оценки точности.",
            )
        fold_of = np.empty(len(y), dtype=int)
        for c in classes:
            idx = np.where(y == c)[0]
            fold_of[idx] = np.arange(len(idx)) % folds
        correct = 0
        total = 0
        per_correct = {c: 0 for c in classes}
        per_total = {c: 0 for c in classes}
        for fold in range(folds):
            test_mask = fold_of == fold
            train_mask = ~test_mask
            if test_mask.sum() == 0 or len(set(y[train_mask].tolist())) < 2:
                continue
            preds = self._centroid_predict(X[train_mask], y[train_mask], X[test_mask])
            truths = y[test_mask]
            for pred, truth in zip(preds, truths):
                total += 1
                per_total[str(truth)] += 1
                if str(pred) == str(truth):
                    correct += 1
                    per_correct[str(truth)] += 1
        if total == 0:
            return EvaluationResult(labels_total=len(classes), message="Не удалось оценить точность.")
        per_label = {
            c: round(per_correct[c] / per_total[c], 3)
            for c in classes
            if per_total[c] > 0
        }
        return EvaluationResult(
            method="stratified_kfold",
            folds=folds,
            accuracy=round(correct / total, 3),
            per_label_accuracy=per_label,
            samples_evaluated=total,
            labels_total=len(classes),
            message=f"Точность по окнам ({folds}-fold): {correct}/{total}.",
        )

    def raw_label_dir(self, label: str) -> Path:
        """Return a safe storage directory for raw recordings of one label."""

        safe_label = self._label_dir_name(label)
        path = self.dataset_dir / "raw" / safe_label
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _normalize_intervals(
        intervals: list[tuple[float, float]] | None, duration_seconds: float
    ) -> list[tuple[float, float]]:
        """Clamp/merge target-present intervals for training ingestion."""

        if not intervals:
            return []
        cleaned: list[tuple[float, float]] = []
        for left, right in intervals:
            a = max(float(left), 0.0)
            b = min(float(right), float(duration_seconds))
            if b > a:
                cleaned.append((a, b))
        cleaned.sort()
        merged: list[tuple[float, float]] = []
        for a, b in cleaned:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return merged

    @staticmethod
    def normalize_label(label: str) -> str:
        """Normalize a human label without forcing transliteration."""

        return " ".join(label.strip().split())

    def _label_dir_name(self, label: str) -> str:
        """Return a filesystem-safe label directory name preserving Cyrillic."""

        normalized = self.normalize_label(label)
        cleaned = "".join(
            "_" if char in {"/", "\\", ":", "\0"} else char
            for char in normalized
        ).strip(" ._-")
        return cleaned or "unlabeled"

    def _append_rows(self, rows: list[dict[str, object]]) -> None:
        """Append extracted rows to the feature CSV."""

        self.feature_dataset_path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(rows)
        for column in FEATURE_COLUMNS:
            if column not in frame:
                frame[column] = 0.0
        if self.feature_dataset_path.exists():
            old = pd.read_csv(self.feature_dataset_path)
            frame = pd.concat([old, frame], ignore_index=True)
        frame.to_csv(self.feature_dataset_path, index=False)

    def _read_dataset(self) -> pd.DataFrame:
        """Read the feature dataset or return an empty dataframe."""

        if not self.feature_dataset_path.exists():
            return pd.DataFrame()
        return pd.read_csv(self.feature_dataset_path)

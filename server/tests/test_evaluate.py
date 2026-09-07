import numpy as np
import pandas as pd

from ml.cluster_classifier import CentroidAudioClassifier
from ml.dataset import SoundDatasetManager
from ml.feature_vector import FEATURE_COLUMNS


def _manager(tmp_path, df):
    csv = tmp_path / "features.csv"
    df.to_csv(csv, index=False)
    return SoundDatasetManager(
        dataset_dir=tmp_path,
        feature_dataset_path=csv,
        classifier=CentroidAudioClassifier(dataset_path=csv, model_path=tmp_path / "model.json"),
    )


def test_evaluate_separable_classes(tmp_path):
    rng = np.random.default_rng(0)
    rows = []
    for label, base in [("A", 0.0), ("B", 5.0)]:
        for file_index in range(3):
            source = f"/{label}/file{file_index}.wav"
            for _ in range(3):
                row = {column: 0.0 for column in FEATURE_COLUMNS}
                row["rms"] = base + rng.normal(0, 0.05)
                row["spectral_centroid_hz"] = base * 100 + rng.normal(0, 1)
                row["label"] = label
                row["source_file"] = source
                rows.append(row)
    manager = _manager(tmp_path, pd.DataFrame(rows))

    result = manager.evaluate()
    assert result.method == "leave_one_file_out"
    assert 0.0 <= result.accuracy <= 1.0
    assert result.accuracy >= 0.8        # clearly separable classes
    assert result.labels_total == 2
    assert set(result.per_label_accuracy) == {"A", "B"}


def test_evaluate_requires_two_classes(tmp_path):
    row = {column: 0.0 for column in FEATURE_COLUMNS}
    row.update({"label": "A", "source_file": "x.wav"})
    manager = _manager(tmp_path, pd.DataFrame([row, {**row}]))

    result = manager.evaluate()
    assert result.accuracy == 0.0
    assert "класс" in result.message.lower()

def test_evaluate_refuses_window_leakage_when_class_has_one_source(tmp_path):
    rows = []
    for label, base, files in [("A", 0.0, 1), ("B", 5.0, 2)]:
        for file_index in range(files):
            for window_index in range(6):
                row = {column: 0.0 for column in FEATURE_COLUMNS}
                row.update({
                    "label": label,
                    "source_file": f"/{label}/file{file_index}.wav",
                    "start_seconds": window_index * 0.5,
                    "rms": base,
                })
                rows.append(row)
    result = _manager(tmp_path, pd.DataFrame(rows)).evaluate()
    assert result.method == "independent_recordings_required"
    assert result.accuracy == 0.0
    assert "оконный k-fold" in result.message.lower()


def test_provisional_class_is_excluded_from_validation_metrics(tmp_path):
    rows=[]
    for label in ["A", "B"]:
        for src in range(2):
            row={c: float(src + (0 if label == "A" else 2)) for c in FEATURE_COLUMNS}
            row.update({"label":label,"source_file":f"{label}_{src}.wav","meta_dataset_role":"training"})
            rows.append(row)
    for src in range(3):
        row={c: 9.0 for c in FEATURE_COLUMNS}
        row.update({"label":"Лютый","source_file":f"LT_{src}.wav","meta_dataset_role":"training_provisional"})
        rows.append(row)
    out=_manager(tmp_path, pd.DataFrame(rows)).evaluate()
    assert out.labels_total == 2
    assert "Лютый" not in out.per_label_accuracy

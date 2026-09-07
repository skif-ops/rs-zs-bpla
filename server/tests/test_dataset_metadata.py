import numpy as np
import pandas as pd
import soundfile as sf

from ml import label_registry
from ml.cluster_classifier import CentroidAudioClassifier
from ml.dataset import SoundDatasetManager
from models.schemas import RecordingMetadata, UploadedFileInfo


def _manager(tmp_path):
    csv = tmp_path / "features.csv"
    return SoundDatasetManager(
        dataset_dir=tmp_path,
        feature_dataset_path=csv,
        classifier=CentroidAudioClassifier(dataset_path=csv, model_path=tmp_path / "model.json"),
    )


def _tone_file(tmp_path, name="rec.wav", freq=120.0) -> UploadedFileInfo:
    sr = 48000
    t = np.arange(int(sr * 2.0)) / sr
    signal = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    path = tmp_path / name
    sf.write(path, signal, sr)
    return UploadedFileInfo(original_name=name, stored_path=str(path), size_bytes=path.stat().st_size)


def test_metadata_written_as_meta_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(label_registry, "registry_path", lambda: tmp_path / "label_meta.json")
    manager = _manager(tmp_path)
    metadata = RecordingMetadata(
        category="drone", is_drone=True, distance_min_m=0.5, distance_max_m=5.0, background="лес"
    )
    result = manager.add_recording("DJI Test", _tone_file(tmp_path), metadata=metadata)
    assert result.windows_added > 0

    df = pd.read_csv(tmp_path / "features.csv")
    assert (df["meta_category"] == "drone").all()
    assert (df["meta_distance_min_m"] == 0.5).all()
    assert (df["meta_background"] == "лес").all()
    # registry now flags the class as a drone (no config edit needed)
    assert "DJI Test" in label_registry.drone_labels(tmp_path / "label_meta.json")


def test_old_rows_get_nan_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(label_registry, "registry_path", lambda: tmp_path / "label_meta.json")
    manager = _manager(tmp_path)
    manager.add_recording("фон", _tone_file(tmp_path, "a.wav"))  # no metadata -> no meta_* columns
    manager.add_recording(
        "DJI Test",
        _tone_file(tmp_path, "b.wav"),
        metadata=RecordingMetadata(category="drone", is_drone=True),
    )
    df = pd.read_csv(tmp_path / "features.csv")
    assert "meta_category" in df.columns
    # the first (metadata-less) recording's rows are NaN after concat
    assert df.loc[df["label"] == "фон", "meta_category"].isna().all()
    assert (df.loc[df["label"] == "DJI Test", "meta_category"] == "drone").all()


def test_delete_label_removes_rows_and_backs_up(tmp_path, monkeypatch):
    monkeypatch.setattr(label_registry, "registry_path", lambda: tmp_path / "label_meta.json")
    manager = _manager(tmp_path)
    manager.add_recording("фон", _tone_file(tmp_path, "a.wav"))
    manager.add_recording(
        "DJI Test", _tone_file(tmp_path, "b.wav"),
        metadata=RecordingMetadata(category="drone", is_drone=True),
    )
    before = len(pd.read_csv(tmp_path / "features.csv"))

    result = manager.delete_label("DJI Test")
    assert result.rows_removed > 0
    assert result.backup_path is not None
    after = pd.read_csv(tmp_path / "features.csv")
    assert "DJI Test" not in set(after["label"])
    assert len(after) == before - result.rows_removed
    assert "DJI Test" not in label_registry.load_registry(tmp_path / "label_meta.json").labels

def test_add_recording_can_limit_training_to_target_intervals(tmp_path):
    manager = SoundDatasetManager(dataset_dir=tmp_path / "dataset", feature_dataset_path=tmp_path / "features.csv")
    result = manager.add_recording(
        "FP-1",
        _tone_file(tmp_path, "pass.wav"),
        window_seconds=0.25,
        hop_seconds=0.25,
        include_intervals=[(0.25, 0.75)],
    )
    assert result.windows_added > 0
    df = pd.read_csv(tmp_path / "features.csv")
    centers = df["start_seconds"] + df["duration_seconds"] / 2.0
    assert centers.min() >= 0.25 - 1e-6
    assert centers.max() <= 0.75 + 1e-6

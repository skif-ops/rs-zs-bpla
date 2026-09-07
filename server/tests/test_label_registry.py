from ml import label_registry
from models.schemas import RecordingMetadata


def _path(tmp_path):
    return tmp_path / "label_meta.json"


def test_upsert_and_load_round_trip(tmp_path):
    path = _path(tmp_path)
    label_registry.upsert_label(
        "DJI Mini 3 Pro",
        category="drone",
        is_drone=True,
        description="малый квадрокоптер",
        last_metadata=RecordingMetadata(category="drone", is_drone=True, distance_min_m=0.5),
        path=path,
    )
    registry = label_registry.load_registry(path)
    meta = registry.labels["DJI Mini 3 Pro"]
    assert meta.category == "drone"
    assert meta.is_drone is True
    assert meta.description == "малый квадрокоптер"
    assert meta.last_metadata.distance_min_m == 0.5


def test_category_drone_implies_is_drone(tmp_path):
    path = _path(tmp_path)
    label_registry.upsert_label("трактор", category="background", path=path)
    label_registry.upsert_label("FP-1", category="drone", path=path)
    drones = label_registry.drone_labels(path)
    assert "FP-1" in drones
    assert "трактор" not in drones


def test_remove_label(tmp_path):
    path = _path(tmp_path)
    label_registry.upsert_label("шум", category="background", path=path)
    assert label_registry.remove_label("шум", path) is True
    assert label_registry.remove_label("шум", path) is False
    assert "шум" not in label_registry.load_registry(path).labels


def test_effective_drone_labels_unions_config(tmp_path, monkeypatch):
    path = _path(tmp_path)
    monkeypatch.setattr(label_registry, "registry_path", lambda: path)
    label_registry.upsert_label("DJI Air 3", category="drone", is_drone=True, path=path)
    effective = label_registry.effective_drone_labels()
    assert "DJI Air 3" in effective          # from registry
    assert "FP-1" in effective                # from config


def test_corrupt_registry_falls_back_empty(tmp_path):
    path = _path(tmp_path)
    path.write_text("{ not json", encoding="utf-8")
    registry = label_registry.load_registry(path)
    assert registry.labels == {}

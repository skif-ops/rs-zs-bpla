"""Level-1 acceptance of the station classifier: UAV presence on the Muhoed dataset.

The firmware detects a UAV when its nearest-centroid class is one of the UAV classes; families and
types are decided later (server hierarchy, consensus).  This test keeps the committed centroid
table in step with the dataset and guards the presence quality that the pilot relies on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import export_station_model as esm  # noqa: E402


@pytest.fixture(scope="module")
def dataset():
    return esm.load_dataset()


def test_committed_header_matches_dataset(dataset):
    order, X, labels, _, _ = dataset
    model = esm.fit(X, labels, esm.DEFAULT_K)
    assert esm.HEADER.read_text(encoding="utf-8") == esm.render_header(model, order), \
        "firmware/generated/zs_model_centroids.h is stale: python server/tools/export_station_model.py"
    parsed = esm.parse_header(esm.HEADER.read_text(encoding="utf-8"))
    assert parsed["centroids"].shape == model["centroids"].shape
    assert list(parsed["class_id"]) == list(model["class_id"])


def test_uav_presence_on_dataset(dataset):
    order, X, labels, files, starts = dataset
    model = esm.parse_header(esm.HEADER.read_text(encoding="utf-8"))
    cid, conf = esm.predict(model, X)
    m = esm.presence_metrics(cid, conf, labels)
    assert m["recall"] >= 0.85, m                      # in-sample: the table must at least fit its own data
    assert m["fpr"] <= 0.05, m
    for label in ("Лютый", "FP-1", "DJI Mini 3 Pro"):
        assert m["per_label"][label] >= 0.80, m["per_label"]
    for label in ("трактор", "городской транспорт", "природный фон", "цикады и насекомые"):
        assert m["per_label"][label] <= 0.10, m["per_label"]


def test_uav_presence_generalizes_within_recordings(dataset):
    order, X, labels, files, starts = dataset
    test = esm.temporal_holdout_mask(files, starts)
    model = esm.fit(X[~test], labels[~test], esm.DEFAULT_K)
    cid, conf = esm.predict(model, X[test])
    m = esm.presence_metrics(cid, conf, labels[test])
    assert m["recall"] >= 0.80, m                      # last 30 % of every recording unseen
    assert m["fpr"] <= 0.10, m

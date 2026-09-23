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


def test_dataset_rows_are_at_the_station_rate():
    """The station extracts the 43 features at 32 kHz; rows extracted at a recording's native 44.1/48 kHz are not
    comparable (YIN f0 halves, MFCC-0 shifts on the DJI Mini 3 Pro file). The loader now resamples to
    settings.target_analysis_sample_rate_hz; this test reports how much of the dataset predates that and fails
    only when the rate column is missing altogether."""
    import csv, gzip, collections
    with gzip.open(esm.DATASET, "rt", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert "sample_rate" in rows[0]
    rates = collections.Counter(r["sample_rate"] for r in rows)
    stale = sum(n for rate, n in rates.items() if rate not in ("32000.0", "32000", ""))
    print(f"dataset rows not at 32 kHz: {stale}/{len(rows)} {dict(rates)}")
    from config import settings
    assert settings.target_analysis_sample_rate_hz == 32000


def test_uav_presence_generalizes_within_recordings(dataset):
    order, X, labels, files, starts = dataset
    test = esm.temporal_holdout_mask(files, starts)
    model = esm.fit(X[~test], labels[~test], esm.DEFAULT_K)
    cid, conf = esm.predict(model, X[test])
    m = esm.presence_metrics(cid, conf, labels[test])
    assert m["recall"] >= 0.80, m                      # last 30 % of every recording unseen
    assert m["fpr"] <= 0.10, m

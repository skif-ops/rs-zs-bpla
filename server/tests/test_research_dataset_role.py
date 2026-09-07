from __future__ import annotations

import pandas as pd

from ml.cluster_classifier import CentroidAudioClassifier
from ml.feature_vector import FEATURE_COLUMNS


def _row(label: str, role: str):
    row = {c: 0.1 for c in FEATURE_COLUMNS}
    row.update({"label": label, "source_file": f"{label}.wav", "meta_dataset_role": role})
    return row


def test_training_provisional_rows_are_included_in_model_training():
    df = pd.DataFrame([_row("FP-1", "training"), _row("Лютый", "training_provisional"), _row("x", "research")])
    clean = CentroidAudioClassifier._clean_dataset(df)
    assert clean["label"].tolist() == ["FP-1", "Лютый"]


def test_weak_provisional_rows_are_included_in_training():
    df = pd.DataFrame([_row("FP-1", "training_provisional_weak"), _row("Лютый", "training_provisional")])
    clean = CentroidAudioClassifier._clean_dataset(df)
    assert set(clean["label"].tolist()) == {"FP-1", "Лютый"}


def test_research_rows_remain_excluded_from_training():
    df = pd.DataFrame([_row("FP-1", "training"), _row("x", "research")])
    clean = CentroidAudioClassifier._clean_dataset(df)
    assert clean["label"].tolist() == ["FP-1"]


def test_trained_model_records_provisional_label(tmp_path):
    rows=[]
    for label, role, base in [("A","training",0.0),("Лютый","training_provisional",2.0)]:
        for source in range(2):
            for w in range(2):
                row={c: base + 0.01*w for c in FEATURE_COLUMNS}
                row.update({"label":label,"source_file":f"{label}_{source}.wav","start_seconds":float(w*2),"meta_dataset_role":role})
                rows.append(row)
    path=tmp_path/"features.csv"
    pd.DataFrame(rows).to_csv(path,index=False)
    model=tmp_path/"model.json"
    clf=CentroidAudioClassifier(dataset_path=path, model_path=model)
    result=clf.train()
    assert result.trained
    payload=clf.load_model()
    assert "Лютый" in payload["classes"]
    assert payload["training_guard"]["provisional_labels"] == ["Лютый"]


def test_provisional_prediction_status_is_explicit():
    status, explanation = CentroidAudioClassifier._apply_provisional_status(
        "Лютый", "single", "base", {"training_guard": {"provisional_labels": ["Лютый"]}}
    )
    assert status == "provisional_candidate"
    assert "предварительный" in explanation.lower()

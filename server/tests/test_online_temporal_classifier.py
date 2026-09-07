from __future__ import annotations

import numpy as np
import pandas as pd

from ml.online_type_classifier import OnlineTemporalTypeClassifier, source_training_weight
from ml.temporal_features import BASE_TEMPORAL_COLUMNS


def _rows(label: str, source: str, role: str, base: float, duration: float = 14.0):
    rows=[]
    t=0.0
    while t <= duration - 1.0 + 1e-9:
        row={
            "label":label,"source_file":source,"start_seconds":t,"duration_seconds":1.0,
            "meta_dataset_role":role,"meta_is_drone":True,
            "meta_recording_quality_score":0.8,
            "meta_label_confidence_score":1.0 if role!="training_provisional_weak" else 0.4,
        }
        for i,name in enumerate(BASE_TEMPORAL_COLUMNS):
            row[name]=base + i*0.01 + 0.01*np.sin(t)
        row["harmonic_count"]=12+base
        row["harmonic_stability"]=0.7
        rows.append(row);t += 0.5
    return rows


def test_source_weight_separates_quality_and_label_confidence():
    confirmed=pd.DataFrame(_rows("Лютый","a.wav","training_provisional",1.0,6.0))
    weak=pd.DataFrame(_rows("FP-1","b.wav","training_provisional_weak",2.0,6.0))
    assert source_training_weight(confirmed) > source_training_weight(weak)


def test_temporal_model_marks_policy_and_never_locks_provisional(tmp_path):
    rows=[]
    for i in range(3):
        rows += _rows("Лютый",f"l{i}.wav","training_provisional",1.0+i*0.03)
        rows += _rows("FP-1",f"f{i}.wav","training_provisional_weak",3.0+i*0.03)
    frame=pd.DataFrame(rows)
    clf=OnlineTemporalTypeClassifier(model_path=tmp_path/"temporal.json")
    model=clf.train(frame)
    assert model["label_policy"]["Лютый"] == "provisional"
    assert model["label_policy"]["FP-1"] == "weak"
    replay=clf.replay(frame[frame.source_file=="l0.wav"], source_file="l0.wav", candidate_detection_seconds=2.0, model=model)
    assert replay.type_lock_allowed is False
    assert any(item.best_label != "UNKNOWN" for item in replay.snapshots)


def test_contradictory_evidence_does_not_create_hard_lock(tmp_path):
    rows=[]
    for i in range(2):
        rows += _rows("Лютый",f"l{i}.wav","training_provisional",1.0)
        rows += _rows("FP-1",f"f{i}.wav","training_provisional_weak",3.0)
    frame=pd.DataFrame(rows)
    clf=OnlineTemporalTypeClassifier(model_path=tmp_path/"temporal.json")
    model=clf.train(frame)
    # Regardless of apparent stability, current data policy forbids an operational lock.
    replay=clf.replay(frame[frame.source_file=="f0.wav"], source_file="f0.wav", candidate_detection_seconds=2.0, model=model)
    assert replay.type_lock_allowed is False


def test_predict_window_preserves_raw_label_when_single_horizon_is_unknown(tmp_path):
    rows=[]
    for i in range(3):
        rows += _rows("Лютый",f"l{i}.wav","training_provisional",1.0+i*0.03)
        rows += _rows("FP-1",f"f{i}.wav","training_provisional_weak",3.0+i*0.03)
    frame=pd.DataFrame(rows)
    clf=OnlineTemporalTypeClassifier(model_path=tmp_path/"temporal.json")
    model=clf.train(frame)
    temporal=clf.builder.build_one_source(frame[frame.source_file=="l0.wav"],5.0)
    assert not temporal.empty
    vector={name: float(temporal.iloc[0][name]) for name in model["feature_columns"]}
    pred=clf.predict_window(vector,5.0,model)
    assert pred["raw_best_label"] in {"Лютый","FP-1"}
    assert "best_label" in pred


def test_v07_model_exposes_type_readiness_and_starts_at_three_seconds(tmp_path):
    rows=[]
    for i in range(3):
        rows += _rows("Лютый",f"l{i}.wav","training_provisional",1.0,14.0)
        rows += _rows("FP-1",f"f{i}.wav","training_provisional_weak",3.0,14.0)
    frame=pd.DataFrame(rows)
    clf=OnlineTemporalTypeClassifier(model_path=tmp_path/"temporal.json")
    model=clf.train(frame)
    assert model["model_type"].endswith("v07")
    assert model["type_readiness"]["research_ready"] is True
    assert model["type_readiness"]["confirmed_contrast_ready"] is False
    assert model["type_readiness"]["operational_validation_ready"] is False
    replay=clf.replay(frame[frame.source_file=="l0.wav"], source_file="l0.wav", candidate_detection_seconds=2.0, model=model)
    assert replay.snapshots
    assert replay.snapshots[0].time_seconds == 3.0
    assert replay.type_lock_allowed is False

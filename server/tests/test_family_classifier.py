from __future__ import annotations

import pandas as pd

from ml.acoustic_family import AcousticFamily, family_for_label
from ml.family_classifier import AcousticFamilyClassifier
from ml.online_type_classifier import source_training_weight


def test_family_mapping_is_hierarchical():
    assert family_for_label("Лютый") == AcousticFamily.PROP_PISTON
    assert family_for_label("FP-1") == AcousticFamily.PROP_PISTON
    assert family_for_label("DJI Mini 3 Pro") == AcousticFamily.ROTOR_ELECTRIC
    assert family_for_label("трактор") == AcousticFamily.GROUND_ENGINE
    assert family_for_label("not-listed") == AcousticFamily.UNKNOWN


def test_weak_source_has_lower_training_weight():
    confirmed = pd.DataFrame({
        "meta_dataset_role": ["training_provisional"],
        "meta_recording_quality_score": [0.8],
        "meta_label_confidence_score": [1.0],
    })
    weak = pd.DataFrame({
        "meta_dataset_role": ["training_provisional_weak"],
        "meta_recording_quality_score": [0.8],
        "meta_label_confidence_score": [0.4],
    })
    assert source_training_weight(weak) < source_training_weight(confirmed)


def test_v08_family_model_trains_from_real_feature_dataset(tmp_path):
    frame = pd.read_csv("dataset/features.csv")
    clf = AcousticFamilyClassifier(model_path=tmp_path / "family.json")
    model = clf.train(frame)
    assert model["model_type"] == "source_balanced_acoustic_family_centroid_v08"
    assert "PROP_PISTON" in model["classes"]
    assert "GROUND_ENGINE" in model["classes"]
    assert "ROTOR_ELECTRIC" in model["classes"]
    assert "TURBINE_JET" not in model["classes"]
    assert "TURBINE_JET" in model["unsupported_families"]
    assert model["classes"]["PROP_PISTON"]["confirmed_sources"] >= 6


def test_v08_family_prediction_does_not_force_specific_uav_type(tmp_path):
    frame = pd.read_csv("dataset/features.csv")
    clf = AcousticFamilyClassifier(model_path=tmp_path / "family.json", min_score=0.0, min_margin=0.0)
    model = clf.train(frame)
    lutyi_source = frame[frame["label"] == "Лютый"].groupby("source_file", sort=False).__iter__().__next__()[1]
    pred = clf.predict_rows(lutyi_source.head(12), model)
    assert pred is not None
    assert pred.best_family in {"PROP_PISTON", "UNKNOWN"}
    assert all(score.family not in {"Лютый", "FP-1"} for score in pred.scores)
    assert pred.status in {"provisional_family", "unknown"}


def test_air_target_gate_removes_background_families_from_competition(tmp_path):
    frame = pd.read_csv("dataset/features.csv")
    clf = AcousticFamilyClassifier(model_path=tmp_path / "family.json", min_score=0.0, min_margin=0.0)
    model = clf.train(frame)
    source = frame[frame["label"] == "Лютый"].groupby("source_file", sort=False).__iter__().__next__()[1]
    pred = clf.predict_rows(source.head(12), model, air_target_confirmed=True)
    assert pred is not None
    assert pred.conditional_on_air_target is True
    assert 0.0 <= pred.absolute_fit <= 1.0
    assert pred.confidence <= pred.scores[0].score
    assert all(score.family in {"PROP_PISTON", "ROTOR_ELECTRIC", "TURBINE_JET"} for score in pred.scores)
    assert pred.best_family in {"PROP_PISTON", "ROTOR_ELECTRIC", "UNKNOWN"}


def test_family_result_has_separate_validation_readiness(tmp_path):
    frame = pd.read_csv("dataset/features.csv")
    clf = AcousticFamilyClassifier(model_path=tmp_path / "family.json", min_score=0.0, min_margin=0.0)
    model = clf.train(frame)
    source = frame[frame["label"] == "Лютый"].groupby("source_file", sort=False).__iter__().__next__()[1]
    pred = clf.predict_rows(source.head(12), model, air_target_confirmed=True)
    assert pred is not None
    assert pred.best_family == "PROP_PISTON"
    assert pred.operational_validation_ready is False
    assert pred.status == "provisional_family"

import pandas as pd

from ml.cluster_classifier import CentroidAudioClassifier
from ml.feature_vector import feature_set_to_row
from models.schemas import AudioFeatureSet


def make_features(**overrides):
    data = {
        "fundamental_hz": 125.0,
        "harmonic_count": 18,
        "harmonic_step_hz": 125.0,
        "harmonic_stability": 0.42,
        "average_energy": 0.04,
        "rms": 0.20,
        "zero_crossing_rate": 0.03,
        "spectral_centroid_hz": 1100.0,
        "spectral_flatness": 0.002,
        "spectral_bandwidth_hz": 1700.0,
        "mfcc_mean": [0.0] * 13,
        "mfcc_std": [0.0] * 13,
        "noise_floor": 0.01,
        "high_band_energy_6_10khz": 0.001,
        "high_band_energy_label": "low",
        "fundamental_variation": 0.30,
        "harmonic_variation": 0.36,
        "frequency_modulation_index": 0.90,
        "spectral_roughness": 0.22,
        "doppler_stability": 0.05,
        "f0_track_hz": [],
        "time_axis_seconds": [],
        "detected_harmonics_hz": [],
    }
    data.update(overrides)
    return AudioFeatureSet(**data)


def labeled_row(label, features, index):
    row = {
        "record_id": f"{label}-{index}",
        "label": label,
        "source_file": f"{label}.wav",
        "window_index": index,
    }
    row.update(feature_set_to_row(features))
    return row


def test_centroid_classifier_trains_and_predicts(tmp_path):
    rows = []
    for index in range(5):
        rows.append(labeled_row("FP-1", make_features(fundamental_hz=122.0 + index), index))
        rows.append(
            labeled_row(
                "ветер",
                make_features(
                    fundamental_hz=45.0 + index,
                    harmonic_count=2,
                    harmonic_stability=0.08,
                    frequency_modulation_index=0.10,
                    spectral_flatness=0.40,
                    spectral_centroid_hz=4200.0,
                    harmonic_variation=0.95,
                    doppler_stability=0.10,
                ),
                index,
            )
        )

    dataset_path = tmp_path / "features.csv"
    model_path = tmp_path / "model.json"
    pd.DataFrame(rows).to_csv(dataset_path, index=False)

    classifier = CentroidAudioClassifier(
        dataset_path=dataset_path,
        model_path=model_path,
        unknown_threshold=0.40,
    )
    trained = classifier.train()
    result = classifier.predict(make_features(fundamental_hz=124.0))

    assert trained.trained
    assert model_path.exists()
    assert result is not None
    assert result.best_label == "FP-1"
    assert result.confidence >= 0.50


def test_centroid_classifier_requires_two_labels(tmp_path):
    dataset_path = tmp_path / "features.csv"
    model_path = tmp_path / "model.json"
    rows = [
        labeled_row("FP-1", make_features(fundamental_hz=122.0 + index), index)
        for index in range(3)
    ]
    pd.DataFrame(rows).to_csv(dataset_path, index=False)

    classifier = CentroidAudioClassifier(dataset_path=dataset_path, model_path=model_path)
    trained = classifier.train()

    assert not trained.trained
    assert trained.labels == 1

def test_training_balances_overlapping_windows_per_source(tmp_path):
    rows = []
    for index in range(80):
        row = labeled_row("FP-1", make_features(fundamental_hz=120.0 + index * 0.01), index)
        row["source_file"] = "fp1-long.wav"
        row["start_seconds"] = index * 0.5
        rows.append(row)
    for index in range(8):
        row = labeled_row("ветер", make_features(fundamental_hz=45.0 + index), index)
        row["source_file"] = "wind.wav"
        row["start_seconds"] = index * 0.5
        rows.append(row)
    dataset_path = tmp_path / "features.csv"
    model_path = tmp_path / "model.json"
    pd.DataFrame(rows).to_csv(dataset_path, index=False)
    classifier = CentroidAudioClassifier(dataset_path=dataset_path, model_path=model_path)
    trained = classifier.train()
    assert trained.trained
    import json
    model = json.loads(model_path.read_text())
    assert model["model_type"] == "source_balanced_knn_centroid_v2"
    assert model["prototype_samples_total"] < len(rows)
    labels = model["prototypes"]["labels"]
    assert labels.count("FP-1") <= 24

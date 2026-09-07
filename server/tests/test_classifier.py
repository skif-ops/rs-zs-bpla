from classification.expert_system import ExpertDroneClassifier
from classification.profiles import PENDING_PROFILE_NAMES, PROFILES
from models.schemas import AudioFeatureSet


def make_features(**overrides):
    data = {
        "fundamental_hz": 94.2,
        "harmonic_count": 27,
        "harmonic_step_hz": 94.1,
        "harmonic_stability": 0.96,
        "average_energy": 0.12,
        "rms": 0.34,
        "zero_crossing_rate": 0.06,
        "spectral_centroid_hz": 1200.0,
        "spectral_flatness": 0.01,
        "spectral_bandwidth_hz": 1800.0,
        "mfcc_mean": [0.0] * 13,
        "mfcc_std": [0.0] * 13,
        "noise_floor": 0.02,
        "high_band_energy_6_10khz": 0.18,
        "high_band_energy_label": "high",
        "fundamental_variation": 0.01,
        "harmonic_variation": 0.02,
        "frequency_modulation_index": 0.04,
        "spectral_roughness": 0.12,
        "doppler_stability": 0.95,
        "f0_track_hz": [93.9, 94.1, 94.3],
        "time_axis_seconds": [0.0, 0.5, 1.0],
        "detected_harmonics_hz": [94.0 * index for index in range(1, 28)],
    }
    data.update(overrides)
    return AudioFeatureSet(**data)


def test_lutyi_is_not_an_active_expert_profile():
    active_names = [profile.display_name for profile in PROFILES]
    assert all("Лютый" not in name for name in active_names)
    assert "Лютый (исследовательская гипотеза)" in PENDING_PROFILE_NAMES


def test_unknown_below_threshold():
    classifier = ExpertDroneClassifier()

    result = classifier.classify(
        make_features(
            fundamental_hz=30.0,
            harmonic_count=1,
            harmonic_stability=0.05,
            high_band_energy_label="low",
            high_band_energy_6_10khz=0.0,
            frequency_modulation_index=0.0,
            spectral_roughness=0.0,
            doppler_stability=0.1,
        )
    )

    assert result.best_match == "UNKNOWN"


def test_fp1_profile_is_active_from_confirmed_table():
    active_names = [profile.display_name for profile in PROFILES]

    assert "FP-1 (тяж. поршневой)" in active_names
    assert "FP-1 (тяж. поршневой)" not in PENDING_PROFILE_NAMES


def test_fp1_table_features_score_high():
    classifier = ExpertDroneClassifier()

    result = classifier.classify(
        make_features(
            fundamental_hz=142.0,
            harmonic_count=18,
            harmonic_stability=0.32,
            high_band_energy_label="low",
            high_band_energy_6_10khz=0.0,
            fundamental_variation=0.25,
            harmonic_variation=0.34,
            frequency_modulation_index=0.84,
            spectral_roughness=0.62,
            doppler_stability=0.05,
        )
    )

    assert result.best_match == "FP-1 (тяж. поршневой)"
    assert result.confidence >= 0.75

def test_provisional_type_does_not_become_hard_identity_when_separator_detects_drone():
    from audio.analyzer import AudioAnalysisService
    from models.schemas import ClassificationResult, ClassificationScore, MLClassificationResult, MLClassificationScore, DroneSeparationFindings
    expert=ClassificationResult(best_match='FP-1',confidence=0.8,scores=[ClassificationScore(profile='FP-1',score=0.8)],explanation='x')
    ml=MLClassificationResult(best_label='Лютый',confidence=0.91,scores=[MLClassificationScore(label='Лютый',score=0.91,distance=1.0,samples=100)],model_version='v',samples_total=100,labels_total=2,status='provisional_candidate',explanation='provisional')
    sep=DroneSeparationFindings(drone_present=True,confidence=0.87,likely_source='persistent propulsion')
    decision=AudioAnalysisService._build_decision(expert,ml,sep)
    assert decision.status=='drone'
    assert 'предположительно' in decision.display_label
    assert decision.needs_review is True
    assert decision.confidence==sep.confidence


def test_expert_hint_does_not_become_operational_type_when_ml_is_unknown():
    from audio.analyzer import AudioAnalysisService
    from models.schemas import ClassificationResult, ClassificationScore, DroneSeparationFindings

    expert = ClassificationResult(
        best_match="GR2",
        confidence=0.82,
        scores=[ClassificationScore(profile="GR2", score=0.82)],
        explanation="research hint",
    )
    sep = DroneSeparationFindings(
        drone_present=True,
        confidence=0.91,
        likely_source="persistent propulsion",
        explanation="target detected",
    )

    decision = AudioAnalysisService._build_decision(expert, None, sep)

    assert decision.status == "drone"
    assert decision.display_label == "БПЛА; тип UNKNOWN"
    assert decision.research_type_hint == "GR2"
    assert decision.research_type_confidence == 0.82
    assert decision.needs_review is True

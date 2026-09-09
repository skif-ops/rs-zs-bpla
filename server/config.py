"""Application configuration for Drone Acoustic Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings used by the application and DSP modules."""

    app_name: str = "Мухоед"
    app_version: str = "1.2.0-evt-pre-20.1"
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    min_sample_rate_hz: int = 20_000
    target_analysis_sample_rate_hz: int | None = None
    fft_max_frequency_hz: float = 12_000.0
    drone_low_frequency_hz: float = 40.0
    drone_high_frequency_hz: float = 500.0
    high_noise_band_low_hz: float = 6_000.0
    high_noise_band_high_hz: float = 10_000.0
    tracking_window_seconds: float = 0.5
    speed_of_sound_default_mps: float = 343.0
    classifier_unknown_threshold: float = 0.45
    ml_window_seconds: float = 1.0
    ml_hop_seconds: float = 0.5
    ml_min_window_rms: float = 0.005
    ml_max_windows_per_file: int = 80
    ml_knn_neighbors: int = 9
    # Training guard: overlapping windows from one long recording must not dominate KNN.
    ml_max_prototypes_per_source: int = 24
    ml_min_prototype_spacing_seconds: float = 2.0
    ml_unknown_threshold: float = 0.42
    ml_non_drone_confidence_threshold: float = 0.70
    ml_drone_labels: tuple[str, ...] = (
        "FP-1",
        "FP-1 (тяж. поршневой)",
        "GR2",
        "DJI Mini 3 Pro",
    )
    # Type labels remain provisional until an explicit dataset freeze.
    # "Лютый" labels are confirmed by the user but the sample is not yet a
    # representative validation reference. FP-1 recordings are weakly labeled.
    ml_provisional_labels: tuple[str, ...] = ("Лютый",)
    ml_weak_labels: tuple[str, ...] = ("FP-1",)
    temporal_type_window_seconds: tuple[float, ...] = (3.0, 5.0, 10.0)
    temporal_type_hop_seconds: float = 1.0
    temporal_candidate_seconds: float = 2.0
    temporal_first_type_target_seconds: float = 8.0
    temporal_stable_type_target_seconds: float = 20.0
    temporal_min_hypothesis_score: float = 0.58
    temporal_min_hypothesis_margin: float = 0.08
    temporal_min_stable_score: float = 0.66
    temporal_min_stable_margin: float = 0.10
    temporal_stable_updates: int = 3
    # Drone source separation / harmonic-comb detection. The separator decimates
    # to a low rate (the whole bird band above ~3 kHz is removed by the anti-alias
    # filter), then isolates the steady low-frequency harmonic comb of a rotor or
    # engine so a quiet background drone is not masked by a loud foreground.
    separation_sample_rate_hz: int = 6_000
    separation_band_low_hz: float = 18.0
    separation_band_high_hz: float = 2_400.0
    comb_f0_min_hz: float = 12.0
    comb_f0_max_hz: float = 180.0
    comb_window_seconds: float = 1.0
    comb_max_harmonics: int = 16
    comb_present_snr_db: float = 6.0
    comb_persistence_threshold: float = 0.35
    comb_min_harmonics: int = 4
    # Steadiness gate on the dominant harmonic line. A hovering source is rock
    # steady (~0.01); a flying drone with Doppler glide drifts more, so this is
    # deliberately loose and relaxed further for high-SNR detections (see
    # DroneSeparator._build_findings) to keep recall on real airborne drones.
    comb_steadiness_cv_max: float = 0.12
    # Reject narrow grid-locked interference before harmonic-comb fitting.
    # The fixed 1.2 Hz stop bands are narrow enough to preserve Doppler-shifted
    # propulsion lines while removing 50/60 Hz mains aliases and harmonics.
    mains_base_frequencies_hz: tuple[float, ...] = (50.0, 60.0)
    mains_notch_bandwidth_hz: float = 1.2
    mains_notch_max_frequency_hz: float = 200.0
    localization_max_iterations: int = 500
    localization_residual_scale_m: float = 15.0
    upload_limit_mb: int = 512
    logger_name: str = "dai"

    @property
    def upload_dir(self) -> Path:
        """Directory where user uploads are stored."""

        return self.base_dir / "uploads"

    @property
    def output_dir(self) -> Path:
        """Directory where generated reports and figures are stored."""

        return self.base_dir / "output"

    @property
    def dataset_dir(self) -> Path:
        """Directory where labeled audio and extracted ML features are stored."""

        return self.base_dir / "dataset"

    @property
    def feature_dataset_path(self) -> Path:
        """CSV table with extracted labeled audio-window features."""

        return self.dataset_dir / "features.csv"

    @property
    def ml_model_path(self) -> Path:
        """Path to the local audio cluster classifier model."""

        return self.base_dir / "models" / "audio_cluster_model.json"

    @property
    def template_dir(self) -> Path:
        """Directory with Jinja2 templates."""

        return self.base_dir / "templates"

    @property
    def static_dir(self) -> Path:
        """Directory with static web assets."""

        return self.base_dir / "static"


settings = Settings()

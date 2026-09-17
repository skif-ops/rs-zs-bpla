"""Pydantic schemas shared by the web layer and processing modules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class UploadedFileInfo(BaseModel):
    """Metadata for a saved upload."""

    original_name: str
    stored_path: str
    size_bytes: int


class AudioQualityReport(BaseModel):
    """Basic quality facts gathered while loading audio."""

    sample_rate: int
    duration_seconds: float
    channels: int
    warnings: list[str] = Field(default_factory=list)


class HarmonicFeatureSet(BaseModel):
    """Harmonic and tonal descriptors used by the expert classifier."""

    fundamental_hz: float
    harmonic_count: int
    harmonic_step_hz: float
    harmonic_stability: float
    harmonic_variation: float
    detected_harmonics_hz: list[float] = Field(default_factory=list)


class AudioFeatureSet(BaseModel):
    """DSP features extracted from a WAV signal."""

    fundamental_hz: float
    harmonic_count: int
    harmonic_step_hz: float
    harmonic_stability: float
    average_energy: float
    rms: float
    zero_crossing_rate: float
    spectral_centroid_hz: float
    spectral_flatness: float
    spectral_bandwidth_hz: float
    mfcc_mean: list[float]
    mfcc_std: list[float]
    noise_floor: float
    high_band_energy_6_10khz: float
    high_band_energy_label: Literal["low", "medium", "high"]
    fundamental_variation: float
    harmonic_variation: float
    frequency_modulation_index: float
    spectral_roughness: float
    doppler_stability: float
    f0_track_hz: list[float] = Field(default_factory=list)
    time_axis_seconds: list[float] = Field(default_factory=list)
    detected_harmonics_hz: list[float] = Field(default_factory=list)


class ClassificationScore(BaseModel):
    """Score assigned to one acoustic profile."""

    profile: str
    score: float
    reasons: list[str] = Field(default_factory=list)


class ClassificationResult(BaseModel):
    """Best expert-system classification result."""

    best_match: str
    confidence: float
    scores: list[ClassificationScore]
    explanation: str


class MLClassificationScore(BaseModel):
    """Score assigned by a trained local audio-cluster model."""

    label: str
    score: float
    distance: float
    samples: int


class FamilyClassificationScore(BaseModel):
    """Score assigned to one broad acoustic family."""

    family: str
    score: float
    distance: float
    sources: int = 0


class FamilyClassificationResult(BaseModel):
    """Hierarchical v0.8 family prediction before specific UAV type identity."""

    best_family: str = "UNKNOWN"
    confidence: float = 0.0
    absolute_fit: float = 0.0
    margin: float = 0.0
    status: str = "unknown"
    conditional_on_air_target: bool = False
    operational_validation_ready: bool = False
    evidence_windows: int = 0
    required_windows: int = 4
    max_windows: int = 8
    consensus_ratio: float = 0.0
    scores: list[FamilyClassificationScore] = Field(default_factory=list)
    model_version: str = "unknown"
    explanation: str = ""


class MLClassificationResult(BaseModel):
    """Prediction from the local feature-cluster classifier."""

    best_label: str
    confidence: float
    scores: list[MLClassificationScore] = Field(default_factory=list)
    model_version: str
    samples_total: int
    labels_total: int
    status: str = "ok"
    explanation: str = ""


class DroneConstructionFeatures(BaseModel):
    """Platform-construction descriptors inferred from the isolated drone tone.

    These are the first acoustic cues toward identifying the drone TYPE: the
    blade-pass rate, rotation speed, an estimate of blade and rotor count, and
    whether the propulsion is electric or a combustion engine. All values are
    estimates/hints from a single channel, not a definitive identification.
    """

    blade_pass_hz: float = 0.0
    rotor_rpm: float = 0.0
    blade_count_estimate: int = 0
    rotor_count_estimate: int = 0
    propulsion: str = "unknown"
    propulsion_confidence: float = 0.0
    half_order_ratio: float = 0.0
    tonality: float = 0.0
    summary: str = ""


class DroneSeparationFindings(BaseModel):
    """Result of isolating a low-frequency drone comb from background noise.

    The separator answers a detection question that is independent of the
    foreground class: is a steady harmonic (rotor/engine) source present, even
    when a louder non-drone source (birds, wind, traffic) dominates the mix?
    """

    drone_present: bool = False
    confidence: float = 0.0
    fundamental_hz: float = 0.0
    dominant_harmonic_hz: float = 0.0
    harmonic_count: int = 0
    harmonic_snr_db: float = 0.0
    persistence: float = 0.0
    steadiness_cv: float = 1.0
    integer_order_ratio: float = 0.0
    separation_gain_db: float = 0.0
    # Coarse identity HINT from harmonic-order structure; it labels, it does not
    # gate detection. UAV vs ground genset needs a flyover/Doppler test to settle.
    likely_source: str = "нет устойчивого источника"
    construction: DroneConstructionFeatures | None = None
    isolated_audio: str = ""
    residual_audio: str = ""
    sample_rate: int = 0
    explanation: str = ""
    spectrum_freq_hz: list[float] = Field(default_factory=list)
    spectrum_db: list[float] = Field(default_factory=list)


class TemporalPortraitWindow(BaseModel):
    """One long-window harmonic portrait measurement."""

    start_seconds: float
    duration_seconds: float
    fundamental_hz: float = 0.0
    dominant_harmonic_hz: float = 0.0
    dominant_order: float = 0.0
    harmonic_count: int = 0
    harmonic_snr_db: float = 0.0
    persistence: float = 0.0
    steadiness_cv: float = 1.0
    persistent_propulsion_match: bool = False
    # Backward compatibility with v0.5.x reports; no longer type-specific.
    lutyi_match: bool = False


class TemporalAcousticPortrait(BaseModel):
    """Long-horizon acoustic portrait used in addition to 1 s ML windows."""

    profile_version: str = "persistent-propulsion-temporal-v2"
    provisional: bool = True
    window_seconds: float = 10.0
    hop_seconds: float = 2.0
    total_windows: int = 0
    matched_windows: int = 0
    longest_match_run: int = 0
    persistent_propulsion_candidate: bool = False
    # Deprecated compatibility alias. Must not be used as a type verdict.
    lutyi_candidate: bool = False
    confidence: float = 0.0
    best_start_seconds: float | None = None
    explanation: str = ""
    windows: list[TemporalPortraitWindow] = Field(default_factory=list)


class OnlineTypeSnapshot(BaseModel):
    """One online type-classifier update during a 40-60 s fly-over."""

    time_seconds: float
    phase: Literal["candidate", "early_type", "temporal", "refinement"]
    best_label: str = "UNKNOWN"
    confidence: float = 0.0
    margin: float = 0.0
    status: Literal["unknown", "provisional_candidate", "weak_candidate", "research_stable"] = "unknown"
    type_lock_allowed: bool = False
    evidence_seconds: float = 0.0


class OnlineTypeReplay(BaseModel):
    """Time-to-decision summary for one recording."""

    source_file: str
    candidate_detection_seconds: float | None = None
    first_type_hypothesis_seconds: float | None = None
    research_stable_seconds: float | None = None
    final_label: str = "UNKNOWN"
    final_status: str = "unknown"
    type_lock_allowed: bool = False
    snapshots: list[OnlineTypeSnapshot] = Field(default_factory=list)


class AnalysisDecision(BaseModel):
    """Final user-facing decision after expert, local ML and separation checks."""

    status: Literal["drone", "not_drone", "unknown"]
    display_label: str
    confidence: float
    source: str
    explanation: str
    suppress_drone_profile: bool = False
    # Dual verdict: the loudest classified source and an INDEPENDENT drone flag,
    # so a quiet background drone is never overwritten by a loud foreground.
    dominant_source: str = ""
    dominant_confidence: float = 0.0
    drone_present: bool = False
    drone_confidence: float = 0.0
    conflict: bool = False
    needs_review: bool = False
    research_type_hint: str = ""
    research_type_confidence: float = 0.0


class AcousticPassport(BaseModel):
    """Human-readable acoustic passport of an object."""

    drone_type: str
    fundamental_hz: float
    harmonic_count: int
    harmonic_step_hz: float
    stability: float
    high_band_noise: str
    frequency_modulation: str
    doppler: str
    probability_percent: float
    notes: list[str] = Field(default_factory=list)


class SingleAnalysisReport(BaseModel):
    """Complete report for a single WAV analysis."""

    analysis_id: str
    source_file: UploadedFileInfo
    quality: AudioQualityReport
    features: AudioFeatureSet
    decision: AnalysisDecision | None = None
    classification: ClassificationResult
    ml_classification: MLClassificationResult | None = None
    family_classification: FamilyClassificationResult | None = None
    separation: DroneSeparationFindings | None = None
    temporal_portrait: TemporalAcousticPortrait | None = None
    passport: AcousticPassport
    plots: dict[str, str]
    report_json: str


class RecordingMetadata(BaseModel):
    """Structured per-recording metadata stored as extra CSV columns.

    Training ignores these (it uses only ``label`` + the feature columns); they
    are kept for browsing, filtering and a future distance-estimation model.
    """

    category: Literal["drone", "background"] = "background"
    is_drone: bool = False
    distance_min_m: float | None = None
    distance_max_m: float | None = None
    background: str | None = None
    flight_mode: str | None = None
    notes: str | None = None
    dataset_role: Literal[
        "training",
        "training_provisional",
        "training_provisional_weak",
        "research",
        "validation",
    ] = "training"
    recording_quality: Literal["unknown", "low", "medium", "high"] = "unknown"
    recording_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    label_confidence: Literal["confirmed", "weak", "unknown"] = "confirmed"
    label_confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _order_distance(self):
        """Swap reversed distance bounds rather than rejecting the upload."""

        lo, hi = self.distance_min_m, self.distance_max_m
        if lo is not None and hi is not None and lo > hi:
            self.distance_min_m, self.distance_max_m = hi, lo
        return self

    def to_row(self) -> dict[str, object]:
        """Flatten to ``meta_*`` columns (prefix avoids feature-name clashes)."""

        return {
            "meta_category": self.category,
            "meta_is_drone": bool(self.is_drone),
            "meta_distance_min_m": self.distance_min_m,
            "meta_distance_max_m": self.distance_max_m,
            "meta_background": self.background,
            "meta_flight_mode": self.flight_mode,
            "meta_notes": self.notes,
            "meta_dataset_role": self.dataset_role,
            "meta_recording_quality": self.recording_quality,
            "meta_recording_quality_score": self.recording_quality_score,
            "meta_label_confidence": self.label_confidence,
            "meta_label_confidence_score": self.label_confidence_score,
        }


class LabelMeta(BaseModel):
    """Registry entry describing one dataset class."""

    label: str
    category: Literal["drone", "background"] = "background"
    is_drone: bool = False
    image_path: str | None = None
    description: str | None = None
    status: Literal[
        "active", "training_provisional", "training_provisional_weak", "research", "pending"
    ] = "active"
    last_metadata: RecordingMetadata | None = None


class LabelRegistry(BaseModel):
    """Top-level document stored at dataset/label_meta.json."""

    version: int = 1
    labels: dict[str, LabelMeta] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """Cross-validation accuracy estimate for the trained model."""

    method: str = "leave_one_file_out"
    folds: int = 0
    accuracy: float = 0.0
    per_label_accuracy: dict[str, float] = Field(default_factory=dict)
    samples_evaluated: int = 0
    labels_total: int = 0
    message: str = ""


class DatasetDeleteResult(BaseModel):
    """Result of removing a class or a single recording from the dataset."""

    label: str
    rows_removed: int = 0
    files_removed: int = 0
    image_removed: bool = False
    backup_path: str | None = None
    message: str = ""


class DatasetLabelSummary(BaseModel):
    """Count of dataset windows and files for one label, plus registry info."""

    label: str
    windows: int
    files: int
    category: str = "background"
    is_drone: bool = False
    image_url: str | None = None
    description: str | None = None


class DatasetSummary(BaseModel):
    """Summary of the local labeled sound dataset."""

    total_windows: int = 0
    total_files: int = 0
    labels: list[DatasetLabelSummary] = Field(default_factory=list)
    feature_dataset_path: str
    model_path: str
    model_exists: bool = False
    model_labels: int = 0
    model_samples: int = 0
    model_version: str | None = None


class DatasetAddResult(BaseModel):
    """Result of adding labeled audio files to the dataset."""

    label: str
    files_added: int
    windows_added: int
    warnings: list[str] = Field(default_factory=list)


class ModelTrainingResult(BaseModel):
    """Result of training the local audio-cluster model."""

    trained: bool
    model_path: str
    labels: int
    samples: int
    message: str


class Microphone(BaseModel):
    """Microphone position and associated WAV filename."""

    id: str
    x: float
    y: float
    z: float = 0.0
    file: str


class MicrophoneArrayConfig(BaseModel):
    """Configuration loaded from mics.json."""

    speed_of_sound: float = 343.0
    temperature: float | None = None
    coordinate_system: Literal["local_xy", "local_xyz"] = "local_xy"
    microphones: list[Microphone]

    @field_validator("microphones")
    @classmethod
    def validate_microphone_count(cls, value: list[Microphone]) -> list[Microphone]:
        """Ensure mics.json contains enough microphones for TDOA."""

        if len(value) < 2:
            raise ValueError("At least two microphones are required.")
        ids = [mic.id for mic in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Microphone ids must be unique.")
        return value


class TdoaMeasurement(BaseModel):
    """TDOA measurement against the reference microphone."""

    reference_mic_id: str
    microphone_id: str
    delay_seconds: float
    distance_delta_m: float
    confidence: float


class SourcePosition(BaseModel):
    """Estimated source position."""

    x: float
    y: float
    z: float | None = None
    confidence: float
    residual_rmse_m: float
    tdoa: list[TdoaMeasurement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TrackPoint(BaseModel):
    """One localization point in a trajectory."""

    time_seconds: float
    x: float
    y: float
    z: float | None = None
    speed_mps: float | None = None
    course_deg: float | None = None
    confidence: float
    residual_rmse_m: float


class LocalizationReport(BaseModel):
    """Complete localization and tracking report."""

    analysis_id: str
    microphone_config: MicrophoneArrayConfig
    position: SourcePosition
    track: list[TrackPoint]
    warnings: list[str] = Field(default_factory=list)
    plots: dict[str, str]
    report_json: str
    track_json: str
    track_csv: str
    track_png: str
    summary: dict[str, Any] = Field(default_factory=dict)

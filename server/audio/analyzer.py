"""High-level single-file audio analysis pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

import soundfile as sf

from audio.features import FeatureExtractor
from audio.loader import AudioLoader
from audio.preprocessing import adaptive_window_rms_threshold
from audio.separation import DroneSeparator
from audio.temporal_portrait import TemporalPortraitAnalyzer
from classification.expert_system import AcousticPassportBuilder, ExpertDroneClassifier
from config import settings
from ml.cluster_classifier import CentroidAudioClassifier
from ml.family_classifier import AcousticFamilyClassifier
from ml.label_registry import effective_drone_labels
from models.schemas import (
    AnalysisDecision,
    AudioFeatureSet,
    AudioQualityReport,
    ClassificationResult,
    DroneSeparationFindings,
    MLClassificationResult,
    SingleAnalysisReport,
    UploadedFileInfo,
)
from utils.file_utils import assert_audio_path
from utils.logging_utils import logger
from utils.serialization import write_json

if TYPE_CHECKING:
    from visualization.plots import PlotGenerator


class AudioAnalysisService:
    """Coordinate loading, feature extraction, classification and reporting."""

    def __init__(
        self,
        loader: AudioLoader | None = None,
        extractor: FeatureExtractor | None = None,
        classifier: ExpertDroneClassifier | None = None,
        ml_classifier: CentroidAudioClassifier | None = None,
        family_classifier: AcousticFamilyClassifier | None = None,
        passport_builder: AcousticPassportBuilder | None = None,
        plotter: PlotGenerator | None = None,
        separator: DroneSeparator | None = None,
        temporal_analyzer: TemporalPortraitAnalyzer | None = None,
    ) -> None:
        self.loader = loader or AudioLoader()
        self.extractor = extractor or FeatureExtractor()
        self.classifier = classifier or ExpertDroneClassifier()
        self.ml_classifier = ml_classifier or CentroidAudioClassifier()
        self.family_classifier = family_classifier or AcousticFamilyClassifier()
        self.passport_builder = passport_builder or AcousticPassportBuilder()
        # The plotter (matplotlib/plotly) is resolved lazily so a broken or
        # missing visualization stack never blocks detection and separation.
        self._plotter = plotter
        self._plotter_resolved = plotter is not None
        self.separator = separator or DroneSeparator()
        self.temporal_analyzer = temporal_analyzer or TemporalPortraitAnalyzer(separator=self.separator)

    def analyze(
        self,
        analysis_id: str,
        source_file: UploadedFileInfo,
        output_dir: Path,
    ) -> SingleAnalysisReport:
        """Run the complete single-file analysis pipeline."""

        path = Path(source_file.stored_path)
        assert_audio_path(path)
        logger.info("Starting single-file analysis %s for %s", analysis_id, path.name)

        loaded = self.loader.load_audio(path)
        extraction = self.extractor.extract(loaded.signal, loaded.sample_rate)
        classification = self.classifier.classify(extraction.features)
        ml_classification = self._predict_ml_windows(
            signal=loaded.signal,
            sample_rate=loaded.sample_rate,
            fallback_features=extraction.features,
        )
        separation = self._separate_drone(loaded.signal, loaded.sample_rate, output_dir)
        family_classification = self._predict_family_windows(
            signal=loaded.signal,
            sample_rate=loaded.sample_rate,
            fallback_features=extraction.features,
            air_target_confirmed=bool(separation and separation.drone_present),
        )
        temporal_portrait = self.temporal_analyzer.analyze(loaded.signal, loaded.sample_rate)
        decision = self._build_decision(classification, ml_classification, separation)
        decision = self._apply_temporal_portrait(decision, temporal_portrait)
        passport = self.passport_builder.build(extraction.features, classification)
        self._apply_separation_to_passport(passport, separation, decision)
        self._apply_type_policy_to_passport(passport, classification, ml_classification, decision)
        plots = self._create_plots(extraction, output_dir)

        report_path = output_dir / "report.json"
        report = SingleAnalysisReport(
            analysis_id=analysis_id,
            source_file=source_file,
            quality=AudioQualityReport(
                sample_rate=loaded.sample_rate,
                duration_seconds=loaded.duration_seconds,
                channels=loaded.channels,
                warnings=loaded.warnings,
            ),
            features=extraction.features,
            decision=decision,
            classification=classification,
            ml_classification=ml_classification,
            family_classification=family_classification,
            separation=separation,
            temporal_portrait=temporal_portrait,
            passport=passport,
            plots=plots,
            report_json=str(report_path),
        )
        write_json(report_path, report)
        logger.info(
            "Single-file analysis %s complete: %s %.3f",
            analysis_id,
            classification.best_match,
            classification.confidence,
        )
        return report

    def _predict_ml_windows(
        self,
        signal: np.ndarray,
        sample_rate: int,
        fallback_features: AudioFeatureSet,
    ) -> MLClassificationResult | None:
        """Run the local ML classifier on windows matching the training layout."""

        if self.ml_classifier.load_model() is None:
            return None

        window_size = max(int(round(settings.ml_window_seconds * sample_rate)), 1)
        hop_size = max(int(round(settings.ml_hop_seconds * sample_rate)), 1)
        min_window_rms = adaptive_window_rms_threshold(
            signal, window_size, hop_size, settings.ml_min_window_rms
        )
        if len(signal) < window_size:
            prediction = self.ml_classifier.predict(fallback_features)
            if prediction is not None:
                prediction.status = "single_short_file"
            return prediction

        window_features: list[AudioFeatureSet] = []
        for start in range(0, len(signal) - window_size + 1, hop_size):
            segment = signal[start:start + window_size]
            rms = float(np.sqrt(np.mean(np.square(segment)))) if segment.size else 0.0
            if rms < min_window_rms:
                continue
            extraction = self.extractor.extract(segment.astype(np.float32), sample_rate)
            window_features.append(extraction.features)

        if not window_features:
            return self.ml_classifier.predict(fallback_features)
        return self.ml_classifier.predict_many(window_features)

    def _predict_family_windows(
        self,
        signal: np.ndarray,
        sample_rate: int,
        fallback_features: AudioFeatureSet,
        air_target_confirmed: bool = False,
    ):
        """Run the broad family layer without changing the 43-feature contract."""

        if self.family_classifier.load_model() is None:
            return None
        window_size = max(int(round(settings.ml_window_seconds * sample_rate)), 1)
        hop_size = max(int(round(settings.ml_hop_seconds * sample_rate)), 1)
        min_window_rms = adaptive_window_rms_threshold(
            signal, window_size, hop_size, settings.ml_min_window_rms
        )
        feature_sets: list[AudioFeatureSet] = []
        if len(signal) < window_size:
            feature_sets.append(fallback_features)
        else:
            for start in range(0, len(signal) - window_size + 1, hop_size):
                segment = signal[start:start + window_size]
                rms = float(np.sqrt(np.mean(np.square(segment)))) if segment.size else 0.0
                if rms < min_window_rms:
                    continue
                feature_sets.append(self.extractor.extract(segment.astype(np.float32), sample_rate).features)
        if not feature_sets:
            feature_sets = [fallback_features]
        return self.family_classifier.predict_features(feature_sets, air_target_confirmed=air_target_confirmed)

    def _separate_drone(
        self,
        signal: np.ndarray,
        sample_rate: int,
        output_dir: Path,
    ) -> DroneSeparationFindings:
        """Isolate the drone comb from background noise and save both signals."""

        try:
            result = self.separator.separate(signal, sample_rate)
        except Exception:
            logger.exception("Drone source separation failed")
            return DroneSeparationFindings(explanation="Разделение источников не выполнено.")

        findings = result.findings
        if result.isolated.size and result.residual.size:
            isolated_path = output_dir / "drone_isolated.wav"
            residual_path = output_dir / "noise_residual.wav"
            try:
                sf.write(isolated_path, result.isolated, result.sample_rate)
                sf.write(residual_path, result.residual, result.sample_rate)
                findings.isolated_audio = str(isolated_path)
                findings.residual_audio = str(residual_path)
            except Exception:
                logger.exception("Saving separated audio failed")
        logger.info(
            "Separation: present=%s F0=%.1f persistence=%.2f SNR=%.1fdB",
            findings.drone_present,
            findings.fundamental_hz,
            findings.persistence,
            findings.harmonic_snr_db,
        )
        return findings

    @staticmethod
    def _apply_separation_to_passport(passport, separation, decision) -> None:
        """Show the robust separation numbers in the passport when a drone is found.

        The legacy DSP fundamental/harmonic-step are unreliable on multirotors, so
        once the verdict is a drone we use the separation blade-pass (and derived
        figures) for the human-facing passport to keep it consistent with the
        verdict and the separation card.
        """

        drone = decision is not None and decision.drone_present
        if separation is None or not drone or separation.fundamental_hz <= 0:
            return
        passport.fundamental_hz = round(float(separation.fundamental_hz), 2)
        passport.harmonic_step_hz = round(float(separation.fundamental_hz), 2)
        passport.harmonic_count = int(separation.harmonic_count)
        passport.stability = round(1.0 - float(separation.steadiness_cv), 3)

    @staticmethod
    def _apply_type_policy_to_passport(passport, classification, ml_classification, decision) -> None:
        """Keep legacy expert scores as research hints, not operational type IDs."""

        if decision is None or not decision.drone_present:
            return
        validated_ml_type = bool(
            ml_classification is not None
            and ml_classification.best_label in effective_drone_labels()
            and ml_classification.confidence >= settings.ml_non_drone_confidence_threshold
            and ml_classification.status not in {"provisional_candidate", "weak_candidate"}
        )
        if validated_ml_type:
            return
        if classification.best_match != "UNKNOWN":
            passport.notes.append(
                f"Исследовательская экспертная гипотеза: {classification.best_match} "
                f"({classification.confidence * 100:.1f}%). Operational type lock запрещён."
            )
        passport.drone_type = "UNKNOWN"
        passport.probability_percent = 0.0

    def _get_plotter(self) -> "PlotGenerator | None":
        """Resolve the plot generator lazily; return None if unavailable."""

        if not self._plotter_resolved:
            self._plotter_resolved = True
            try:
                from visualization.plots import PlotGenerator

                self._plotter = PlotGenerator()
            except Exception:
                logger.exception("Visualization unavailable; continuing without plots")
                self._plotter = None
        return self._plotter

    def _create_plots(self, extraction, output_dir: Path) -> dict[str, str]:
        """Generate plots, degrading gracefully if the plotter is unavailable."""

        plotter = self._get_plotter()
        if plotter is None:
            return {}
        try:
            return plotter.create_audio_plots(extraction, output_dir)
        except Exception:
            logger.exception("Plot generation failed; continuing without plots")
            return {}

    @staticmethod
    def _apply_temporal_portrait(decision, portrait):
        """Keep the provisional temporal pattern diagnostic-only.

        Research samples for Lutyi are not a reference class.  Until a dataset
        freeze explicitly promotes the class, a temporal match must not change
        status, type, confidence, drone_present, or ML/expert source.
        """

        return decision

    @staticmethod
    def _build_decision(
        classification: ClassificationResult,
        ml_classification: MLClassificationResult | None,
        separation: DroneSeparationFindings | None = None,
    ) -> AnalysisDecision:
        """Build the final user-facing decision for web/API output.

        Foreground class and drone presence are independent channels: a confident
        non-drone label sets the dominant source but never suppresses a drone that
        the separation stage isolated from the background.
        """

        drone_present = bool(separation and separation.drone_present)
        drone_confidence = float(separation.confidence) if separation else 0.0

        # Config drone labels unioned with UI-registered drone classes, so a
        # drone added through the training menu counts as a drone right away.
        drone_label_set = effective_drone_labels()

        dominant_source = ""
        dominant_confidence = 0.0
        ml_is_confident_non_drone = (
            ml_classification is not None
            and ml_classification.best_label not in drone_label_set
            and ml_classification.best_label != "UNKNOWN"
            and ml_classification.confidence >= settings.ml_non_drone_confidence_threshold
        )
        if ml_classification is not None and ml_classification.best_label != "UNKNOWN":
            dominant_source = ml_classification.best_label
            dominant_confidence = float(ml_classification.confidence)

        # A confident ML prediction of a known drone TYPE is itself a drone
        # verdict that names the type (corroborated by separation when present).
        ml_type_is_provisional = bool(
            ml_classification is not None
            and ml_classification.status in {"provisional_candidate", "weak_candidate"}
        )
        ml_is_drone = (
            ml_classification is not None
            and ml_classification.best_label in drone_label_set
            and ml_classification.confidence >= settings.ml_non_drone_confidence_threshold
            and not ml_type_is_provisional
        )
        if ml_is_drone:
            label = ml_classification.best_label
            conf = max(float(ml_classification.confidence), drone_confidence)
            explanation = (
                f"Локальная модель распознала тип БПЛА «{label}» "
                f"({ml_classification.confidence * 100:.1f}%)."
            )
            if drone_present:
                explanation += f" {separation.explanation}"
            return AnalysisDecision(
                status="drone",
                display_label=label,
                confidence=conf,
                source="local_ml+separation" if drone_present else "local_ml",
                drone_present=True,
                drone_confidence=conf,
                explanation=explanation,
            )

        # Provisional/weak type hypotheses may name a candidate for the operator,
        # but must never become an operational type lock. Drone presence still
        # comes from the independent detector/separation channel.
        if ml_type_is_provisional and drone_present and ml_classification is not None:
            return AnalysisDecision(
                status="drone",
                display_label=f"БПЛА; тип предположительно {ml_classification.best_label}",
                confidence=drone_confidence,
                source="separation+provisional_type",
                dominant_source=ml_classification.best_label,
                dominant_confidence=float(ml_classification.confidence),
                drone_present=True,
                drone_confidence=drone_confidence,
                needs_review=True,
                explanation=(
                    f"Независимый акустический детектор подтверждает БПЛА. "
                    f"Тип «{ml_classification.best_label}» является только предварительной "
                    f"гипотезой ({ml_classification.confidence * 100:.1f}%) и не фиксируется."
                ),
            )

        # A loud non-drone foreground with a drone isolated underneath it: raise
        # the alarm (recall-first) and route the conflict to operator review.
        if ml_is_confident_non_drone and drone_present:
            label = ml_classification.best_label
            return AnalysisDecision(
                status="drone",
                display_label=f"Фон: {label} + БПЛА в фоне ({separation.likely_source})",
                confidence=drone_confidence,
                source="separation+local_ml",
                suppress_drone_profile=False,
                dominant_source=label,
                dominant_confidence=dominant_confidence,
                drone_present=True,
                drone_confidence=drone_confidence,
                conflict=True,
                needs_review=True,
                explanation=(
                    f"Передний план: {label} ({dominant_confidence * 100:.0f}%). "
                    f"{separation.explanation} Громкий фон не подавляет независимую "
                    "детекцию дрона — требуется проверка оператором."
                ),
            )

        # Confident non-drone and no isolated comb: a genuine not-drone result.
        if ml_is_confident_non_drone and not drone_present:
            label = ml_classification.best_label
            confidence_percent = ml_classification.confidence * 100.0
            return AnalysisDecision(
                status="not_drone",
                display_label=f"Не БПЛА: {label}",
                confidence=ml_classification.confidence,
                source="local_ml",
                suppress_drone_profile=True,
                dominant_source=label,
                dominant_confidence=dominant_confidence,
                drone_present=False,
                drone_confidence=drone_confidence,
                explanation=(
                    f"Локальная модель уверенно распознала класс '{label}' "
                    f"({confidence_percent:.1f}%), устойчивый гармонический "
                    "источник под шумом не выделен."
                ),
            )

        if classification.best_match == "UNKNOWN" and not drone_present:
            return AnalysisDecision(
                status="unknown",
                display_label="Не определено",
                confidence=classification.confidence,
                source="expert",
                dominant_source=dominant_source,
                dominant_confidence=dominant_confidence,
                drone_present=False,
                drone_confidence=drone_confidence,
                explanation=classification.explanation,
            )

        # The legacy expert profiles are retained as diagnostics, but they are
        # not independently validated type identities. When the separator has
        # detected a target and the ML type layer has no validated verdict, the
        # operational result must remain type UNKNOWN.
        if drone_present:
            expert_hint = classification.best_match if classification.best_match != "UNKNOWN" else ""
            conflict = bool(dominant_source and dominant_source not in drone_label_set)
            explanation = separation.explanation
            if expert_hint:
                explanation += (
                    f" Экспертная система дала исследовательскую гипотезу "
                    f"«{expert_hint}» ({classification.confidence * 100:.1f}%), "
                    "но она не используется как operational type lock."
                )
            return AnalysisDecision(
                status="drone",
                display_label="БПЛА; тип UNKNOWN",
                confidence=drone_confidence,
                source="separation+expert_hint" if expert_hint else "separation",
                dominant_source=dominant_source,
                dominant_confidence=dominant_confidence,
                drone_present=True,
                drone_confidence=drone_confidence,
                conflict=conflict,
                needs_review=True,
                research_type_hint=expert_hint,
                research_type_confidence=float(classification.confidence) if expert_hint else 0.0,
                explanation=explanation,
            )

        # Expert flagged a drone, or the separation stage isolated one.
        if classification.best_match != "UNKNOWN":
            display_label = classification.best_match
            confidence = classification.confidence
            source = "expert"
            explanation = classification.explanation
            if drone_present:
                source = "expert+separation"
                explanation = f"{classification.explanation} {separation.explanation}"
            elif (
                ml_classification is not None
                and ml_classification.best_label in drone_label_set
            ):
                source = "expert+local_ml"
                explanation = (
                    f"{classification.explanation} Локальная модель не выявила "
                    "уверенный фоновый класс не-БПЛА."
                )
        else:
            display_label = f"БПЛА в фоне ({separation.likely_source})"
            confidence = drone_confidence
            source = "separation"
            explanation = separation.explanation

        # A drone co-occurring with a non-drone foreground label is a conflict
        # worth operator review, even when that label was below the suppress
        # threshold (so it did not reach the explicit conflict branch above).
        conflict = (
            drone_present
            and bool(dominant_source)
            and dominant_source not in drone_label_set
        )
        return AnalysisDecision(
            status="drone",
            display_label=display_label,
            confidence=confidence,
            source=source,
            dominant_source=dominant_source,
            dominant_confidence=dominant_confidence,
            drone_present=drone_present,
            drone_confidence=drone_confidence,
            conflict=conflict,
            needs_review=conflict,
            explanation=explanation,
        )

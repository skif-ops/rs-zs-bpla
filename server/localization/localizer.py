"""TDOA localizer built on GCC-PHAT and least squares geometry."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from audio.loader import AudioLoader
from config import settings
from localization.gcc_phat import GccPhatEstimator
from localization.geometry import TdoaGeometrySolver
from models.schemas import (
    LocalizationReport,
    MicrophoneArrayConfig,
    SourcePosition,
    TdoaMeasurement,
    UploadedFileInfo,
)
from tracking.tracker import TrajectoryTracker
from utils.logging_utils import logger
from utils.serialization import write_json, write_track_csv
from visualization.plots import PlotGenerator


class TdoaLocalizer:
    """Estimate source position from synchronized microphone signals."""

    def __init__(
        self,
        gcc: GccPhatEstimator | None = None,
        solver: TdoaGeometrySolver | None = None,
    ) -> None:
        self.gcc = gcc or GccPhatEstimator()
        self.solver = solver or TdoaGeometrySolver()

    def estimate(
        self,
        signals: list[np.ndarray],
        sample_rate: int,
        config: MicrophoneArrayConfig,
    ) -> SourcePosition:
        """Estimate source coordinates for one signal window."""

        warnings = self._quality_warnings(config)
        if len(signals) != len(config.microphones):
            raise ValueError("Number of signals must match microphones in mics.json.")

        reference_signal = signals[0]
        reference_mic = config.microphones[0]
        tdoa_measurements: list[TdoaMeasurement] = []
        tdoa_values: list[float] = []

        for mic, mic_signal in zip(config.microphones[1:], signals[1:], strict=True):
            max_tau = self._max_tau(reference_mic, mic, config.speed_of_sound)
            result = self.gcc.estimate(
                reference=reference_signal,
                signal=mic_signal,
                sample_rate=sample_rate,
                max_tau=max_tau,
            )
            tdoa_values.append(result.delay_seconds)
            tdoa_measurements.append(
                TdoaMeasurement(
                    reference_mic_id=reference_mic.id,
                    microphone_id=mic.id,
                    delay_seconds=result.delay_seconds,
                    distance_delta_m=result.delay_seconds * config.speed_of_sound,
                    confidence=result.confidence,
                )
            )

        solution = self.solver.solve(config, np.array(tdoa_values, dtype=np.float64))
        if not solution.success:
            warnings.append(f"Least squares did not fully converge: {solution.message}")

        gcc_confidence = float(np.mean([item.confidence for item in tdoa_measurements])) if tdoa_measurements else 0.0
        residual_confidence = float(
            np.exp(-solution.residual_rmse_m / settings.localization_residual_scale_m)
        )
        geometry_confidence = self._geometry_confidence(config)
        confidence = float(np.clip(gcc_confidence * residual_confidence * geometry_confidence, 0.0, 1.0))

        return SourcePosition(
            x=float(solution.coordinates[0]),
            y=float(solution.coordinates[1]),
            z=float(solution.coordinates[2]) if config.coordinate_system == "local_xyz" else None,
            confidence=confidence,
            residual_rmse_m=solution.residual_rmse_m,
            tdoa=tdoa_measurements,
            warnings=warnings,
        )

    @staticmethod
    def _quality_warnings(config: MicrophoneArrayConfig) -> list[str]:
        """Return geometry warnings for localization."""

        warnings: list[str] = []
        mic_count = len(config.microphones)
        if mic_count < 4:
            warnings.append(
                "Fewer than 4 microphones: localization accuracy is limited, "
                "especially for 3D or ambiguous source positions."
            )
        if config.coordinate_system == "local_xy" and mic_count < 3:
            warnings.append("2D localization with fewer than 3 microphones is underdetermined.")
        if config.coordinate_system == "local_xyz" and mic_count < 4:
            warnings.append("3D localization requires at least 4 microphones for robust results.")
        return warnings

    @staticmethod
    def _max_tau(reference_mic, mic, speed_of_sound: float) -> float:
        """Return physically plausible maximum delay for a microphone pair."""

        distance = float(
            np.sqrt(
                (reference_mic.x - mic.x) ** 2
                + (reference_mic.y - mic.y) ** 2
                + (reference_mic.z - mic.z) ** 2
            )
        )
        return distance / max(speed_of_sound, 1.0) + 0.02

    @staticmethod
    def _geometry_confidence(config: MicrophoneArrayConfig) -> float:
        """Return confidence multiplier based on array size."""

        mic_count = len(config.microphones)
        required = 4 if config.coordinate_system == "local_xyz" else 3
        return float(np.clip((mic_count - 1) / max(required - 1, 1), 0.25, 1.0))


class LocalizationAnalysisService:
    """Coordinate multi-microphone localization and trajectory reporting."""

    def __init__(
        self,
        loader: AudioLoader | None = None,
        localizer: TdoaLocalizer | None = None,
        plotter: PlotGenerator | None = None,
    ) -> None:
        self.loader = loader or AudioLoader()
        self.localizer = localizer or TdoaLocalizer()
        self.tracker = TrajectoryTracker(localizer=self.localizer)
        self.plotter = plotter or PlotGenerator()

    def analyze(
        self,
        analysis_id: str,
        config: MicrophoneArrayConfig,
        uploaded_files: list[UploadedFileInfo],
        output_dir: Path,
    ) -> LocalizationReport:
        """Run localization and tracking for uploaded microphone WAV files."""

        logger.info("Starting localization analysis %s", analysis_id)
        paths = self._paths_for_config(config, uploaded_files)
        loaded, load_warnings = self.loader.load_many_resampled(paths)
        if not loaded:
            raise ValueError("No microphone audio was loaded.")

        sample_rate = loaded[0].sample_rate
        min_samples = min(len(item.signal) for item in loaded)
        signals = [item.signal[:min_samples] for item in loaded]
        warnings = load_warnings + [warning for item in loaded for warning in item.warnings]

        position = self.localizer.estimate(signals, sample_rate, config)
        track = self.tracker.track(
            signals=signals,
            sample_rate=sample_rate,
            config=config,
            window_seconds=settings.tracking_window_seconds,
        )
        warnings.extend(position.warnings)
        plots = self.plotter.create_localization_plots(config, position, track, output_dir)

        track_json_path = output_dir / "track.json"
        track_csv_path = output_dir / "track.csv"
        report_json_path = output_dir / "report.json"
        track_rows = [point.model_dump() for point in track]
        write_json(track_json_path, track_rows)
        write_track_csv(track_csv_path, track_rows)

        summary = self._summary(track, min_samples / float(sample_rate))
        report = LocalizationReport(
            analysis_id=analysis_id,
            microphone_config=config,
            position=position,
            track=track,
            warnings=sorted(set(warnings)),
            plots=plots,
            report_json=str(report_json_path),
            track_json=str(track_json_path),
            track_csv=str(track_csv_path),
            track_png=plots.get("track", ""),
            summary=summary,
        )
        write_json(report_json_path, report)
        logger.info(
            "Localization analysis %s complete: x=%.2f y=%.2f confidence=%.3f",
            analysis_id,
            position.x,
            position.y,
            position.confidence,
        )
        return report

    @staticmethod
    def _paths_for_config(
        config: MicrophoneArrayConfig,
        uploaded_files: list[UploadedFileInfo],
    ) -> list[Path]:
        """Resolve mics.json file names against uploaded files."""

        by_original = {Path(item.original_name).name: Path(item.stored_path) for item in uploaded_files}
        by_stored = {Path(item.stored_path).name: Path(item.stored_path) for item in uploaded_files}
        paths: list[Path] = []
        missing: list[str] = []
        for mic in config.microphones:
            path = by_original.get(mic.file) or by_stored.get(mic.file)
            if path is None:
                missing.append(mic.file)
                continue
            paths.append(path)
        if missing:
            raise ValueError(f"Missing microphone WAV files: {', '.join(missing)}")
        return paths

    @staticmethod
    def _summary(track: list, duration_seconds: float) -> dict[str, float | int]:
        """Return aggregate track metrics."""

        speeds = [point.speed_mps for point in track if point.speed_mps is not None]
        confidences = [point.confidence for point in track]
        return {
            "duration_seconds": round(float(duration_seconds), 3),
            "track_points": len(track),
            "average_speed_mps": round(float(np.mean(speeds)), 3) if speeds else 0.0,
            "max_speed_mps": round(float(np.max(speeds)), 3) if speeds else 0.0,
            "average_confidence": round(float(np.mean(confidences)), 3) if confidences else 0.0,
        }


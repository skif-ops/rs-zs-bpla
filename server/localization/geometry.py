"""Geometry helpers for TDOA localization."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from config import settings
from models.schemas import MicrophoneArrayConfig


@dataclass(frozen=True, slots=True)
class LeastSquaresPosition:
    """Position estimated from least squares."""

    coordinates: np.ndarray
    residual_rmse_m: float
    success: bool
    message: str


class TdoaGeometrySolver:
    """Solve source position from microphone positions and TDOA values."""

    def solve(
        self,
        config: MicrophoneArrayConfig,
        tdoa_seconds: np.ndarray,
    ) -> LeastSquaresPosition:
        """Solve TDOA equations with scipy least_squares."""

        mic_positions = self.microphone_positions(config)
        speed = float(config.speed_of_sound)
        is_3d = config.coordinate_system == "local_xyz"
        dimension = 3 if is_3d else 2
        initial = self.initial_guess(mic_positions, dimension)
        reference = mic_positions[0, :dimension]
        other_positions = mic_positions[1:, :dimension]
        target_delta = np.asarray(tdoa_seconds, dtype=np.float64) * speed

        def residuals(candidate: np.ndarray) -> np.ndarray:
            source = np.asarray(candidate, dtype=np.float64)
            reference_distance = np.linalg.norm(source - reference)
            distances = np.linalg.norm(other_positions - source, axis=1)
            return (distances - reference_distance) - target_delta

        result = least_squares(
            residuals,
            initial,
            max_nfev=settings.localization_max_iterations,
        )
        residual = residuals(result.x)
        rmse = float(np.sqrt(np.mean(np.square(residual)))) if residual.size else 0.0

        coordinates = np.asarray(result.x, dtype=np.float64)
        if not is_3d:
            z_value = float(np.mean(mic_positions[:, 2])) if mic_positions.shape[1] >= 3 else 0.0
            coordinates = np.array([coordinates[0], coordinates[1], z_value], dtype=np.float64)

        return LeastSquaresPosition(
            coordinates=coordinates,
            residual_rmse_m=rmse,
            success=bool(result.success),
            message=str(result.message),
        )

    @staticmethod
    def microphone_positions(config: MicrophoneArrayConfig) -> np.ndarray:
        """Return microphone positions as an Nx3 array."""

        return np.array(
            [[mic.x, mic.y, mic.z] for mic in config.microphones],
            dtype=np.float64,
        )

    @staticmethod
    def initial_guess(mic_positions: np.ndarray, dimension: int) -> np.ndarray:
        """Return a stable initial source guess."""

        centroid = np.mean(mic_positions[:, :dimension], axis=0)
        spread = np.max(np.ptp(mic_positions[:, :dimension], axis=0))
        offset = max(float(spread), 10.0) * 0.25
        guess = centroid.copy()
        guess[0] += offset
        if dimension >= 2:
            guess[1] += offset
        if dimension == 3:
            guess[2] += max(offset * 0.4, 2.0)
        return guess


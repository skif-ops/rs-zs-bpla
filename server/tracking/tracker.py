"""Windowed trajectory tracking over TDOA localizations."""

from __future__ import annotations

import math
from typing import Protocol

import numpy as np

from models.schemas import MicrophoneArrayConfig, SourcePosition, TrackPoint


class LocalizerProtocol(Protocol):
    """Minimal protocol implemented by TdoaLocalizer."""

    def estimate(
        self,
        signals: list[np.ndarray],
        sample_rate: int,
        config: MicrophoneArrayConfig,
    ) -> SourcePosition:
        """Estimate source position for a window."""


class KalmanFilterHook:
    """No-op placeholder for future Kalman filtering."""

    def update(self, point: TrackPoint) -> TrackPoint:
        """Return point unchanged until a real filter is installed."""

        return point


class TrajectoryTracker:
    """Track source movement by localizing consecutive audio windows."""

    def __init__(
        self,
        localizer: LocalizerProtocol,
        filter_hook: KalmanFilterHook | None = None,
    ) -> None:
        self.localizer = localizer
        self.filter_hook = filter_hook or KalmanFilterHook()

    def track(
        self,
        signals: list[np.ndarray],
        sample_rate: int,
        config: MicrophoneArrayConfig,
        window_seconds: float = 0.5,
    ) -> list[TrackPoint]:
        """Estimate trajectory points over fixed windows."""

        if not signals:
            return []
        window_samples = max(8, int(round(sample_rate * window_seconds)))
        min_samples = min(len(signal) for signal in signals)
        if min_samples < window_samples:
            position = self.localizer.estimate(signals, sample_rate, config)
            return [
                self.filter_hook.update(
                    TrackPoint(
                        time_seconds=0.0,
                        x=position.x,
                        y=position.y,
                        z=position.z,
                        speed_mps=None,
                        course_deg=None,
                        confidence=position.confidence,
                        residual_rmse_m=position.residual_rmse_m,
                    )
                )
            ]

        points: list[TrackPoint] = []
        previous: TrackPoint | None = None
        for start in range(0, min_samples - window_samples + 1, window_samples):
            end = start + window_samples
            window_signals = [signal[start:end] for signal in signals]
            position = self.localizer.estimate(window_signals, sample_rate, config)
            center_time = (start + window_samples / 2.0) / float(sample_rate)
            speed, course = self._motion(previous, position, center_time)
            point = TrackPoint(
                time_seconds=round(center_time, 4),
                x=position.x,
                y=position.y,
                z=position.z,
                speed_mps=speed,
                course_deg=course,
                confidence=position.confidence,
                residual_rmse_m=position.residual_rmse_m,
            )
            point = self.filter_hook.update(point)
            points.append(point)
            previous = point
        return points

    @staticmethod
    def _motion(
        previous: TrackPoint | None,
        position: SourcePosition,
        time_seconds: float,
    ) -> tuple[float | None, float | None]:
        """Calculate speed and course from the previous point."""

        if previous is None:
            return None, None
        dt = max(time_seconds - previous.time_seconds, 1e-9)
        dx = position.x - previous.x
        dy = position.y - previous.y
        dz = (position.z or 0.0) - (previous.z or 0.0)
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        speed = distance / dt
        course = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
        return round(float(speed), 3), round(float(course), 2)


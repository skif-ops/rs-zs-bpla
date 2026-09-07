"""Long-horizon persistent propulsion diagnostics for UAV candidates.

The 1 s feature/KNN path is intentionally retained for compatibility, but it is
not allowed to be the only source of type identity.  A long recording can contain
only a short fly-over followed by urban background; averaging or labeling the
whole tail contaminates training and can turn the scene into the class.

This module evaluates overlapping 10 s windows with the harmonic separator and
measures a generic persistent propulsion-harmonic pattern. It is deliberately
not type-specific: both Lutyi and FP-1-like piston/propeller sources may match it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from audio.separation import DroneSeparator
from models.schemas import TemporalAcousticPortrait, TemporalPortraitWindow


@dataclass(slots=True)
class TemporalPortraitAnalyzer:
    """Build a long-window acoustic portrait on top of ``DroneSeparator``."""

    separator: DroneSeparator | None = None
    window_seconds: float = 10.0
    hop_seconds: float = 2.0
    max_windows: int = 30

    # Generic propulsion-comb evidence gate; not a type definition.
    propulsion_order_low: float = 4.5
    propulsion_order_high: float = 5.5
    propulsion_min_harmonics: int = 10
    propulsion_min_snr_db: float = 15.0
    propulsion_min_persistence: float = 0.90
    propulsion_max_steadiness_cv: float = 0.04
    propulsion_min_consecutive_windows: int = 2

    def __post_init__(self) -> None:
        if self.separator is None:
            self.separator = DroneSeparator()

    def analyze(self, signal: np.ndarray, sample_rate: int) -> TemporalAcousticPortrait:
        """Evaluate overlapping long windows and return a provisional portrait."""

        y = np.asarray(signal, dtype=np.float32)
        sr = int(sample_rate)
        win = max(int(round(self.window_seconds * sr)), 1)
        hop = max(int(round(self.hop_seconds * sr)), 1)
        if y.size < win or sr <= 0:
            return TemporalAcousticPortrait(
                window_seconds=self.window_seconds,
                hop_seconds=self.hop_seconds,
                explanation=(
                    f"Для временного портрета требуется не менее {self.window_seconds:.0f} с аудио."
                ),
            )

        starts = list(range(0, y.size - win + 1, hop))
        if len(starts) > self.max_windows:
            # Keep chronological coverage across a long file without letting an
            # hour-long recording dominate runtime.
            positions = np.linspace(0, len(starts) - 1, self.max_windows)
            starts = [starts[i] for i in sorted(set(int(round(v)) for v in positions))]

        windows: list[TemporalPortraitWindow] = []
        run = 0
        longest = 0
        best_score = -1.0
        best_start: float | None = None
        for start in starts:
            segment = y[start : start + win]
            findings = self.separator.separate(segment, sr).findings
            order = (
                float(findings.dominant_harmonic_hz / findings.fundamental_hz)
                if findings.fundamental_hz > 0.0
                else 0.0
            )
            match = self._propulsion_window_match(
                order=order,
                harmonic_count=findings.harmonic_count,
                snr_db=findings.harmonic_snr_db,
                persistence=findings.persistence,
                steadiness_cv=findings.steadiness_cv,
            )
            if match:
                run += 1
                longest = max(longest, run)
            else:
                run = 0

            score = self._window_score(
                order=order,
                harmonic_count=findings.harmonic_count,
                snr_db=findings.harmonic_snr_db,
                persistence=findings.persistence,
                steadiness_cv=findings.steadiness_cv,
            )
            if score > best_score:
                best_score = score
                best_start = start / float(sr)

            windows.append(
                TemporalPortraitWindow(
                    start_seconds=round(start / float(sr), 3),
                    duration_seconds=self.window_seconds,
                    fundamental_hz=float(findings.fundamental_hz),
                    dominant_harmonic_hz=float(findings.dominant_harmonic_hz),
                    dominant_order=round(order, 3),
                    harmonic_count=int(findings.harmonic_count),
                    harmonic_snr_db=float(findings.harmonic_snr_db),
                    persistence=float(findings.persistence),
                    steadiness_cv=float(findings.steadiness_cv),
                    persistent_propulsion_match=bool(match),
                    lutyi_match=bool(match),
                )
            )

        matched = sum(int(item.persistent_propulsion_match) for item in windows)
        candidate = longest >= self.propulsion_min_consecutive_windows
        confidence = self._aggregate_confidence(windows, longest, candidate)
        if candidate:
            explanation = (
                "Обнаружен устойчивый долговременный гармонический источник тяговой установки: "
                f"{matched}/{len(windows)} окон соответствуют профилю, "
                f"максимальная непрерывная серия {longest} окон. "
                "Признак не различает типы БПЛА и не влияет на итоговую идентификацию; "
                "он подтверждает лишь наличие устойчивого поршневого/винтового источника."
            )
        else:
            explanation = (
                "Устойчивой серии тягового гармонического паттерна не найдено. "
                "Это не подтверждает и не исключает какой-либо тип БПЛА."
            )

        return TemporalAcousticPortrait(
            window_seconds=self.window_seconds,
            hop_seconds=self.hop_seconds,
            total_windows=len(windows),
            matched_windows=matched,
            longest_match_run=longest,
            persistent_propulsion_candidate=candidate,
            lutyi_candidate=False,
            confidence=round(confidence, 3),
            best_start_seconds=round(best_start, 3) if best_start is not None else None,
            explanation=explanation,
            windows=windows,
        )

    def _propulsion_window_match(
        self,
        *,
        order: float,
        harmonic_count: int,
        snr_db: float,
        persistence: float,
        steadiness_cv: float,
    ) -> bool:
        return bool(
            self.propulsion_order_low <= order <= self.propulsion_order_high
            and harmonic_count >= self.propulsion_min_harmonics
            and snr_db >= self.propulsion_min_snr_db
            and persistence >= self.propulsion_min_persistence
            and steadiness_cv <= self.propulsion_max_steadiness_cv
        )

    def _window_score(
        self,
        *,
        order: float,
        harmonic_count: int,
        snr_db: float,
        persistence: float,
        steadiness_cv: float,
    ) -> float:
        order_error = abs(order - 5.0)
        order_score = max(0.0, 1.0 - order_error / 1.0)
        harmonic_score = min(max(harmonic_count, 0) / 14.0, 1.0)
        snr_score = min(max(snr_db, 0.0) / 25.0, 1.0)
        persistence_score = min(max(persistence, 0.0), 1.0)
        steady_score = max(0.0, 1.0 - steadiness_cv / 0.08)
        return float(
            0.28 * order_score
            + 0.18 * harmonic_score
            + 0.22 * snr_score
            + 0.18 * persistence_score
            + 0.14 * steady_score
        )

    @staticmethod
    def _aggregate_confidence(
        windows: list[TemporalPortraitWindow], longest: int, candidate: bool
    ) -> float:
        if not windows:
            return 0.0
        matched = [item for item in windows if item.persistent_propulsion_match]
        if not matched:
            return 0.0
        coverage = len(matched) / len(windows)
        snr = min(float(np.median([item.harmonic_snr_db for item in matched])) / 30.0, 1.0)
        steady = 1.0 - min(float(np.median([item.steadiness_cv for item in matched])) / 0.04, 1.0)
        run_score = min(longest / 4.0, 1.0)
        score = 0.25 * coverage + 0.30 * snr + 0.20 * steady + 0.25 * run_score
        return float(np.clip(score if candidate else score * 0.5, 0.0, 1.0))

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from audio.analyzer import AudioAnalysisService
from audio.temporal_portrait import TemporalPortraitAnalyzer
from models.schemas import AnalysisDecision, TemporalAcousticPortrait


class SequenceSeparator:
    """Return deterministic long-window harmonic findings."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.index = 0

    def separate(self, signal, sample_rate):
        row = self.rows[min(self.index, len(self.rows) - 1)]
        self.index += 1
        return SimpleNamespace(findings=SimpleNamespace(**row))


def _row(*, order=5.0, harmonics=14, snr=24.0, persistence=0.98, cv=0.01):
    f0 = 75.0
    return {
        "fundamental_hz": f0,
        "dominant_harmonic_hz": f0 * order,
        "harmonic_count": harmonics,
        "harmonic_snr_db": snr,
        "persistence": persistence,
        "steadiness_cv": cv,
    }


def test_temporal_propulsion_requires_consecutive_long_windows():
    # 14 s with 10 s window / 2 s hop gives three windows. Two consecutive
    # Lutyi-like windows are enough; a single isolated match is not.
    y = np.zeros(14_000, dtype=np.float32)
    analyzer = TemporalPortraitAnalyzer(
        separator=SequenceSeparator([_row(), _row(), _row(order=3.0)]),
        window_seconds=10.0,
        hop_seconds=2.0,
    )
    portrait = analyzer.analyze(y, 1000)
    assert portrait.total_windows == 3
    assert portrait.matched_windows == 2
    assert portrait.longest_match_run == 2
    assert portrait.persistent_propulsion_candidate is True
    assert portrait.lutyi_candidate is False
    assert portrait.confidence > 0.0


def test_temporal_propulsion_rejects_isolated_match():
    y = np.zeros(14_000, dtype=np.float32)
    analyzer = TemporalPortraitAnalyzer(
        separator=SequenceSeparator([_row(), _row(order=3.0), _row()]),
        window_seconds=10.0,
        hop_seconds=2.0,
    )
    portrait = analyzer.analyze(y, 1000)
    assert portrait.matched_windows == 2
    assert portrait.longest_match_run == 1
    assert portrait.lutyi_candidate is False


def test_temporal_portrait_is_diagnostic_only_and_does_not_promote_type():
    decision = AnalysisDecision(
        status="unknown",
        display_label="FP-1",
        confidence=0.72,
        source="ml",
        explanation="short-window classifier",
        drone_present=True,
        drone_confidence=0.72,
        needs_review=False,
    )
    portrait = TemporalAcousticPortrait(
        total_windows=8,
        matched_windows=5,
        longest_match_run=4,
        persistent_propulsion_candidate=True,
        lutyi_candidate=False,
        confidence=0.82,
        explanation="stable long-horizon comb",
    )
    out = AudioAnalysisService._apply_temporal_portrait(decision, portrait)
    assert out.status == "unknown"
    assert out.display_label == "FP-1"
    assert out.source == "ml"
    assert out.confidence == 0.72
    assert out.needs_review is False
    assert out.drone_present is True

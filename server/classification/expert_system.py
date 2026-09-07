"""Rule-based acoustic classifier and passport builder."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from classification.profiles import PROFILES, AcousticProfile
from config import settings
from models.schemas import (
    AcousticPassport,
    AudioFeatureSet,
    ClassificationResult,
    ClassificationScore,
)


@dataclass(frozen=True, slots=True)
class WeightedScore:
    """Internal weighted score item."""

    score: float
    weight: float
    reason: str


class ExpertDroneClassifier:
    """Classify drone type using transparent expert rules."""

    def classify(self, features: AudioFeatureSet) -> ClassificationResult:
        """Return best matching acoustic profile and confidence."""

        scores = [
            self._score_profile(profile, features)
            for profile in PROFILES
        ]
        scores.sort(key=lambda item: item.score, reverse=True)

        best = scores[0] if scores else ClassificationScore(profile="UNKNOWN", score=0.0)
        best_match = best.profile
        confidence = float(best.score)
        if confidence < settings.classifier_unknown_threshold:
            best_match = "UNKNOWN"

        explanation = self._explain(features, scores, best_match, confidence)
        return ClassificationResult(
            best_match=best_match,
            confidence=confidence,
            scores=scores,
            explanation=explanation,
        )

    def _score_profile(
        self,
        profile: AcousticProfile,
        features: AudioFeatureSet,
    ) -> ClassificationScore:
        """Calculate weighted score for one profile."""

        items = self._profile_rules(profile, features)
        total_weight = sum(item.weight for item in items)
        if total_weight <= 0:
            score = 0.0
        else:
            score = sum(item.score * item.weight for item in items) / total_weight

        reasons = [
            f"{item.reason}: {item.score:.2f}"
            for item in items
            if item.score >= 0.55
        ]
        return ClassificationScore(
            profile=profile.display_name,
            score=float(np.clip(score, 0.0, 1.0)),
            reasons=reasons,
        )

    def _profile_rules(
        self,
        profile: AcousticProfile,
        features: AudioFeatureSet,
    ) -> list[WeightedScore]:
        """Return profile-specific rule scores."""

        common = [
            WeightedScore(
                self._range_score(features.fundamental_hz, *profile.fundamental_range_hz),
                0.24,
                "base frequency matches profile",
            ),
            WeightedScore(
                self._range_score(
                    features.harmonic_stability,
                    profile.stability_range[0],
                    profile.stability_range[1],
                    margin_ratio=0.50,
                ),
                0.17,
                "harmonic stability matches profile",
            ),
        ]
        if profile.harmonic_count_range is not None:
            common.append(
                WeightedScore(
                    self._range_score(
                        features.harmonic_count,
                        profile.harmonic_count_range[0],
                        profile.harmonic_count_range[1],
                        margin_ratio=0.65,
                    ),
                    0.18,
                    "harmonic count matches profile",
                )
            )
        if profile.high_band_noise is not None:
            common.append(
                WeightedScore(
                    self._label_score(features.high_band_energy_label, profile.high_band_noise),
                    0.12,
                    "6-10 kHz noise matches profile",
                )
            )

        if profile.name == "LT":
            return common + [
                WeightedScore(
                    self._upper_is_better(features.harmonic_count, low=18, high=30),
                    0.09,
                    "many stable harmonics",
                ),
                WeightedScore(
                    self._lower_is_better(features.frequency_modulation_index, low=0.05, high=0.35),
                    0.08,
                    "low frequency modulation",
                ),
                WeightedScore(
                    self._upper_is_better(features.doppler_stability, low=0.78, high=0.98),
                    0.07,
                    "stable Doppler/F0 track",
                ),
                WeightedScore(
                    self._lower_is_better(features.spectral_roughness, low=0.08, high=0.45),
                    0.05,
                    "smooth rotor hum",
                ),
            ]

        if profile.name == "GR2":
            return common + [
                WeightedScore(
                    self._target_score(features.harmonic_count, target=12.5, width=7.0),
                    0.09,
                    "moderate harmonic count",
                ),
                WeightedScore(
                    self._target_score(features.harmonic_stability, target=0.68, width=0.35),
                    0.08,
                    "uneven but structured harmonics",
                ),
                WeightedScore(
                    self._target_score(features.spectral_roughness, target=0.45, width=0.45),
                    0.07,
                    "rattling spectral texture",
                ),
                WeightedScore(
                    self._lower_is_better(features.high_band_energy_6_10khz, low=0.01, high=0.10),
                    0.05,
                    "weak high-frequency hiss",
                ),
                WeightedScore(
                    self._target_score(features.frequency_modulation_index, target=0.28, width=0.45),
                    0.08,
                    "moderate GR2 modulation",
                ),
            ]

        if profile.name == "FP1":
            return common + [
                WeightedScore(
                    self._upper_is_better(features.frequency_modulation_index, low=0.45, high=0.80),
                    0.22,
                    "strong frequency modulation",
                ),
                WeightedScore(
                    self._lower_is_better(features.harmonic_stability, low=0.28, high=0.62),
                    0.16,
                    "low stability / blurred peaks",
                ),
                WeightedScore(
                    self._upper_is_better(features.harmonic_variation, low=0.12, high=0.38),
                    0.13,
                    "irregular side-lobed harmonic spacing",
                ),
                WeightedScore(
                    self._upper_is_better(features.spectral_roughness, low=0.25, high=0.65),
                    0.09,
                    "metallic rough texture",
                ),
                WeightedScore(
                    self._lower_is_better(features.doppler_stability, low=0.10, high=0.55),
                    0.07,
                    "unstable F0/Doppler track",
                ),
            ]

        return common + [
            WeightedScore(
                0.0,
                1.0,
                "no dedicated profile rule",
            ),
        ]

    @staticmethod
    def _range_score(
        value: float,
        low: float,
        high: float,
        margin_ratio: float = 0.35,
    ) -> float:
        """Score value inside a target interval with soft margins."""

        if low <= value <= high:
            return 1.0
        width = max(high - low, 1e-9)
        margin = width * margin_ratio
        if value < low:
            return float(np.clip(1.0 - (low - value) / margin, 0.0, 1.0))
        return float(np.clip(1.0 - (value - high) / margin, 0.0, 1.0))

    @staticmethod
    def _target_score(value: float, target: float, width: float) -> float:
        """Score closeness to a target value."""

        if width <= 0:
            return 0.0
        return float(np.clip(1.0 - abs(value - target) / width, 0.0, 1.0))

    @staticmethod
    def _upper_is_better(value: float, low: float, high: float) -> float:
        """Score where higher values are better."""

        if value <= low:
            return 0.0
        if value >= high:
            return 1.0
        return float((value - low) / (high - low))

    @staticmethod
    def _lower_is_better(value: float, low: float, high: float) -> float:
        """Score where lower values are better."""

        if value <= low:
            return 1.0
        if value >= high:
            return 0.0
        return float(1.0 - (value - low) / (high - low))

    @staticmethod
    def _label_score(actual: str, expected: str) -> float:
        """Score ordered labels low/medium/high."""

        order = {"low": 0, "medium": 1, "high": 2}
        if actual == expected:
            return 1.0
        distance = abs(order.get(actual, 1) - order.get(expected, 1))
        return 0.55 if distance == 1 else 0.15

    @staticmethod
    def _explain(
        features: AudioFeatureSet,
        scores: list[ClassificationScore],
        best_match: str,
        confidence: float,
    ) -> str:
        """Build a concise human explanation in Russian."""

        if best_match == "UNKNOWN":
            return (
                "Сигнал содержит признаки акустики БПЛА, но совпадение с "
                f"известными профилями недостаточно уверенное ({confidence:.0%}). "
                "Рекомендуется расширить базу профилей или проверить качество записи."
            )

        top = scores[0]
        reason_text = "; ".join(top.reasons[:4]) if top.reasons else "совокупность признаков"
        return (
            f"Наиболее вероятный тип: {best_match}. Основание: F0 "
            f"{features.fundamental_hz:.1f} Гц, гармоник {features.harmonic_count}, "
            f"стабильность {features.harmonic_stability:.2f}, шум 6-10 кГц "
            f"{features.high_band_energy_label}. Правила: {reason_text}."
        )


class AcousticPassportBuilder:
    """Build a compact acoustic passport from features and classification."""

    def build(
        self,
        features: AudioFeatureSet,
        classification: ClassificationResult,
    ) -> AcousticPassport:
        """Return a human-readable acoustic passport."""

        modulation = self._modulation_label(features.frequency_modulation_index)
        doppler = self._doppler_label(features.doppler_stability)
        notes = [
            f"Spectral centroid: {features.spectral_centroid_hz:.1f} Hz",
            f"Spectral roughness: {features.spectral_roughness:.2f}",
            f"High-band energy ratio: {features.high_band_energy_6_10khz:.3f}",
        ]
        return AcousticPassport(
            drone_type=classification.best_match,
            fundamental_hz=round(features.fundamental_hz, 2),
            harmonic_count=features.harmonic_count,
            harmonic_step_hz=round(features.harmonic_step_hz, 2),
            stability=round(features.harmonic_stability, 3),
            high_band_noise=features.high_band_energy_label,
            frequency_modulation=modulation,
            doppler=doppler,
            probability_percent=round(classification.confidence * 100.0, 1),
            notes=notes,
        )

    @staticmethod
    def _modulation_label(value: float) -> str:
        """Label frequency modulation strength."""

        if value >= 0.55:
            return "high"
        if value >= 0.25:
            return "medium"
        return "low"

    @staticmethod
    def _doppler_label(value: float) -> str:
        """Label Doppler/F0 stability."""

        if value >= 0.80:
            return "stable"
        if value >= 0.50:
            return "variable"
        return "unstable"

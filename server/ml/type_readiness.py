"""Dataset readiness gates for UAV type classification.

The classifier may learn from provisional and weak labels, but an operational
identity lock needs independent, confirmed and validation-eligible sources for
*every* class participating in the contrast.  This module keeps that policy
separate from acoustic similarity so missing ground truth can never be hidden by
lowering a confidence threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import pandas as pd


@dataclass(frozen=True, slots=True)
class LabelReadiness:
    label: str
    total_sources: int
    confirmed_sources: int
    weak_sources: int
    validation_sources: int
    representative_sources: int


@dataclass(frozen=True, slots=True)
class TypeReadiness:
    labels: tuple[LabelReadiness, ...]
    research_ready: bool
    confirmed_contrast_ready: bool
    operational_validation_ready: bool
    mode: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "labels": [asdict(item) for item in self.labels],
            "research_ready": self.research_ready,
            "confirmed_contrast_ready": self.confirmed_contrast_ready,
            "operational_validation_ready": self.operational_validation_ready,
            "mode": self.mode,
            "reason": self.reason,
        }


def _first(group: pd.DataFrame, name: str, fallback: str) -> str:
    if name not in group.columns:
        return fallback
    values = group[name].dropna().astype(str).str.strip().str.lower()
    return str(values.iloc[0]) if not values.empty else fallback


def assess_type_readiness(
    frame: pd.DataFrame,
    target_labels: Iterable[str],
    *,
    min_confirmed_sources: int = 3,
    min_validation_sources: int = 3,
) -> TypeReadiness:
    """Assess whether type labels are suitable for research vs operational use."""

    labels: list[LabelReadiness] = []
    for label in target_labels:
        subset = frame[frame.get("label", pd.Series(dtype=str)).astype(str) == str(label)].copy()
        total = confirmed = weak = validation = representative = 0
        if not subset.empty and "source_file" in subset.columns:
            for _, group in subset.groupby("source_file", sort=False):
                total += 1
                role = _first(group, "meta_dataset_role", "training")
                default_conf = "weak" if role == "training_provisional_weak" else "confirmed"
                conf = _first(group, "meta_label_confidence", default_conf)
                eligible = _first(group, "meta_validation_eligible", "false") in {"1", "true", "yes"}
                if conf == "confirmed":
                    confirmed += 1
                else:
                    weak += 1
                if eligible:
                    validation += 1
                if conf == "confirmed" and role == "training" and eligible:
                    representative += 1
        labels.append(LabelReadiness(
            label=str(label),
            total_sources=total,
            confirmed_sources=confirmed,
            weak_sources=weak,
            validation_sources=validation,
            representative_sources=representative,
        ))

    research_ready = len(labels) >= 2 and all(item.total_sources >= 2 for item in labels)
    confirmed_ready = len(labels) >= 2 and all(item.confirmed_sources >= min_confirmed_sources for item in labels)
    validation_ready = len(labels) >= 2 and all(item.validation_sources >= min_validation_sources for item in labels)
    if validation_ready:
        mode = "operational_type_validation_ready"
        reason = "Every compared type has an independent validation set."
    elif confirmed_ready:
        mode = "confirmed_contrast_research_only"
        reason = "Confirmed contrast exists, but the representative validation freeze is incomplete."
    elif research_ready:
        mode = "weak_contrast_research_only"
        reason = "Type research is possible, but at least one compared class lacks enough confirmed independent sources."
    else:
        mode = "detection_only"
        reason = "There are not enough independent sources for a meaningful type contrast."
    return TypeReadiness(tuple(labels), research_ready, confirmed_ready, validation_ready, mode, reason)

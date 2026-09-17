"""Acoustic family taxonomy used by the v0.8 hierarchical classifier."""
from __future__ import annotations

from enum import StrEnum


class AcousticFamily(StrEnum):
    UNKNOWN = "UNKNOWN"
    PROP_PISTON = "PROP_PISTON"
    ROTOR_ELECTRIC = "ROTOR_ELECTRIC"
    TURBINE_JET = "TURBINE_JET"
    GROUND_ENGINE = "GROUND_ENGINE"
    BIOLOGICAL_BACKGROUND = "BIOLOGICAL_BACKGROUND"
    IMPULSE_BACKGROUND = "IMPULSE_BACKGROUND"


_LABEL_TO_FAMILY: dict[str, AcousticFamily] = {
    "Лютый": AcousticFamily.PROP_PISTON,
    "FP-1": AcousticFamily.PROP_PISTON,
    "DJI Mini 3 Pro": AcousticFamily.ROTOR_ELECTRIC,
    "трактор": AcousticFamily.GROUND_ENGINE,
    "городской транспорт": AcousticFamily.GROUND_ENGINE,
    "птицы": AcousticFamily.BIOLOGICAL_BACKGROUND,
    "цикады и насекомые": AcousticFamily.BIOLOGICAL_BACKGROUND,
    "природный фон": AcousticFamily.BIOLOGICAL_BACKGROUND,
    "стрельба": AcousticFamily.IMPULSE_BACKGROUND,
}

_UNKNOWN_UAV_BRANCH: dict[AcousticFamily, str] = {
    AcousticFamily.PROP_PISTON: "UNKNOWN_PROP_PISTON_UAV",
    AcousticFamily.ROTOR_ELECTRIC: "UNKNOWN_ROTOR_ELECTRIC_UAV",
    AcousticFamily.TURBINE_JET: "UNKNOWN_TURBINE_JET_UAV",
}


def family_for_label(label: str) -> AcousticFamily:
    """Return the family currently assigned to a dataset label."""

    return _LABEL_TO_FAMILY.get(str(label).strip(), AcousticFamily.UNKNOWN)


def known_family_labels() -> dict[str, str]:
    """Return a serializable copy for model metadata and audit."""

    return {label: family.value for label, family in _LABEL_TO_FAMILY.items()}


def hierarchical_label(family: str | AcousticFamily, specific_type: str = "UNKNOWN") -> str:
    """Preserve a known UAV family when the exact airframe type is unknown."""

    if str(specific_type).strip().upper() != "UNKNOWN":
        return str(specific_type)
    try:
        normalized = family if isinstance(family, AcousticFamily) else AcousticFamily(str(family))
    except ValueError:
        return "UNKNOWN"
    return _UNKNOWN_UAV_BRANCH.get(normalized, normalized.value)

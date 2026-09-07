"""Acoustic profile definitions for known drone classes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AcousticProfile:
    """Expert profile used by the rule-based classifier."""

    name: str
    display_name: str
    description: str
    fundamental_range_hz: tuple[float, float]
    harmonic_count_range: tuple[int, int] | None
    stability_range: tuple[float, float]
    high_band_noise: str | None
    modulation: str
    roughness: str


PROFILES: tuple[AcousticProfile, ...] = (
    AcousticProfile(
        name="GR2",
        display_name="GR2",
        description=(
            "Uneven mid-low rotor pattern with rattling harmonic structure and "
            "little high-frequency hiss."
        ),
        fundamental_range_hz=(80.0, 150.0),
        harmonic_count_range=(10, 15),
        stability_range=(0.45, 0.88),
        high_band_noise="low",
        modulation="medium",
        roughness="medium",
    ),
    AcousticProfile(
        name="FP1",
        display_name="FP-1 (тяж. поршневой)",
        description=(
            "High base frequency piston profile: metallic ringing, strong "
            "frequency modulation, blurred peaks with side lobes, low stability, "
            "and pop/crackle texture from propeller and exhaust interaction."
        ),
        fundamental_range_hz=(95.0, 165.0),
        harmonic_count_range=None,
        stability_range=(0.0, 0.65),
        high_band_noise=None,
        modulation="high",
        roughness="high",
    ),
)

PENDING_PROFILE_NAMES: tuple[str, ...] = ("Лютый (исследовательская гипотеза)",)

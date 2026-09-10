#!/usr/bin/env python3
"""Cross-check fail-closed RU868 candidate channels between config and firmware."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "config/lora/RU868.yaml"
SOURCE = ROOT / "firmware/src/zs_sx1262.c"

EXPECTED = [864100000, 864300000, 864500000, 864700000, 864900000, 868900000, 869100000]
FORBIDDEN_LEGACY = [868100000, 868300000, 868500000, 868700000]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def profile_channels(text: str) -> list[int]:
    block = text.split("candidate_channels_hz:", 1)[1].split("lorawan_mandatory_default_channels_hz:", 1)[0]
    return [int(value) for value in re.findall(r"(?m)^\s+-\s+(\d+)\s*$", block)]


def firmware_channels(text: str) -> list[int]:
    match = re.search(r"zs_ru868_candidate_channels_hz\[7\]\s*=\s*\{([^}]+)\}", text)
    require(match is not None, "firmware candidate-channel array missing")
    return [int(value) for value in re.findall(r"(\d+)u", match.group(1))]


def main() -> None:
    profile = PROFILE.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    require("tx_enabled: false" in profile, "RU868 must remain fail-closed")
    require("max_eirp_dbm: null" in profile and "duty_cycle: null" in profile,
            "unsigned power or duty-cycle value present")
    require(profile_channels(profile) == EXPECTED, "RU868 profile channel drift")
    require(firmware_channels(source) == EXPECTED, "firmware/profile channel mismatch")
    require("zs_sx1262_frequency_allowed_ru868" in source, "firmware frequency guard missing")
    require(all(str(value) not in source for value in FORBIDDEN_LEGACY),
            "legacy RU868 frequency remains in firmware")
    print("RU868 firmware/profile gate: PASS (7 candidates; legacy plan rejected; TX disabled)")


if __name__ == "__main__":
    main()

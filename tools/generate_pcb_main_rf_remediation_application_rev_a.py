#!/usr/bin/env python3
"""Compose the two independently accepted PCB-MAIN RF remediation deltas.

The cellular proposal adds one local GND_MODEM In1.Cu zone.  The GNSS
proposal moves only FL1/C64 and replaces only its controlled trace UUID set.
Both were reviewed against the same authoritative RF-P0 board.  This helper
proves that the operations commute over their disjoint fields and emits the
single deterministic board used for application and native-gate comparison.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import generate_pcb_main_gnss_rf_eco_001_candidate_rev_a as gnss
import generate_pcb_main_rf_return_001_candidate_rev_a as cellular


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001"
    / "PCB-MAIN_GNSS_RF_ECO_001_BASE_REV_A.kicad_pcb"
)
GNSS_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001"
    / "PCB-MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.kicad_pcb"
)
CELLULAR_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001"
    / "PCB-MAIN_RF_RETURN_CANDIDATE_REV_A.kicad_pcb"
)
DEFAULT_OUTPUT = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-REMEDIATION-APPLICATION-001"
    / "PCB-MAIN_RF_REMEDIATION_COMPOSED_REV_A.kicad_pcb"
)

BASE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
GNSS_CANDIDATE_SHA256 = "d4c0eaa95bb62c7b9ae15b110fb3a76e6a056f462f0a36a734b3fa63730d2aee"
CELLULAR_CANDIDATE_SHA256 = "22ddd8c56ceabf397ed033a44235b439625d3104fa2cf798bb57b782d24b1352"
COMPOSED_SHA256 = "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def composed_bytes() -> bytes:
    base = BASE.read_bytes()
    cellular_payload = CELLULAR_CANDIDATE.read_bytes()
    reviewed_gnss = GNSS_CANDIDATE.read_bytes()
    require(sha256_bytes(base) == BASE_SHA256, "reviewed RF base SHA-256 drift")
    require(
        sha256_bytes(cellular_payload) == CELLULAR_CANDIDATE_SHA256,
        "reviewed cellular candidate SHA-256 drift",
    )
    require(
        sha256_bytes(reviewed_gnss) == GNSS_CANDIDATE_SHA256,
        "reviewed GNSS candidate SHA-256 drift",
    )

    regenerated_gnss = gnss.candidate_bytes(base)
    require(
        regenerated_gnss == reviewed_gnss,
        "reviewed GNSS delta no longer regenerates the accepted candidate",
    )
    composed = gnss.candidate_bytes(cellular_payload)
    require(
        sha256_bytes(composed) == COMPOSED_SHA256,
        "composed RF-remediation SHA-256 drift",
    )

    zone = cellular.ZONE_BLOCK.encode("utf-8")
    require(composed.count(zone) == 1, "cellular L2 zone composition drift")
    require(
        composed.replace(zone, b"", 1) == reviewed_gnss,
        "removing the accepted cellular zone does not recover the exact GNSS candidate",
    )
    return composed


def generate(output: Path, check: bool) -> dict[str, object]:
    payload = composed_bytes()
    if check:
        require(output.is_file(), f"missing composed application board: {output}")
        require(output.read_bytes() == payload, "composed application board drift")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    return {
        "base_sha256": BASE_SHA256,
        "cellular_candidate_sha256": CELLULAR_CANDIDATE_SHA256,
        "gnss_candidate_sha256": GNSS_CANDIDATE_SHA256,
        "composed_sha256": COMPOSED_SHA256,
        "output": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
        "cellular_zone_preserved_exactly": True,
        "gnss_delta_regenerated_exactly": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(generate(args.output.resolve(), args.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

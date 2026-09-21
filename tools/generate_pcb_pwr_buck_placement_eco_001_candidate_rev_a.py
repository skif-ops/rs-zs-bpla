#!/usr/bin/env python3
"""Generate the bounded PCB-PWR dual-buck placement ECO-001 candidate.

The historical proposal moves only the two bootstrap capacitors and the two
inductors. It adds no copper and regenerates from the frozen reviewed base.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-PLACEMENT-ECO-001"
)
DEFAULT_BASE_OUTPUT = (
    CANDIDATE_DIR / "PCB-PWR_BUCK_PLACEMENT_ECO_001_BASE_REV_A.kicad_pcb"
)
DEFAULT_OUTPUT = (
    CANDIDATE_DIR / "PCB-PWR_BUCK_PLACEMENT_ECO_001_CANDIDATE_REV_A.kicad_pcb"
)
SOURCE = DEFAULT_BASE_OUTPUT

BASE_SHA256 = "fdd53e669a167df8925c38e289993c38b818c231eddd0be54de378b51538bf48"
CANDIDATE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"

# C4/C6 are placed immediately below the BOOT/SW edge of U3/U4 and rotated
# so pad 1 (BOOT) faces pin 4 while pad 2 (SW) faces pin 3.  L1/L2 are
# rotated so pad 1 (SW) faces the regulator and translated to the minimum
# conservative 0.25 mm fitted-courtyard gap from U3/U4.
PLACEMENT_REPLACEMENTS = {
    "C4": ("\t\t(at 53 10)", "\t\t(at 54.575 16.4 180)"),
    "C6": ("\t\t(at 53 38)", "\t\t(at 54.575 44.4 180)"),
    "L1": ("\t\t(at 62 14)", "\t\t(at 60.75 14 180)"),
    "L2": ("\t\t(at 62 42)", "\t\t(at 60.75 42 180)"),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def footprint_block(source: str, reference: str) -> tuple[int, int, str]:
    marker = f'(property "Reference" "{reference}"'
    require(source.count(marker) == 1,
            f"missing or duplicate footprint reference {reference}")
    marker_index = source.index(marker)
    start = source.rfind("\n\t(footprint ", 0, marker_index)
    require(start >= 0, f"cannot locate start of footprint {reference}")
    start += 1
    end = source.find("\n\t(footprint ", marker_index)
    if end < 0:
        end = source.find("\n\t(segment ", marker_index)
    if end < 0:
        end = source.find("\n\t(zone ", marker_index)
    if end < 0:
        end = source.find("\n\t(gr_", marker_index)
    require(end > start, f"cannot locate end of footprint {reference}")
    return start, end, source[start:end]


def move_footprint(source: str, reference: str, old: str, new: str) -> str:
    start, end, block = footprint_block(source, reference)
    require(block.count(old) == 1, f"{reference}: source placement drift")
    require(new not in block, f"{reference}: target placement already present")
    return source[:start] + block.replace(old, new) + source[end:]


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "historical PCB-PWR buck placement base SHA-256 drift")
    source = base_payload.decode("utf-8")
    for reference, (old, new) in PLACEMENT_REPLACEMENTS.items():
        source = move_footprint(source, reference, old, new)
    return source.encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    base_payload = SOURCE.read_bytes()
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "historical PCB-PWR buck placement base SHA-256 drift")
    candidate_payload = candidate_bytes(base_payload)
    require(candidate_payload != base_payload,
            "PCB-PWR buck placement candidate is unchanged")
    candidate_sha256 = sha256_bytes(candidate_payload)
    require(candidate_sha256 == CANDIDATE_SHA256,
            "PCB-PWR buck placement candidate SHA-256 drift")
    if check:
        require(base_output.read_bytes() == base_payload,
                "committed PCB-PWR buck placement base drift")
        require(output.read_bytes() == candidate_payload,
                "committed PCB-PWR buck placement candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(base_payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(candidate_payload)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha256,
        "moved_footprints": sorted(PLACEMENT_REPLACEMENTS),
        "copper_changed": False,
        "historical_candidate_regeneration": True,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-output", type=Path, default=DEFAULT_BASE_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(generate(args.base_output.resolve(), args.output.resolve(), args.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

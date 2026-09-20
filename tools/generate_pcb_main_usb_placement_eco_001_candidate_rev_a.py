#!/usr/bin/env python3
"""Generate the bounded PCB-MAIN USB source-termination placement ECO-001.

The proposal moves only the previously unrouted R91/R92 series terminations.
It does not add or remove copper and never modifies the authoritative PCB.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-PLACEMENT-ECO-001"
DEFAULT_BASE_OUTPUT = CANDIDATE_DIR / "PCB-MAIN_USB_PLACEMENT_ECO_001_BASE_REV_A.kicad_pcb"
DEFAULT_OUTPUT = CANDIDATE_DIR / "PCB-MAIN_USB_PLACEMENT_ECO_001_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA256 = "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9"

PLACEMENT_REPLACEMENTS = {
    "R91": ("    (at 49 18.25 180)", "    (at 64 25.25)"),
    "R92": ("    (at 55 18.25 180)", "    (at 64 26.25)"),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def footprint_block(source: str, reference: str) -> tuple[int, int, str]:
    marker = f'(fp_text reference "{reference}" '
    require(source.count(marker) == 1, f"missing or duplicate footprint {reference}")
    marker_index = source.index(marker)
    start = source.rfind("\n  (footprint ", 0, marker_index)
    require(start >= 0, f"cannot locate start of footprint {reference}")
    start += 1
    end = source.find("\n  (footprint ", marker_index)
    if end < 0:
        end = source.find("\n  (segment ", marker_index)
    require(end > start, f"cannot locate end of footprint {reference}")
    return start, end, source[start:end]


def move_footprint(source: str, reference: str, old: str, new: str) -> str:
    start, end, block = footprint_block(source, reference)
    require(block.count(old) == 1, f"{reference}: source placement drift")
    require(new not in block, f"{reference}: target placement already present")
    return source[:start] + block.replace(old, new) + source[end:]


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative PCB-MAIN SHA-256 drift")
    source = base_payload.decode("utf-8")
    for reference, (old, new) in PLACEMENT_REPLACEMENTS.items():
        source = move_footprint(source, reference, old, new)
    return source.encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    base_payload = BASE.read_bytes()
    candidate_payload = candidate_bytes(base_payload)
    require(candidate_payload != base_payload, "USB placement ECO candidate is unchanged")
    if check:
        require(base_output.read_bytes() == base_payload, "committed USB ECO base drift")
        require(output.read_bytes() == candidate_payload, "committed USB ECO candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(base_payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(candidate_payload)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": sha256_bytes(candidate_payload),
        "moved_footprints": sorted(PLACEMENT_REPLACEMENTS),
        "copper_changed": False,
        "authoritative_board_modified": False,
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

#!/usr/bin/env python3
"""Generate the bounded PCB-PWR buck warning-remediation candidate.

The proposal starts from the accepted and applied buck-placement ECO-001 board.
It canonicalizes only the rotated C4/C6 instance data that KiCad 9 compares
against the system footprint library, retains the original physical C4/C6
reference centres, and moves only the visible R10 reference field away from the
L2 pin-1 silkscreen marker and solder-mask openings. Component poses, copper
geometry, nets, outline, tracks, vias, and zones are unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-WARNING-REMEDIATION-001"
)
DEFAULT_BASE_OUTPUT = (
    CANDIDATE_DIR
    / "PCB-PWR_BUCK_WARNING_REMEDIATION_001_BASE_REV_A.kicad_pcb"
)
DEFAULT_OUTPUT = (
    CANDIDATE_DIR
    / "PCB-PWR_BUCK_WARNING_REMEDIATION_001_CANDIDATE_REV_A.kicad_pcb"
)
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"

BASE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"
CANDIDATE_SHA256 = "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"


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
        for token in ("\n\t(segment ", "\n\t(zone ", "\n\t(gr_"):
            end = source.find(token, marker_index)
            if end >= 0:
                break
    require(end > start, f"cannot locate end of footprint {reference}")
    return start, end, source[start:end]


def replace_count(block: str, old: str, new: str, count: int,
                  reference: str) -> str:
    require(block.count(old) == count,
            f"{reference}: expected {count} occurrences of {old!r}")
    require(new not in block,
            f"{reference}: target representation is already present")
    return block.replace(old, new)


def normalize_rotated_capacitor(source: str, reference: str) -> str:
    start, end, block = footprint_block(source, reference)
    block = replace_count(
        block,
        "\t\t\t(at 0 -1.4 0)",
        "\t\t\t(at 0 -1.4 180)",
        1,
        reference,
    )
    block = replace_count(
        block,
        "\t\t\t(at 0 1.16 0)",
        "\t\t\t(at 0 1.16 180)",
        1,
        reference,
    )
    block = replace_count(
        block,
        "\t\t\t(at 0 0 0)",
        "\t\t\t(at 0 0 180)",
        3,
        reference,
    )
    block = replace_count(
        block,
        "\t\t\t(at -0.48 0)",
        "\t\t\t(at -0.48 0 180)",
        1,
        reference,
    )
    block = replace_count(
        block,
        "\t\t\t(at 0.48 0)",
        "\t\t\t(at 0.48 0 180)",
        1,
        reference,
    )
    return source[:start] + block + source[end:]


def move_r10_reference(source: str) -> str:
    reference = "R10"
    start, end, block = footprint_block(source, reference)
    block = replace_count(
        block,
        "\t\t\t(at 0 -1.4 0)",
        "\t\t\t(at 0 1.4 0)",
        1,
        reference,
    )
    return source[:start] + block + source[end:]


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "PCB-PWR warning-remediation base SHA-256 drift")
    source = base_payload.decode("utf-8")
    for reference in ("C4", "C6"):
        source = normalize_rotated_capacitor(source, reference)
    source = move_r10_reference(source)
    return source.encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    base_payload = SOURCE.read_bytes()
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative PCB-PWR warning-remediation base drift")
    candidate_payload = candidate_bytes(base_payload)
    require(candidate_payload != base_payload,
            "PCB-PWR warning-remediation candidate is unchanged")
    candidate_sha256 = sha256_bytes(candidate_payload)
    if CANDIDATE_SHA256 != "TO_BE_FROZEN":
        require(candidate_sha256 == CANDIDATE_SHA256,
                "PCB-PWR warning-remediation candidate SHA-256 drift")
    if check:
        require(base_output.read_bytes() == base_payload,
                "committed PCB-PWR warning-remediation base drift")
        require(output.read_bytes() == candidate_payload,
                "committed PCB-PWR warning-remediation candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(base_payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(candidate_payload)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha256,
        "normalized_instances": ["C4", "C6"],
        "moved_reference_fields": ["R10"],
        "component_poses_changed": False,
        "copper_geometry_changed": False,
        "routing_complete": False,
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

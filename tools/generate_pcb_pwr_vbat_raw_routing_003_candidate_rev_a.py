#!/usr/bin/env python3
"""Generate isolated PCB-PWR VBAT_RAW routing candidate 003."""

from __future__ import annotations

import argparse
import hashlib
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003"
DEFAULT_BASE_OUTPUT = CANDIDATE_DIR / "PCB-PWR_VBAT_RAW_ROUTING_003_BASE_REV_A.kicad_pcb"
DEFAULT_OUTPUT = CANDIDATE_DIR / "PCB-PWR_VBAT_RAW_ROUTING_003_CANDIDATE_REV_A.kicad_pcb"

BASE_SHA256 = "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
CANDIDATE_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
TRACE_WIDTH_MM = 4.0
NET_NAME = "VBAT_RAW"
START = (7.7, 31.25)
END = (10.6, 31.25)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative PCB-PWR candidate-003 base SHA-256 drift")
    source = base_payload.decode("utf-8")
    found = re.search(r'^\s*\(net (\d+) "VBAT_RAW"\)$', source, re.M)
    require(found is not None, "VBAT_RAW net identity drift")
    route_uuid = uuid.uuid5(
        uuid.NAMESPACE_URL,
        "dioneya:pcb-pwr:routing-candidate-003:VBAT_RAW:J1.1-F1.1",
    )
    segment = (
        "\t(segment\n"
        f"\t\t(start {number(START[0])} {number(START[1])})\n"
        f"\t\t(end {number(END[0])} {number(END[1])})\n"
        f"\t\t(width {number(TRACE_WIDTH_MM)})\n"
        "\t\t(layer \"F.Cu\")\n"
        f"\t\t(net {found.group(1)})\n"
        f"\t\t(uuid \"{route_uuid}\")\n"
        "\t)"
    )
    marker = "\n\t(embedded_fonts no)"
    require(source.count(marker) == 1, "cannot locate PCB insertion boundary")
    return source.replace(marker, "\n" + segment + marker, 1).encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    base_payload = SOURCE.read_bytes()
    candidate_payload = candidate_bytes(base_payload)
    candidate_sha256 = sha256_bytes(candidate_payload)
    if not CANDIDATE_SHA256.startswith("TO_BE_"):
        require(candidate_sha256 == CANDIDATE_SHA256,
                "PCB-PWR routing candidate 003 SHA-256 drift")
    else:
        require(not check, "candidate SHA-256 has not been bound")
    if check:
        require(base_output.read_bytes() == base_payload, "committed base drift")
        require(output.read_bytes() == candidate_payload, "committed candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(base_payload)
        output.write_bytes(candidate_payload)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha256,
        "routed_net": NET_NAME,
        "connection": "J1.1-F1.1",
        "added_segments": 1,
        "trace_width_mm": TRACE_WIDTH_MM,
        "vias_added": 0,
        "authoritative_board_modified": False,
        "routing_complete": False,
        "review_b_complete": False,
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

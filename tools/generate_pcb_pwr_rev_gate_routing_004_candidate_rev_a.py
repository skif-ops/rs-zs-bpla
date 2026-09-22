#!/usr/bin/env python3
"""Generate isolated PCB-PWR REV_GATE routing candidate 004."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-REV-GATE-ROUTING-004"
DEFAULT_BASE_OUTPUT = CANDIDATE_DIR / "PCB-PWR_REV_GATE_ROUTING_004_BASE_REV_A.kicad_pcb"
DEFAULT_OUTPUT = CANDIDATE_DIR / "PCB-PWR_REV_GATE_ROUTING_004_CANDIDATE_REV_A.kicad_pcb"

BASE_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
CANDIDATE_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
TRACE_WIDTH_MM = 0.5
NET_NAME = "REV_GATE"
POINTS = (
    (21.3, 30.0),
    (22.6, 30.0),
    (22.6, 27.0),
    (29.77, 27.0),
    (29.77, 28.095),
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative PCB-PWR candidate-004 base SHA-256 drift")
    source = base_payload.decode("utf-8")
    found = re.search(r'^\s*\(net (\d+) "REV_GATE"\)$', source, re.M)
    require(found is not None, "REV_GATE net identity drift")
    segments: list[str] = []
    for index, (start, end) in enumerate(zip(POINTS, POINTS[1:]), start=1):
        route_uuid = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"dioneya:pcb-pwr:routing-candidate-004:REV_GATE:U1.5-Q1.4:{index}",
        )
        segments.append(
            "\t(segment\n"
            f"\t\t(start {number(start[0])} {number(start[1])})\n"
            f"\t\t(end {number(end[0])} {number(end[1])})\n"
            f"\t\t(width {number(TRACE_WIDTH_MM)})\n"
            "\t\t(layer \"F.Cu\")\n"
            f"\t\t(net {found.group(1)})\n"
            f"\t\t(uuid \"{route_uuid}\")\n"
            "\t)"
        )
    marker = "\n\t(embedded_fonts no)"
    require(source.count(marker) == 1, "cannot locate PCB insertion boundary")
    return source.replace(marker, "\n" + "\n".join(segments) + marker, 1).encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    source_payload = SOURCE.read_bytes()
    source_sha256 = sha256_bytes(source_payload)
    require(source_sha256 in {BASE_SHA256, CANDIDATE_SHA256},
            "authoritative PCB-PWR is not a controlled candidate-004 successor")
    base_payload = (source_payload if source_sha256 == BASE_SHA256
                    else base_output.read_bytes())
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "committed candidate-004 base SHA-256 drift")
    candidate_payload = candidate_bytes(base_payload)
    candidate_sha256 = sha256_bytes(candidate_payload)
    if not CANDIDATE_SHA256.startswith("TO_BE_"):
        require(candidate_sha256 == CANDIDATE_SHA256,
                "PCB-PWR routing candidate 004 SHA-256 drift")
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
        "connection": "U1.5-Q1.4",
        "added_segments": len(POINTS) - 1,
        "route_length_mm": sum(math.dist(first, second)
                               for first, second in zip(POINTS, POINTS[1:])),
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

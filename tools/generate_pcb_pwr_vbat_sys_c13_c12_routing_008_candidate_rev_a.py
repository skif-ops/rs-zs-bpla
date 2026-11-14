#!/usr/bin/env python3
"""Generate isolated C13.1-to-C12.1 VBAT_SYS candidate 008; never edit PCB-PWR."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
DIRECTORY = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-C13-C12-ROUTING-008"
BASE = DIRECTORY / "PCB-PWR_VBAT_SYS_C13_C12_ROUTING_008_BASE_REV_A.kicad_pcb"
CANDIDATE = DIRECTORY / "PCB-PWR_VBAT_SYS_C13_C12_ROUTING_008_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA256 = "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"

# C13 is the central input bulk capacitor and C12 is the local input capacitor
# for the lower buck. Keep the entire branch on F.Cu at the controlled 3.0 mm
# 4 A width. The first segment leaves C13 vertically in the empty lower corridor;
# the second enters C12.1 horizontally with 0.875 mm screened clearance to C12.2.
ROUTES = (
    ((44.0, 31.8), (44.0, 42.0), 3.0),
    ((44.0, 42.0), (47.525, 42.0), 3.0),
)


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def generate(base: Path = BASE, candidate: Path = CANDIDATE, check: bool = False) -> dict:
    payload = SOURCE.read_bytes()
    if sha(payload) != BASE_SHA256:
        raise AssertionError("PCB-PWR authoritative predecessor drift")
    source = payload.decode("utf-8")
    match = re.search(r'^\s*\(net (\d+) "VBAT_SYS"\)$', source, re.M)
    if match is None:
        raise AssertionError("VBAT_SYS net identity drift")
    segments = []
    for index, (start, end, width) in enumerate(ROUTES, 1):
        route_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"dioneya:pcb-pwr:008:c13-c12:{index}")
        segments.append(
            "\t(segment\n"
            f"\t\t(start {start[0]:g} {start[1]:g})\n"
            f"\t\t(end {end[0]:g} {end[1]:g})\n"
            f"\t\t(width {width:g})\n"
            "\t\t(layer \"F.Cu\")\n"
            f"\t\t(net {match.group(1)})\n"
            f"\t\t(uuid \"{route_uuid}\")\n"
            "\t)"
        )
    marker = "\n\t(embedded_fonts no)"
    if source.count(marker) != 1:
        raise AssertionError("PCB insertion point drift")
    output = source.replace(marker, "\n" + "\n".join(segments) + marker, 1).encode("utf-8")
    if check:
        if base.read_bytes() != payload or candidate.read_bytes() != output:
            raise AssertionError("committed candidate 008 or base drift")
    else:
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_bytes(payload)
        candidate.write_bytes(output)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": sha(output),
        "added_segments": len(ROUTES),
        "added_vias": 0,
        "added_zones": 0,
        "route_length_mm": sum(math.dist(start, end) for start, end, _ in ROUTES),
        "authoritative_board_modified": False,
        "routing_complete": False,
        "manufacturing_release": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(generate(check=args.check))

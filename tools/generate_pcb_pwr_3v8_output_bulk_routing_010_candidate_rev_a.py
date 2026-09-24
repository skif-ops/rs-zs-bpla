#!/usr/bin/env python3
"""Generate isolated L1-to-output-capacitor 3V8_MODEM candidate 010."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
DIRECTORY = ROOT / "hardware/kicad/candidates/PCB-PWR-3V8-OUTPUT-BULK-ROUTING-010"
BASE = DIRECTORY / "PCB-PWR_3V8_OUTPUT_BULK_ROUTING_010_BASE_REV_A.kicad_pcb"
CANDIDATE = DIRECTORY / "PCB-PWR_3V8_OUTPUT_BULK_ROUTING_010_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA256 = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"

# Two compact 3.0 mm F.Cu branches leave the tall L1.2 pad. The upper and
# lower capacitor pairs are joined outside their intervening GND_PWR pads.
ROUTES = (
    ((64.76, 12.0), (67.525, 10.0), 3.0),
    ((64.76, 17.0), (67.525, 17.0), 3.0),
    ((67.525, 10.0), (67.525, 6.8), 3.0),
    ((67.525, 6.8), (72.525, 6.8), 3.0),
    ((72.525, 6.8), (72.525, 7.4), 3.0),
    ((72.525, 7.4), (72.525, 10.0), 0.5),
    ((67.525, 17.0), (67.525, 20.2), 3.0),
    ((67.525, 20.2), (72.525, 20.2), 3.0),
    ((72.525, 20.2), (72.525, 19.6), 3.0),
    ((72.525, 19.6), (72.525, 17.0), 0.5),
)


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def generate(base: Path = BASE, candidate: Path = CANDIDATE, check: bool = False) -> dict:
    payload = SOURCE.read_bytes()
    if sha(payload) != BASE_SHA256:
        raise AssertionError("PCB-PWR authoritative predecessor drift")
    source = payload.decode("utf-8")
    match = re.search(r'^\s*\(net (\d+) "3V8_MODEM"\)$', source, re.M)
    if match is None:
        raise AssertionError("3V8_MODEM net identity drift")
    segments = []
    for index, (start, end, width) in enumerate(ROUTES, 1):
        route_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"dioneya:pcb-pwr:010:3v8-output-bulk:{index}")
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
            raise AssertionError("committed candidate 010 or base drift")
    else:
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_bytes(payload)
        candidate.write_bytes(output)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": sha(output),
        "routed_net": "3V8_MODEM",
        "connections": ["L1.2-C3.1-C14.1-C15.1-C16.1"],
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

#!/usr/bin/env python3
"""Generate the isolated RSH1.2 to C13.1 VBAT_SYS candidate; never edit PCB-PWR."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
DIRECTORY = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-SHUNT-BULK-ROUTING-007"
BASE = DIRECTORY / "PCB-PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_BASE_REV_A.kicad_pcb"
CANDIDATE = DIRECTORY / "PCB-PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA256 = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"

# Kelvin pickup RSH1.4 occupies x38.93..40.63, y29.35..30.11. A broad
# 4 mm track directly out of RSH1.2 would short it. Begin at the shunt load
# pad with a short narrow pad escape and widen only beyond its Kelvin contact.
# C13.1 is the central bulk capacitor; the two buck CIN branches are deferred.
ROUTES = (
    ((40.0, 31.8), (43.0, 31.8), 1.0),
    ((43.0, 31.8), (44.0, 31.8), 4.0),
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
        route_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"dioneya:pcb-pwr:007:shunt-bulk:{index}")
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
            raise AssertionError("committed candidate 007 or base drift")
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
        "pad_escape_length_mm": math.dist(*ROUTES[0][:2]),
        "authoritative_board_modified": False,
        "routing_complete": False,
        "manufacturing_release": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(generate(check=args.check))

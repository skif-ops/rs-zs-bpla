#!/usr/bin/env python3
"""Generate isolated PCB-PWR dual buck switch-node routing candidate 005."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-SWITCH-NODE-ROUTING-005"
)
DEFAULT_BASE_OUTPUT = (
    CANDIDATE_DIR / "PCB-PWR_BUCK_SWITCH_NODE_ROUTING_005_BASE_REV_A.kicad_pcb"
)
DEFAULT_OUTPUT = (
    CANDIDATE_DIR / "PCB-PWR_BUCK_SWITCH_NODE_ROUTING_005_CANDIDATE_REV_A.kicad_pcb"
)

BASE_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
CANDIDATE_SHA256 = "5d135a38774c4e223c1db8d6a3fc0e8c9c492fe3ba24f5e2ec4c1b00ab2166d7"

# Each route starts at the controller SW pad, touches the bootstrap-capacitor SW
# pad, escapes the pad-limited corridor at 0.5 mm and then expands explicitly to
# the controlled 2.1 mm local switch-node body before entering the inductor pad.
# The 0.5 mm exit is the maximum width that retains the 0.4 mm switch-node
# separation from the adjacent exposed GND and BOOT copper at the QFN edge.
ROUTES = {
    "SW_3V8": {
        "connection": "U3.3-C4.2-L1.1",
        "segments": (
            ((53.900, 14.928), (53.550, 15.550), 0.5),
            ((53.550, 15.550), (54.095, 16.400), 0.5),
            ((54.095, 16.400), (54.095, 17.450), 0.5),
            ((54.095, 17.450), (55.900, 17.450), 0.5),
            ((55.900, 17.450), (56.250, 17.450), 1.0),
            ((56.250, 17.450), (56.800, 16.800), 1.5),
            ((56.800, 16.800), (58.490, 16.800), 2.1),
        ),
    },
    "SW_3V3": {
        "connection": "U4.3-C6.2-L2.1",
        "segments": (
            ((53.900, 42.928), (53.550, 43.550), 0.5),
            ((53.550, 43.550), (54.095, 44.400), 0.5),
            ((54.095, 44.400), (54.095, 45.450), 0.5),
            ((54.095, 45.450), (55.900, 45.450), 0.5),
            ((55.900, 45.450), (56.250, 45.450), 1.0),
            ((56.250, 45.450), (56.800, 44.800), 1.5),
            ((56.800, 44.800), (58.490, 44.800), 2.1),
        ),
    },
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def candidate_bytes(base_payload: bytes) -> bytes:
    require(
        sha256_bytes(base_payload) == BASE_SHA256,
        "authoritative PCB-PWR candidate-005 base SHA-256 drift",
    )
    source = base_payload.decode("utf-8")
    segments: list[str] = []
    for net_name, route in ROUTES.items():
        found = re.search(rf'^\s*\(net (\d+) "{net_name}"\)$', source, re.M)
        require(found is not None, f"{net_name} net identity drift")
        for index, (start, end, width) in enumerate(route["segments"], start=1):
            route_uuid = uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    "dioneya:pcb-pwr:routing-candidate-005:"
                    f"{net_name}:{route['connection']}:{index}"
                ),
            )
            segments.append(
                "\t(segment\n"
                f"\t\t(start {number(start[0])} {number(start[1])})\n"
                f"\t\t(end {number(end[0])} {number(end[1])})\n"
                f"\t\t(width {number(width)})\n"
                "\t\t(layer \"F.Cu\")\n"
                f"\t\t(net {found.group(1)})\n"
                f"\t\t(uuid \"{route_uuid}\")\n"
                "\t)"
            )
    marker = "\n\t(embedded_fonts no)"
    require(source.count(marker) == 1, "cannot locate PCB insertion boundary")
    return source.replace(marker, "\n" + "\n".join(segments) + marker, 1).encode(
        "utf-8"
    )


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    source_payload = SOURCE.read_bytes()
    source_sha256 = sha256_bytes(source_payload)
    require(
        source_sha256 in {BASE_SHA256, CANDIDATE_SHA256},
        "authoritative PCB-PWR is not a controlled candidate-005 successor",
    )
    base_payload = (
        source_payload if source_sha256 == BASE_SHA256 else base_output.read_bytes()
    )
    require(
        sha256_bytes(base_payload) == BASE_SHA256,
        "committed candidate-005 base SHA-256 drift",
    )
    candidate_payload = candidate_bytes(base_payload)
    candidate_sha256 = sha256_bytes(candidate_payload)
    if CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(
            candidate_sha256 == CANDIDATE_SHA256,
            "PCB-PWR routing candidate 005 SHA-256 drift",
        )
    else:
        require(not check, "candidate SHA-256 has not been bound")
    if check:
        require(base_output.read_bytes() == base_payload, "committed base drift")
        require(output.read_bytes() == candidate_payload, "committed candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(base_payload)
        output.write_bytes(candidate_payload)

    widths = [
        float(width)
        for route in ROUTES.values()
        for _start, _end, width in route["segments"]
    ]
    route_lengths = {
        net_name: sum(
            math.dist(start, end) for start, end, _width in route["segments"]
        )
        for net_name, route in ROUTES.items()
    }
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha256,
        "routed_nets": list(ROUTES),
        "connections": [str(route["connection"]) for route in ROUTES.values()],
        "added_segments": sum(len(route["segments"]) for route in ROUTES.values()),
        "route_lengths_mm": route_lengths,
        "widths_mm": sorted(set(widths)),
        "full_width_mm": 2.1,
        "explicit_pad_entry_neckdown_mm": 0.5,
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

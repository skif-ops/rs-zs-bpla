#!/usr/bin/env python3
"""Generate the bounded PCB-MAIN cellular USB fixture-routing candidate.

The proposal connects R39/R40 pad 2 and U26 pads 1/2 to TP_CELL_USB pads
2/3.  Local launches are on F.Cu, each signal changes layer exactly once,
and the length-matched trunk runs on B.Cu over the accepted GND_MODEM In4.Cu
reference zone.  The authoritative board is never modified by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import uuid
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")) if str(ROOT / "tools") not in sys.path else None
import pcb_main_lineage_rev_a as _lineage  # noqa: E402  (PCB-MAIN 003: earlier sub-gates read the predecessor)
SOURCE = _lineage.historical_board()
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001"
)
DEFAULT_BASE_OUTPUT = (
    CANDIDATE_DIR / "PCB-MAIN_USB_CELL_FIXTURE_BASE_REV_A.kicad_pcb"
)
DEFAULT_OUTPUT = (
    CANDIDATE_DIR / "PCB-MAIN_USB_CELL_FIXTURE_CANDIDATE_REV_A.kicad_pcb"
)

BASE_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
# Filled after the first deterministic materialization and then enforced.
CANDIDATE_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
TRACE_WIDTH_MM = 0.1537
PAIR_GAP_MM = 0.2032
VIA_SIZE_MM = 0.5
VIA_DRILL_MM = 0.3

DM_VIA_Y = 51.85 + math.sqrt(0.625)
DP_TUNING_X = 10.572249357621711

# Each local F.Cu route is a tree expressed as a three-segment walk: the first
# two segments form the primary R-to-via path and the last segment is the short
# ESD shunt to U26.  Both ESD shunts are exactly length matched.
F_ROUTES: dict[str, tuple[tuple[float, float], ...]] = {
    "CELL_USB_DP_TP": (
        (9.675, 50.75),
        (9.675, 50.15),
        (8.2, 50.15),
        (8.075, 51.15),
    ),
    "CELL_USB_DM_TP": (
        (9.675, 52.0),
        (9.675, DM_VIA_Y),
        (8.7, DM_VIA_Y),
        (8.075, 51.85),
    ),
}

# The long B.Cu pair uses public engineering width/gap.  The DP rectangular
# excursion between y=36 and y=32 compensates the fixture fanout and makes the
# complete R39/R40-to-pogo primary paths exactly equal.
B_ROUTES: dict[str, tuple[tuple[float, float], ...]] = {
    "CELL_USB_DP_TP": (
        (8.2, 50.15),
        (6.7869, 50.0),
        (6.7869, 36.0),
        (DP_TUNING_X, 36.0),
        (DP_TUNING_X, 32.0),
        (6.7869, 32.0),
        (6.7869, 22.1569),
        (30.0, 22.1569),
        (30.0, 25.8569),
        (36.0, 25.8569),
        (36.5, 28.5),
        (35.539999, 30.0),
    ),
    "CELL_USB_DM_TP": (
        (8.7, DM_VIA_Y),
        (8.7, 53.2),
        (6.5, 53.2),
        (6.5, 50.446125),
        (6.43, 50.446125),
        (6.43, 21.8),
        (30.3569, 21.8),
        (30.3569, 25.5),
        (38.5, 25.5),
        (38.8, 28.5),
        (38.079999, 30.0),
    ),
}

VIAS = {
    "CELL_USB_DP_TP": (8.2, 50.15),
    "CELL_USB_DM_TP": (8.7, DM_VIA_Y),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def number(value: float) -> str:
    return f"{value:.15f}".rstrip("0").rstrip(".")


def item_uuid(kind: str, net_name: str, index: int) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"dioneya:pcb-main:usb-cell-fixture-routing-001:{kind}:{net_name}:{index}",
    ))


def net_codes(source: str) -> dict[str, int]:
    found = {
        name: int(code)
        for code, name in re.findall(r'^  \(net (\d+) "([^"]+)"\)$', source, re.M)
    }
    require(set(F_ROUTES) <= set(found), "cellular USB fixture net identity drift")
    return found


def added_lines(source: str) -> list[str]:
    codes = net_codes(source)
    lines: list[str] = []
    for layer, routes in (("F.Cu", F_ROUTES), ("B.Cu", B_ROUTES)):
        for net_name, points in routes.items():
            for index, (start, end) in enumerate(zip(points, points[1:]), 1):
                lines.append(
                    "  (segment "
                    f"(start {number(start[0])} {number(start[1])}) "
                    f"(end {number(end[0])} {number(end[1])}) "
                    f"(width {number(TRACE_WIDTH_MM)}) (layer \"{layer}\") "
                    f"(net {codes[net_name]}) "
                    f"(tstamp {item_uuid(layer, net_name, index)}))"
                )
    for index, (net_name, position) in enumerate(VIAS.items(), 1):
        lines.append(
            "  (via "
            f"(at {number(position[0])} {number(position[1])}) "
            f"(size {number(VIA_SIZE_MM)}) (drill {number(VIA_DRILL_MM)}) "
            "(layers \"F.Cu\" \"B.Cu\") "
            f"(net {codes[net_name]}) "
            f"(tstamp {item_uuid('via', net_name, index)}))"
        )
    return lines


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative cellular USB fixture-routing base SHA-256 drift")
    source = base_payload.decode("utf-8")
    marker = "\n  (zone "
    require(source.count(marker) >= 1, "cannot locate PCB zone insertion boundary")
    insertion = "\n" + "\n".join(added_lines(source))
    return source.replace(marker, insertion + marker, 1).encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    active_payload = SOURCE.read_bytes()
    active_sha256 = sha256_bytes(active_payload)
    if active_sha256 == BASE_SHA256:
        base_payload = active_payload
    else:
        require(active_sha256 == CANDIDATE_SHA256,
                "authoritative cellular USB fixture-routing lineage drift")
        base_payload = DEFAULT_BASE_OUTPUT.read_bytes()
        require(sha256_bytes(base_payload) == BASE_SHA256,
                "committed cellular USB fixture predecessor drift")
    candidate_payload = candidate_bytes(base_payload)
    candidate_sha256 = sha256_bytes(candidate_payload)
    if CANDIDATE_SHA256 != "TO_BE_MATERIALIZED":
        require(candidate_sha256 == CANDIDATE_SHA256,
                "cellular USB fixture candidate SHA-256 drift")
    require(candidate_payload != base_payload, "cellular USB fixture candidate is unchanged")
    if check:
        require(base_output.read_bytes() == base_payload,
                "committed cellular USB fixture base drift")
        require(output.read_bytes() == candidate_payload,
                "committed cellular USB fixture candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(base_payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(candidate_payload)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha256,
        "routed_nets": sorted(F_ROUTES),
        "added_segments": sum(len(points) - 1 for points in F_ROUTES.values())
        + sum(len(points) - 1 for points in B_ROUTES.values()),
        "added_signal_vias": len(VIAS),
        "trace_width_mm": TRACE_WIDTH_MM,
        "pair_gap_mm": PAIR_GAP_MM,
        "authoritative_board_modified": False,
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

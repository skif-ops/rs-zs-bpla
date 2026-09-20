#!/usr/bin/env python3
"""Generate the bounded PCB-MAIN USB MCU source-segment routing candidate.

The proposal connects only U1.71/U1.70 to R91.1/R92.1 on F.Cu using the
public JLC06161H-3313 engineering geometry.  One local GND_DIGITAL fanout via
and its attached segment are relocated because the accepted pre-route copper
occupies the only clearance-clean differential-pair channel.  The
authoritative PCB is never modified by this generator.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-SOURCE-ROUTING-001"
)
DEFAULT_BASE_OUTPUT = CANDIDATE_DIR / "PCB-MAIN_USB_SOURCE_BASE_REV_A.kicad_pcb"
DEFAULT_OUTPUT = CANDIDATE_DIR / "PCB-MAIN_USB_SOURCE_CANDIDATE_REV_A.kicad_pcb"

BASE_SHA256 = "d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e"
CANDIDATE_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
TRACE_WIDTH_MM = 0.1537
PAIR_GAP_MM = 0.2032

GROUND_SEGMENT_OLD = (
    '  (segment (start 62.1 27.225) (end 62.1 26.475) (width 0.15) '
    '(layer "F.Cu") (net 45) '
    '(tstamp fb9ade5d-8496-4617-9d20-390d44c347c4))'
)
GROUND_SEGMENT_NEW = (
    '  (segment (start 62.1 27.225) (end 62.5 26.75) (width 0.15) '
    '(layer "F.Cu") (net 45) '
    '(tstamp fb9ade5d-8496-4617-9d20-390d44c347c4))'
)
GROUND_VIA_OLD = (
    '  (via (at 62.1 26.475) (size 0.5) (drill 0.3) '
    '(layers "F.Cu" "B.Cu") (net 45) '
    '(tstamp bbd350c1-609d-43b7-9dd0-824ee009466f))'
)
GROUND_VIA_NEW = (
    '  (via (at 62.5 26.75) (size 0.5) (drill 0.3) '
    '(layers "F.Cu" "B.Cu") (net 45) '
    '(tstamp bbd350c1-609d-43b7-9dd0-824ee009466f))'
)

# The two polylines are exactly length matched.  Their long parallel section
# uses 0.1537 mm width and 0.2032 mm edge gap.  The small DM tuning chevron is
# confined to the clearance-clean area between the accepted C12/R3 fanouts.
ROUTES: dict[str, tuple[tuple[float, float], ...]] = {
    "USB_DP_U1": (
        (59.75, 26.0),
        (60.7, 26.0),
        (61.2, 25.85),
        (63.0, 25.85),
        (63.45, 25.4),
        (63.675, 25.25),
    ),
    "USB_DM_U1": (
        (59.75, 26.5),
        (60.7, 26.5),
        (61.2, 26.35),
        (61.6, 26.2069),
        (61.7, 26.2069),
        (61.95, 26.454798070497958),
        (62.2, 26.2069),
        (63.35, 26.2069),
        (63.675, 26.25),
    ),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def number(value: float) -> str:
    return f"{value:.15f}".rstrip("0").rstrip(".")


def route_uuid(net_name: str, index: int) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"dioneya:pcb-main:usb-source-routing-001:{net_name}:{index}",
    ))


def net_codes(source: str) -> dict[str, int]:
    found = {
        name: int(code)
        for code, name in re.findall(r'^  \(net (\d+) "([^"]+)"\)$', source, re.M)
    }
    require(set(ROUTES) <= set(found), "USB source net identity drift")
    return found


def segment_lines(source: str) -> list[str]:
    codes = net_codes(source)
    lines: list[str] = []
    for net_name, points in ROUTES.items():
        for index, (start, end) in enumerate(zip(points, points[1:]), 1):
            lines.append(
                "  (segment "
                f"(start {number(start[0])} {number(start[1])}) "
                f"(end {number(end[0])} {number(end[1])}) "
                f"(width {number(TRACE_WIDTH_MM)}) (layer \"F.Cu\") "
                f"(net {codes[net_name]}) "
                f"(tstamp {route_uuid(net_name, index)}))"
            )
    return lines


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative USB source-routing base SHA-256 drift")
    source = base_payload.decode("utf-8")
    require(source.count(GROUND_SEGMENT_OLD) == 1,
            "local GND_DIGITAL fanout segment identity drift")
    require(source.count(GROUND_VIA_OLD) == 1,
            "local GND_DIGITAL fanout via identity drift")
    source = source.replace(GROUND_SEGMENT_OLD, GROUND_SEGMENT_NEW)
    source = source.replace(GROUND_VIA_OLD, GROUND_VIA_NEW)
    marker = "\n  (zone "
    require(source.count(marker) >= 1, "cannot locate PCB zone insertion boundary")
    insertion = "\n" + "\n".join(segment_lines(source))
    source = source.replace(marker, insertion + marker, 1)
    return source.encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    active_payload = SOURCE.read_bytes()
    active_sha256 = sha256_bytes(active_payload)
    if active_sha256 == BASE_SHA256:
        base_payload = active_payload
    else:
        require(active_sha256 == CANDIDATE_SHA256,
                "authoritative USB source-routing lineage drift")
        base_payload = DEFAULT_BASE_OUTPUT.read_bytes()
        require(sha256_bytes(base_payload) == BASE_SHA256,
                "committed USB source-routing base SHA-256 drift")
    candidate_payload = candidate_bytes(base_payload)
    require(sha256_bytes(candidate_payload) == CANDIDATE_SHA256,
            "USB source candidate SHA-256 drift")
    require(candidate_payload != base_payload, "USB source candidate is unchanged")
    if check:
        require(base_output.read_bytes() == base_payload,
                "committed USB source base drift")
        require(output.read_bytes() == candidate_payload,
                "committed USB source candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(base_payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(candidate_payload)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": sha256_bytes(candidate_payload),
        "routed_nets": sorted(ROUTES),
        "added_segments": sum(len(points) - 1 for points in ROUTES.values()),
        "moved_ground_items": [
            "fb9ade5d-8496-4617-9d20-390d44c347c4",
            "bbd350c1-609d-43b7-9dd0-824ee009466f",
        ],
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

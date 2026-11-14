#!/usr/bin/env python3
"""Generate the bounded PCB-MAIN BG95 USB modem-segment candidate.

The proposal connects only U8.9/U8.10 to R39.1/R40.1 on F.Cu.  It uses the
public JLC06161H-3313 engineering geometry over the accepted GND_MODEM In1.Cu
reference zone and never modifies the authoritative board.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import uuid
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")) if str(ROOT / "tools") not in sys.path else None
import pcb_main_lineage_rev_a as _lineage  # noqa: E402  (PCB-MAIN 003: earlier sub-gates read the predecessor)
SOURCE = _lineage.historical_board()
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001"
)
DEFAULT_BASE_OUTPUT = CANDIDATE_DIR / "PCB-MAIN_USB_CELL_MODEM_BASE_REV_A.kicad_pcb"
DEFAULT_OUTPUT = CANDIDATE_DIR / "PCB-MAIN_USB_CELL_MODEM_CANDIDATE_REV_A.kicad_pcb"

BASE_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
CANDIDATE_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
FIXTURE_SUCCESSOR_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
TRACE_WIDTH_MM = 0.1537
PAIR_GAP_MM = 0.2032

# The fan-in and fan-out transitions are analytically balanced around the
# coupled section.  Both complete routes are exactly length matched while the
# coupled centre-line spacing is width + public engineering gap.
ROUTES: dict[str, tuple[tuple[float, float], ...]] = {
    "CELL_USB_DP_U8": (
        (14.85, 51.1),
        (14.15, 51.324286504055095),
        (11.025, 51.324286504055095),
        (10.325, 50.75),
    ),
    "CELL_USB_DM_U8": (
        (14.85, 52.2),
        (14.15, 51.68118650405509),
        (11.025, 51.68118650405509),
        (10.325, 52.0),
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
        f"dioneya:pcb-main:usb-cell-modem-routing-001:{net_name}:{index}",
    ))


def net_codes(source: str) -> dict[str, int]:
    found = {
        name: int(code)
        for code, name in re.findall(r'^  \(net (\d+) "([^"]+)"\)$', source, re.M)
    }
    require(set(ROUTES) <= set(found), "cellular USB modem net identity drift")
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
            "authoritative cellular USB modem-routing base SHA-256 drift")
    source = base_payload.decode("utf-8")
    marker = "\n  (zone "
    require(source.count(marker) >= 1, "cannot locate PCB zone insertion boundary")
    insertion = "\n" + "\n".join(segment_lines(source))
    return source.replace(marker, insertion + marker, 1).encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    active_payload = SOURCE.read_bytes()
    active_sha256 = sha256_bytes(active_payload)
    if active_sha256 == BASE_SHA256:
        base_payload = active_payload
    else:
        require(active_sha256 in {CANDIDATE_SHA256, FIXTURE_SUCCESSOR_SHA256},
                "authoritative cellular USB modem-routing lineage drift")
        base_payload = DEFAULT_BASE_OUTPUT.read_bytes()
        require(sha256_bytes(base_payload) == BASE_SHA256,
                "committed cellular USB modem-routing base SHA-256 drift")
    candidate_payload = candidate_bytes(base_payload)
    require(sha256_bytes(candidate_payload) == CANDIDATE_SHA256,
            "cellular USB modem candidate SHA-256 drift")
    require(candidate_payload != base_payload, "cellular USB modem candidate is unchanged")
    if check:
        require(base_output.read_bytes() == base_payload,
                "committed cellular USB modem base drift")
        require(output.read_bytes() == candidate_payload,
                "committed cellular USB modem candidate drift")
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

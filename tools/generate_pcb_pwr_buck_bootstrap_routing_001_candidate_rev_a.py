#!/usr/bin/env python3
"""Generate the isolated PCB-PWR dual-buck bootstrap routing candidate 001.

The candidate adds only the two local F.Cu bootstrap connections U3.4-C4.1
and U4.4-C6.1.  It never modifies the authoritative PCB and deliberately
leaves switch-node, VIN/PGND, feedback, rail, return and control routing open.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001"
DEFAULT_BASE_OUTPUT = CANDIDATE_DIR / "PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_BASE_REV_A.kicad_pcb"
DEFAULT_OUTPUT = CANDIDATE_DIR / "PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE_REV_A.kicad_pcb"

BASE_SHA256 = "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
CANDIDATE_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
TRACE_WIDTH_MM = 0.5

ROUTES: dict[str, tuple[tuple[float, float], ...]] = {
    "BOOT_3V8": ((54.925, 15.125), (55.055, 16.4)),
    "BOOT_3V3": ((54.925, 43.125), (55.055, 44.4)),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def route_uuid(net_name: str, index: int) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"dioneya:pcb-pwr:buck-bootstrap-routing-001:{net_name}:{index}",
    ))


def net_codes(source: str) -> dict[str, int]:
    found = {
        name: int(code)
        for code, name in re.findall(r'^\s*\(net (\d+) "([^"]+)"\)$', source, re.M)
    }
    require(set(ROUTES) <= set(found), "bootstrap net identity drift")
    return found


def segment_text(source: str) -> str:
    codes = net_codes(source)
    blocks: list[str] = []
    for net_name, points in ROUTES.items():
        for index, (start, end) in enumerate(zip(points, points[1:]), 1):
            blocks.append(
                "\t(segment\n"
                f"\t\t(start {number(start[0])} {number(start[1])})\n"
                f"\t\t(end {number(end[0])} {number(end[1])})\n"
                f"\t\t(width {number(TRACE_WIDTH_MM)})\n"
                "\t\t(layer \"F.Cu\")\n"
                f"\t\t(net {codes[net_name]})\n"
                f"\t\t(uuid \"{route_uuid(net_name, index)}\")\n"
                "\t)"
            )
    return "\n".join(blocks)


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative PCB-PWR bootstrap-routing base SHA-256 drift")
    source = base_payload.decode("utf-8")
    marker = "\n\t(embedded_fonts no)"
    require(source.count(marker) == 1, "cannot locate PCB insertion boundary")
    return source.replace(marker, "\n" + segment_text(source) + marker, 1).encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    source_payload = SOURCE.read_bytes()
    source_sha256 = sha256_bytes(source_payload)
    require(source_sha256 in {
        BASE_SHA256,
        CANDIDATE_SHA256,
        "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5",
        "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3",
        "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c",
        "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c",
    }, "authoritative PCB-PWR is not a controlled bootstrap successor")
    base_payload = (source_payload if source_sha256 == BASE_SHA256
                    else base_output.read_bytes())
    candidate_payload = candidate_bytes(base_payload)
    candidate_sha256 = sha256_bytes(candidate_payload)
    if CANDIDATE_SHA256.startswith("TO_BE_"):
        require(not check, "candidate SHA-256 has not been bound")
    else:
        require(candidate_sha256 == CANDIDATE_SHA256,
                "PCB-PWR bootstrap-routing candidate SHA-256 drift")
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
        "routed_nets": sorted(ROUTES),
        "added_segments": 2,
        "trace_width_mm": TRACE_WIDTH_MM,
        "vias_added": 0,
        "authoritative_board_modified": False,
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

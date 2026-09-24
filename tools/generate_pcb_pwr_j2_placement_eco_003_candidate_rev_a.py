#!/usr/bin/env python3
"""Generate the bounded PCB-PWR J2 placement ECO-003 candidate.

Finding: the native J2 (Molex 43045-1202, right angle) at (90, 56, -90) has 12 of
its 14 pads/NPTH pegs on or outside the 90 x 60 mm outline.  The placement
audits model rotation with the y-up sign convention, so their envelope put J2
inside the DIM-003 service box while KiCad (y-down) places the pin field south
of y = 56 and the pegs east of x = 90.

ECO-003 places J2 by the accepted DIM-003 service box instead of by the echoed
reference point: housing front face flush with the east edge (x = 90.00), body
x 80.09..90.00, y 36.43..58.58 inside the accepted box x 80..130, y 35..60.
Pin 1 (footprint origin) therefore moves to (81.08, 40.00); rotation is kept.
U5/C7/C8, NT1-NT3 and the DNP pull-ups R13/R14 move out of the J2 pin field;
R13 also clears the pre-existing H3 courtyard overlap.  No copper, net,
footprint, value or rotation changes.  Board outline and all accepted routing
(53 trace items, two GND_PWR zones) are untouched.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
# Byte-identical committed copy of the routing-010 board; the candidate is always
# materialised from it so candidate evidence replays after ECO-003 is applied.
BASE_SOURCE = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-3V8-OUTPUT-BULK-ROUTING-010/"
    "PCB-PWR_3V8_OUTPUT_BULK_ROUTING_010_CANDIDATE_REV_A.kicad_pcb"
)
CANDIDATE_NAME = "PCB-PWR_J2_PLACEMENT_ECO_003_CANDIDATE_REV_A.kicad_pcb"
BASE_NAME = "PCB-PWR_J2_PLACEMENT_ECO_003_BASE_REV_A.kicad_pcb"

# Authoritative board after routing 010 application (commit c9e8c3f) and the
# exact candidate this generator must produce from it.  The candidate is
# materialised on demand instead of being committed; the SHA-256 pair binds it.
BASE_SHA256 = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
CANDIDATE_SHA256 = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"

PLACEMENT_REPLACEMENTS = {
    "J2": ("\n\t\t(at 90 56 -90)", "\n\t\t(at 81.08 40 -90)"),
    "U5": ("\n\t\t(at 76 46)", "\n\t\t(at 74.4 46)"),
    "C7": ("\n\t\t(at 76 50)", "\n\t\t(at 74.4 50)"),
    "C8": ("\n\t\t(at 76 54)", "\n\t\t(at 74.9 54)"),
    "NT1": ("\n\t\t(at 79 38)", "\n\t\t(at 75.6 40.12)"),
    "NT2": ("\n\t\t(at 79 41)", "\n\t\t(at 75.6 48.52)"),
    "NT3": ("\n\t\t(at 79 44)", "\n\t\t(at 75.6 52)"),
    "R13": ("\n\t\t(at 71 51)", "\n\t\t(at 74.6 56.5)"),
    "R14": ("\n\t\t(at 73.5 51)", "\n\t\t(at 74.6 58)"),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def footprint_span(source: str, reference: str) -> tuple[int, int]:
    marker = f'(property "Reference" "{reference}"'
    require(source.count(marker) == 1, f"missing or duplicate footprint reference {reference}")
    marker_index = source.index(marker)
    start = source.rfind("\n\t(footprint ", 0, marker_index)
    require(start >= 0, f"cannot locate start of footprint {reference}")
    return start, marker_index


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256, "PCB-PWR ECO-003 base SHA-256 drift")
    source = base_payload.decode("utf-8")
    for reference, (old, new) in PLACEMENT_REPLACEMENTS.items():
        start, header_end = footprint_span(source, reference)
        header = source[start:header_end]
        require(header.count(old) == 1, f"{reference}: source placement drift")
        source = source[:start] + header.replace(old, new) + source[header_end:]
    payload = source.encode("utf-8")
    require(sha256_bytes(payload) == CANDIDATE_SHA256, "PCB-PWR ECO-003 candidate SHA-256 drift")
    return payload


def materialize(directory: Path) -> tuple[Path, Path]:
    """Write BASE and CANDIDATE boards into directory; return their paths."""
    base = BASE_SOURCE.read_bytes()
    candidate = candidate_bytes(base)
    directory.mkdir(parents=True, exist_ok=True)
    base_path, candidate_path = directory / BASE_NAME, directory / CANDIDATE_NAME
    base_path.write_bytes(base)
    candidate_path.write_bytes(candidate)
    return base_path, candidate_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, help="materialise BASE and CANDIDATE boards here")
    args = parser.parse_args()
    candidate = candidate_bytes(BASE_SOURCE.read_bytes())
    if args.output_dir:
        base_path, candidate_path = materialize(args.output_dir)
        print(f"materialised {base_path} and {candidate_path}")
    print(f"PCB-PWR J2 placement ECO-003 candidate regeneration: PASS {sha256_bytes(candidate)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

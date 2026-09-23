#!/usr/bin/env python3
"""Generate isolated PCB-PWR dual-buck power-stage ECO-002 candidate."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-POWER-STAGE-ECO-002"
DEFAULT_BASE_OUTPUT = CANDIDATE_DIR / "PCB-PWR_BUCK_POWER_STAGE_ECO_002_BASE_REV_A.kicad_pcb"
DEFAULT_OUTPUT = CANDIDATE_DIR / "PCB-PWR_BUCK_POWER_STAGE_ECO_002_CANDIDATE_REV_A.kicad_pcb"

BASE_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
CANDIDATE_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"

# Rotate both regulators so SW faces the inductors and VIN faces the local input
# capacitors.  The remaining moves keep the two channels symmetric and preserve
# the established 0.20 mm fitted-body clearance floor.
PLACEMENT_REPLACEMENTS = {
    "U3": ("\t\t(at 55 14)", "\t\t(at 55 14 90)"),
    "U4": ("\t\t(at 55 42)", "\t\t(at 55 42 90)"),
    "C4": ("\t\t(at 54.575 16.4 180)", "\t\t(at 57.8 14.03 270)"),
    "C6": ("\t\t(at 54.575 44.4 180)", "\t\t(at 57.8 42.03 270)"),
    "C20": ("\t\t(at 52.4 14 90)", "\t\t(at 52.35 14 90)"),
    "C21": ("\t\t(at 52.4 42 90)", "\t\t(at 52.35 42 90)"),
    "L1": ("\t\t(at 60.75 14 180)", "\t\t(at 62.5 14 180)"),
    "L2": ("\t\t(at 60.75 42 180)", "\t\t(at 62.5 42 180)"),
}

# Keep assembly references on F.SilkS while moving only their text anchors away
# from the three warning locations proven by commit-bound KiCad 9 DRC.  C4/C6
# use post-rotation serialized angles here; R2 itself is not moved.
SILK_REFERENCE_REPLACEMENTS = {
    "C4": ("\t\t\t(at 0 -1.4 270)", "\t\t\t(at -2.5 0 270)"),
    "C6": ("\t\t\t(at 0 -1.4 270)", "\t\t\t(at -2.5 0 270)"),
    "R2": ("\t\t\t(at 0 -1.4 0)", "\t\t\t(at 0 1.4 0)"),
}

# These are the only accepted traces invalidated by the controller/capacitor
# rotation.  All LM74700, VBAT_RAW and REV_GATE copper remains byte-identical.
REMOVED_BOOT_SEGMENTS = (
    (
        "\t(segment\n"
        "\t\t(start 54.925 15.125)\n"
        "\t\t(end 55.055 16.4)\n"
        "\t\t(width 0.5)\n"
        "\t\t(layer \"F.Cu\")\n"
        "\t\t(net 5)\n"
        "\t\t(uuid \"33d5a14a-c116-598c-9a36-a9c346290690\")\n"
        "\t)\n"
    ),
    (
        "\t(segment\n"
        "\t\t(start 54.925 43.125)\n"
        "\t\t(end 55.055 44.4)\n"
        "\t\t(width 0.5)\n"
        "\t\t(layer \"F.Cu\")\n"
        "\t\t(net 4)\n"
        "\t\t(uuid \"b3a30403-6e12-5f32-b056-bd06f2f787ea\")\n"
        "\t)\n"
    ),
)

# The 2.1 mm SW segment uses its round end cap as a compact pad-entry flare.  It
# overlaps the small controller SW pad and bootstrap-capacitor SW pad while
# retaining more than the required 0.4 mm foreign-copper clearance.  Thus the
# routed copper has no sub-rule external neck; only the device-pad geometry is
# narrower than 2.1 mm.
ROUTES = {
    "BOOT_3V8": {
        "connection": "U3.4-C4.1",
        "segments": (
            ((56.45, 13.95), (56.90, 13.95), 0.5),
            ((56.90, 13.95), (57.10, 13.55), 0.5),
            ((57.10, 13.55), (57.49, 13.55), 0.5),
        ),
    },
    "BOOT_3V3": {
        "connection": "U4.4-C6.1",
        "segments": (
            ((56.45, 41.95), (56.90, 41.95), 0.5),
            ((56.90, 41.95), (57.10, 41.55), 0.5),
            ((57.10, 41.55), (57.49, 41.55), 0.5),
        ),
    },
    "SW_3V8": {
        "connection": "U3.3-C4.2-L1.1",
        "segments": (
            ((56.80, 15.78), (59.45, 15.78), 2.1),
        ),
    },
    "SW_3V3": {
        "connection": "U4.3-C6.2-L2.1",
        "segments": (
            ((56.80, 43.78), (59.45, 43.78), 2.1),
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


def footprint_block(source: str, reference: str) -> tuple[int, int, str]:
    marker = f'(property "Reference" "{reference}"'
    require(source.count(marker) == 1, f"missing or duplicate footprint {reference}")
    marker_index = source.index(marker)
    start = source.rfind("\n\t(footprint ", 0, marker_index)
    require(start >= 0, f"cannot locate start of footprint {reference}")
    start += 1
    end = source.find("\n\t(footprint ", marker_index)
    if end < 0:
        end = source.find("\n\t(gr_", marker_index)
    require(end > start, f"cannot locate end of footprint {reference}")
    return start, end, source[start:end]


def placement_angle(placement: str) -> float:
    found = re.fullmatch(
        r"\t\t\(at\s+[-+]?\d+(?:\.\d+)?\s+[-+]?\d+(?:\.\d+)?"
        r"(?:\s+([-+]?\d+(?:\.\d+)?))?\)",
        placement,
    )
    require(found is not None, f"invalid placement expression: {placement!r}")
    return float(found.group(1) or 0.0)


def rotate_child_orientations(block: str, delta_deg: float) -> str:
    """Apply a KiCad footprint rotation to serialized child orientations.

    KiCad board files store pad, property, and footprint-text orientations in
    board coordinates.  Changing only the parent footprint ``(at ...)`` angle
    rotates child positions but leaves their shapes at the old board angle.
    That malformed serialization was rejected by the commit-bound KiCad 9 DRC.
    """
    if math.isclose(delta_deg % 360.0, 0.0, abs_tol=1e-9):
        return block

    child_at = re.compile(
        r"(?m)^(\t{3,}\(at\s+[-+]?\d+(?:\.\d+)?\s+[-+]?\d+(?:\.\d+)?)"
        r"(?:\s+([-+]?\d+(?:\.\d+)?))?(\))$"
    )

    def replace(match: re.Match[str]) -> str:
        angle = (float(match.group(2) or 0.0) + delta_deg) % 360.0
        return f"{match.group(1)} {number(angle)}{match.group(3)}"

    rotated, count = child_at.subn(replace, block)
    require(count > 0, "rotated footprint has no serialized child orientations")
    return rotated


def move_footprint(source: str, reference: str, old: str, new: str) -> str:
    start, end, block = footprint_block(source, reference)
    require(block.count(old) == 1, f"{reference}: source placement drift")
    require(new not in block, f"{reference}: target placement already present")
    moved = block.replace(old, new, 1)
    delta = placement_angle(new) - placement_angle(old)
    moved = rotate_child_orientations(moved, delta)
    return source[:start] + moved + source[end:]


def move_reference_text(source: str, reference: str, old: str, new: str) -> str:
    start, end, block = footprint_block(source, reference)
    marker = f'(property "Reference" "{reference}"'
    property_start = block.index(marker)
    property_end = block.find("\n\t\t(property ", property_start + len(marker))
    require(property_end > property_start, f"{reference}: reference property boundary missing")
    property_block = block[property_start:property_end]
    require(property_block.count(old) == 1, f"{reference}: reference anchor drift")
    require(new not in property_block, f"{reference}: target reference anchor already present")
    property_block = property_block.replace(old, new, 1)
    moved = block[:property_start] + property_block + block[property_end:]
    return source[:start] + moved + source[end:]


def segment_text(net: int, net_name: str, connection: str, index: int,
                 start: tuple[float, float], end: tuple[float, float],
                 width: float) -> str:
    route_uuid = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"dioneya:pcb-pwr:buck-power-stage-eco-002:{net_name}:{connection}:{index}",
    )
    return (
        "\t(segment\n"
        f"\t\t(start {number(start[0])} {number(start[1])})\n"
        f"\t\t(end {number(end[0])} {number(end[1])})\n"
        f"\t\t(width {number(width)})\n"
        "\t\t(layer \"F.Cu\")\n"
        f"\t\t(net {net})\n"
        f"\t\t(uuid \"{route_uuid}\")\n"
        "\t)"
    )


def candidate_bytes(base_payload: bytes) -> bytes:
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative PCB-PWR ECO-002 base SHA-256 drift")
    source = base_payload.decode("utf-8")
    for reference, (old, new) in PLACEMENT_REPLACEMENTS.items():
        source = move_footprint(source, reference, old, new)
    for reference, (old, new) in SILK_REFERENCE_REPLACEMENTS.items():
        source = move_reference_text(source, reference, old, new)
    for segment in REMOVED_BOOT_SEGMENTS:
        require(source.count(segment) == 1, "accepted BOOT segment identity drift")
        source = source.replace(segment, "", 1)

    additions: list[str] = []
    for net_name, route in ROUTES.items():
        found = re.search(rf'^\s*\(net (\d+) "{net_name}"\)$', source, re.M)
        require(found is not None, f"{net_name} net identity drift")
        for index, (start, end, width) in enumerate(route["segments"], start=1):
            additions.append(segment_text(
                int(found.group(1)), net_name, str(route["connection"]), index,
                start, end, float(width),
            ))
    marker = "\n\t(embedded_fonts no)"
    require(source.count(marker) == 1, "cannot locate PCB insertion boundary")
    source = source.replace(marker, "\n" + "\n".join(additions) + marker, 1)
    return source.encode("utf-8")


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    source_payload = SOURCE.read_bytes()
    source_sha256 = sha256_bytes(source_payload)
    require(source_sha256 in {BASE_SHA256, CANDIDATE_SHA256},
            "authoritative PCB-PWR is not the controlled ECO-002 base or exact candidate")
    base_payload = (
        source_payload if source_sha256 == BASE_SHA256 else base_output.read_bytes()
    )
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "committed ECO-002 base SHA-256 drift")
    candidate_payload = candidate_bytes(base_payload)
    candidate_sha256 = sha256_bytes(candidate_payload)
    if CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha256 == CANDIDATE_SHA256,
                "PCB-PWR buck power-stage ECO-002 SHA-256 drift")
    else:
        require(not check, "candidate SHA-256 has not been bound")
    if check:
        require(base_output.read_bytes() == base_payload, "committed base drift")
        require(output.read_bytes() == candidate_payload, "committed candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(base_payload)
        output.write_bytes(candidate_payload)

    route_lengths = {
        net_name: sum(math.dist(start, end) for start, end, _ in route["segments"])
        for net_name, route in ROUTES.items()
    }
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha256,
        "moved_footprints": sorted(PLACEMENT_REPLACEMENTS),
        "removed_segments": len(REMOVED_BOOT_SEGMENTS),
        "added_segments": sum(len(route["segments"]) for route in ROUTES.values()),
        "routed_nets": list(ROUTES),
        "route_lengths_mm": route_lengths,
        "vias_added": 0,
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

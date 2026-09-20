#!/usr/bin/env python3
"""Generate the bounded PCB-MAIN GNSS RF placement/routing ECO-001 candidate.

The proposal keeps U9 and J9 fixed, moves only FL1 and C64 to the RF_IN side
of U9, removes the obsolete FL1 ground fanout and post-filter wrap, then adds
deterministic replacement RF copper and local ground fanout.  It does not
apply the candidate to the authoritative board or close Review B.
"""

from __future__ import annotations

import argparse
import hashlib
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001"
)
DEFAULT_BASE_OUTPUT = CANDIDATE_DIR / "PCB-MAIN_GNSS_RF_ECO_001_BASE_REV_A.kicad_pcb"
DEFAULT_OUTPUT = CANDIDATE_DIR / "PCB-MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
CANDIDATE_SHA256 = "eeb5689abd3ddc79c3efd88f4f197aebc070c4175d90eefde4690b0f26142295"
RF_WIDTH_MM = 0.1509
GROUND_WIDTH_MM = 0.15
UUID_NAMESPACE = uuid.UUID("6b7d32f9-8e31-4a45-9f83-ecae7e20cc2f")

PLACEMENT_REPLACEMENTS = {
    "FL1": ("    (at 60.5 68)", "    (at 56.8 51.8 270)"),
    "C64": ("    (at 58.75 68)", "    (at 58.3 51.6 180)"),
}

# Remove only the obsolete FL1 ground fanout and the two GNSS RF nets whose
# endpoints move.  The already accepted J9-to-old-C64 antenna path is retained
# and extended from its former endpoint.
REMOVED_TRACE_TSTAMPS = {
    # GNSS_RF_DC_BLOCK and GNSS_RF_FILTERED
    "1dfbdae1-2515-4a74-ac93-32252bfff0bc",
    "0de81ed9-e21d-4a77-8665-1c6f9f233bb5",
    "0ecb7fd9-e7ca-4939-a2e0-d2d1cc20afb6",
    "cb4b0680-668d-47ac-82bb-4687dca027de",
    "cc1858ee-b635-4ec2-93f2-83b945f8f7e6",
    "d421cfb1-108c-4d9a-a0a2-3f4dd0795a9c",
    "f66c9606-454e-4415-aa49-7c8e66ab2659",
    # Obsolete FL1 GND_DIGITAL fanout
    "8bb16eba-0c23-436c-83cb-15711942aa13",
    "97b4ffd7-640c-458b-a674-df70012edd9e",
    "e4d5b871-eae5-40c8-bc94-33070afaccfd",
    "ed333547-457e-4a27-b04c-76eefac1703b",
    "f0cf6fbe-b2d3-49cb-ac31-38e0b70d131a",
    "1b0fbb03-8a78-4e3f-b887-5b3096c609de",
    "3b6e7ac6-f2af-49e1-bbb9-dd1c158f1517",
    "72553cba-285e-40e8-afa0-669c5c279833",
}

# (net code, net name, start, end, width)
ADDED_SEGMENTS = (
    # Extend the preserved GNSS_RF_ANT_BIASED path to relocated C64.1.
    (57, "GNSS_RF_ANT_BIASED", (58.4125, 67.975), (61.95, 68.25), RF_WIDTH_MM),
    (57, "GNSS_RF_ANT_BIASED", (61.95, 68.25), (63.2, 67.0), RF_WIDTH_MM),
    (57, "GNSS_RF_ANT_BIASED", (63.2, 67.0), (63.2, 54.7), RF_WIDTH_MM),
    (57, "GNSS_RF_ANT_BIASED", (63.2, 54.7), (59.5, 51.0), RF_WIDTH_MM),
    (57, "GNSS_RF_ANT_BIASED", (59.5, 51.0), (58.625, 51.6), RF_WIDTH_MM),
    # Relocated C64.2 to FL1.C.
    (58, "GNSS_RF_DC_BLOCK", (57.975, 51.6), (56.8, 51.425), RF_WIDTH_MM),
    # Short post-filter route from U9.11 RF_IN to FL1.A.
    (59, "GNSS_RF_FILTERED", (56.8, 53.25), (56.8, 52.55), RF_WIDTH_MM),
    (59, "GNSS_RF_FILTERED", (56.8, 52.55), (56.55, 52.175), RF_WIDTH_MM),
    # FL1 B/D/E ground fanout; B reuses the adjacent U9.12 ground via.
    (45, "GND_DIGITAL", (56.55, 51.8), (55.725, 51.85), GROUND_WIDTH_MM),
    (45, "GND_DIGITAL", (57.05, 51.8), (57.75, 52.55), GROUND_WIDTH_MM),
    (45, "GND_DIGITAL", (57.05, 52.175), (57.75, 52.55), GROUND_WIDTH_MM),
)
ADDED_VIAS = (
    (45, "GND_DIGITAL", (57.75, 52.55), 0.5, 0.3),
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def item_uuid(kind: str, index: int, net_name: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, f"{kind}:{index}:{net_name}"))


def footprint_block(source: str, reference: str) -> tuple[int, int, str]:
    marker = f'(fp_text reference "{reference}" '
    require(source.count(marker) == 1, f"missing or duplicate footprint {reference}")
    marker_index = source.index(marker)
    start = source.rfind("\n  (footprint ", 0, marker_index)
    require(start >= 0, f"cannot locate start of footprint {reference}")
    start += 1
    end = source.find("\n  (footprint ", marker_index)
    if end < 0:
        end = source.find("\n  (segment ", marker_index)
    require(end > start, f"cannot locate end of footprint {reference}")
    return start, end, source[start:end]


def move_footprint(source: str, reference: str, old: str, new: str) -> str:
    start, end, block = footprint_block(source, reference)
    require(block.count(old) == 1, f"{reference}: source placement drift")
    require(new not in block, f"{reference}: target placement already present")
    block = block.replace(old, new)
    return source[:start] + block + source[end:]


def remove_controlled_trace_items(source: str) -> str:
    lines = source.splitlines(keepends=True)
    seen = {tstamp: 0 for tstamp in REMOVED_TRACE_TSTAMPS}
    retained: list[str] = []
    for line in lines:
        matches = [tstamp for tstamp in REMOVED_TRACE_TSTAMPS
                   if f"(tstamp {tstamp})" in line]
        require(len(matches) <= 1, "trace-item UUID matching is ambiguous")
        if matches:
            seen[matches[0]] += 1
            continue
        retained.append(line)
    require(all(count == 1 for count in seen.values()),
            f"controlled trace-item inventory drift: {seen}")
    return "".join(retained)


def segment_line(index: int, item: tuple[object, ...]) -> str:
    net_code, net_name, start, end, width = item
    tstamp = item_uuid("segment", index, str(net_name))
    return (
        f'  (segment (start {fmt(start[0])} {fmt(start[1])}) '
        f'(end {fmt(end[0])} {fmt(end[1])}) (width {fmt(float(width))}) '
        f'(layer "F.Cu") (net {net_code}) (tstamp {tstamp}))\n'
    )


def via_line(index: int, item: tuple[object, ...]) -> str:
    net_code, net_name, position, size, drill = item
    tstamp = item_uuid("via", index, str(net_name))
    return (
        f'  (via (at {fmt(position[0])} {fmt(position[1])}) '
        f'(size {fmt(float(size))}) (drill {fmt(float(drill))}) '
        f'(layers "F.Cu" "B.Cu") (net {net_code}) (tstamp {tstamp}))\n'
    )


def candidate_bytes(base_payload: bytes) -> bytes:
    source = base_payload.decode("utf-8")
    for reference, (old, new) in PLACEMENT_REPLACEMENTS.items():
        source = move_footprint(source, reference, old, new)
    source = remove_controlled_trace_items(source)
    insertion = "".join(
        segment_line(index, item) for index, item in enumerate(ADDED_SEGMENTS)
    ) + "".join(
        via_line(index, item) for index, item in enumerate(ADDED_VIAS)
    )
    marker = "\n  (zone "
    require(source.count(marker) >= 1, "zone insertion marker is missing")
    source = source.replace(marker, "\n" + insertion + "  (zone ", 1)
    return source.encode("utf-8")


def generate(base_output: Path, output: Path) -> dict[str, object]:
    base_payload = BASE.read_bytes()
    require(sha256_bytes(base_payload) == BASE_SHA256,
            "authoritative PCB-MAIN SHA-256 drift")
    candidate_payload = candidate_bytes(base_payload)
    require(candidate_payload != base_payload, "GNSS ECO candidate is unchanged")
    require(sha256_bytes(candidate_payload) == CANDIDATE_SHA256,
            "GNSS ECO candidate SHA-256 drift")
    base_output.parent.mkdir(parents=True, exist_ok=True)
    base_output.write_bytes(base_payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate_payload)
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": sha256_bytes(candidate_payload),
        "base_output": (
            str(base_output.relative_to(ROOT))
            if base_output.is_relative_to(ROOT)
            else str(base_output)
        ),
        "candidate_output": (
            str(output.relative_to(ROOT))
            if output.is_relative_to(ROOT)
            else str(output)
        ),
        "moved_footprints": sorted(PLACEMENT_REPLACEMENTS),
        "removed_trace_items": len(REMOVED_TRACE_TSTAMPS),
        "added_segments": len(ADDED_SEGMENTS),
        "added_vias": len(ADDED_VIAS),
        "authoritative_board_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-output", type=Path, default=DEFAULT_BASE_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(generate(args.base_output.resolve(), args.output.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

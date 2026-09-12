#!/usr/bin/env python3
"""Record completed reviews on selected KiCad-library PCB-MAIN footprints.

Only the two Dioneya properties inside the named footprint expressions are
changed.  Copper, drills, paste, nets, placement and UUIDs remain byte-for-byte
untouched; the independent layout audit checks the resulting geometry.  A
package-outline-only review remains explicitly blocked for independent
IPC/assembly land-pattern control.
"""
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

from materialize_pcb_main_manufacturer_footprints_rev_a import footprint_spans


ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
PENDING = "KICAD_LIBRARY_PATTERN_REVIEW_PENDING"
VERIFIED = "KICAD_LIBRARY_PATTERN_DRAWING_VERIFIED"
PACKAGE_ONLY = "PACKAGE_OUTLINE_VERIFIED_IPC_ASSEMBLY_CONTROL_REQUIRED"

CONTROLLED = {
    "J11": (
        "KiCad:Connector_USB.pretty/USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
        "GCT_USB4105_RevB4_2023-12-18_RecommendedPCBLayout",
    ),
    "J_MIC1": (
        "KiCad:Connector_Molex.pretty/Molex_Pico-Lock_504050-0691_1x06-1MP_P1.50mm_Horizontal",
        "Molex_5040500000-SD_PSD000_RevB_RecommendedPattern",
    ),
    "J_MIC2": (
        "KiCad:Connector_Molex.pretty/Molex_Pico-Lock_504050-0691_1x06-1MP_P1.50mm_Horizontal",
        "Molex_5040500000-SD_PSD000_RevB_RecommendedPattern",
    ),
    "J_MIC3": (
        "KiCad:Connector_Molex.pretty/Molex_Pico-Lock_504050-0691_1x06-1MP_P1.50mm_Horizontal",
        "Molex_5040500000-SD_PSD000_RevB_RecommendedPattern",
    ),
    "J_MIC4": (
        "KiCad:Connector_Molex.pretty/Molex_Pico-Lock_504050-0691_1x06-1MP_P1.50mm_Horizontal",
        "Molex_5040500000-SD_PSD000_RevB_RecommendedPattern",
    ),
}

PACKAGE_ONLY_CONTROLLED = {
    "U2": (
        "KiCad:Package_SO.pretty/SOIC-16W_7.5x10.3mm_P1.27mm",
        "Winbond_W25Q512JV_RevB_PackageF_NoManufacturerLandPattern",
    ),
    "U25": (
        "KiCad:Package_TO_SOT_SMD.pretty/Texas_DRT-3",
        "TI_DRT0003A_MPDS340_PackageOnly_NoManufacturerLandPattern",
    ),
    "U26": (
        "KiCad:Package_TO_SOT_SMD.pretty/Texas_DRT-3",
        "TI_DRT0003A_MPDS340_PackageOnly_NoManufacturerLandPattern",
    ),
}


def replace_property(block: str, key: str, allowed: set[str], value: str, ref: str) -> str:
    pattern = re.compile(r'(\(property "' + re.escape(key) + r'" ")([^"]+)("\))')
    match = pattern.search(block)
    if match is None:
        raise RuntimeError(f"{ref}: missing {key}")
    if match.group(2) not in allowed:
        raise RuntimeError(f"{ref}: unexpected {key}={match.group(2)}")
    return block[:match.start(2)] + value + block[match.end(2):]


def materialize(source: Path, destination: Path) -> None:
    board_text = source.read_text(encoding="utf-8")
    targets = {
        **{ref: (*values, VERIFIED) for ref, values in CONTROLLED.items()},
        **{ref: (*values, PACKAGE_ONLY)
           for ref, values in PACKAGE_ONLY_CONTROLLED.items()},
    }
    spans = [span for span in footprint_spans(board_text) if span[2] in targets]
    if {span[2] for span in spans} != set(targets):
        raise RuntimeError("could not locate every reviewed KiCad-library footprint")
    for start, end, ref in reversed(spans):
        old_source, reviewed_source, target_status = targets[ref]
        block = board_text[start:end]
        block = replace_property(
            block, "DIONEA_FOOTPRINT_SOURCE",
            {old_source, reviewed_source}, reviewed_source, ref
        )
        block = replace_property(
            block, "DIONEA_FOOTPRINT_STATUS",
            {PENDING, target_status}, target_status, ref
        )
        board_text = board_text[:start] + block + board_text[end:]
    destination.write_text(board_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="pcb-main-library-review-") as temp_dir:
            candidate = Path(temp_dir) / PCB.name
            materialize(PCB, candidate)
            if candidate.read_bytes() != PCB.read_bytes():
                raise SystemExit(
                    "PCB-MAIN reviewed-library properties are stale; run materializer"
                )
        print("PCB-MAIN reviewed-library footprint materialization: PASS")
    else:
        materialize(PCB, PCB)
        print("PCB-MAIN reviewed-library footprint materialization: UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

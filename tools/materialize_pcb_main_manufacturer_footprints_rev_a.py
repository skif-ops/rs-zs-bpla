#!/usr/bin/env python3
"""Materialize PCB-MAIN manufacturer-controlled footprints.

This pure-kiutils materializer is usable outside KiCad.  It preserves each
component's locked placement, schematic nets, RefDes/value text and population
state while replacing only its land-pattern geometry.
"""
from __future__ import annotations

import argparse
import copy
import math
import re
import tempfile
import uuid
from pathlib import Path

from kiutils.board import Board
from kiutils.footprint import Footprint


ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
LIB = ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty"
UUID_NAMESPACE = uuid.UUID("f699db62-94ee-57ef-b2df-eb7590723bf8")

CONTROLLED = {
    "D1": (
        "Nexperia_PESD5V0S1UL_SOD882.kicad_mod",
        "Nexperia_PESD5V0S1UL_v5_2025-12-01_Fig11_ReflowFootprint",
    ),
    "D2": (
        "Nexperia_PESD5V0S1UL_SOD882.kicad_mod",
        "Nexperia_PESD5V0S1UL_v5_2025-12-01_Fig11_ReflowFootprint",
    ),
    "Q1": (
        "Nexperia_MMBT3904_SOT23.kicad_mod",
        "Nexperia_MMBT3904_v5_2026-04-08_Fig8_ReflowFootprint",
    ),
    "Q2": (
        "Nexperia_MMBT3904_SOT23.kicad_mod",
        "Nexperia_MMBT3904_v5_2026-04-08_Fig8_ReflowFootprint",
    ),
    "Q3": (
        "Nexperia_MMBT3904_SOT23.kicad_mod",
        "Nexperia_MMBT3904_v5_2026-04-08_Fig8_ReflowFootprint",
    ),
    "D4": (
        "TI_DYA0002A_SOD523.kicad_mod",
        "TI_DYA0002A_4224978B_2021-09_RecommendedLandPattern",
    ),
    "D6": (
        "TI_DYA0002A_SOD523.kicad_mod",
        "TI_DYA0002A_4224978B_2021-09_RecommendedLandPattern",
    ),
    "D7": (
        "TI_DYA0002A_SOD523.kicad_mod",
        "TI_DYA0002A_4224978B_2021-09_RecommendedLandPattern",
    ),
    "D8": (
        "TI_DYA0002A_SOD523.kicad_mod",
        "TI_DYA0002A_4224978B_2021-09_RecommendedLandPattern",
    ),
    "D9": (
        "TI_DYA0002A_SOD523.kicad_mod",
        "TI_DYA0002A_4224978B_2021-09_RecommendedLandPattern",
    ),
    "D10": (
        "TI_DYA0002A_SOD523.kicad_mod",
        "TI_DYA0002A_4224978B_2021-09_RecommendedLandPattern",
    ),
    "D11": (
        "TI_DYA0002A_SOD523.kicad_mod",
        "TI_DYA0002A_4224978B_2021-09_RecommendedLandPattern",
    ),
    "U1": (
        "ST_STM32U585_LQFP100_1L.kicad_mod",
        "ST_DS13086_Rev10_Figure96_LQFP100_1L",
    ),
    "U7": (
        "TI_PW0024A_TSSOP24.kicad_mod",
        "TI_PW0024A_4220208A_2017-02_RecommendedLandPattern",
    ),
    "U13": (
        "TI_PW0024A_TSSOP24.kicad_mod",
        "TI_PW0024A_4220208A_2017-02_RecommendedLandPattern",
    ),
    "U16": (
        "TI_PW0024A_TSSOP24.kicad_mod",
        "TI_PW0024A_4220208A_2017-02_RecommendedLandPattern",
    ),
    "U17": (
        "TI_PW0014A_TSSOP14.kicad_mod",
        "TI_PW0014A_4220202B_2023-12_RecommendedLandPattern",
    ),
    "U18": (
        "TI_DRL0006A_SOT6.kicad_mod",
        "TI_DRL0006A_4223266F_2024-11_RecommendedLandPattern",
    ),
    "U6": (
        "TI_DBV0005A_SOT23-5.kicad_mod",
        "TI_DBV0005A_4214839K_2024-08_RecommendedLandPattern",
    ),
    "U19": (
        "TI_DQA0010A_USON10.kicad_mod",
        "TI_DQA0010A_4220328A_2015-12_RecommendedLandPattern",
    ),
    "U20": (
        "TI_DQA0010A_USON10.kicad_mod",
        "TI_DQA0010A_4220328A_2015-12_RecommendedLandPattern",
    ),
    "U21": (
        "TI_DQA0010A_USON10.kicad_mod",
        "TI_DQA0010A_4220328A_2015-12_RecommendedLandPattern",
    ),
    "U22": (
        "TI_DQA0010A_USON10.kicad_mod",
        "TI_DQA0010A_4220328A_2015-12_RecommendedLandPattern",
    ),
    "U23": (
        "TI_DQA0010A_USON10.kicad_mod",
        "TI_DQA0010A_4220328A_2015-12_RecommendedLandPattern",
    ),
    "U24": (
        "TI_DQA0010A_USON10.kicad_mod",
        "TI_DQA0010A_4220328A_2015-12_RecommendedLandPattern",
    ),
    "U27": (
        "TI_DQA0010A_USON10.kicad_mod",
        "TI_DQA0010A_4220328A_2015-12_RecommendedLandPattern",
    ),
    "J8": (
        "Hirose_U.FL-R-SMT-1.kicad_mod",
        "Hirose_U.FL_CAT_2026-08-01_PCB_and_MetalMask",
    ),
    "J9": (
        "Hirose_U.FL-R-SMT-1.kicad_mod",
        "Hirose_U.FL_CAT_2026-08-01_PCB_and_MetalMask",
    ),
    "J10": (
        "Hirose_U.FL-R-SMT-1.kicad_mod",
        "Hirose_U.FL_CAT_2026-08-01_PCB_and_MetalMask",
    ),
    "J12": (
        "GCT_MEM2052-00-195-00-A.kicad_mod",
        "GCT_MEM2052_RevA3_RecommendedPCBLayout",
    ),
    "J13": (
        "Molex_504050-0291_PicoLock-2.kicad_mod",
        "Molex_5040500000-SD_PSD001_RevB_RecommendedPattern",
    ),
    "J_PWR": (
        "Molex_43045-1202_MicroFit-12_RA.kicad_mod",
        "Molex_SD-43045-001_PSD001_RevH1_PCBLayout",
    ),
    "U8": (
        "Quectel_BG95-M3_LGA-102.kicad_mod",
        "Quectel_BG95_HW_Design_V1.8_Figure46",
    ),
    "U3": (
        "ST_LIS2DW12_LGA-12L.kicad_mod",
        "ST_DS11811_Rev9_and_TN0018_Rev8_LGA-12L_Pattern",
    ),
    "U11": (
        "Raytac_MDBT50Q-P1MV2.kicad_mod",
        "Raytac_MDBT50Q_Footprint_Design_Guide_230606",
    ),
}


def ref_of(footprint: Footprint) -> str:
    for item in footprint.graphicItems:
        if getattr(item, "type", None) == "reference":
            return str(item.text)
    return ""


def replace(old: Footprint, ref: str, filename: str, source: str) -> Footprint:
    new = Footprint.from_file(str(LIB / filename), encoding="utf-8")
    old_by_number = {pad.number: pad for pad in old.pads if pad.number}
    new_numbers = {pad.number for pad in new.pads if pad.number}
    if new_numbers != set(old_by_number):
        raise RuntimeError(
            f"{ref}: footprint logical pins {sorted(new_numbers)} do not match "
            f"board pins {sorted(old_by_number)}"
        )

    new.position = copy.deepcopy(old.position)
    new.tstamp = old.tstamp
    new.tedit = old.tedit
    new.locked = old.locked
    new.placed = old.placed
    new.path = old.path
    new.properties = {
        "DIONEA_FOOTPRINT_SOURCE": source,
        "DIONEA_FOOTPRINT_STATUS": "MANUFACTURER_DRAWING_PATTERN_CONTROLLED",
        "DIONEA_PACKAGE": old.properties["DIONEA_PACKAGE"],
        "DIONEA_POPULATION": old.properties["DIONEA_POPULATION"],
    }
    new.attributes.excludeFromPosFiles = old.attributes.excludeFromPosFiles
    new.attributes.excludeFromBom = old.attributes.excludeFromBom

    old_text = {
        item.type: copy.deepcopy(item)
        for item in old.graphicItems
        if getattr(item, "type", None) in {"reference", "value"}
    }
    new.graphicItems = [
        item for item in new.graphicItems
        if getattr(item, "type", None) not in {"reference", "value"}
    ] + [old_text["reference"], old_text["value"]]

    rotation = float(new.position.angle or 0.0) % 360.0
    for index, item in enumerate(new.graphicItems):
        if getattr(item, "tstamp", None) is None:
            item.tstamp = str(uuid.uuid5(UUID_NAMESPACE, f"PCB-MAIN:{ref}:graphic:{index}"))
    duplicate_count: dict[str, int] = {}
    for pad in new.pads:
        occurrence = duplicate_count.get(pad.number, 0)
        duplicate_count[pad.number] = occurrence + 1
        pad.tstamp = str(uuid.uuid5(
            UUID_NAMESPACE, f"PCB-MAIN:{ref}:pad:{pad.number}:{occurrence}"
        ))
        pad.position.angle = rotation or None
        if pad.number:
            authority = old_by_number[pad.number]
            pad.net = copy.deepcopy(authority.net)
            pad.pinFunction = authority.pinFunction
            pad.pinType = authority.pinType
    # Footprint-file rule areas use local coordinates, while the KiCad board
    # syntax stores their polygon points in board coordinates.  Transform them
    # explicitly so the pure-kiutils materializer matches pcbnew placement.
    angle = math.radians(float(new.position.angle or 0.0))
    cosine, sine = math.cos(angle), math.sin(angle)
    for zone_index, zone in enumerate(new.zones):
        zone.tstamp = str(uuid.uuid5(UUID_NAMESPACE, f"PCB-MAIN:{ref}:zone:{zone_index}"))
        for polygon in [*zone.polygons, *zone.filledPolygons]:
            for point in polygon.coordinates:
                local_x, local_y = point.X, point.Y
                point.X = round(new.position.X + local_x * cosine + local_y * sine, 6)
                point.Y = round(new.position.Y - local_x * sine + local_y * cosine, 6)
    return new


def footprint_spans(board_text: str) -> list[tuple[int, int, str]]:
    """Return top-level footprint spans without reserializing unrelated PCB data."""
    spans: list[tuple[int, int, str]] = []
    for match in re.finditer(r"(?m)^  \(footprint ", board_text):
        start = match.start()
        depth = 0
        quoted = False
        escaped = False
        end = None
        for index in range(start, len(board_text)):
            char = board_text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise RuntimeError("unterminated footprint expression")
        block = board_text[start:end]
        ref_match = re.search(r'\(fp_text reference "([^"]+)"', block)
        spans.append((start, end, ref_match.group(1) if ref_match else ""))
    return spans


def materialize(source: Path, destination: Path) -> None:
    board_text = source.read_text(encoding="utf-8")
    board = Board.from_file(str(source), encoding="utf-8")
    found: set[str] = set()
    rendered: dict[str, str] = {}
    for footprint in board.footprints:
        ref = ref_of(footprint)
        if ref in CONTROLLED:
            filename, drawing = CONTROLLED[ref]
            footprint = replace(footprint, ref, filename, drawing)
            found.add(ref)
            rendered_footprint = footprint.to_sexpr(
                indent=2, layerInFirstLine=True
            ).rstrip("\n")
            # kiutils serializes a one-item wildcard layer list as singular
            # ``(layer "*.Cu")``.  KiCad requires the plural ``layers`` form
            # for wildcard zone scopes even when the list has one token.
            rendered[ref] = rendered_footprint.replace(
                '(layer "*.Cu")', '(layers "*.Cu")'
            )
    if found != set(CONTROLLED):
        raise RuntimeError(f"controlled reference set mismatch: {sorted(found)}")
    spans = [span for span in footprint_spans(board_text) if span[2] in CONTROLLED]
    if {span[2] for span in spans} != set(CONTROLLED):
        raise RuntimeError("could not locate all controlled footprint expressions")
    for start, end, ref in reversed(spans):
        board_text = board_text[:start] + rendered[ref] + board_text[end:]
    destination.write_text(board_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / PCB.name
            materialize(PCB, candidate)
            if candidate.read_bytes() != PCB.read_bytes():
                raise SystemExit("PCB-MAIN manufacturer footprints are stale; run materializer")
        print("PCB-MAIN manufacturer-footprint materialization: PASS")
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / PCB.name
            materialize(PCB, candidate)
            PCB.write_bytes(candidate.read_bytes())
        print("PCB-MAIN manufacturer-footprint materialization: UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

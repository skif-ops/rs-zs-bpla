#!/usr/bin/env python3
"""Materialize PCB-MAIN controlled project-local footprints.

This pure-kiutils materializer is usable outside KiCad.  It preserves each
component's placement and traceability properties, schematic nets, RefDes/value
text and population state while replacing only its land-pattern geometry.
Manufacturer-pattern controls and package-derived IPC candidates retain distinct
release statuses.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from kiutils.board import Board
from kiutils.footprint import Footprint


ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
LIB = ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty"
ECO_003_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_APPLICATION.json"
)
ECO_003_APPROVED_BOARD_SHA256 = "dfcd8780cb3f189fe89cca98f32e3ee9693947a9a28d25e0154f7cce65d51684"
ECO_004_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_STTS22H_FOOTPRINT_ECO_004_APPLICATION.json"
)
ECO_004_APPROVED_BOARD_SHA256 = "a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8"
GROUND_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_APPLICATION_REV_A.json"
)
GROUND_APPROVED_BOARD_SHA256 = "9c8abfabc18fa22b53c94b6b4d7946dbe1dfab797fbff9d00d7c3408aece1b9e"
SIGNAL_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_SIGNAL_HARD_NETS_ROUTING_APPLICATION_REV_A.json"
)
SIGNAL_APPROVED_BOARD_SHA256 = "7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3"
OCTOSPI_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_APPLICATION_REV_A.json"
)
OCTOSPI_APPROVED_BOARD_SHA256 = "04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f"
UUID_NAMESPACE = uuid.UUID("f699db62-94ee-57ef-b2df-eb7590723bf8")

CONTROLLED = {
    "C36": (
        "KEMET_T52X_D_7343-31_DensityB.kicad_mod",
        "KEMET_T2076_T52X-530_2026-08-20_Table2_DensityB",
    ),
    "C44": (
        "KEMET_T52X_D_7343-31_DensityB.kicad_mod",
        "KEMET_T2076_T52X-530_2026-08-20_Table2_DensityB",
    ),
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
    "Q4": (
        "Vishay_Si1016X_SC-89.kicad_mod",
        "Vishay_Si1016X_RevE_AN826_RecommendedMinimumPads",
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
    "U14": (
        "ST_ESDALC6V1-5P6_SOT666.kicad_mod",
        "ST_ESDALC6V1-5P6_Rev3_Figure14_SOT666_Footprint",
    ),
    "U15": (
        "ST_ESDALC6V1-5P6_SOT666.kicad_mod",
        "ST_ESDALC6V1-5P6_Rev3_Figure14_SOT666_Footprint",
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
    "U4": (
        "STTS22H_UDFN-6L.kicad_mod",
        "ST_DS12606_Rev8_Fig10_11",
    ),
    "U11": (
        "Raytac_MDBT50Q-P1MV2.kicad_mod",
        "Raytac_MDBT50Q_Footprint_Design_Guide_230606",
    ),
}

IPC_CANDIDATE_CONTROLLED = {
    "U2": (
        "Winbond_W25Q512JV_PackageF_IPC_Candidate.kicad_mod",
        "PROJECT_IPC_W25Q512JV_F_KICAD_GULLWING_ASSEMBLER_DFM_REQUIRED",
    ),
    "U25": (
        "TI_DRT0003A_IPC_Candidate.kicad_mod",
        "PROJECT_IPC_TI_DRT0003A_KICAD_DRT3_ASSEMBLER_DFM_REQUIRED",
    ),
    "U26": (
        "TI_DRT0003A_IPC_Candidate.kicad_mod",
        "PROJECT_IPC_TI_DRT0003A_KICAD_DRT3_ASSEMBLER_DFM_REQUIRED",
    ),
}


def ref_of(footprint: Footprint) -> str:
    for item in footprint.graphicItems:
        if getattr(item, "type", None) == "reference":
            return str(item.text)
    return ""


def replace(old: Footprint, ref: str, filename: str, source: str, status: str) -> Footprint:
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
    new.properties = copy.deepcopy(old.properties)
    new.properties.update({
        "DIONEA_FOOTPRINT_SOURCE": source,
        "DIONEA_FOOTPRINT_STATUS": status,
        "DIONEA_PACKAGE": old.properties["DIONEA_PACKAGE"],
        "DIONEA_POPULATION": old.properties["DIONEA_POPULATION"],
    })
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
            # Preserve board-level electrical clearance overrides.  U3 uses a
            # reviewed 0.12 mm local pad clearance which is intentionally
            # absent from the reusable manufacturer land-pattern library.
            pad.clearance = authority.clearance
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
    controlled = {
        **{
            ref: (*values, "MANUFACTURER_DRAWING_PATTERN_CONTROLLED")
            for ref, values in CONTROLLED.items()
        },
        **{
            ref: (*values, "PROJECT_IPC_PATTERN_CONTROLLED_ASSEMBLY_DFM_REQUIRED")
            for ref, values in IPC_CANDIDATE_CONTROLLED.items()
        },
    }
    found: set[str] = set()
    rendered: dict[str, str] = {}
    for footprint in board.footprints:
        ref = ref_of(footprint)
        if ref in controlled:
            filename, drawing, status = controlled[ref]
            footprint = replace(footprint, ref, filename, drawing, status)
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
    if found != set(controlled):
        raise RuntimeError(f"controlled reference set mismatch: {sorted(found)}")
    spans = [span for span in footprint_spans(board_text) if span[2] in controlled]
    if {span[2] for span in spans} != set(controlled):
        raise RuntimeError("could not locate all controlled footprint expressions")
    for start, end, ref in reversed(spans):
        board_text = board_text[:start] + rendered[ref] + board_text[end:]
    destination.write_text(board_text, encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_SERIALIZATION_ONLY_FIELDS = {
    "filePath",
    "generator",
    "renderCache",
    "tedit",
    "tstamp",
    "version",
}


def canonical(value: Any, field: str = "") -> Any:
    """Return a serialization-neutral representation of KiCad objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, dict):
        return (
            "dict",
            tuple(
                (str(key), canonical(item, str(key)))
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                if str(key) not in _SERIALIZATION_ONLY_FIELDS
            ),
        )
    if isinstance(value, (list, tuple)):
        items = [canonical(item) for item in value]
        # KiCad/kiutils may reorder independent footprint children while
        # retaining identical geometry.  Polygon point order remains ordered.
        if field in {"graphicItems", "groups", "models", "pads", "zones"}:
            items.sort(key=repr)
        return ("list", tuple(items))
    if isinstance(value, set):
        return ("set", tuple(sorted((canonical(item) for item in value), key=repr)))
    if hasattr(value, "__dict__"):
        return (
            type(value).__name__,
            tuple(
                (key, canonical(item, key))
                for key, item in sorted(vars(value).items())
                if key not in _SERIALIZATION_ONLY_FIELDS
            ),
        )
    return repr(value)


def verify_frozen_materialization(candidate: Path) -> None:
    """Validate the signed ECO lineage and all controlled footprint semantics."""
    if not ECO_003_APPLICATION.is_file():
        raise RuntimeError("PCB-MAIN ECO-003 application evidence is missing")
    if not ECO_004_APPLICATION.is_file():
        raise RuntimeError("PCB-MAIN ECO-004 application evidence is missing")
    if not GROUND_APPLICATION.is_file():
        raise RuntimeError("PCB-MAIN ground-domain application evidence is missing")
    if not OCTOSPI_APPLICATION.is_file():
        raise RuntimeError("PCB-MAIN OctoSPI application evidence is missing")
    eco003 = json.loads(ECO_003_APPLICATION.read_text(encoding="utf-8"))
    eco003_applied = eco003.get("applied", {})
    eco004 = json.loads(ECO_004_APPLICATION.read_text(encoding="utf-8"))
    eco004_applied = eco004.get("applied", {})
    ground = json.loads(GROUND_APPLICATION.read_text(encoding="utf-8"))
    ground_baseline = ground.get("historical_baseline", {})
    ground_applied = ground.get("applied", {})
    signal = json.loads(SIGNAL_APPLICATION.read_text(encoding="utf-8"))
    signal_applied = signal.get("applied", {})
    octospi = json.loads(OCTOSPI_APPLICATION.read_text(encoding="utf-8"))
    octospi_applied = octospi.get("applied", {})
    actual_board_sha256 = sha256(PCB)
    if not (
        eco003.get("proposal_id") == "PCB-MAIN-RF-ROUTEABILITY-ECO-003"
        and eco003.get("decision") == "ACCEPT_LIMITED_RF_ROUTEABILITY_ECO"
        and eco003_applied.get("board_sha256") == ECO_003_APPROVED_BOARD_SHA256
        and eco004.get("proposal_id") == "PCB-MAIN-STTS22H-FOOTPRINT-ECO-004"
        and eco004.get("decision") == "ACCEPT_STTS22H_FOOTPRINT_ECO_004"
        and eco004.get("routing_engineering_continuation_authorized") is True
        and eco004.get("candidate_or_future_copper_final_authorized") is False
        and eco004.get("routing_complete") is False
        and eco004.get("review_b_complete") is False
        and eco004.get("cam_or_manufacturing_release") is False
        and eco004_applied.get("track_segments") == 0
        and eco004_applied.get("copper_zones") == 0
        and eco004_applied.get("board_sha256") == ECO_004_APPROVED_BOARD_SHA256
        and ground.get("proposal_id") == "PCB-MAIN-GROUND-DOMAIN-ROUTING-001"
        and ground.get("decision") == "ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE"
        and ground.get("status") ==
        "APPLIED_ACCEPTED_GROUND_DOMAIN_SUBGATE_ROUTING_ENGINEERING_CONTINUES"
        and ground_baseline.get("board_sha256") == ECO_004_APPROVED_BOARD_SHA256
        and ground_applied.get("board_sha256") == GROUND_APPROVED_BOARD_SHA256
        and ground_applied.get("exact_candidate_byte_identity") is True
        and ground.get("routing_complete") is False
        and ground.get("review_b_complete") is False
        and ground.get("cam_or_manufacturing_release") is False
        and signal.get("decision") == "ACCEPT_SIGNAL_HARD_NETS_ROUTING_SUBGATE"
        and signal_applied.get("board_sha256") == SIGNAL_APPROVED_BOARD_SHA256
        and signal_applied.get("exact_candidate_byte_identity") is True
        and signal.get("routing_complete") is False
        and signal.get("review_b_complete") is False
        and signal.get("cam_or_manufacturing_release") is False
        and octospi.get("decision") ==
        "ACCEPT_LIMITED_OCTOSPI_R8_PLACEMENT_ECO_AND_ROUTING_SUBGATE"
        and octospi.get("historical_baseline", {}).get("board_sha256") ==
        SIGNAL_APPROVED_BOARD_SHA256
        and octospi_applied.get("board_sha256") == OCTOSPI_APPROVED_BOARD_SHA256
        and octospi_applied.get("exact_candidate_byte_identity") is True
        and octospi.get("routing_complete") is False
        and octospi.get("review_b_complete") is False
        and octospi.get("cam_or_manufacturing_release") is False
        and actual_board_sha256 == OCTOSPI_APPROVED_BOARD_SHA256
    ):
        raise RuntimeError(
            "PCB-MAIN ECO-003/ECO-004/ground-domain frozen-board authority mismatch"
        )

    controlled = set(CONTROLLED) | set(IPC_CANDIDATE_CONTROLLED)
    approved_board = Board.from_file(str(PCB), encoding="utf-8")
    candidate_board = Board.from_file(str(candidate), encoding="utf-8")
    approved = {
        ref_of(footprint): footprint
        for footprint in approved_board.footprints
        if ref_of(footprint) in controlled
    }
    regenerated = {
        ref_of(footprint): footprint
        for footprint in candidate_board.footprints
        if ref_of(footprint) in controlled
    }
    if set(approved) != controlled or set(regenerated) != controlled:
        raise RuntimeError("PCB-MAIN controlled footprint reference set mismatch")
    mismatched = [
        ref for ref in sorted(controlled)
        if canonical(approved[ref]) != canonical(regenerated[ref])
    ]
    if mismatched:
        raise RuntimeError(
            "PCB-MAIN controlled footprint semantic mismatch: " + ", ".join(mismatched)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / PCB.name
            materialize(PCB, candidate)
            if candidate.read_bytes() != PCB.read_bytes():
                try:
                    verify_frozen_materialization(candidate)
                except RuntimeError as error:
                    raise SystemExit(
                        "PCB-MAIN controlled project-local footprints are stale: "
                        f"{error}"
                    ) from error
        print(
            "PCB-MAIN controlled project-local footprint materialization: PASS "
            "(accepted routing-lineage board hash; semantic footprint match)"
        )
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / PCB.name
            materialize(PCB, candidate)
            PCB.write_bytes(candidate.read_bytes())
        print("PCB-MAIN controlled project-local footprint materialization: UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

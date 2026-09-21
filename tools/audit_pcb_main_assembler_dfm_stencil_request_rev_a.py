#!/usr/bin/env python3
"""Audit the bounded PCB-MAIN assembler DFM/stencil request packet.

A PASS proves only that a source-bound request and blank external-response
register are ready.  It must never synthesize process parameters, release a
paste layer, close USB SI, sign Review B, or authorize manufacture.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
NATIVE_BOARD_BINDING = "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
ACTIVE_BOARD = ROOT / NATIVE_BOARD_BINDING
BOARD = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-001"
    / "PCB-MAIN_GROUND_DOMAIN_BASE_REV_A.kicad_pcb"
)
GROUND_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_APPLICATION_REV_A.json"
)
PLACEMENT = ROOT / "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv"
U2_FOOTPRINT = (
    ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty/"
    "Winbond_W25Q512JV_PackageF_IPC_Candidate.kicad_mod"
)
DRT_FOOTPRINT = (
    ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty/"
    "TI_DRT0003A_IPC_Candidate.kicad_mod"
)
U9_FOOTPRINT = (
    ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty/"
    "u-blox_MAX-M10S_LCC-18.kicad_mod"
)
IPC_AUTHORITY = ROOT / "hardware/PCB_MAIN_IPC_CANDIDATE_FOOTPRINTS_REV_A.md"
FOOTPRINT_DISPOSITION = ROOT / "hardware/reviews/PCB_MAIN_FOOTPRINT_DISPOSITION_REV_A.md"
FOOTPRINT_REVIEW = ROOT / "hardware/reviews/PCB_MAIN_KICAD_FOOTPRINT_REVIEW_REV_A.csv"
STORAGE_AUTHORITY = ROOT / "hardware/PCB_MAIN_STORAGE_SENSOR_AUTHORITY_REV_A.md"
GNSS_AUTHORITY = ROOT / "hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md"
PASSIVE_AUTHORITY = ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
PROCUREMENT = ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv"
RFQ = ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv"
DOUBLE_REVIEW = ROOT / "hardware/PCB_DOUBLE_REVIEW_GATE.md"
RELEASE_CHECKLIST = ROOT / "hardware/PCB_RELEASE_CHECKLIST.csv"
REVIEW_B_CHECKLIST = ROOT / "hardware/reviews/PCB_MAIN_REVIEW_B_CHECKLIST_REV_A.md"
RELEASE_GATE = ROOT / "hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md"
CONTRACT = ROOT / "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.json"
PACKET = ROOT / "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.md"
RESPONSE = ROOT / "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_RESPONSE_REV_A.csv"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
NATIVE_WORKFLOW = ROOT / ".github/workflows/pcb-native.yml"
HARDWARE_RELEASE_AUDIT = ROOT / "tools/audit_evt_pre_20_hardware_release.py"

ASSEMBLER_SLOT = "ASM-MAIN-CANDIDATE"
QUESTION_IDS = [
    "ASSEMBLER-IDENTITY",
    "PROCESS-BASELINE",
    "U2-LAND-ACCEPTANCE",
    "U2-MASK-RULE",
    "U2-STENCIL-APERTURE",
    "U2-INSPECTION-REWORK",
    "DRT-LAND-ACCEPTANCE",
    "DRT-MASK-STENCIL",
    "DRT-PLACEMENT-INSPECTION",
    "U9-STENCIL-FIG31",
    "U9-REFLOW-INSPECTION",
    "PNP-PIN1-POLARITY",
    "FIRST-ARTICLE-PLAN",
    "DFM-CLOSURE-TRACEABILITY",
]

AUTHORITY_INPUTS = [
    "hardware/PCB_MAIN_IPC_CANDIDATE_FOOTPRINTS_REV_A.md",
    "hardware/reviews/PCB_MAIN_FOOTPRINT_DISPOSITION_REV_A.md",
    "hardware/reviews/PCB_MAIN_KICAD_FOOTPRINT_REVIEW_REV_A.csv",
    "hardware/PCB_MAIN_STORAGE_SENSOR_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json",
    "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
    "hardware/CHINA_PROCUREMENT_RFQ.csv",
    "hardware/PCB_DOUBLE_REVIEW_GATE.md",
    "hardware/PCB_RELEASE_CHECKLIST.csv",
]

RESPONSE_FIELDS = [
    "Gate_ID",
    "Assembler_Slot",
    "Required_Party",
    "Requirement",
    "Required_Evidence",
    "Disposition",
    "Response_Value",
    "Response_Reference",
    "Responder",
    "Response_Date",
    "Blocking",
]

QUESTION_TOKENS = {
    "ASSEMBLER-IDENTITY": [
        "legal entity", "manufacturing site", "process engineer", "quotation",
        "assembly line", "process revision",
    ],
    "PROCESS-BASELINE": [
        "solder-paste", "alloy", "stencil", "thickness", "reflow-profile",
        "peak temperature", "time above liquidus",
    ],
    "U2-LAND-ACCEPTANCE": [
        "u2", "w25q512jvfiq", "2.05 x 0.60 mm", "1.27 mm", "9.30 mm",
        "heel toe and side", "numeric eco",
    ],
    "U2-MASK-RULE": [
        "u2", "solder-mask", "registration", "minimum-dam", "numeric openings",
    ],
    "U2-STENCIL-APERTURE": [
        "u2", "stencil aperture", "reduction", "area ratio", "paste-transfer",
    ],
    "U2-INSPECTION-REWORK": [
        "u2", "coplanarity", "solder-joint inspection", "acceptance criteria", "rework",
    ],
    "DRT-LAND-ACCEPTANCE": [
        "u25 and u26", "drt0003a", "0.30 x 0.30 mm", "package tolerance",
        "numeric eco",
    ],
    "DRT-MASK-STENCIL": [
        "u25 and u26", "solder-mask", "minimum dam", "stencil apertures",
        "area ratio", "paste-release",
    ],
    "DRT-PLACEMENT-INSPECTION": [
        "u25 and u26", "pin-1", "flow-through", "bridging", "open detection",
        "without claiming usb signal-integrity acceptance",
    ],
    "U9-STENCIL-FIG31": [
        "u9", "max-m10s-00b", "eighteen-aperture", "figure 31", "coordinate",
        "area reduction", "paste-transfer",
    ],
    "U9-REFLOW-INSPECTION": [
        "u9", "reflow profile", "coplanarity", "pin-1", "bridging", "voiding",
        "rf-zone cleanliness", "rework",
    ],
    "PNP-PIN1-POLARITY": [
        "rotation convention", "u2 u25 u26 and u9", "centroid", "pin-1",
        "assembly drawing", "pick-and-place",
    ],
    "FIRST-ARTICLE-PLAN": [
        "first-article quantity", "inspection", "acceptance limits", "rework",
        "hold point", "without creating a purchase authorization",
    ],
    "DFM-CLOSURE-TRACEABILITY": [
        "unique id", "severity", "owner", "disposition", "paste", "stencil",
        "profile", "close every blocker or critical",
    ],
}

CONTROLLED_SOURCES = [
    ACTIVE_BOARD,
    BOARD,
    GROUND_APPLICATION,
    PLACEMENT,
    U2_FOOTPRINT,
    DRT_FOOTPRINT,
    U9_FOOTPRINT,
    IPC_AUTHORITY,
    FOOTPRINT_DISPOSITION,
    FOOTPRINT_REVIEW,
    STORAGE_AUTHORITY,
    GNSS_AUTHORITY,
    PASSIVE_AUTHORITY,
    STATUS,
    PROCUREMENT,
    RFQ,
    DOUBLE_REVIEW,
    RELEASE_CHECKLIST,
    REVIEW_B_CHECKLIST,
    RELEASE_GATE,
    CONTRACT,
    PACKET,
    RESPONSE,
    CI_WORKFLOW,
    NATIVE_WORKFLOW,
    HARDWARE_RELEASE_AUDIT,
    Path(__file__).resolve(),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None, f"CSV header missing: {relative(path)}")
        return list(reader.fieldnames), list(reader)


def validate_git_binding(commit_sha: str, require_clean_source: bool) -> None:
    require(re.fullmatch(r"[0-9a-f]{40}", commit_sha) is not None,
            f"invalid evidence commit SHA: {commit_sha!r}")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    require(head == commit_sha, f"evidence commit {commit_sha} != checked-out HEAD {head}")
    if require_clean_source:
        dirty = subprocess.check_output(
            [
                "git", "status", "--porcelain", "--",
                *[relative(path) for path in CONTROLLED_SOURCES],
            ],
            cwd=ROOT,
            text=True,
        ).strip()
        require(not dirty, f"controlled assembler-request source set is dirty: {dirty}")


def footprint_reference(footprint: Any) -> str:
    references = [
        item.text for item in footprint.graphicItems
        if item.__class__.__name__ == "FpText" and item.type == "reference"
    ]
    require(len(references) == 1, "footprint has missing or duplicate reference text")
    return str(references[0])


def footprint_value(footprint: Any) -> str:
    values = [
        item.text for item in footprint.graphicItems
        if item.__class__.__name__ == "FpText" and item.type == "value"
    ]
    require(len(values) == 1, "footprint has missing or duplicate value text")
    return str(values[0])


def require_close(actual: float, expected: float, message: str) -> None:
    require(abs(float(actual) - expected) < 0.002,
            f"{message}: {actual} != {expected}")


def validate_source_binding(contract: dict[str, Any]) -> None:
    for path in CONTROLLED_SOURCES:
        require(path.is_file(), f"controlled source is missing: {relative(path)}")
    require(contract.get("authority_inputs") == AUTHORITY_INPUTS,
            "assembler request authority-input set mismatch")
    for item in AUTHORITY_INPUTS:
        require((ROOT / item).is_file(), f"authority input is missing: {item}")
    require(contract.get("source_binding") == {
        "native_board": NATIVE_BOARD_BINDING,
        "native_board_sha256": sha256(BOARD),
        "placement_manifest": relative(PLACEMENT),
        "placement_manifest_sha256": sha256(PLACEMENT),
        "u2_footprint": relative(U2_FOOTPRINT),
        "u2_footprint_sha256": sha256(U2_FOOTPRINT),
        "u25_u26_footprint": relative(DRT_FOOTPRINT),
        "u25_u26_footprint_sha256": sha256(DRT_FOOTPRINT),
        "u9_footprint": relative(U9_FOOTPRINT),
        "u9_footprint_sha256": sha256(U9_FOOTPRINT),
        "ipc_candidate_authority": relative(IPC_AUTHORITY),
        "ipc_candidate_authority_sha256": sha256(IPC_AUTHORITY),
        "footprint_disposition": relative(FOOTPRINT_DISPOSITION),
        "footprint_disposition_sha256": sha256(FOOTPRINT_DISPOSITION),
        "footprint_review_register": relative(FOOTPRINT_REVIEW),
        "footprint_review_register_sha256": sha256(FOOTPRINT_REVIEW),
    }, "assembler request source-hash binding mismatch")
    application = json.loads(GROUND_APPLICATION.read_text(encoding="utf-8"))
    require(application.get("historical_baseline") == {
                "board": relative(BOARD),
                "board_sha256": sha256(BOARD),
                "track_segments": 0,
                "vias": 0,
                "copper_zones": 0,
            } and application.get("applied", {}).get("board") == NATIVE_BOARD_BINDING,
            "historical request baseline is not preserved by the ground-domain application")


def validate_board_geometry(contract: dict[str, Any]) -> dict[str, Any]:
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(len(board.traceItems) == 0 and len(board.zones) == 0,
            "assembler request must be revised when routed copper or zones appear")
    require(float(board.setup.packToMaskClearance or 0.0) == 0.0
            and board.setup.padToPasteClearance is None
            and board.setup.padToPasteClearanceRatio is None,
            "board-level mask/paste settings silently alter candidate geometry")
    footprints = {footprint_reference(fp): fp for fp in board.footprints}
    require(all(ref in footprints for ref in ("U2", "U25", "U26", "U9")),
            "assembler-request footprint set missing from native board")

    u2 = footprints["U2"]
    require(footprint_value(u2) == "W25Q512JVFIQ"
            and u2.entryName == "Winbond_W25Q512JV_PackageF_IPC_Candidate"
            and u2.properties.get("DIONEA_FOOTPRINT_STATUS") ==
            "PROJECT_IPC_PATTERN_CONTROLLED_ASSEMBLY_DFM_REQUIRED"
            and u2.properties.get("DIONEA_FOOTPRINT_SOURCE") ==
            "PROJECT_IPC_W25Q512JV_F_KICAD_GULLWING_ASSEMBLER_DFM_REQUIRED",
            "U2 identity or DFM-required disposition differs")
    u2_pads = {pad.number: pad for pad in u2.pads if pad.number}
    require(set(u2_pads) == {str(index) for index in range(1, 17)},
            "U2 pad set differs")
    for index in range(1, 17):
        pad = u2_pads[str(index)]
        expected_x = -4.65 if index <= 8 else 4.65
        expected_y = (
            -4.445 + (index - 1) * 1.27
            if index <= 8 else 4.445 - (index - 9) * 1.27
        )
        require_close(pad.position.X, expected_x, f"U2.{index} X")
        require_close(pad.position.Y, expected_y, f"U2.{index} Y")
        require_close(pad.size.X, 2.05, f"U2.{index} land X")
        require_close(pad.size.Y, 0.60, f"U2.{index} land Y")
        require(pad.shape == "roundrect" and pad.roundrectRatio == 0.25,
                f"U2.{index} corner rule differs")
        require(pad.layers == ["F.Cu", "F.Paste", "F.Mask"]
                and pad.solderMaskMargin is None
                and pad.solderPasteMargin is None
                and pad.solderPasteMarginRatio is None,
                f"U2.{index} native coextensive mask/paste state differs")

    expected_drt_nets = {
        "U25": {"1": "USB_DP_CONN", "2": "USB_DM_CONN", "3": "GND_DIGITAL"},
        "U26": {"1": "CELL_USB_DP_TP", "2": "CELL_USB_DM_TP", "3": "GND_MODEM"},
    }
    expected_drt_positions = {
        "1": (-0.35, 0.425), "2": (0.35, 0.425), "3": (0.0, -0.425),
    }
    for ref in ("U25", "U26"):
        fp = footprints[ref]
        require(footprint_value(fp) == "TPD2EUSB30DRTR"
                and fp.entryName == "TI_DRT0003A_IPC_Candidate"
                and fp.properties.get("DIONEA_FOOTPRINT_STATUS") ==
                "PROJECT_IPC_PATTERN_CONTROLLED_ASSEMBLY_DFM_REQUIRED"
                and fp.properties.get("DIONEA_FOOTPRINT_SOURCE") ==
                "PROJECT_IPC_TI_DRT0003A_KICAD_DRT3_ASSEMBLER_DFM_REQUIRED",
                f"{ref} identity or DFM-required disposition differs")
        pads = {pad.number: pad for pad in fp.pads if pad.number}
        require(set(pads) == {"1", "2", "3"}, f"{ref} pad set differs")
        for number, (x, y) in expected_drt_positions.items():
            pad = pads[number]
            require_close(pad.position.X, x, f"{ref}.{number} X")
            require_close(pad.position.Y, y, f"{ref}.{number} Y")
            require_close(pad.size.X, 0.30, f"{ref}.{number} land X")
            require_close(pad.size.Y, 0.30, f"{ref}.{number} land Y")
            require(pad.shape == "roundrect" and pad.roundrectRatio == 0.25,
                    f"{ref}.{number} corner rule differs")
            require(pad.layers == ["F.Cu", "F.Paste", "F.Mask"]
                    and pad.solderMaskMargin is None
                    and pad.solderPasteMargin is None
                    and pad.solderPasteMarginRatio is None,
                    f"{ref}.{number} native coextensive mask/paste state differs")
            actual_net = pad.net.name if pad.net is not None else "NC"
            require(actual_net == expected_drt_nets[ref][number],
                    f"{ref}.{number} net differs: {actual_net}")

    u9 = footprints["U9"]
    require(footprint_value(u9) == "MAX-M10S-00B"
            and u9.entryName == "u-blox_MAX-M10S_LCC-18"
            and u9.properties.get("DIONEA_FOOTPRINT_STATUS") ==
            "MANUFACTURER_DRAWING_PATTERN_CONTROLLED"
            and u9.properties.get("DIONEA_FOOTPRINT_SOURCE") ==
            "u-blox_UBX-20053088_R05_Fig30_Table44",
            "U9 identity or manufacturer-drawing disposition differs")
    u9_pads = {pad.number: pad for pad in u9.pads if pad.number}
    require(set(u9_pads) == {str(index) for index in range(1, 19)},
            "U9 LCC-18 pad set differs")
    corner_pads = {"1", "9", "10", "18"}
    for number, pad in u9_pads.items():
        expected_width = 0.70 if number in corner_pads else 0.80
        require_close(pad.size.X, expected_width, f"U9.{number} land X")
        require_close(pad.size.Y, 1.80, f"U9.{number} land Y")
        require(pad.layers == ["F.Cu", "F.Mask"]
                and "F.Paste" not in pad.layers,
                f"U9.{number} must retain zero native paste aperture")
    require_close(u9_pads["1"].position.Y, 4.75, "U9 top row")
    require_close(u9_pads["10"].position.Y, -4.75, "U9 bottom row")
    for index in range(1, 9):
        require_close(abs(u9_pads[str(index)].position.X
                          - u9_pads[str(index + 1)].position.X),
                      1.10, f"U9 pitch {index}/{index + 1}")

    geometries = contract.get("candidate_geometries", {})
    u2_contract = geometries.get("u2", {})
    require(u2_contract.get("references") == ["U2"]
            and u2_contract.get("manufacturer") == "Winbond"
            and u2_contract.get("mpn") == "W25Q512JVFIQ"
            and u2_contract.get("package") == "SOIC-16_300mil_F"
            and u2_contract.get("pad_count") == 16
            and u2_contract.get("pad_pitch_mm") == 1.27
            and u2_contract.get("row_center_separation_mm") == 9.3
            and u2_contract.get("copper_land_mm") == [2.05, 0.6]
            and u2_contract.get("roundrect_radius_mm") == 0.15
            and u2_contract.get("manufacturer_complete_pcb_stencil_pattern_available") is False,
            "U2 machine-contract geometry differs")
    drt_contract = geometries.get("u25_u26", {})
    require(drt_contract.get("references") == ["U25", "U26"]
            and drt_contract.get("manufacturer") == "Texas Instruments"
            and drt_contract.get("mpn") == "TPD2EUSB30DRTR"
            and drt_contract.get("pad_count_each") == 3
            and drt_contract.get("pad_positions_mm") == {
                key: list(value) for key, value in expected_drt_positions.items()
            }
            and drt_contract.get("copper_land_mm") == [0.3, 0.3]
            and drt_contract.get("roundrect_radius_mm") == 0.075
            and drt_contract.get("reference_net_contract") == expected_drt_nets
            and drt_contract.get("manufacturer_complete_pcb_stencil_pattern_available") is False
            and drt_contract.get("usb_si_acceptance") == "SEPARATE_PROJECT_REVIEW_B_GATE",
            "U25/U26 machine-contract geometry or SI boundary differs")
    u9_contract = geometries.get("u9", {})
    require(u9_contract.get("references") == ["U9"]
            and u9_contract.get("manufacturer") == "u-blox"
            and u9_contract.get("mpn") == "MAX-M10S-00B"
            and u9_contract.get("pad_count") == 18
            and u9_contract.get("pad_pitch_mm") == 1.1
            and u9_contract.get("row_center_separation_mm") == 9.5
            and u9_contract.get("regular_copper_land_mm") == [0.8, 1.8]
            and u9_contract.get("corner_copper_land_mm") == [0.7, 1.8]
            and u9_contract.get("corner_pads") == ["1", "9", "10", "18"]
            and u9_contract.get("native_paste_state") ==
            "ABSENT_PROCESS_SPECIFIC_APERTURE_REQUIRED"
            and u9_contract.get("manufacturer_evidence_sha256") ==
            "5a7510ef84f7e2757c57e362a25e3c16bcf8c80af5a4f70790c2e51032dbcd13",
            "U9 machine-contract geometry or evidence differs")
    for item in (u2_contract, drt_contract):
        require(item.get("native_mask_state") ==
                "COEXTENSIVE_ZERO_LOCAL_MARGIN_CANDIDATE_NOT_APPROVED"
                and item.get("native_paste_state") ==
                "COEXTENSIVE_ZERO_LOCAL_REDUCTION_CANDIDATE_NOT_APPROVED",
                "candidate mask/paste release boundary differs")
    for key in ("land_acceptance", "mask_rule_accepted", "stencil_rule_accepted"):
        require(u2_contract.get(key) is False, f"U2 {key} advanced internally")
        require(drt_contract.get(key) is False, f"U25/U26 {key} advanced internally")
    require(drt_contract.get("placement_inspection_rule_accepted") is False,
            "U25/U26 placement/inspection rule advanced internally")
    require(u9_contract.get("stencil_rule_accepted") is False
            and u9_contract.get("reflow_inspection_rule_accepted") is False,
            "U9 external process gate advanced internally")

    return {
        "path": NATIVE_BOARD_BINDING,
        "historical_archive_path": relative(BOARD),
        "sha256": sha256(BOARD),
        "trace_items": len(board.traceItems),
        "copper_zones": len(board.zones),
        "scope_references": ["U2", "U25", "U26", "U9"],
        "u2_pad_count": len(u2_pads),
        "u25_pad_count": 3,
        "u26_pad_count": 3,
        "u9_pad_count": len(u9_pads),
        "u9_native_paste_apertures": 0,
    }


def validate_authorities_and_release(contract: dict[str, Any]) -> None:
    ipc = IPC_AUTHORITY.read_text(encoding="utf-8")
    disposition = FOOTPRINT_DISPOSITION.read_text(encoding="utf-8")
    storage = STORAGE_AUTHORITY.read_text(encoding="utf-8")
    gnss = GNSS_AUTHORITY.read_text(encoding="utf-8")
    require(all(token in ipc for token in (
        "Winbond_W25Q512JV_PackageF_IPC_Candidate",
        "TI_DRT0003A_IPC_Candidate",
        "assembly-house DFM",
        "stencil",
        "USB differential-impedance/SI evidence",
        "NOT FOR MANUFACTURE",
    )), "IPC-candidate authority no longer preserves assembly/USB interlocks")
    require(all(token in disposition for token in (
        "`U2/U25/U26`",
        "Paste geometry remains open",
        "u-blox UBX-20053088 R05 Figure 30 and Table 44",
        "assembly house accepts the land, solder-mask and stencil rules",
        "No Gerber, drill, paste, pick-and-place, IPC-356 or",
    )), "footprint disposition no longer preserves process-release interlocks")
    require("a898962af314ca90719eadba732e7f5fd42a1c48c4bfd283062c403d1c27bfd0"
            in storage and "Assembly-house land" in storage,
            "U2 package evidence or assembly gate differs")
    require("5a7510ef84f7e2757c57e362a25e3c16bcf8c80af5a4f70790c2e51032dbcd13"
            in gnss and "UBX-20053088 R05" in gnss,
            "U9 manufacturer evidence binding differs")

    _, review_rows = read_csv(FOOTPRINT_REVIEW)
    review_by_refs = {row["References"]: row for row in review_rows}
    require(review_by_refs.get("U2", {}).get("Review_Status") ==
            "PROJECT_IPC_CANDIDATE_DFM_REQUIRED"
            and review_by_refs.get("U2", {}).get("Board_Source") ==
            "PROJECT_IPC_W25Q512JV_F_KICAD_GULLWING_ASSEMBLER_DFM_REQUIRED"
            and "assembly-house DFM remains mandatory"
            in review_by_refs.get("U2", {}).get("Disposition", ""),
            "U2 footprint-review disposition differs")
    require(review_by_refs.get("U25;U26", {}).get("Review_Status") ==
            "PROJECT_IPC_CANDIDATE_DFM_REQUIRED"
            and review_by_refs.get("U25;U26", {}).get("Board_Source") ==
            "PROJECT_IPC_TI_DRT0003A_KICAD_DRT3_ASSEMBLER_DFM_REQUIRED"
            and "USB SI review remain mandatory"
            in review_by_refs.get("U25;U26", {}).get("Disposition", ""),
            "U25/U26 footprint-review disposition differs")

    _, passive_rows = read_csv(PASSIVE_AUTHORITY)
    passive = {row["RefDes"]: row for row in passive_rows}
    require(passive.get("U25", {}).get("MPN") == "TPD2EUSB30DRTR"
            and passive.get("U25", {}).get("Pin_Map") ==
            "1=USB_DP_CONN;2=USB_DM_CONN;3=GND"
            and passive.get("U26", {}).get("MPN") == "TPD2EUSB30DRTR"
            and passive.get("U26", {}).get("Pin_Map") ==
            "1=CELL_USB_DP_TP;2=CELL_USB_DM_TP;3=GND_MODEM",
            "U25/U26 electrical authority differs")

    _, procurement_rows = read_csv(PROCUREMENT)
    assembly_rows = [
        row for row in procurement_rows
        if row.get("Assemblies") == "PCB-MAIN" and row.get("Item_IDs") == "ASM-MAIN"
    ]
    require(len(assembly_rows) == 1,
            "PCB-MAIN assembly procurement row is missing or duplicated")
    assembly = assembly_rows[0]
    require(assembly.get("Assemblies") == "PCB-MAIN"
            and assembly.get("Item_IDs") == "ASM-MAIN"
            and assembly.get("Manufacturer") == "Dioneya controlled design"
            and assembly.get("MPN") == "DIO-ASM-MAIN-REV-A"
            and assembly.get("Status") ==
            "CONTROLLED_INTERNAL_ARTICLE_CUSTOMER_EMS_SELECTION_PENDING"
            and assembly.get("China_source_policy") ==
            "Customer-selected qualified EMS; quotation and purchase outside the engineering repository"
            and "AOI" in assembly.get("Incoming_control", ""),
            "PCB-MAIN selected-assembler procurement boundary differs")
    _, rfq_rows = read_csv(RFQ)
    rfq = {row["RFQ_ID"]: row for row in rfq_rows}
    main_assembly = rfq.get("RFQ-011", {})
    require(main_assembly.get("BOM_Item_IDs") == "ASM-MAIN"
            and main_assembly.get("Manufacturer") == "Dioneya controlled design"
            and main_assembly.get("MPN_or_spec", "").startswith(
                "DIO-ASM-MAIN-REV-A ")
            and main_assembly.get("Preferred_channel") ==
            "Customer-selected qualified EMS with AOI"
            and main_assembly.get("Status") == "RFQ_REQUIRED"
            and all(token in main_assembly.get("Blocking_check", "")
                    for token in ("DFM", "stencil", "traceability", "test coverage")),
            "RFQ-011 does not preserve assembler DFM/stencil requirements")

    double_review = DOUBLE_REVIEW.read_text(encoding="utf-8")
    require("Pick-and-place origin/rotation/side is checked" in double_review
            and "Assembly drawing shows reference designators, pin-1/polarity marks"
            in double_review
            and "Factory DFM review is archived" in double_review
            and "DFM response/closure" in double_review,
            "double-review gate does not preserve assembly DFM evidence")
    _, checklist_rows = read_csv(RELEASE_CHECKLIST)
    checklist = {row["Check_ID"]: row for row in checklist_rows}
    require(checklist.get("PCB-GEN-007", {}).get("Status") == "OPEN"
            and checklist.get("PCB-GEN-007", {}).get("Required_Evidence") ==
            "PnP review report",
            "PCB-GEN-007 PnP release gate was advanced or weakened")
    require(checklist.get("PCB-GEN-009", {}).get("Status") == "OPEN"
            and checklist.get("PCB-GEN-009", {}).get("Required_Evidence") ==
            "DFM report and dispositions",
            "PCB-GEN-009 DFM release gate was advanced or weakened")

    scope = contract.get("request_scope", {})
    require(scope == {
        "assembler_slot": ASSEMBLER_SLOT,
        "selected_assembler_identity_required": True,
        "response_valid_only_for_named_legal_entity_site_and_process": True,
        "references": ["U2", "U25", "U26", "U9"],
        "purpose": "LAND_MASK_STENCIL_PLACEMENT_INSPECTION_AND_FIRST_ARTICLE_PROCESS_REVIEW",
        "excluded_from_acceptance": [
            "PCB_ROUTING", "USB_SIGNAL_INTEGRITY", "FABRICATOR_STACKUP",
            "GERBER_OR_PASTE_EXPORT", "WHOLE_BOARD_DFM_CLOSURE",
            "REVIEW_B_SIGNATURE", "MANUFACTURING_RELEASE",
        ],
    }, "assembler request scope or excluded-gate boundary differs")
    interlock = contract.get("release_interlock", {})
    require(interlock == {
        "selected_assembler_identified": False,
        "u2_land_mask_stencil_accepted": False,
        "u25_u26_land_mask_stencil_accepted": False,
        "u9_stencil_reflow_inspection_accepted": False,
        "pnp_polarity_accepted": False,
        "first_article_plan_accepted": False,
        "blocker_critical_dfm_closed": False,
        "paste_export_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
        "fabrication_authorized": False,
    }, "assembler request release interlock differs")


def validate_process_and_response(contract: dict[str, Any]) -> dict[str, Any]:
    process = contract.get("process_baseline_request", {})
    nullable = [
        "assembler_legal_entity", "manufacturing_site", "process_owner",
        "quotation_reference", "assembly_line", "paste_manufacturer_product",
        "paste_alloy_and_type", "stencil_material", "stencil_thickness_mm",
        "aperture_cut_and_finish", "step_stencil_or_local_support",
        "reflow_profile_identifier", "peak_temperature_c", "time_above_liquidus_s",
        "inspection_standard", "first_article_quantity",
    ]
    require(set(process) == set(nullable) | {"numeric_process_parameters_frozen"},
            "process-baseline field set differs")
    require(all(process.get(key) is None for key in nullable),
            "internal packet guessed an external process parameter")
    require(process.get("numeric_process_parameters_frozen") is False,
            "process parameters were prematurely frozen")

    fields, rows = read_csv(RESPONSE)
    require(fields == RESPONSE_FIELDS, f"assembler response fields differ: {fields}")
    expected_gate_ids = [f"ASM-MAIN-{question}" for question in QUESTION_IDS]
    require(len(rows) == 14
            and [row.get("Gate_ID") for row in rows] == expected_gate_ids
            and len({row.get("Gate_ID") for row in rows}) == 14,
            "assembler response register is not the ordered 14-gate set")
    for question, row in zip(QUESTION_IDS, rows):
        gate_id = f"ASM-MAIN-{question}"
        require(row.get("Assembler_Slot") == ASSEMBLER_SLOT
                and row.get("Required_Party") == "SELECTED_ASSEMBLER",
                f"{gate_id}: assembler identity rule differs")
        requirement = row.get("Requirement", "")
        evidence = row.get("Required_Evidence", "")
        require(requirement and evidence, f"{gate_id}: requirement/evidence missing")
        lower = requirement.lower()
        require(all(token in lower for token in QUESTION_TOKENS[question]),
                f"{gate_id}: question semantics incomplete")
        require(row.get("Disposition") == "PENDING_EXTERNAL_RESPONSE"
                and row.get("Blocking") == "YES",
                f"{gate_id}: response row is not pending/blocking")
        require(all(not row.get(field) for field in (
            "Response_Value", "Response_Reference", "Responder", "Response_Date",
        )), f"{gate_id}: unsigned response fields are not blank")

    require(contract.get("required_question_ids") == QUESTION_IDS,
            "machine-contract assembler question set differs")
    external = contract.get("external_response", {})
    require(external == {
        "response_register": relative(RESPONSE),
        "required_rows": 14,
        "pending_rows": 14,
        "accepted_rows": 0,
        "selected_assembler_legal_entity": None,
        "selected_manufacturing_site": None,
        "selected_process_revision": None,
        "complete": False,
    }, "machine-contract assembler response state differs")
    return {
        "path": relative(RESPONSE),
        "sha256": sha256(RESPONSE),
        "rows": len(rows),
        "pending_rows": len(rows),
        "accepted_rows": 0,
        "selected_assembler_legal_entity": None,
        "selected_manufacturing_site": None,
    }


def validate_status_packet_and_ci(contract: dict[str, Any]) -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    handoff = status.get("review_b", {}).get("evidence", {}).get(
        "assembler_dfm_stencil_handoff", {}
    )
    require(handoff == {
        "complete": False,
        "status": "PACKET_READY_SELECTED_ASSEMBLER_RESPONSE_REQUIRED",
        "internal_packet_complete": True,
        "packet": relative(PACKET),
        "machine_contract": relative(CONTRACT),
        "response_register": relative(RESPONSE),
        "audit": "artifacts/pcb_main_assembler_dfm_stencil_request_rev_a.json",
        "required_scope_references": ["U2", "U25", "U26", "U9"],
        "required_response_rows": 14,
        "accepted_response_rows": 0,
        "selected_assembler_legal_entity": None,
        "selected_manufacturing_site": None,
        "u2_land_mask_stencil_accepted": False,
        "u25_u26_land_mask_stencil_accepted": False,
        "u9_stencil_reflow_inspection_accepted": False,
        "pnp_polarity_accepted": False,
        "first_article_plan_accepted": False,
        "blocker_critical_dfm_closed": False,
        "paste_export_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }, "PCB-MAIN capture status assembler DFM/stencil handoff differs")
    require(status.get("review_b", {}).get("complete") is False
            and status.get("manufacturing_release") is False,
            "internal assembler request advanced Review B or manufacturing release")

    packet = PACKET.read_text(encoding="utf-8")
    packet_flat = " ".join(packet.split())
    source = contract["source_binding"]
    packet_tokens = [
        "NOT FOR MANUFACTURE",
        source["native_board_sha256"],
        source["placement_manifest_sha256"],
        source["u2_footprint_sha256"],
        source["u25_u26_footprint_sha256"],
        source["u9_footprint_sha256"],
        source["ipc_candidate_authority_sha256"],
        source["footprint_disposition_sha256"],
        source["footprint_review_register_sha256"],
        "ASM-MAIN-CANDIDATE",
        "not a selected supplier",
        "deliberately `null`",
        "sixteen 2.05 x 0.60 mm",
        "three 0.30 x 0.30 mm",
        "zero `F.Paste` apertures",
        "All 14 rows",
        "USB impedance, routing or signal-integrity review",
        "does not close USB SI",
        relative(RESPONSE),
    ]
    require(all(" ".join(token.split()) in packet_flat for token in packet_tokens),
            "human-readable assembler DFM/stencil packet is incomplete")

    review_b = REVIEW_B_CHECKLIST.read_text(encoding="utf-8")
    release_gate = RELEASE_GATE.read_text(encoding="utf-8")
    require("0/14 accepted assembler responses" in review_b,
            "Review-B checklist does not expose pending assembler responses")
    require("0/14 assembler DFM/stencil responses accepted" in release_gate,
            "hardware release gate does not expose pending assembler responses")

    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    native = NATIVE_WORKFLOW.read_text(encoding="utf-8")
    command = "audit_pcb_main_assembler_dfm_stencil_request_rev_a.py"
    require(command in ci and command in native,
            "assembler request audit is not enforced by both CI workflows")
    for workflow, name in ((ci, "CI"), (native, "PCB Native Gate")):
        require("--commit-sha \"$GITHUB_SHA\"" in workflow
                and "--require-clean-source" in workflow,
                f"{name} lacks commit/clean-source audit binding")
    for source_path in (relative(CONTRACT), relative(PACKET), relative(RESPONSE)):
        require(source_path in ci and source_path in native,
                f"workflow artifact/source coverage missing for {source_path}")
    hardware_release = HARDWARE_RELEASE_AUDIT.read_text(encoding="utf-8")
    require("pcb_main_assembler_dfm_stencil_request_packet" in hardware_release
            and "pcb_main_assembler_dfm_stencil_acceptance" in hardware_release
            and "accepted_response_rows" in hardware_release,
            "hardware production-release audit does not enforce assembler acceptance")


def audit(commit_sha: str, require_clean_source: bool) -> dict[str, Any]:
    validate_git_binding(commit_sha, require_clean_source)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract.get("schema") == "dioneya-pcb-main-assembler-dfm-stencil-request-v1"
            and contract.get("configuration") == "EVT-PRE-20 Rev.A"
            and contract.get("assembly") == "PCB-MAIN"
            and contract.get("revision") == "A",
            "assembler DFM/stencil request identity mismatch")
    require(contract.get("status") ==
            "PACKET_READY_SELECTED_ASSEMBLER_RESPONSE_REQUIRED_NOT_FOR_PASTE_RELEASE_OR_MANUFACTURE",
            "assembler DFM/stencil request status is not bounded")
    validate_source_binding(contract)
    board = validate_board_geometry(contract)
    validate_authorities_and_release(contract)
    response = validate_process_and_response(contract)
    validate_status_packet_and_ci(contract)
    return {
        "schema": "dioneya-pcb-main-assembler-dfm-stencil-request-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "status": "PASS_PACKET_READY_SELECTED_ASSEMBLER_RESPONSE_REQUIRED",
        "evidence_commit_sha": commit_sha,
        "board": board,
        "external_response_register": response,
        "source_hashes": {
            relative(path): sha256(path) for path in CONTROLLED_SOURCES
        },
        "selected_assembler_identified": False,
        "process_parameters_frozen": False,
        "paste_export_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
        "fabrication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--commit-sha")
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args()
    commit_sha = args.commit_sha or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    try:
        report = audit(commit_sha, args.require_clean_source)
    except Exception as exc:
        report = {
            "schema": "dioneya-pcb-main-assembler-dfm-stencil-request-audit-v1",
            "configuration": "EVT-PRE-20 Rev.A",
            "assembly": "PCB-MAIN",
            "status": "FAIL_ASSEMBLER_DFM_STENCIL_REQUEST_AUDIT",
            "evidence_commit_sha": commit_sha,
            "error": f"{type(exc).__name__}: {exc}",
            "paste_export_authorized": False,
            "review_b_complete": False,
            "manufacturing_release": False,
            "fabrication_authorized": False,
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"PCB-MAIN assembler DFM/stencil request audit FAIL: {exc}")
        return 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN assembler DFM/stencil request audit: PASS")
    print(
        "references=4 response_rows=14 accepted=0 selected_assembler=false "
        "u9_native_paste_apertures=0 paste_export_authorized=false "
        "manufacturing_release=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

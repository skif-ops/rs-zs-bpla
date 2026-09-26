#!/usr/bin/env python3
"""Audit application of the accepted PCB-MAIN OctoSPI R8 ECO-002 subgate."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

from kiutils.board import Board

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")) if str(ROOT / "tools") not in sys.path else None
import pcb_main_lineage_rev_a as _lineage  # noqa: E402  (PCB-MAIN 003: earlier sub-gates read the predecessor)
BOARD = _lineage.historical_board()
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-OCTOSPI-R8-ECO-002/"
    "PCB-MAIN_OCTOSPI_R8_ECO_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-OCTOSPI-R8-ECO-002/"
    "PCB-MAIN_OCTOSPI_R8_ECO_CANDIDATE_REV_A.kicad_pcb"
)
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_CANDIDATE_REV_A.json"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_APPROVAL_REV_A.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_APPLICATION_REV_A.json"
SIGNAL_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_SIGNAL_HARD_NETS_ROUTING_APPLICATION_REV_A.json"
)
RF_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001/"
    "PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb"
)
RF_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_APPLICATION_REV_A.json"
PLACEMENT = _lineage.historical_placement()
STATUS = _lineage.historical_status()

BASE_SHA256 = "7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3"
CANDIDATE_SHA256 = "04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f"
RF_CANDIDATE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
ACTIVE_BOARD_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
USB_AUTHORIZED_MODIFIED_TSTAMPS = {
    "bbd350c1-609d-43b7-9dd0-824ee009466f",
    "fb9ade5d-8496-4617-9d20-390d44c347c4",
}
PLACEMENT_SHA256 = "70b453c77745580f16d571c999eeb0cde3f5581db69568668131dbe84ab20925"
ACTIVE_PLACEMENT_SHA256 = "df7cdbfc2ac023d43ac040b14eb99440fc392d402793d5a3b03f2fd560af6a6f"
APPROVAL_SHA256 = "55058d20783f99d129f68c1f107537fe8661919aad6e4aaf7557a0f2d0606ebf"
REVIEWED_COMMIT = "0104cf1bddd28f6bd4b0abc52d8b12bc6cc8cf67"
REVIEWED_TREE = "8a6d4b82727df6449db731a5aea47290e01cc1df"
APPROVAL_COMMIT = "1cf7c346f32a9bce5518ae5110cda753804fa23c"
DECISION = "ACCEPT_LIMITED_OCTOSPI_R8_PLACEMENT_ECO_AND_ROUTING_SUBGATE"
APPLICATION_STATUS = (
    "APPLIED_ACCEPTED_OCTOSPI_R8_ECO_002_SUBGATE_ROUTING_ENGINEERING_CONTINUES"
)
ROUTED_NETS = [
    "NOR_CLK_U1", "NOR_CLK_U2", "NOR_IO0_U1", "NOR_IO0_U2",
    "NOR_IO1_U1", "NOR_IO1_U2", "NOR_IO2_U1", "NOR_IO2_U2",
    "NOR_IO3_U1", "NOR_IO3_U2", "NOR_NCS_U2",
]


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref_of(footprint: Any) -> str:
    return next(
        (
            str(item.text)
            for item in footprint.graphicItems
            if getattr(item, "type", None) == "reference"
        ),
        "",
    )


def audit() -> dict[str, Any]:
    for path in (
        BOARD, BASE, CANDIDATE, PROPOSAL, APPROVAL, MAPPING, APPLICATION,
        SIGNAL_APPLICATION, RF_CANDIDATE, RF_APPLICATION, PLACEMENT, STATUS,
    ):
        require(path.is_file() and path.stat().st_size > 0, f"missing application input: {path}")

    require(sha256(BASE) == BASE_SHA256, "reviewed OctoSPI base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "reviewed OctoSPI candidate SHA-256 drift")
    require(sha256(RF_CANDIDATE) == RF_CANDIDATE_SHA256 and
            sha256(BOARD) == ACTIVE_BOARD_SHA256,
            "authoritative PCB-MAIN RF-remediation successor hash drift")
    require(sha256(PLACEMENT) == ACTIVE_PLACEMENT_SHA256,
            "active placement manifest SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "signed approval SHA-256 drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    require(
        approval.get("proposal_id") == "PCB-MAIN-OCTOSPI-R8-ECO-002"
        and approval.get("reviewer") == "Скиф"
        and approval.get("decision_date") == "2026-09-19"
        and approval.get("decision") == DECISION
        and approval.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and approval.get("reviewed_tree_sha") == REVIEWED_TREE
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and approval.get("authorization", {}).get(
            "apply_exact_hash_bound_r8_placement_and_octospi_routes"
        ) is True
        and approval.get("authorization", {}).get("routing_complete") is False
        and approval.get("authorization", {}).get("review_b_complete") is False
        and approval.get("authorization", {}).get("cam_or_manufacturing_release") is False,
        "OctoSPI approval identity, scope, or release boundary drift",
    )

    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    require(
        mapping.get("proposal_id") == "PCB-MAIN-OCTOSPI-R8-ECO-002"
        and mapping.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and mapping.get("reviewed_tree_sha") == REVIEWED_TREE
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS"
        and mapping.get("review_b_complete") is False
        and mapping.get("manufacturing_release") is False,
        "OctoSPI review-commit mapping drift",
    )

    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    applied = application.get("applied", {})
    require(
        application.get("proposal_id") == "PCB-MAIN-OCTOSPI-R8-ECO-002"
        and application.get("approval") == str(APPROVAL.relative_to(ROOT))
        and application.get("reviewed_proposal_commit_sha") == REVIEWED_COMMIT
        and application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and application.get("decision") == DECISION
        and application.get("scope") ==
        "EXACT_R8_PLACEMENT_ECO_AND_ELEVEN_NET_OCTOSPI_ROUTING_ONLY"
        and application.get("routed_nets") == ROUTED_NETS
        and application.get("status") == APPLICATION_STATUS
        and application.get("remaining_signal_and_power_routing_continuation_authorized") is True
        and application.get("routing_complete") is False
        and application.get("return_path_review_complete") is False
        and application.get("si_review_complete") is False
        and application.get("pi_review_complete") is False
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False,
        "OctoSPI application binding or release boundary drift",
    )
    require(
        application.get("historical_baseline", {}).get("board_sha256") == BASE_SHA256
        and applied.get("board") == "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
        and applied.get("board_sha256") == CANDIDATE_SHA256
        and applied.get("exact_candidate_byte_identity") is True
        and applied.get("placement_manifest_sha256") == PLACEMENT_SHA256
        and applied.get("r8_position_mm") == [54.5, 16.0]
        and applied.get("track_segments") == 553
        and applied.get("vias") == 285
        and applied.get("copper_zones") == 3
        and applied.get("mounting_rule_areas") == 4
        and applied.get("added_segments") == 132
        and applied.get("added_vias") == 22
        and applied.get("native_filled_connectivity_baseline_to_candidate") == [454, 444]
        and applied.get("kicad9_comparative_drc_violations_baseline_to_candidate") == [228, 226]
        and applied.get("new_comparative_drc_error_counts") == {},
        "OctoSPI applied geometry or comparative-gate evidence drift",
    )

    signal = json.loads(SIGNAL_APPLICATION.read_text(encoding="utf-8"))
    require(
        signal.get("applied", {}).get("board_sha256") == BASE_SHA256
        and signal.get("applied", {}).get("exact_candidate_byte_identity") is True
        and signal.get("routing_complete") is False
        and signal.get("review_b_complete") is False,
        "accepted signal-hard-nets predecessor evidence drift",
    )
    rf_application = json.loads(RF_APPLICATION.read_text(encoding="utf-8"))
    require(
        rf_application.get("historical_baseline", {}).get("board_sha256") ==
        CANDIDATE_SHA256
        and rf_application.get("applied", {}).get("board_sha256") ==
        RF_CANDIDATE_SHA256
        and rf_application.get("applied", {}).get("exact_candidate_byte_identity") is True
        and rf_application.get("routing_complete") is False
        and rf_application.get("review_b_complete") is False,
        "accepted RF successor evidence drift",
    )

    with PLACEMENT.open(encoding="utf-8", newline="") as stream:
        placement = {row["RefDes"]: row for row in csv.DictReader(stream)}
    require(
        placement.get("R8", {}).get("X_mm") == "54.5"
        and placement.get("R8", {}).get("Y_mm") == "16"
        and placement.get("R8", {}).get("Rotation_deg") == "0",
        "R8 placement-manifest application drift",
    )

    board = Board.from_file(str(BOARD), encoding="utf-8")
    octospi_candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    accepted_items = {str(item.tstamp): item for item in octospi_candidate.traceItems}
    active_items = {str(item.tstamp): item for item in board.traceItems}
    authorized_removed = {
        "8bb16eba-0c23-436c-83cb-15711942aa13",
        "97b4ffd7-640c-458b-a674-df70012edd9e",
        "e4d5b871-eae5-40c8-bc94-33070afaccfd",
        "ed333547-457e-4a27-b04c-76eefac1703b",
        "f0cf6fbe-b2d3-49cb-ac31-38e0b70d131a",
        "1b0fbb03-8a78-4e3f-b887-5b3096c609de",
        "3b6e7ac6-f2af-49e1-bbb9-dd1c158f1517",
        "72553cba-285e-40e8-afa0-669c5c279833",
    }
    require(
        set(accepted_items) - set(active_items) == authorized_removed
        and all(
            accepted_items[key] == active_items[key]
            for key in set(accepted_items) & set(active_items)
            if str(key) not in USB_AUTHORIZED_MODIFIED_TSTAMPS
        ),
        "accepted OctoSPI copper changed outside the authorized GNSS fanout delta",
    )
    accepted_zones = {str(item.tstamp): item for item in octospi_candidate.zones}
    active_zones = {str(item.tstamp): item for item in board.zones}
    require(
        set(accepted_zones) <= set(active_zones)
        and all(accepted_zones[key] == active_zones[key] for key in accepted_zones),
        "accepted ground zones changed outside cellular L2 composition",
    )
    segments = [item for item in board.traceItems if type(item).__name__ == "Segment"]
    vias = [item for item in board.traceItems if type(item).__name__ == "Via"]
    length = sum(
        math.hypot(
            float(item.end.X) - float(item.start.X),
            float(item.end.Y) - float(item.start.Y),
        )
        for item in segments
    )
    footprints = {ref_of(fp): fp for fp in board.footprints}
    r8 = footprints["R8"]
    require(
        len(board.traceItems) == 1023
        and len(segments) == 738
        and len(vias) == 285
        and len(board.zones) == 8
        and abs(length - 1059.4540078755238) < 1e-9
        and (float(r8.position.X), float(r8.position.Y)) == (54.5, 16.0),
        "authoritative RF successor board inventory or R8 position drift",
    )

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    review_b = status.get("review_b", {})
    evidence = review_b.get("evidence", {})
    control = evidence.get("routing_constraint_control", {})
    require(
        review_b.get("complete") is False
        and review_b.get("status") ==
        "OPEN_HIERARCHY_ACCEPTED_PLACEMENT_CLEARANCE_PASS_RF_REMEDIATION_"
        "REPEAT_REVIEW_PASS_USB_MCU_SOURCE_CELL_MODEM_AND_CELL_FIXTURE_"
        "APPLIED_MAIN_CONNECTOR_ROUTING_PENDING"
        and evidence.get("octospi_r8_eco_002_application") == str(APPLICATION.relative_to(ROOT))
        and evidence.get("octospi_r8_eco_002_status") ==
        "APPROVED_APPLIED_BOUNDED_R8_PLACEMENT_AND_OCTOSPI_ROUTING_"
        "SUBGATE_REMAINING_ROUTING_ENGINEERING_CONTINUES"
        and evidence.get("placement_clearance_control", {}).get("board_sha256") ==
        ACTIVE_BOARD_SHA256
        and control.get("board_sha256") == ACTIVE_BOARD_SHA256
        and control.get("trace_items") == 1023
        and control.get("octospi_r8_eco_002_subgate") ==
        "APPLIED_EXACT_ACCEPTED_CANDIDATE"
        and control.get("routing_complete") is False
        and control.get("manufacturing_release") is False
        and status.get("manufacturing_release") is False,
        "PCB-MAIN capture-status OctoSPI application boundary drift",
    )

    return {
        "schema_version": "dioneya.pcb-main-octospi-r8-eco-002-application-audit.v1",
        "proposal_id": "PCB-MAIN-OCTOSPI-R8-ECO-002",
        "status": "PASS_ACCEPTED_OCTOSPI_COPPER_PRESERVED_IN_RF_SUCCESSOR",
        "board_sha256": ACTIVE_BOARD_SHA256,
        "octospi_candidate_sha256": CANDIDATE_SHA256,
        "placement_manifest_sha256": ACTIVE_PLACEMENT_SHA256,
        "r8_position_mm": [54.5, 16.0],
        "track_segments": len(segments),
        "vias": len(vias),
        "trace_items": len(board.traceItems),
        "routed_nets": ROUTED_NETS,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print("PCB-MAIN OctoSPI R8 ECO-002 application audit: PASS")
    print("r8_position_mm=54.5,16.0 trace_items=1023 routed_nets=13 routing_complete=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

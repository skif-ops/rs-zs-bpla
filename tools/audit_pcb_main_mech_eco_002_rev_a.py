#!/usr/bin/env python3
"""Audit the signed PCB-MAIN-MECH-ECO-002 evidence and application.

The decision owns only the J_PWR and J6 mechanical-anchor translations.  H1 at
(8, 5) is retained from ECO-001.  The exact generated board is clearance
evidence, remains unrouted, and never implies Review B or manufacturing release.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path
from typing import Any

from kiutils.board import Board

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "hardware/reviews/PCB_MAIN_MECH_ECO_002_CANDIDATE.md"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_MECH_ECO_002_APPROVAL.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_MECH_ECO_002_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_MECH_ECO_002_APPLICATION.json"
AUTHORITY = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
PLACEMENT = ROOT / "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
ECO003_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_APPLICATION.json"
ECO004_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_STTS22H_FOOTPRINT_ECO_004_APPLICATION.json"
OCTOSPI_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_APPLICATION_REV_A.json"
RF_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_APPLICATION_REV_A.json"

CANDIDATE_SHA256 = "5164195ebf6a9a66b6a30197abfcb314655bfe059d0aea5f3782a744069780ff"
AUTHORITY_SHA256 = "8b3dbcb5b3fffe8ce393850e4fa65b178ea79c03b584c2f8b54e6fdfd93e42f9"
BOARD_SHA256 = "e81daf6d8cf0220f762c64f1fc637f65d71d6bc99128ab8c4993a540431e461e"
PLACEMENT_SHA256 = "dbc433cb36b0bec612f55dbb96e6dce34d502728e488810c115207ffbbebc1d1"
ECO003_BOARD_SHA256 = "dfcd8780cb3f189fe89cca98f32e3ee9693947a9a28d25e0154f7cce65d51684"
CURRENT_BOARD_SHA256 = "a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8"
OCTOSPI_BOARD_SHA256 = "04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f"
RF_P0_BOARD_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
ACTIVE_BOARD_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
CURRENT_PLACEMENT_SHA256 = "34abe08f925ec03f045b295d5c40a0391e0597a09ecdad5a7e563c93f53a62c4"
RF_P0_PLACEMENT_SHA256 = "70b453c77745580f16d571c999eeb0cde3f5581db69568668131dbe84ab20925"
ACTIVE_PLACEMENT_SHA256 = "df7cdbfc2ac023d43ac040b14eb99440fc392d402793d5a3b03f2fd560af6a6f"
REVIEWED_LOCAL_COMMIT = "16ee36b9432508b539736a8ee78890ad99ce0788"
REVIEWED_GITHUB_COMMIT = "b3ab796bcdee727798a121d114605e7ba84d683a"
REVIEWED_TREE = "b5c2892d795389eb07a216139dc50f725a13e849"
CANDIDATE_BLOB = "8706f629af1b42418f7a6d9046af6d6816b39480"
APPROVAL_COMMIT = "228ceef4dc90e23603befaf9ae57608bc2e1190e"
APPLICATION_COMMIT = "f8884613729faa7d796649b661797cd920042b5d"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_object_exists(commit: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT, capture_output=True, check=False,
    ).returncode == 0


def git_text(commit: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    require(completed.returncode == 0, f"cannot read {path} from {commit}")
    return completed.stdout


def git_tree(commit: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    require(completed.returncode == 0, f"cannot resolve tree for {commit}")
    return completed.stdout.strip()


def git_blob_sha(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()


def csv_rows(text: str) -> dict[str, dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(text)))
    result = {row["Record_ID"]: row for row in rows}
    require(len(rows) == 70 and len(result) == 70,
            "MAIN-AUTH-011 record count or identity drift")
    return result


def ref_of(footprint: Any) -> str:
    ref = footprint.properties.get("Reference")
    if ref:
        return str(ref)
    for item in footprint.graphicItems:
        if getattr(item, "type", None) == "reference":
            return str(item.text)
    raise AssertionError("footprint reference is missing")


def close(first: float, second: float, tolerance: float = 0.002) -> bool:
    return abs(float(first) - float(second)) <= tolerance


def audit() -> dict[str, Any]:
    for path in (CANDIDATE, APPROVAL, MAPPING, APPLICATION, AUTHORITY, BOARD,
                 PLACEMENT, STATUS):
        require(path.is_file() and path.stat().st_size > 0, f"missing ECO-002 evidence: {path}")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "PCB-MAIN ECO-002 candidate SHA-256 drift")
    require(sha256(AUTHORITY) == AUTHORITY_SHA256,
            "PCB-MAIN ECO-002 authority SHA-256 drift")
    historical_board = git_text(APPLICATION_COMMIT, str(BOARD.relative_to(ROOT))).encode("utf-8")
    historical_placement = git_text(
        APPLICATION_COMMIT, str(PLACEMENT.relative_to(ROOT))
    ).encode("utf-8")
    require(hashlib.sha256(historical_board).hexdigest() == BOARD_SHA256,
            "PCB-MAIN ECO-002 historical generated-board SHA-256 drift")
    require(hashlib.sha256(historical_placement).hexdigest() == PLACEMENT_SHA256,
            "PCB-MAIN ECO-002 historical placement-repack SHA-256 drift")
    require(ECO003_APPLICATION.is_file(),
            "PCB-MAIN ECO-003 application is missing from the current placement lineage")
    require(ECO004_APPLICATION.is_file(),
            "PCB-MAIN ECO-004 application is missing from the current footprint lineage")
    require(OCTOSPI_APPLICATION.is_file(),
            "PCB-MAIN OctoSPI application is missing from the current routing lineage")
    require(RF_APPLICATION.is_file(),
            "PCB-MAIN RF application is missing from the current routing lineage")
    eco003 = json.loads(ECO003_APPLICATION.read_text(encoding="utf-8"))
    require(eco003.get("proposal_id") == "PCB-MAIN-RF-ROUTEABILITY-ECO-003" and
            eco003.get("decision") == "ACCEPT_LIMITED_RF_ROUTEABILITY_ECO" and
            eco003.get("candidate_copper_final_authorized") is False and
            eco003.get("review_b_complete") is False and
            eco003.get("manufacturing_release") is False and
            eco003.get("applied", {}).get("board_sha256") == ECO003_BOARD_SHA256 and
            eco003.get("applied", {}).get("placement_repack_sha256") ==
            CURRENT_PLACEMENT_SHA256,
            "PCB-MAIN post-ECO-002 placement lineage drift")
    eco004 = json.loads(ECO004_APPLICATION.read_text(encoding="utf-8"))
    require(eco004.get("proposal_id") == "PCB-MAIN-STTS22H-FOOTPRINT-ECO-004" and
            eco004.get("decision") == "ACCEPT_STTS22H_FOOTPRINT_ECO_004" and
            eco004.get("candidate_or_future_copper_final_authorized") is False and
            eco004.get("review_b_complete") is False and
            eco004.get("cam_or_manufacturing_release") is False and
            eco004.get("applied", {}).get("board_sha256") == CURRENT_BOARD_SHA256 and
            eco004.get("applied", {}).get("changed_references") == ["U4"],
            "PCB-MAIN post-ECO-003 footprint lineage drift")
    octospi = json.loads(OCTOSPI_APPLICATION.read_text(encoding="utf-8"))
    require(octospi.get("proposal_id") == "PCB-MAIN-OCTOSPI-R8-ECO-002" and
            octospi.get("decision") ==
            "ACCEPT_LIMITED_OCTOSPI_R8_PLACEMENT_ECO_AND_ROUTING_SUBGATE" and
            octospi.get("applied", {}).get("board_sha256") == OCTOSPI_BOARD_SHA256 and
            octospi.get("applied", {}).get("placement_manifest_sha256") ==
            RF_P0_PLACEMENT_SHA256,
            "PCB-MAIN OctoSPI placement/routing successor lineage drift")
    rf_application = json.loads(RF_APPLICATION.read_text(encoding="utf-8"))
    require(rf_application.get("proposal_id") == "PCB-MAIN-RF-P0-001" and
            rf_application.get("decision") == "ACCEPT_RF_P0_ROUTING_SUBGATE" and
            rf_application.get("historical_baseline", {}).get("board_sha256") ==
            OCTOSPI_BOARD_SHA256 and
            rf_application.get("applied", {}).get("board_sha256") ==
            RF_P0_BOARD_SHA256 and
            rf_application.get("applied", {}).get("exact_candidate_byte_identity") is True and
            sha256(BOARD) == ACTIVE_BOARD_SHA256 and
            sha256(PLACEMENT) == ACTIVE_PLACEMENT_SHA256,
            "PCB-MAIN RF routing successor lineage drift")

    candidate = CANDIDATE.read_text(encoding="utf-8")
    require("PCB-MAIN mechanical ECO-002 candidate" in candidate and
            AUTHORITY_SHA256 in candidate and BOARD_SHA256 in candidate and
            "NOT A FABRICATION RELEASE" in candidate,
            "PCB-MAIN ECO-002 candidate identity or boundary drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    require(approval.get("proposal_id") == "PCB-MAIN-MECH-ECO-002" and
            approval.get("reviewer") == "Скиф" and
            approval.get("date") == "2026-09-18" and
            approval.get("decision") == "ACCEPT_LIMITED_MECHANICAL_ECO" and
            approval.get("scope") == "LIMITED_MECH_007_MECH_012_TRANSLATION_ONLY" and
            approval.get("approved_change_records") == ["MECH-007", "MECH-012"] and
            approval.get("reviewed_candidate_sha256") == CANDIDATE_SHA256 and
            approval.get("reviewed_authority_sha256") == AUTHORITY_SHA256 and
            approval.get("reviewed_board_sha256") == BOARD_SHA256 and
            approval.get("reviewed_placement_repack_sha256") == PLACEMENT_SHA256 and
            approval.get("implementation_authorized") is True and
            approval.get("routing_authorized") is False and
            approval.get("review_b_complete") is False and
            approval.get("manufacturing_release") is False,
            "PCB-MAIN ECO-002 approval binding drift")
    require(approval.get("approved_geometry") == {
                "MECH-007": {"refdes": "J_PWR", "from": [0.0, 15.0, 90.0],
                             "to": [0.0, 22.0, 90.0]},
                "MECH-012": {"refdes": "J6", "from": [18.0, 2.5, 180.0],
                             "to": [21.0, 2.5, 180.0]},
            }, "PCB-MAIN ECO-002 approved geometry drift")

    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    require(mapping.get("reviewed_local_commit_sha") == REVIEWED_LOCAL_COMMIT and
            mapping.get("github_equivalent_commit_sha") == REVIEWED_GITHUB_COMMIT and
            mapping.get("reviewed_tree_sha") == REVIEWED_TREE and
            mapping.get("candidate_blob_sha") == CANDIDATE_BLOB and
            mapping.get("candidate_sha256") == CANDIDATE_SHA256 and
            mapping.get("equivalence") == "EXACT_TREE_AND_CANDIDATE_BLOB" and
            mapping.get("routing_authorized") is False and
            mapping.get("review_b_complete") is False and
            mapping.get("manufacturing_release") is False,
            "PCB-MAIN ECO-002 commit mapping drift")
    present = [item for item in (REVIEWED_LOCAL_COMMIT, REVIEWED_GITHUB_COMMIT)
               if git_object_exists(item)]
    require(present, "no mapped PCB-MAIN ECO-002 reviewed commit is available")
    for commit in present:
        require(git_tree(commit) == REVIEWED_TREE,
                f"PCB-MAIN ECO-002 reviewed tree drift: {commit}")
        payload = git_text(commit, str(CANDIDATE.relative_to(ROOT))).encode("utf-8")
        require(hashlib.sha256(payload).hexdigest() == CANDIDATE_SHA256 and
                git_blob_sha(payload) == CANDIDATE_BLOB,
                f"PCB-MAIN ECO-002 reviewed candidate blob drift: {commit}")

    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    require(application.get("proposal_id") == "PCB-MAIN-MECH-ECO-002" and
            application.get("approval") == str(APPROVAL.relative_to(ROOT)) and
            application.get("reviewed_candidate_commit_sha") == REVIEWED_GITHUB_COMMIT and
            application.get("approval_commit_sha") == APPROVAL_COMMIT and
            application.get("reviewed_candidate_sha256") == CANDIDATE_SHA256 and
            application.get("decision") == "ACCEPT_LIMITED_MECHANICAL_ECO" and
            application.get("scope") == "LIMITED_MECH_007_MECH_012_TRANSLATION_ONLY" and
            application.get("status") ==
            "APPLIED_STRICT_2D_CLEARANCE_PASS_ROUTING_AND_3D_REVIEW_PENDING" and
            application.get("routing_authorized") is False and
            application.get("review_b_complete") is False and
            application.get("manufacturing_release") is False,
            "PCB-MAIN ECO-002 application binding or interlock drift")
    applied = application.get("applied", {})
    require(applied.get("authority_sha256") == AUTHORITY_SHA256 and
            applied.get("board_sha256") == BOARD_SHA256 and
            applied.get("placement_repack_sha256") == PLACEMENT_SHA256 and
            applied.get("changed_records") == ["MECH-007", "MECH-012"] and
            applied.get("retained_eco_001_baseline", {}).get("position_mm") == [8.0, 5.0],
            "PCB-MAIN ECO-002 applied-source record drift")

    baseline = csv_rows(git_text(REVIEWED_GITHUB_COMMIT, str(AUTHORITY.relative_to(ROOT))))
    live = csv_rows(AUTHORITY.read_text(encoding="utf-8"))
    changed: dict[str, set[str]] = {}
    for record_id in live:
        fields = {key for key in live[record_id]
                  if live[record_id][key] != baseline[record_id][key]}
        if fields:
            changed[record_id] = fields
    require(changed == {
                "MECH-003": {"X_mm", "Notes"},
                "MECH-007": {"Y_mm", "Notes"},
                "MECH-012": {"X_mm", "Notes"},
            }, f"PCB-MAIN ECO-002 authority delta drift: {changed!r}")
    require((live["MECH-003"]["RefDes"], live["MECH-003"]["X_mm"],
             live["MECH-003"]["Y_mm"]) == ("H1", "8.00", "5.00") and
            (live["MECH-007"]["RefDes"], live["MECH-007"]["X_mm"],
             live["MECH-007"]["Y_mm"], live["MECH-007"]["Rotation_deg"]) ==
            ("J_PWR", "0.00", "22.00", "90") and
            (live["MECH-012"]["RefDes"], live["MECH-012"]["X_mm"],
             live["MECH-012"]["Y_mm"], live["MECH-012"]["Rotation_deg"]) ==
            ("J6", "21.00", "2.50", "180"),
            "PCB-MAIN ECO-002 authority coordinates drift")

    board = Board.from_file(str(BOARD), encoding="utf-8")
    footprints = {ref_of(item): item for item in board.footprints}
    require(len(footprints) == 251 and len(footprints) == len(board.footprints),
            "PCB-MAIN ECO-002 board footprint set drift")
    h1, j_pwr, j6 = footprints["H1"], footprints["J_PWR"], footprints["J6"]
    require(close(h1.position.X, 8.0) and close(h1.position.Y, 5.0),
            "H1 retained ECO-001 position drift")
    require(close(j_pwr.position.X, 8.92) and close(j_pwr.position.Y, 29.5) and
            close(float(j_pwr.position.angle or 0.0) % 360.0, 90.0) and
            j_pwr.properties.get("DIONEA_MECHANICAL_ANCHOR") ==
            "0.000,22.000,90.000",
            "J_PWR ECO-002 anchor or footprint datum drift")
    require(close(j6.position.X, 21.0) and close(j6.position.Y, 8.5) and
            close(float(j6.position.angle or 0.0) % 360.0, 180.0) and
            j6.properties.get("DIONEA_MECHANICAL_ANCHOR") ==
            "21.000,2.500,180.000",
            "J6 ECO-002 anchor or footprint datum drift")
    require(len(getattr(board, "traceItems", [])) == 994 and
            len(getattr(board, "zones", [])) == 8,
            "PCB-MAIN post-ground-subgate routing inventory drift")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    evidence = status["review_b"]["evidence"]
    control = evidence["placement_clearance_control"]
    require(evidence.get("mechanical_eco_002_status") ==
            "APPROVED_APPLIED_PLACEMENT_REPACK_PASS" and
            control.get("state") == "PASS" and
            control.get("board_sha256") == ACTIVE_BOARD_SHA256 and
            control.get("authority_sha256") == AUTHORITY_SHA256 and
            status["review_b"].get("complete") is False and
            status.get("manufacturing_release") is False,
            "PCB-MAIN ECO-002 capture-status boundary drift")

    return {
        "schema_version": "dioneya.pcb-main-mech-eco-002-audit.v1",
        "proposal_id": "PCB-MAIN-MECH-ECO-002",
        "status": "PASS_APPROVED_APPLIED_STRICT_2D_CLEARANCE",
        "reviewer": "Скиф",
        "decision": "ACCEPT_LIMITED_MECHANICAL_ECO",
        "changed_records": ["MECH-007", "MECH-012"],
        "retained_eco_001_record": "MECH-003",
        "authority_sha256": AUTHORITY_SHA256,
        "historical_board_sha256": BOARD_SHA256,
        "historical_placement_repack_sha256": PLACEMENT_SHA256,
        "current_board_sha256": ACTIVE_BOARD_SHA256,
        "current_placement_repack_sha256": ACTIVE_PLACEMENT_SHA256,
        "routing_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    print("PCB-MAIN mechanical ECO-002 audit: PASS_APPROVED_APPLIED_STRICT_2D_CLEARANCE")
    print("changed_records=['MECH-007', 'MECH-012'] retained_eco_001=['MECH-003']")
    print("routing=false review_b=false manufacturing_release=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

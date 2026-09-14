#!/usr/bin/env python3
"""Audit the controlled PCB-MIC manufacturing handoff without granting release."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pcb"
DRU = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_dru"
METADATA = ROOT / "hardware/kicad/native/PCB-MIC/fabrication_metadata.json"
MECHANICAL_AUTHORITY = ROOT / "hardware/kicad/REV_A_CAPTURE_ADDENDUM_003_PCB_MIC_MECH.md"
RFQ = ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv"
DOUBLE_REVIEW_GATE = ROOT / "hardware/PCB_DOUBLE_REVIEW_GATE.md"
STATUS = ROOT / "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json"
CONTRACT = ROOT / "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.json"
PACKET = ROOT / "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.md"
RESPONSE = ROOT / "hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv"
NATIVE_GATE = ROOT / "tools/kicad_native_gate.py"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
NATIVE_WORKFLOW = ROOT / ".github/workflows/pcb-native.yml"

EXPECTED_GATES = {
    "FAB-STACKUP": "FABRICATOR",
    "FAB-GEOMETRY": "FABRICATOR",
    "FAB-FINE-FEATURE": "FABRICATOR",
    "FAB-NET-TEST": "FABRICATOR",
    "PANEL-DRAWING": "FABRICATOR",
    "PANEL-DEPANEL": "FABRICATOR_ASSEMBLER",
    "ASM-PLACEMENT": "ASSEMBLER",
    "ASM-ACOUSTIC-KEEPOUT": "ASSEMBLER",
    "DFM-CLOSURE": "FABRICATOR_ASSEMBLER",
}

EXPECTED_OUTPUTS = {
    "gerber/PCB-MIC-job.gbrjob",
    "drill/PCB-MIC.drl",
    "PCB-MIC.d356",
    "PCB-MIC_pos.csv",
    "PCB-MIC_manufacturing_bom.csv",
    "PCB-MIC_assembly_fabrication.pdf",
    "PCB-MIC_F_Cu_review.svg",
    "PCB-MIC_B_Cu_review.svg",
}

CONTROLLED_SOURCES = [
    BOARD,
    DRU,
    METADATA,
    MECHANICAL_AUTHORITY,
    RFQ,
    DOUBLE_REVIEW_GATE,
    STATUS,
    CONTRACT,
    PACKET,
    RESPONSE,
    NATIVE_GATE,
    CI_WORKFLOW,
    NATIVE_WORKFLOW,
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None, f"CSV header missing: {path}")
        return list(reader)


def audit(commit_sha: str, require_clean_source: bool) -> dict[str, Any]:
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
                *[str(path.relative_to(ROOT)) for path in CONTROLLED_SOURCES],
            ],
            cwd=ROOT,
            text=True,
        ).strip()
        require(not dirty, f"controlled manufacturing-handoff source set is dirty: {dirty}")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    packet = PACKET.read_text(encoding="utf-8")
    dru = DRU.read_text(encoding="utf-8")
    rows = read_csv(RESPONSE)

    require(contract.get("schema") == "dioneya-pcb-mic-manufacturing-handoff-v1",
            "unexpected manufacturing-handoff schema")
    require(contract.get("configuration") == "EVT-PRE-20 Rev.A"
            and contract.get("assembly") == "PCB-MIC"
            and contract.get("revision") == "A",
            "manufacturing-handoff identity mismatch")
    require(contract.get("status") ==
            "PACKET_READY_EXTERNAL_ACCEPTANCE_REQUIRED_NOT_FOR_MANUFACTURE",
            "manufacturing-handoff status is not bounded")
    require(contract.get("authority_inputs") == [
        str(MECHANICAL_AUTHORITY.relative_to(ROOT)),
        str(DRU.relative_to(ROOT)),
        str(RFQ.relative_to(ROOT)),
        str(DOUBLE_REVIEW_GATE.relative_to(ROOT)),
        str(STATUS.relative_to(ROOT)),
    ], "manufacturing-handoff authority set mismatch")

    source = contract.get("source_binding", {})
    review_a = status.get("review_a", {})
    review_b = status.get("review_b", {})
    copper_gate = review_b.get("copper_return_gate", {})
    require(source.get("native_board") == str(BOARD.relative_to(ROOT))
            and source.get("native_board_sha256") == sha256(BOARD),
            "handoff board binding mismatch")
    require(source.get("repeat_review_a_commit_sha") == review_a.get("commit_sha")
            and source.get("copper_return_decision_commit_sha") == copper_gate.get("commit_sha")
            and source.get("copper_return_acceptance_state_commit_sha") ==
            copper_gate.get("acceptance_state_evidence", {}).get("evidence_commit_sha"),
            "handoff review-decision binding mismatch")
    require(review_a.get("complete") is True and review_a.get("status") == "PASS",
            "repeat Review A is not signed PASS")
    require(copper_gate.get("complete") is True
            and copper_gate.get("decision") == "ACCEPT_COPPER_RETURN",
            "copper-return subgate is not accepted")
    require(review_b.get("complete") is False
            and status.get("manufacturing_release") is False,
            "handoff audit must not run as a release grant")

    board_contract = contract.get("board_contract", {})
    require(board_contract.get("coordinate_origin") == "LOWER_LEFT_OF_BOARD_OUTLINE"
            and board_contract.get("outline_mm") == [24.0, 22.0]
            and board_contract.get("thickness_mm") == 1.0
            and board_contract.get("copper_layers") == 2
            and board_contract.get("material") == "FR-4"
            and board_contract.get("surface_finish") == "ENIG",
            "unit-board fabrication contract mismatch")
    require(metadata.get("board") == "PCB-MIC"
            and metadata.get("revision") == "A"
            and metadata.get("board_thickness_mm") == board_contract.get("thickness_mm")
            and metadata.get("copper_layers") == board_contract.get("copper_layers")
            and metadata.get("material") == board_contract.get("material")
            and metadata.get("surface_finish") == board_contract.get("surface_finish")
            and metadata.get("status") == "NOT_FOR_MANUFACTURE",
            "fabrication metadata differs from the handoff contract")
    require(board_contract.get("acoustic_port") == {
        "type": "NPTH", "diameter_mm": 0.8, "x_mm": 12.0, "y_mm": 16.65,
    }, "acoustic-port contract mismatch")
    require(board_contract.get("mounting_holes") == [
        {"reference": "H1", "type": "NPTH", "diameter_mm": 2.2,
         "x_mm": 4.0, "y_mm": 16.65},
        {"reference": "H2", "type": "NPTH", "diameter_mm": 2.2,
         "x_mm": 20.0, "y_mm": 16.65},
    ], "mounting-hole contract mismatch")
    require(board_contract.get("fitted_top_references") == ["C1", "J1", "MK1", "R1"]
            and board_contract.get("fitted_bottom_references") == [],
            "assembly-side contract mismatch")

    process = contract.get("process_contract", {})
    fine_feature = process.get("t5838_local_clearance_rule", {})
    require(fine_feature.get("minimum_copper_clearance_mm") == 0.125
            and fine_feature.get("minimum_npth_to_copper_clearance_mm") == 0.1
            and fine_feature.get("fabricator_acceptance_required") is True,
            "T5838 fine-feature DFM contract mismatch")
    require("(constraint clearance (min 0.125mm))" in dru
            and "(constraint hole_clearance (min 0.10mm))" in dru
            and "PCB-fabricator DFM must confirm" in dru,
            "native DRU does not preserve the vendor-acceptance rule")
    acoustic = process.get("acoustic_path", {})
    required_obstructions = {
        "copper", "solder mask", "solder paste", "adhesive",
        "conformal coating", "membrane glue", "enclosure feature",
        "mounting screw", "washer", "metallic insert",
    }
    require(set(acoustic.get("prohibited_obstructions", [])) == required_obstructions
            and acoustic.get("assembler_process_acceptance_required") is True,
            "acoustic process-keepout contract mismatch")
    panel = process.get("panelization", {})
    require(panel.get("vendor_panel_drawing_required") is True
            and panel.get("tooling_rails_required") is True
            and panel.get("mems_safe_depanel_method_required") is True
            and panel.get("numerical_panel_geometry_frozen") is False,
            "panelization/depanel proposal interlock mismatch")
    require(process.get("electrical_test") ==
            "100_PERCENT_NET_TEST_AGAINST_CONTROLLED_IPC_356"
            and process.get("lot_traceability_required") is True,
            "fabrication test/traceability contract mismatch")
    rfq_rows = {row["RFQ_ID"]: row for row in read_csv(RFQ)}
    mic_rfq = rfq_rows.get("RFQ-024", {})
    require(mic_rfq.get("BOM_Item_IDs") == "PCB-MIC"
            and "24 x 22 x 1.0 mm ENIG" in mic_rfq.get("MPN_or_spec", "")
            and "100 percent net test" in mic_rfq.get("Blocking_check", "")
            and "panelization/depanel plan" in mic_rfq.get("Blocking_check", "")
            and "DFM" in mic_rfq.get("Blocking_check", ""),
            "PCB-MIC RFQ authority does not support the handoff contract")
    double_review = DOUBLE_REVIEW_GATE.read_text(encoding="utf-8")
    require("DFM response/closure" in double_review
            and "Factory DFM review is archived" in double_review,
            "double-review gate does not require a controlled DFM response")
    require(set(contract.get("controlled_candidate_outputs", [])) == EXPECTED_OUTPUTS,
            "controlled candidate-output set mismatch")
    require(contract.get("pcb_native_gate_bundle") == {
        "audit": "PCB-MIC/manufacturing_handoff_audit.json",
        "packet": "PCB-MIC/manufacturing-handoff/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.md",
        "machine_contract":
            "PCB-MIC/manufacturing-handoff/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.json",
        "response_register":
            "PCB-MIC/manufacturing-handoff/PCB_MIC_DFM_RESPONSE_REV_A.csv",
    }, "PCB Native Gate handoff-bundle path contract mismatch")

    external = contract.get("external_acceptance", {})
    require(external.get("response_register") == str(RESPONSE.relative_to(ROOT))
            and external.get("required_gate_ids") == list(EXPECTED_GATES),
            "external response-register binding mismatch")
    for key in (
        "fabricator_acceptance",
        "assembler_acceptance",
        "panelization_depanel_acceptance",
        "adhesive_conformal_coating_keepout_acceptance",
        "blocker_critical_dfm_closure",
    ):
        require(external.get(key) == "PENDING_EXTERNAL_ACCEPTANCE",
                f"external gate was advanced without a response: {key}")
    require(external.get("complete") is False,
            "external DFM acceptance was completed by an internal packet")

    by_gate = {row.get("Gate_ID", ""): row for row in rows}
    require(len(rows) == len(by_gate) == len(EXPECTED_GATES)
            and set(by_gate) == set(EXPECTED_GATES),
            "DFM response register gate set mismatch")
    for gate_id, party in EXPECTED_GATES.items():
        row = by_gate[gate_id]
        require(row.get("Required_Party") == party,
                f"{gate_id}: responsible party mismatch")
        require(bool(row.get("Requirement")) and bool(row.get("Required_Evidence")),
                f"{gate_id}: requirement/evidence text missing")
        require(row.get("Disposition") == "PENDING_EXTERNAL_ACCEPTANCE"
                and row.get("Blocking") == "YES",
                f"{gate_id}: response row is not blocking/pending")
        require(all(not row.get(field) for field in
                    ("Response_Reference", "Responder", "Response_Date")),
                f"{gate_id}: unsigned external response fields are not blank")

    packet_tokens = [
        "NOT FOR MANUFACTURE",
        source["native_board_sha256"],
        source["repeat_review_a_commit_sha"],
        source["copper_return_decision_commit_sha"],
        "0.125 mm minimum copper clearance",
        "0.10 mm minimum",
        "NPTH-to-copper clearance",
        "No panel array, rail width, tab location",
        "PENDING_EXTERNAL_ACCEPTANCE",
        str(RESPONSE.relative_to(ROOT)),
    ]
    require(all(token in packet for token in packet_tokens),
            "human-readable manufacturing packet is incomplete")

    handoff = review_b.get("manufacturing_handoff", {})
    require(handoff.get("status") == "PACKET_READY_EXTERNAL_ACCEPTANCE_REQUIRED"
            and handoff.get("internal_packet_complete") is True
            and handoff.get("complete") is False,
            "PCB-MIC status does not record bounded handoff readiness")
    for key in (
        "fabricator_dfm_acceptance",
        "assembler_dfm_acceptance",
        "panelization_acceptance",
        "depanel_acceptance",
        "assembler_process_keepout_acceptance",
    ):
        require(handoff.get(key) is False, f"status advanced external gate: {key}")
    interlock = contract.get("release_interlock", {})
    require(interlock == {
        "review_b_complete": False,
        "manufacturing_release": False,
        "fabrication_authorized": False,
    }, "manufacturing release interlock mismatch")

    return {
        "schema": "dioneya-pcb-mic-manufacturing-handoff-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MIC",
        "status": "PASS_PACKET_READY_EXTERNAL_ACCEPTANCE_REQUIRED",
        "evidence_commit_sha": commit_sha,
        "checks": {
            "source_binding": "PASS",
            "board_contract": "PASS",
            "fine_feature_vendor_acceptance_contract": "PASS_PENDING_EXTERNAL_ACCEPTANCE",
            "panelization_depanel_contract": "PASS_PACKET_READY_PENDING_EXTERNAL_ACCEPTANCE",
            "assembler_acoustic_process_contract": "PASS_PACKET_READY_PENDING_EXTERNAL_ACCEPTANCE",
            "response_register": {
                "status": "PASS_EMPTY_CONTROLLED_TEMPLATE",
                "rows": len(rows),
                "pending_external_acceptance": len(rows),
                "completed_external_acceptance": 0,
            },
        },
        "source_hashes": {
            str(path.relative_to(ROOT)): sha256(path) for path in CONTROLLED_SOURCES
        },
        "remaining_external_acceptance": list(EXPECTED_GATES),
        "remaining_non_vendor_gates": contract["remaining_non_vendor_gates"],
        "review_b_complete": False,
        "manufacturing_release": False,
        "fabrication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit-sha")
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    commit_sha = args.commit_sha or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    try:
        report = audit(commit_sha, args.require_clean_source)
    except Exception as exc:
        report = {
            "schema": "dioneya-pcb-mic-manufacturing-handoff-audit-v1",
            "configuration": "EVT-PRE-20 Rev.A",
            "assembly": "PCB-MIC",
            "status": "FAIL_MANUFACTURING_HANDOFF_AUDIT",
            "evidence_commit_sha": commit_sha,
            "error": f"{type(exc).__name__}: {exc}",
            "review_b_complete": False,
            "manufacturing_release": False,
            "fabrication_authorized": False,
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"PCB-MIC manufacturing handoff audit FAIL: {exc}")
        return 1
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-MIC manufacturing handoff audit PASS: packet ready")
    print("Fabricator/assembler acceptance, Review B and manufacturing release remain OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

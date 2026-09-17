#!/usr/bin/env python3
"""Audit PCB-PWR pre-purchase identity and first-lot receiving controls.

This audit closes only the documentary subgate of PWR-IPQ-002. The matrix row
stays pending until the actual EVT lot is received, photographed and traced.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.json"
)
EVIDENCE_MD = (
    ROOT
    / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.md"
)
CONTRACT = ROOT / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_QUALIFICATION_REV_A.json"
MATRIX = ROOT / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_TEST_MATRIX_REV_A.csv"
CAPTURE_STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            ROOT
            / "artifacts/pcb_pwr_input_protection_procurement_identity_rev_a.json"
        ),
    )
    args = parser.parse_args()

    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    evidence_md = EVIDENCE_MD.read_text(encoding="utf-8")
    evidence_sha256 = sha256(EVIDENCE)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    capture_status = json.loads(CAPTURE_STATUS.read_text(encoding="utf-8"))
    matrix = {row["Test_ID"]: row for row in read_csv(MATRIX)}

    require(evidence["schema_version"] == 1, "identity-evidence schema drift")
    require(evidence["configuration"] == "EVT-PRE-20 Rev.A", "configuration drift")
    require(evidence["assembly"] == "PCB-PWR", "assembly drift")
    require(evidence["retrieved_utc_date"] == "2026-09-17", "retrieval date drift")
    require(
        evidence["status"]
        == "PASS_PREPURCHASE_DOCUMENTARY_IDENTITY_FIRST_LOT_RECEIVING_INSPECTION_PENDING",
        "procurement-identity status drift",
    )

    decision = evidence["decision"]
    require(
        decision
        == {
            "standalone_engineering_sample_purchase_required": False,
            "qualification_batch_may_supply_receiving_samples": True,
            "prepurchase_documentary_identity_complete": True,
            "actual_future_lot_date_code_available_online": False,
            "first_lot_receiving_inspection_required": True,
            "electrical_qualification_complete": False,
        },
        "sample-purchase/receiving decision drift",
    )

    exact_orderables = ["0451008.MRL", "SMBJ18A", "43045-0213", "43030-0038"]
    require(evidence["exact_orderables"] == exact_orderables,
            "exact orderable set/order drift")
    targets = evidence["targets"]
    require(list(targets) == exact_orderables, "target identity records drift")

    fuse = targets["0451008.MRL"]
    require(fuse["manufacturer"] == "Littelfuse", "fuse manufacturer drift")
    require(fuse["individual_marking"]["expected"] ==
            ["Littelfuse F brand mark", "8A ampere marking"],
            "fuse expected body marking drift")
    require(fuse["individual_marking"]["exact_full_mpn_on_body"] is False and
            fuse["individual_marking"]["lot_date_on_body"] is False,
            "fuse body marking overclaimed")
    require(fuse["factory_packaging"] == {
        "type": "12 mm tape and reel",
        "quantity_pieces": 1000,
        "specification": "EIA RS-481-2 (IEC 286 part 3)",
        "ordering_code_binding": "0451 + 008. + M + R + L",
    }, "fuse packaging identity drift")

    tvs = targets["SMBJ18A"]
    require(tvs["individual_marking"] == {
        "exact_device_code": "LT",
        "trace_format": "YMXXX",
        "trace_fields": {
            "Y": "year code",
            "M": "month code",
            "XXX": "lot code",
        },
        "polarity_feature": "Cathode band required for the unidirectional SMBJ18A",
        "reject_adjacent_code": "BT is SMBJ18CA and is not acceptable",
    }, "TVS marking system drift")
    require(tvs["factory_packaging"] == {
        "type": "12 mm tape on 13 inch reel",
        "quantity_pieces": 3000,
        "specification": "EIA STD RS-481",
    }, "TVS packaging identity drift")

    header = targets["43045-0213"]
    require(header["manufacturer"] == "Molex", "header manufacturer drift")
    require(header["official_packaging_type"] == "Tray", "header packaging drift")
    require(header["upc"] == "800754370066", "header UPC drift")
    require(
        header["official_product_image"]["sha256"]
        == "d0fdbe0b053d81cc0001bc228c8a30ef07962d9f3b6902f4518d1d037419d49c",
        "header official image hash drift",
    )

    terminal = targets["43030-0038"]
    require(terminal["manufacturer"] == "Molex", "terminal manufacturer drift")
    require(terminal["official_packaging_type"] == "Reel", "terminal packaging drift")
    require(terminal["upc"] == "889056413237", "terminal UPC drift")
    require(
        terminal["official_product_image"]["sha256"]
        == "3964a86c3efa3975f59f4ed95a92d85532617434f98f59f4ed95eff79cb32",
        "terminal official image hash drift",
    )
    terminal_packaging = terminal["official_packaging_drawing"]
    require(terminal_packaging["document_number"] == "PK-43030-001-001" and
            terminal_packaging["revision"] == "B1" and
            terminal_packaging["release_date"] == "2022-10-07",
            "terminal packaging drawing identity drift")
    require(
        terminal_packaging["sha256"]
        == "2f60beee920157c12547322ae81cfcf13d62e084180fb67c3b0d9d1df38efb86",
        "terminal packaging drawing hash drift",
    )
    require(terminal_packaging["claims"] == {
        "quantity_pieces_per_reel": 12000,
        "reel_flange_diameter_in": 24,
        "product_label_location_shown": True,
        "reels_per_carton": 7,
    }, "terminal packaging claims drift")
    illustrative = terminal["illustrative_exact_mpn_reel_photo"]
    require(illustrative["authority"] is False,
            "third-party reel photo promoted to authority")
    require(
        illustrative["sha256"]
        == "058f74c8b92e63f5b6509067988d8ef0cd8e9cd67123e1e35e2020ff012dd1c3",
        "illustrative reel photo hash drift",
    )

    channel = evidence["channel_evidence"]
    require([item["mpn"] for item in channel["exact_mpn_catalog_examples"]]
            == ["0451008.MRL", "43045-0213", "43030-0038"],
            "authorized-channel examples drift")
    for forbidden in ("Marketplace", "Unlabeled", "Adjacent", "Mixed"):
        require(any(item.startswith(forbidden) for item in channel["forbidden"]),
                f"missing procurement rejection rule: {forbidden}")

    receiving = evidence["first_lot_receiving_gate"]
    require(receiving["status"] == "PENDING_ACTUAL_RECEIPT",
            "first-lot gate prematurely closed")
    require("100 percent" in receiving["package_inspection"],
            "package inspection is not exhaustive")
    require("at least five" in receiving["body_inspection"],
            "body inspection sample floor drift")
    for token in ("Exact MPN", "Manufacturer or distributor date/lot code",
                  "Photo filenames and SHA-256 values", "Inspector and UTC date"):
        require(token in receiving["required_record_fields"],
                f"receiving record missing {token}")

    binding = evidence["qualification_binding"]
    require(binding == {
        "matrix_row": "PWR-IPQ-002",
        "matrix_status": "PENDING_PHYSICAL_TEST",
        "prepurchase_subgate_complete": True,
        "first_lot_receiving_subgate_complete": False,
        "internet_photos_are_not_future_lot_evidence": True,
    }, "qualification binding drift")
    boundary = evidence["release_boundary"]
    require(boundary == {
        "identity_evidence_allows_sample_only_purchase_to_be_omitted": True,
        "exact_parts_may_be_bought_with_the_controlled_evt_test_batch_when_other_procurement_gates_allow": True,
        "received_parts_released_to_evt_kitting": False,
        "physical_qualification_complete": False,
        "pcba_procurement_authorized": False,
        "manufacturing_release": False,
    }, "identity release boundary drift")

    identity = contract["procurement_identity"]
    require(identity["prepurchase_documentary_identity_complete"] is True and
            identity["standalone_engineering_sample_purchase_required"] is False and
            identity["qualification_batch_may_supply_receiving_samples"] is True and
            identity["actual_future_lot_date_code_available_online"] is False and
            identity["first_lot_receiving_inspection_required"] is True and
            identity["first_lot_receiving_inspection_complete"] is False,
            "qualification contract identity decision drift")
    require(identity["record"] == EVIDENCE_MD.relative_to(ROOT).as_posix() and
            identity["machine_record"] == EVIDENCE.relative_to(ROOT).as_posix() and
            identity["independent_audit"] ==
            "tools/audit_pcb_pwr_input_protection_procurement_identity_rev_a.py" and
            identity["evidence_sha256"] == evidence_sha256 and
            identity["matrix_row"] == "PWR-IPQ-002" and
            identity["matrix_status"] == "PENDING_PHYSICAL_TEST" and
            identity["exact_orderables"] == exact_orderables,
            "qualification contract identity binding drift")

    status = capture_status["input_protection_candidate_eco"]
    require(status["prepurchase_identity_complete"] is True and
            status["standalone_engineering_sample_purchase_required"] is False and
            status["first_lot_receiving_inspection_complete"] is False and
            status["procurement_identity_record"] == identity["record"] and
            status["procurement_identity_machine_record"] == identity["machine_record"] and
            status["procurement_identity_audit"] == identity["independent_audit"] and
            status["procurement_identity_evidence_sha256"] == evidence_sha256,
            "capture-status procurement identity binding drift")

    row = matrix["PWR-IPQ-002"]
    require(row["Gate"] == "FIRST_LOT_RECEIVING_IDENTITY",
            "PWR-IPQ-002 gate drift")
    require(row["Status"] == "PENDING_PHYSICAL_TEST",
            "PWR-IPQ-002 prematurely closed")
    require("Controlled EVT test-batch" in row["Required_Input"] and
            all(mpn in row["Procedure"] for mpn in exact_orderables) and
            "F plus 8A" in row["Pass_Criteria"] and
            "LT plus YMXXX" in row["Pass_Criteria"],
            "PWR-IPQ-002 receiving criteria drift")
    require(not any(row[field] for field in
                    ("Result", "Operator", "Date", "Artifact_SHA256")),
            "pending PWR-IPQ-002 carries unaudited receipt evidence")

    for token in (
        "0451008.MRL",
        "SMBJ18A",
        "43045-0213",
        "43030-0038",
        "F` plus `8A",
        "`LT`",
        "`YMXXX`",
        "12,000",
        evidence_sha256,
        "PENDING_PHYSICAL_TEST",
        "NOT FOR MANUFACTURE",
    ):
        require(token in evidence_md, f"Markdown identity record missing {token}")

    result = {
        "configuration": evidence["configuration"],
        "audit": "PCB-PWR Rev.A pre-purchase and receiving identity control",
        "status": "PASS_PREPURCHASE_DOCUMENTARY_IDENTITY_FIRST_LOT_PENDING",
        "retrieved_utc_date": evidence["retrieved_utc_date"],
        "evidence_sha256": evidence_sha256,
        "exact_orderables": exact_orderables,
        "standalone_engineering_sample_purchase_required": False,
        "first_lot_receiving_inspection_complete": False,
        "matrix_row": "PWR-IPQ-002",
        "matrix_status": row["Status"],
        "physical_qualification_complete": False,
        "pcba_procurement_authorized": False,
        "manufacturing_release": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("PCB-PWR pre-purchase identity audit PASS")
    print("No sample-only purchase; first actual EVT lot remains quarantined pending receipt inspection")
    print(f"Evidence SHA-256: {evidence_sha256}")
    print("PWR-IPQ-002 remains PENDING_PHYSICAL_TEST; manufacturing release remains BLOCKED")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

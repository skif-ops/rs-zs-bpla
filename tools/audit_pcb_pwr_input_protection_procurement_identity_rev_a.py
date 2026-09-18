#!/usr/bin/env python3
"""Audit the PCB-PWR documentary procurement-identity control.

PWR-IPQ-002 is closed before purchase from manufacturer authority and exact-MPN
supplier catalogue records. It deliberately imposes no sample-only order,
receiving quarantine, mandatory photographs, body sample, lot/date record or
certificate of conformance.
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

    require(evidence["schema_version"] == 2, "identity-evidence schema drift")
    require(evidence["configuration"] == "EVT-PRE-20 Rev.A", "configuration drift")
    require(evidence["assembly"] == "PCB-PWR", "assembly drift")
    require(evidence["retrieved_utc_date"] == "2026-09-17", "retrieval date drift")
    require(
        evidence["status"]
        == "PASS_DOCUMENTARY_PROCUREMENT_IDENTITY_NO_RECEIVING_HOLD",
        "procurement-identity status drift",
    )

    decision = evidence["decision"]
    require(
        decision
        == {
            "standalone_engineering_sample_purchase_required": False,
            "qualification_batch_may_be_ordered_without_identity_samples": True,
            "prepurchase_documentary_identity_complete": True,
            "mandatory_receiving_quarantine_required": False,
            "mandatory_receiving_photography_required": False,
            "mandatory_body_sampling_required": False,
            "certificate_of_conformance_required": False,
            "electrical_qualification_complete": False,
        },
        "documentary procurement decision drift",
    )

    exact_orderables = ["0451008.MRL", "SMBJ18A", "43045-0213", "43030-0038"]
    require(evidence["exact_orderables"] == exact_orderables,
            "exact orderable set/order drift")
    targets = evidence["targets"]
    require(list(targets) == exact_orderables, "target identity records drift")

    fuse = targets["0451008.MRL"]
    require(fuse["manufacturer"] == "Littelfuse", "fuse manufacturer drift")
    require(fuse["documentary_identity"]["nominal_current_a"] == 8.0,
            "fuse nominal current drift")
    require(fuse["documentary_identity"]["voltage_rating_vdc"] == 125,
            "fuse voltage rating drift")
    require(fuse["documentary_identity"]["ordering_code_binding"]
            == "0451 + 008. + M + R + L",
            "fuse ordering-code binding drift")

    tvs = targets["SMBJ18A"]
    require(tvs["manufacturer"] == "Littelfuse", "TVS manufacturer drift")
    require(tvs["documentary_identity"]["reverse_standoff_v"] == 18.0 and
            tvs["documentary_identity"]["maximum_clamp_v"] == 29.2,
            "TVS controlled ratings drift")
    require("BT identifies rejected SMBJ18CA" in
            tvs["documentary_identity"]["body_marking_reference"],
            "TVS adjacent-part rejection drift")

    header = targets["43045-0213"]
    require(header["manufacturer"] == "Molex", "header manufacturer drift")
    require(header["documentary_identity"]["official_packaging_type"] == "Tray",
            "header packaging drift")
    require(header["documentary_identity"]["maximum_current_per_contact_a"] == 8.5,
            "header current field drift")
    require(
        header["official_product_image"]["sha256"]
        == "d0fdbe0b053d81cc0001bc228c8a30ef07962d9f3b6902f4518d1d037419d49c",
        "header official image hash drift",
    )

    terminal = targets["43030-0038"]
    require(terminal["manufacturer"] == "Molex", "terminal manufacturer drift")
    require(terminal["documentary_identity"]["official_packaging_type"] == "Reel",
            "terminal packaging drift")
    require(terminal["documentary_identity"]["wire_awg"] == 18 and
            terminal["documentary_identity"]["wire_cross_section_mm2"] == 0.75,
            "terminal wire range drift")
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

    supplier_bindings = {
        mpn: [entry["supplier"] for entry in targets[mpn]["supplier_catalog_records"]]
        for mpn in exact_orderables
    }
    require(supplier_bindings == {
        "0451008.MRL": ["DigiKey"],
        "SMBJ18A": ["Mouser"],
        "43045-0213": ["DigiKey"],
        "43030-0038": ["DigiKey", "Mouser"],
    }, "exact-MPN supplier catalogue bindings drift")
    for mpn in exact_orderables:
        for entry in targets[mpn]["supplier_catalog_records"]:
            require(entry["url"].startswith("https://"),
                    f"{mpn}: supplier record is not HTTPS")
            require(entry["claims_used"],
                    f"{mpn}: supplier record lacks controlled claims")
        require(mpn in targets[mpn]["purchase_order_identity_rule"],
                f"{mpn}: purchase-order identity rule does not name exact MPN")

    availability = evidence["nonbinding_supplier_availability_snapshot"]
    require(
        availability["observed_utc_date"] == evidence["retrieved_utc_date"],
        "supplier availability snapshot date drift",
    )
    expected_availability = {
        "0451008.MRL": (30, 14150, 23),
        "SMBJ18A": (25, 12758, None),
        "43045-0213": (25, 4507, 17),
        "43030-0038": (252, 670806, 8),
    }
    require(
        [record["mpn"] for record in availability["records"]] == exact_orderables,
        "supplier availability MPN order drift",
    )
    for record in availability["records"]:
        expected = expected_availability[record["mpn"]]
        actual = (
            record["evt_20_quantity_with_spares"],
            record["displayed_in_stock"],
            record["manufacturer_standard_lead_time_weeks"],
        )
        require(actual == expected,
                f"{record['mpn']}: supplier availability snapshot drift")
        require(record["displayed_in_stock"]
                >= record["evt_20_quantity_with_spares"],
                f"{record['mpn']}: displayed stock does not cover EVT-20 quantity")
        require(record["supplier_page"].startswith("https://"),
                f"{record['mpn']}: availability source is not HTTPS")
    require(
        availability["displayed_stock_covers_controlled_evt_20_quantities"] is True
        and availability["two_week_delivery_guaranteed"] is False
        and availability[
            "cart_or_quote_destination_delivery_confirmation_required_at_order"
        ] is True,
        "supplier availability delivery boundary drift",
    )

    gate = evidence["documentary_procurement_gate"]
    require(gate["status"] == "PASS", "documentary procurement gate is not PASS")
    require(any("exact MPN" in item for item in gate["purchase_order_rule"]),
            "purchase-order exact-MPN rule missing")
    require(any("substitution" in item.lower() for item in gate["purchase_order_rule"]),
            "purchase-order no-substitution rule missing")
    require(gate["volatile_commercial_fields_confirm_at_order"] == [
        "Orderable status",
        "Available quantity",
        "Price",
        "Ship date and delivery date to destination",
        "Packaging option when ordering less than the factory pack",
    ], "volatile commercial field boundary drift")
    for token in (
        "A separate engineering sample order",
        "Future shipment date or lot code",
        "Certificate of conformance",
        "Incoming package or body photographs",
        "A minimum incoming body sample count",
    ):
        require(token in gate["not_required_for_gate"],
                f"non-required incoming control missing: {token}")

    receipt = evidence["non_blocking_receipt_reconciliation"]
    require(receipt == {
        "status": "NOT_A_QUALIFICATION_OR_RELEASE_GATE",
        "quarantine_required": False,
        "mandatory_photographs_required": False,
        "minimum_body_sample_count": 0,
        "certificate_of_conformance_required": False,
        "actions_using_existing_commercial_data": [
            "Reconcile delivered quantity and supplier line against the purchase order or packing slip",
            "Escalate an obvious MPN, quantity or transit-damage discrepancy through normal procurement nonconformance handling",
            "Proceed directly to kitting when no discrepancy is reported",
        ],
        "new_receiving_evidence_package_required": False,
    }, "non-blocking receipt boundary drift")

    binding = evidence["qualification_binding"]
    require(binding == {
        "matrix_row": "PWR-IPQ-002",
        "matrix_status": "PASS",
        "documentary_gate_complete": True,
        "physical_lot_identity_gate_required": False,
        "functional_confirmation_routes": [
            "PWR-IPQ-005 through PWR-IPQ-020",
            "Assembly inspection and AOI",
            "PCB-PWR electrical end-of-line test",
            "EVT thermal, inrush, fault and transient tests",
        ],
    }, "qualification binding drift")
    boundary = evidence["release_boundary"]
    require(boundary == {
        "identity_control_allows_sample_only_purchase_to_be_omitted": True,
        "exact_parts_may_be_bought_with_the_controlled_evt_test_batch_when_other_procurement_gates_allow": True,
        "identity_control_allows_direct_evt_kitting_without_receiving_hold": True,
        "physical_qualification_complete": False,
        "pcba_procurement_authorized": False,
        "manufacturing_release": False,
    }, "identity release boundary drift")

    identity = contract["procurement_identity"]
    require(identity["prepurchase_documentary_identity_complete"] is True and
            identity["standalone_engineering_sample_purchase_required"] is False and
            identity["qualification_batch_may_be_ordered_without_identity_samples"] is True and
            identity["mandatory_receiving_quarantine_required"] is False and
            identity["mandatory_receiving_photography_required"] is False and
            identity["mandatory_body_sampling_required"] is False and
            identity["certificate_of_conformance_required"] is False,
            "qualification contract documentary identity decision drift")
    require(identity["record"] == EVIDENCE_MD.relative_to(ROOT).as_posix() and
            identity["machine_record"] == EVIDENCE.relative_to(ROOT).as_posix() and
            identity["independent_audit"] ==
            "tools/audit_pcb_pwr_input_protection_procurement_identity_rev_a.py" and
            identity["evidence_sha256"] == evidence_sha256 and
            identity["matrix_row"] == "PWR-IPQ-002" and
            identity["matrix_status"] == "PASS" and
            identity["exact_orderables"] == exact_orderables,
            "qualification contract identity binding drift")

    status = capture_status["input_protection_candidate_eco"]
    require(status["prepurchase_identity_complete"] is True and
            status["standalone_engineering_sample_purchase_required"] is False and
            status["documentary_procurement_identity_complete"] is True and
            status["receiving_identity_hold_required"] is False and
            status["procurement_identity_record"] == identity["record"] and
            status["procurement_identity_machine_record"] == identity["machine_record"] and
            status["procurement_identity_audit"] == identity["independent_audit"] and
            status["procurement_identity_evidence_sha256"] == evidence_sha256,
            "capture-status procurement identity binding drift")

    row = matrix["PWR-IPQ-002"]
    require(row["Gate"] == "DOCUMENTARY_PROCUREMENT_IDENTITY",
            "PWR-IPQ-002 gate drift")
    require(row["Status"] == "PASS", "PWR-IPQ-002 is not PASS")
    require(all(mpn in row["Procedure"] for mpn in exact_orderables),
            "PWR-IPQ-002 procedure does not name all exact orderables")
    require("no sample-only order" in row["Pass_Criteria"] and
            "receiving quarantine" in row["Pass_Criteria"] and
            "body sampling" in row["Pass_Criteria"] and
            "CoC" in row["Pass_Criteria"],
            "PWR-IPQ-002 no-receiving-hold criteria drift")
    require(row["Result"] ==
            "Four exact orderables bound to current manufacturer and supplier records; documentary identity closes without a receiving hold" and
            row["Operator"] == "Codex manufacturer/supplier documentary audit" and
            row["Date"] == "2026-09-17" and
            row["Artifact_SHA256"] == evidence_sha256,
            "PWR-IPQ-002 attributable evidence drift")

    for token in (
        "0451008.MRL",
        "SMBJ18A",
        "43045-0213",
        "43030-0038",
        "NO SUBSTITUTION",
        "minimum inspected bodies per MPN/lot: `0`",
        "DigiKey 14,150",
        "Mouser 12,758",
        "DigiKey 4,507",
        "DigiKey 670,806",
        evidence_sha256,
        "PWR-IPQ-002`: `PASS",
        "NOT FOR MANUFACTURE",
    ):
        require(token in evidence_md, f"Markdown identity record missing {token}")

    result = {
        "configuration": evidence["configuration"],
        "audit": "PCB-PWR Rev.A documentary procurement identity control",
        "status": "PASS_DOCUMENTARY_PROCUREMENT_IDENTITY_NO_RECEIVING_HOLD",
        "retrieved_utc_date": evidence["retrieved_utc_date"],
        "evidence_sha256": evidence_sha256,
        "exact_orderables": exact_orderables,
        "supplier_catalogue_bindings": supplier_bindings,
        "supplier_availability_snapshot_date": availability["observed_utc_date"],
        "displayed_stock_covers_controlled_evt_20_quantities": True,
        "two_week_delivery_guaranteed": False,
        "destination_delivery_confirmation_required_at_order": True,
        "standalone_engineering_sample_purchase_required": False,
        "receiving_quarantine_required": False,
        "mandatory_receiving_photography_required": False,
        "minimum_body_sample_count": 0,
        "certificate_of_conformance_required": False,
        "matrix_row": "PWR-IPQ-002",
        "matrix_status": row["Status"],
        "physical_qualification_complete": False,
        "pcba_procurement_authorized": False,
        "manufacturing_release": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("PCB-PWR documentary procurement-identity audit PASS")
    print("PWR-IPQ-002 PASS; no sample-only order or receiving identity hold")
    print(f"Evidence SHA-256: {evidence_sha256}")
    print("Physical qualification and manufacturing release remain BLOCKED")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

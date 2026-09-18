#!/usr/bin/env python3
"""Audit documentary purchase identity for the exact EVT system OTS set.

The gate closes exact-MPN documentary control before order. It deliberately does
not require a separate pre-order qualification unit or a blanket receiving hold,
and it never converts unperformed assembly, EOL or EVT checks into PASS evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "hardware/reviews/EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.json"
RECORD_MD = ROOT / "hardware/reviews/EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.md"
BOM = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
RFQ = ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv"
INCOMING = ROOT / "manufacturing/INCOMING_INSPECTION_PLAN.csv"
DECISIONS = ROOT / "docs/DECISION_LOG.csv"


EXPECTED = {
    "BAT1": ("RELiON", "RB40", 21, "RFQ-008"),
    "PV1": ("SLD Tech / Solarland", "SLP080S-12M", 21, "RFQ-009"),
    "MPPT1": ("Victron Energy", "SCC075010060R", 21, "RFQ-010"),
    "MPPT-TEMP": ("Victron Energy", "SBS050150200", 21, "RFQ-026"),
    "ANT-CELL": ("Taoglas", "G30.B.108111", 22, "RFQ-020"),
    "ANT-GNSS": ("Taoglas", "AA.166.A.301111", 22, "RFQ-021"),
    "ANT-LORA": ("Taoglas", "TI.89.B.2111W", 22, "RFQ-022"),
    "RF-PIGTAIL": ("Taoglas", "CAB.0243", 66, "RFQ-027"),
}
CONTROLLED_STATUS = "CONTROLLED_EVT_PURCHASE_EXACT_MPN_VALIDATION_DURING_ASSEMBLY_EVT"


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
        default=ROOT / "artifacts/evt_system_ots_procurement_identity_rev_a.json",
    )
    args = parser.parse_args()

    record = json.loads(RECORD.read_text(encoding="utf-8"))
    record_md = RECORD_MD.read_text(encoding="utf-8")
    bom = {row["Item_ID"]: row for row in read_csv(BOM)}
    rfq_rows = read_csv(RFQ)
    rfq = {row["RFQ_ID"]: row for row in rfq_rows}
    incoming = read_csv(INCOMING)
    decisions = {row["Decision_ID"]: row for row in read_csv(DECISIONS)}

    require(record["schema_version"] == 1, "record schema drift")
    require(record["configuration"] == "EVT-PRE-20 Rev.A", "configuration drift")
    require(record["scope"] == "SYSTEM_OTS_DOCUMENTARY_PURCHASE_IDENTITY", "scope drift")
    require(record["retrieved_utc_date"] == "2026-09-18", "retrieval date drift")
    require(
        record["status"]
        == "PASS_DOCUMENTARY_PURCHASE_IDENTITY_PHYSICAL_VALIDATION_DURING_ASSEMBLY_EOL_EVT",
        "documentary purchase status drift",
    )

    require(
        record["decision"]
        == {
            "standalone_preorder_qualification_unit_required": False,
            "selected_evt_lot_is_qualification_batch": True,
            "prepurchase_documentary_identity_complete": True,
            "mandatory_receiving_quarantine_required": False,
            "mandatory_receiving_photography_required": False,
            "mandatory_body_sampling_required": False,
            "manufacturer_lot_or_date_capture_required": False,
            "certificate_of_conformance_required": False,
            "battery_transport_documents_when_applicable_required": True,
            "physical_qualification_complete": False,
        },
        "documentary decision boundary drift",
    )

    item_ids = list(EXPECTED)
    require(record["exact_item_ids"] == item_ids, "exact item set/order drift")
    targets = record["targets"]
    require(list(targets) == item_ids, "target record set/order drift")

    for item_id, (manufacturer, mpn, quantity, rfq_id) in EXPECTED.items():
        target = targets[item_id]
        require(target["manufacturer"] == manufacturer, f"{item_id}: manufacturer drift")
        require(target["mpn"] == mpn, f"{item_id}: MPN drift")
        require(
            target["evt_20_quantity_with_spares"] == quantity,
            f"{item_id}: controlled EVT-20 quantity drift",
        )
        require(target["official_sources"], f"{item_id}: official source missing")
        require(
            all(url.startswith("https://") for url in target["official_sources"]),
            f"{item_id}: official source is not HTTPS",
        )
        supplier_records = target["supplier_catalog_records"]
        require(supplier_records, f"{item_id}: supplier catalogue binding missing")
        for supplier_record in supplier_records:
            require(supplier_record["supplier"], f"{item_id}: supplier name missing")
            require(
                supplier_record["url"].startswith("https://"),
                f"{item_id}: supplier URL is not HTTPS",
            )
            require(
                supplier_record["claims_used"],
                f"{item_id}: supplier binding has no controlled claim",
            )
        require(mpn in target["purchase_order_rule"], f"{item_id}: PO rule omits exact MPN")
        require(
            "no substitution" in target["purchase_order_rule"].lower(),
            f"{item_id}: PO rule lacks no-substitution control",
        )
        require(
            target["physical_validation_routes"],
            f"{item_id}: physical validation route missing",
        )

        row = bom.get(item_id)
        require(row is not None, f"{item_id}: controlled BOM row missing")
        require(row["Manufacturer"] == manufacturer, f"{item_id}: BOM manufacturer drift")
        require(row["MPN"] == mpn, f"{item_id}: BOM MPN drift")
        require(row["Status"] == CONTROLLED_STATUS, f"{item_id}: BOM status drift")
        require(row["Line_class"] == "SYSTEM_ITEM", f"{item_id}: BOM line class drift")
        require(row["Population"] == "FITTED", f"{item_id}: BOM population drift")
        require(row["BOM_disposition"] == "CONTROLLED", f"{item_id}: BOM is not controlled")
        require(row["Procure_qty_20"] == str(quantity), f"{item_id}: BOM quantity drift")
        incoming_control = row["Incoming_control"].lower()
        require(
            "evt" in incoming_control and ("assembly" in incoming_control or "installation" in incoming_control),
            f"{item_id}: BOM does not route physical checks to assembly/EVT",
        )
        require(
            not any(token in incoming_control for token in ("quarantine", "photo", "sample", "coc")),
            f"{item_id}: obsolete receiving gate remains in BOM",
        )

        rfq_row = rfq.get(rfq_id)
        require(rfq_row is not None, f"{item_id}: RFQ {rfq_id} missing")
        require(rfq_row["BOM_Item_IDs"] == item_id, f"{item_id}: RFQ mapping drift")
        require(mpn in rfq_row["MPN_or_spec"], f"{item_id}: RFQ omits exact MPN")
        require(rfq_row["Traceability_required"] == "Yes", f"{item_id}: RFQ traceability drift")
        require(rfq_row["Sample_required"] == "No", f"{item_id}: RFQ still requires pre-order unit")
        require(rfq_row["Status"] == "RFQ_REQUIRED", f"{item_id}: RFQ status drift")
        require(rfq_row["URL"].startswith("https://"), f"{item_id}: RFQ authority URL missing")
        check_text = rfq_row["Blocking_check"].lower()
        require("no substitution" in check_text, f"{item_id}: RFQ no-substitution rule missing")
        require(
            "evt" in check_text and ("assembly" in check_text or "installation" in check_text),
            f"{item_id}: RFQ does not route validation to assembly/EVT",
        )

    require(targets["BAT1"]["controlled_facts"]["energy_wh"] == 512,
            "RB40 energy binding drift")
    require(targets["PV1"]["controlled_facts"]["voc_v"] == 22.52,
            "SLP080S-12M Voc binding drift")
    require(targets["MPPT1"]["controlled_facts"]["rated_charge_current_a"] == 10 and
            targets["MPPT1"]["controlled_facts"]["maximum_pv_open_circuit_voltage_v"] == 75,
            "SmartSolar 75/10 rating drift")
    require(targets["MPPT-TEMP"]["controlled_facts"]["cable_length_m"] == 0.45,
            "Smart Battery Sense lead-length drift")
    require(targets["ANT-CELL"]["controlled_facts"]["cable_construction"]
            == "UNRESOLVED_MANUFACTURER_PAGE_CONFLICT_RG316_VS_RG178",
            "G30 cable-construction conflict was silently resolved")
    require(targets["ANT-GNSS"]["controlled_facts"]["connector"] == "SMA male",
            "GNSS connector binding drift")
    require(targets["ANT-LORA"]["controlled_facts"]["ingress_rating"] == "IP67",
            "LoRa antenna ingress rating drift")
    require(targets["RF-PIGTAIL"]["controlled_facts"]["minimum_bend_radius_mm"] == 6.8 and
            targets["RF-PIGTAIL"]["controlled_facts"]["numeric_bulkhead_ip_rating_published"] is False,
            "CAB.0243 bend/IP evidence boundary drift")

    availability = record["nonbinding_supplier_availability_snapshot"]
    require(availability["observed_utc_date"] == record["retrieved_utc_date"],
            "availability date drift")
    require([entry["item_id"] for entry in availability["records"]] == item_ids,
            "availability item set/order drift")
    for entry in availability["records"]:
        expected_quantity = EXPECTED[entry["item_id"]][2]
        require(entry["required_quantity"] == expected_quantity,
                f"{entry['item_id']}: availability quantity drift")
        displayed = entry["displayed_available_quantity"]
        expected_coverage = displayed is not None and displayed >= expected_quantity
        require(entry["quantity_coverage_confirmed"] is expected_coverage,
                f"{entry['item_id']}: availability coverage flag drift")
        require(entry["source"].startswith("https://"),
                f"{entry['item_id']}: availability source is not HTTPS")
    require(
        availability["rf_chain_displayed_stock_covers_evt_20_quantities"] is True
        and availability["power_chain_full_quantity_coverage_confirmed"] is False
        and availability["full_evt_20_quantity_coverage_confirmed"] is False
        and availability["two_week_delivery_to_destination_guaranteed"] is False
        and availability["cart_or_quote_destination_delivery_confirmation_required_at_order"] is True,
        "commercial availability/delivery boundary drift",
    )

    gate = record["documentary_procurement_gate"]
    require(gate["status"] == "PASS", "documentary gate is not PASS")
    require(any("NO SUBSTITUTION" in item for item in gate["purchase_order_rules"]),
            "global no-substitution rule missing")
    require(any("destination delivery" in item for item in gate["purchase_order_rules"]),
            "order-time destination delivery confirmation missing")
    require(set(gate["not_required_for_gate"]) == {
        "A separate pre-order qualification unit",
        "Receiving quarantine of a conforming shipment",
        "Mandatory package or body photographs",
        "A fixed incoming body count",
        "Future manufacturer lot or date code",
        "Certificate of conformance",
    }, "non-required gate set drift")

    receipt = record["non_blocking_receipt_reconciliation"]
    require(receipt["status"] == "NOT_A_TECHNICAL_QUALIFICATION_OR_RELEASE_GATE",
            "receipt boundary drift")
    require(receipt["new_receiving_evidence_package_required"] is False,
            "receipt evidence-package gate reintroduced")
    require(any("packing slip" in item for item in receipt["actions"]),
            "ordinary packing-slip reconciliation missing")
    require(any("systemic" in item for item in receipt["actions"]),
            "systemic-discrepancy escalation boundary missing")

    require(len(rfq_rows) == 27, "RFQ row count drift")
    require(all(row["Sample_required"] == "No" for row in rfq_rows),
            "one or more RFQs still require a separate pre-order unit")
    require(all(row["Traceability_required"] == "Yes" for row in rfq_rows),
            "RFQ exact-order traceability policy drift")

    require(len(incoming) == 19, "incoming-control row count drift")
    obsolete_tokens = ("quarantine", "photo", "5_minimum", "five-piece", "certificate of conformance", "coc")
    obsolete_rows = []
    for row in incoming:
        text = " ".join(row.values()).lower()
        if any(token in text for token in obsolete_tokens):
            obsolete_rows.append(row["IC_ID"])
    require(not obsolete_rows,
            "obsolete blanket receiving controls remain: " + ", ".join(obsolete_rows))
    require(all("100_PERCENT" not in row["Sample"] or
                any(token in row["Sample"] for token in ("SUPPLIER", "ASSEMBLER", "CONTINUITY"))
                for row in incoming),
            "incoming plan contains an unexplained receiving 100-percent technical gate")

    decision = decisions.get("DEC-066")
    require(decision is not None, "DEC-066 missing")
    require(decision["Status"]
            == "IMPLEMENTED_DOCUMENTARY_SYSTEM_OTS_PURCHASE_CONTROL_PHYSICAL_VALIDATION_PENDING",
            "DEC-066 status drift")
    require("DEC-057 and DEC-059" in decision["Impact"],
            "DEC-066 supersession boundary missing")

    record_hash = sha256(RECORD)
    require(record_hash in record_md, "machine-record hash missing from Markdown")
    for item_id, (_, mpn, _, _) in EXPECTED.items():
        require(item_id in record_md and mpn in record_md,
                f"{item_id}: Markdown identity coverage missing")
    require("not a production release" in record_md.lower(),
            "Markdown production-release boundary missing")

    quote_fields = ("Quote_date", "Supplier", "MOQ", "Lead_time_days", "Stock_claim")
    exact_rfq_rows = [rfq[EXPECTED[item_id][3]] for item_id in item_ids]
    commercial_quote_complete = all(
        all(row[field].strip() for field in quote_fields) for row in exact_rfq_rows
    )
    boundary = record["release_boundary"]
    require(boundary == {
        "documentary_purchase_identity_complete": True,
        "commercial_quote_and_destination_delivery_complete": False,
        "physical_qualification_complete": False,
        "hardware_design_release": False,
        "purchase_release": False,
        "manufacturing_release": False,
    }, "release boundary drift")
    require(commercial_quote_complete is False,
            "commercial quotes are unexpectedly complete; update the controlled record")

    result = {
        "status": record["status"],
        "configuration": record["configuration"],
        "documentary_purchase_identity_complete": True,
        "controlled_item_ids": item_ids,
        "controlled_item_count": len(item_ids),
        "standalone_preorder_qualification_unit_required": False,
        "receiving_hold_required": False,
        "commercial_quote_and_destination_delivery_complete": commercial_quote_complete,
        "physical_qualification_complete": False,
        "hardware_design_release": False,
        "purchase_release": False,
        "manufacturing_release": False,
        "record": str(RECORD.relative_to(ROOT)),
        "record_sha256": record_hash,
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("EVT system OTS documentary purchase-identity audit: PASS")
    print("8 exact MPNs controlled; physical assembly/EOL/EVT qualification remains open")
    try:
        display_output = output.relative_to(ROOT)
    except ValueError:
        display_output = output
    print(f"report: {display_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

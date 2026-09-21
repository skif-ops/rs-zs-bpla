#!/usr/bin/env python3
"""Audit the controlled preliminary EVT-PRE-20 internal harness drawing."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = ROOT / "hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv"
LOGICAL = ROOT / "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv"
CONNECTORS = ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv"
DRAWING = ROOT / "hardware/HARNESS_MANUFACTURING_DRAWING_REV_A.md"
STALE_REGISTER = ROOT / "hardware/CONNECTOR_REGISTER_DRAFT.csv"
SUPPLIER_REQUEST = ROOT / "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_REQUEST_REV_A.md"
SUPPLIER_CONTRACT = ROOT / "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_REQUEST_REV_A.json"
SUPPLIER_RESPONSE = ROOT / "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_RESPONSE_REV_A.csv"
RFQ = ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv"
BOM = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
LOT_SELECTION = ROOT / "manufacturing/EVT_LOT_SELECTION_REV_A.csv"

SUPPLIER_REQUEST_STATUS = (
    "PACKET_READY_16_ATTRIBUTABLE_RESPONSES_REQUIRED_"
    "FINAL_LENGTHS_OPEN_NOT_FOR_BUILD"
)

SUPPLIER_RESPONSE_FIELDS = [
    "Gate_ID",
    "Supplier_Slot",
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

SUPPLIER_GATE_IDS = [
    "HARNESS-SUPPLIER-IDENTITY",
    "HARNESS-ASSEMBLY-IDENTITY",
    "HARNESS-QMS-CAPABILITY",
    "HARNESS-WIRE-AVL",
    "HARNESS-TEMPERATURE-RATING",
    "HARNESS-CONTACT-TRACEABILITY",
    "HARNESS-CRIMP-TOOLING",
    "HARNESS-CRIMP-PARAMETERS",
    "HARNESS-CRIMP-VALIDATION",
    "HARNESS-LENGTH-CAPABILITY",
    "HARNESS-LABEL-MATERIALS",
    "HARNESS-ROUTING-STRAIN-RELIEF",
    "HARNESS-ELECTRICAL-TEST",
    "HARNESS-FIRST-ARTICLE",
    "HARNESS-TRACEABILITY-CHANGE",
    "HARNESS-COMMERCIAL-QUOTE",
]

SUPPLIER_AUTHORITY_INPUTS = [
    "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv",
    "hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv",
    "hardware/HARNESS_MANUFACTURING_DRAWING_REV_A.md",
    "hardware/CONNECTOR_FREEZE_REV_A.csv",
    "hardware/EVT_PRE_20_BOM_REV_A.csv",
    "hardware/CHINA_PROCUREMENT_RFQ.csv",
    "manufacturing/EVT_LOT_SELECTION_REV_A.csv",
]

CONNECTOR_TO_HARNESS = {
    "J_MIC1": "H-MIC1",
    "J_MIC2": "H-MIC2",
    "J_MIC3": "H-MIC3",
    "J_MIC4": "H-MIC4",
    "J_PWR": "H-MAIN-PWR",
    "J_PWR_IN": "H-BAT-PWR",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def normalized_mpn(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value).upper()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_supplier_request() -> dict[str, object]:
    for path in (SUPPLIER_REQUEST, SUPPLIER_CONTRACT, SUPPLIER_RESPONSE, RFQ, BOM, LOT_SELECTION):
        require(path.is_file(), f"controlled harness supplier input missing: {path.relative_to(ROOT)}")

    contract = json.loads(SUPPLIER_CONTRACT.read_text(encoding="utf-8"))
    require(contract.get("schema") == "dioneya-harness-supplier-capability-request-v1",
            "harness supplier request schema drift")
    require(contract.get("configuration") == "EVT-PRE-20 Rev.A",
            "harness supplier request configuration drift")
    require(contract.get("revision") == "A", "harness supplier request revision drift")
    require(contract.get("status") == SUPPLIER_REQUEST_STATUS,
            "harness supplier request status drift")
    require(contract.get("authority_inputs") == SUPPLIER_AUTHORITY_INPUTS,
            "harness supplier request authority-input set drift")

    expected_binding = [
        {"path": relative, "sha256": sha256(ROOT / relative)}
        for relative in SUPPLIER_AUTHORITY_INPUTS
    ]
    require(contract.get("source_binding") == expected_binding,
            "harness supplier request source binding differs")

    scope = contract.get("controlled_scope", {})
    require(isinstance(scope, dict), "harness supplier controlled scope missing")
    require(scope.get("harness_sets_per_station") == 6,
            "harness supplier request must cover six harnesses per station")
    require(scope.get("controlled_conductors") == 38,
            "harness supplier request conductor count drift")
    require(scope.get("selected_station_quantity") == 20 and
            scope.get("rfq_complete_sets") == 22,
            "harness supplier request selected quantity or spare quantity drift")
    require(scope.get("supplier_slot") == "HARNESS-CANDIDATE",
            "harness supplier slot drift")
    require(scope.get("cut_lengths") ==
            "OPEN_DIM_001_DIM_005_DIM_006_DIM_012_ENCLOSURE_ROUTE_DIM_003_BOARD_DATUM_ACCEPTED",
            "harness cut-length interlock drift")
    require(contract.get("required_gate_ids") == SUPPLIER_GATE_IDS,
            "harness supplier required gate set drift")

    with SUPPLIER_RESPONSE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        require(reader.fieldnames == SUPPLIER_RESPONSE_FIELDS,
                "harness supplier response columns drift")
        response_rows = list(reader)
    require(len(response_rows) == len(SUPPLIER_GATE_IDS),
            f"expected {len(SUPPLIER_GATE_IDS)} harness supplier responses, got {len(response_rows)}")
    require([row["Gate_ID"] for row in response_rows] == SUPPLIER_GATE_IDS,
            "harness supplier response gate order or identity drift")
    require(len({row["Gate_ID"] for row in response_rows}) == len(response_rows),
            "duplicate harness supplier response gate")
    for row in response_rows:
        gate = row["Gate_ID"]
        require(row["Supplier_Slot"] == "HARNESS-CANDIDATE",
                f"{gate}: supplier slot drift")
        require(row["Disposition"] == "PENDING_EXTERNAL_RESPONSE",
                f"{gate}: initial response disposition must remain pending")
        require(row["Blocking"] == "YES", f"{gate}: response must remain blocking")
        require(all(row[field] == "" for field in
                    ("Response_Value", "Response_Reference", "Responder", "Response_Date")),
                f"{gate}: unattributed response data was inserted")
        require(bool(row["Requirement"].strip()) and bool(row["Required_Evidence"].strip()),
                f"{gate}: requirement or evidence request missing")

    external = contract.get("external_response", {})
    require(external == {
        "response_register": str(SUPPLIER_RESPONSE.relative_to(ROOT)),
        "required_rows": 16,
        "pending_rows": 16,
        "accepted_rows": 0,
        "complete": False,
    }, "harness supplier external-response state drift")

    accepted = contract.get("accepted_authority", {})
    require(isinstance(accepted, dict) and accepted.get("accepted_supplier") is False,
            "harness supplier must remain unselected")
    for field in (
        "legal_entity", "manufacturing_site", "supplier_assembly_mpn",
        "supplier_drawing_revision", "temperature_range_c", "wire_avl_reference",
        "crimp_process_reference", "quotation_reference",
    ):
        require(accepted.get(field) is None,
                f"harness supplier accepted field was populated prematurely: {field}")

    interlock = contract.get("release_interlock", {})
    expected_false = (
        "supplier_selected", "assembly_identity_accepted", "temperature_rating_accepted",
        "wire_avl_accepted", "crimp_process_qualified", "final_lengths_accepted",
        "external_endpoints_accepted", "first_article_accepted",
        "manufacturing_release",
    )
    require(isinstance(interlock, dict) and
            all(interlock.get(field) is False for field in expected_false),
            "harness supplier release interlock was opened prematurely")

    packet_text = SUPPLIER_REQUEST.read_text(encoding="utf-8")
    for token in (
        "0 OF 16 RESPONSES ACCEPTED", "NOT FOR BUILD", "DIM-001", "DIM-003",
        "DIM-005", "DIM-006", "DIM-012", "supplier assembly MPN", "wire AVL",
        "100 %", "first article",
    ):
        require(token in packet_text, f"harness supplier request missing: {token}")

    rfq_rows = {row["RFQ_ID"]: row for row in read_csv(RFQ)}
    rfq = rfq_rows.get("RFQ-014", {})
    require(rfq.get("BOM_Item_IDs") == "HARNESS" and
            rfq.get("Manufacturer") == "Dioneya controlled design" and
            "DIO-HARNESS-SET-REV-A" in rfq.get("MPN_or_spec", ""),
            "RFQ-014 harness identity drift")
    require(rfq.get("Required_qty_20") == "22" and rfq.get("Status") == "RFQ_REQUIRED",
            "RFQ-014 selected-lot quantity or status drift")
    require("selected assembler" in rfq.get("MPN_or_spec", "") and
            "assembly MPN" in rfq.get("Blocking_check", "") and
            "HARNESS_SUPPLIER_CAPABILITY_RESPONSE_REV_A.csv" in rfq.get("Blocking_check", ""),
            "RFQ-014 does not bind the supplier response packet")

    lot_rows = read_csv(LOT_SELECTION)
    selected = [row for row in lot_rows if row["Selection_Status"] == "SELECTED"]
    require(len(selected) == 1 and selected[0]["Scenario_ID"] == "EVT-20" and
            selected[0]["Station_Qty"] == "20",
            "harness supplier request is not bound to the selected EVT-20 lot")

    return {
        "status": SUPPLIER_REQUEST_STATUS,
        "request": str(SUPPLIER_REQUEST.relative_to(ROOT)),
        "contract": str(SUPPLIER_CONTRACT.relative_to(ROOT)),
        "response_register": str(SUPPLIER_RESPONSE.relative_to(ROOT)),
        "required_response_rows": 16,
        "pending_response_rows": 16,
        "accepted_response_rows": 0,
        "selected_supplier": None,
        "final_lengths_accepted": False,
        "build_authorized": False,
    }


def audit() -> dict[str, object]:
    require(DRAWING.is_file(), "controlled harness drawing missing")
    require(not STALE_REGISTER.exists(),
            "obsolete CONNECTOR_REGISTER_DRAFT.csv competes with connector authority")

    logical = [row for row in read_csv(LOGICAL) if row["Connector_Ref"] in CONNECTOR_TO_HARNESS]
    schedule = read_csv(SCHEDULE)
    require(len(logical) == 38, f"expected 38 controlled logical harness conductors, got {len(logical)}")
    require(len(schedule) == 38, f"expected 38 manufacturing schedule rows, got {len(schedule)}")
    require(all(all(value.strip() for value in row.values()) for row in schedule),
            "harness schedule contains a blank field")
    require(len({row["Conductor_ID"] for row in schedule}) == len(schedule),
            "duplicate harness conductor ID")

    counts = Counter(row["Harness_ID"] for row in schedule)
    require(counts == Counter({
        "H-MIC1": 6,
        "H-MIC2": 6,
        "H-MIC3": 6,
        "H-MIC4": 6,
        "H-MAIN-PWR": 12,
        "H-BAT-PWR": 2,
    }), f"harness conductor-count drift: {dict(counts)}")

    schedule_key = {(row["Harness_ID"], row["To_Cavity"]): row for row in schedule}
    require(len(schedule_key) == len(schedule), "duplicate harness cavity assignment")
    for source in logical:
        harness_id = CONNECTOR_TO_HARNESS[source["Connector_Ref"]]
        key = (harness_id, source["Pin"])
        require(key in schedule_key, f"missing manufacturing row for {key}")
        row = schedule_key[key]
        require(row["Net"] == source["Net"], f"{key}: net mismatch")
        require(row["From_Cavity"] == row["To_Cavity"] or harness_id == "H-BAT-PWR",
                f"{key}: internal harness is not straight-through")
        require(row["Cut_Length_mm"].startswith("TBD_DIM-"),
                f"{key}: unknown cut length must remain an explicit DIM blocker")
        require(row["Length_Tolerance_mm"] == "TBD_AFTER_ROUTE_FREEZE",
                f"{key}: length tolerance prematurely frozen")
        require(row["Continuity_Test"].startswith("100_PERCENT_"),
                f"{key}: 100 percent continuity control missing")

        wire_rule = source["Wire_rule"]
        if wire_rule == "AWG28_or_larger":
            require(row["Wire_Gauge"].startswith("AWG28_"), f"{key}: microphone gauge drift")
            require(row["From_Terminal_MPN"] == "5040520098" and
                    row["To_Terminal_MPN"] == "5040520098",
                    f"{key}: microphone terminal drift")
        elif wire_rule == "AWG18_0.75mm2_Molex430300038":
            require(row["Wire_Gauge"].startswith("AWG18_0.75MM2_"),
                    f"{key}: power gauge drift")
            require(row["To_Terminal_MPN"] == "430300038",
                    f"{key}: controlled power terminal missing")
            if harness_id == "H-MAIN-PWR":
                require(row["From_Terminal_MPN"] == "430300038",
                        f"{key}: MAIN-PWR source power terminal drift")
        elif wire_rule == "AWG20_to_24_Molex430300001":
            require(row["Wire_Gauge"].startswith("AWG20_TO_24_"),
                    f"{key}: control-wire gauge drift")
            require(row["From_Terminal_MPN"] == "430300001" and
                    row["To_Terminal_MPN"] == "430300001",
                    f"{key}: control terminal drift")
        else:
            raise AssertionError(f"{key}: unsupported logical wire rule {wire_rule}")

    connector_rows = {row["Connector_ID"]: row for row in read_csv(CONNECTORS)}
    mic = connector_rows["CON-MIC"]
    require(normalized_mpn(mic["Mating_Housing_MPN"]) == "MOLEX5040510601",
            "CON-MIC mating housing drift")
    require(normalized_mpn(mic["Terminal_MPN"]) == "MOLEX5040520098",
            "CON-MIC terminal drift")
    for connector_id in ("CON-004A", "CON-004B"):
        row = connector_rows[connector_id]
        require(normalized_mpn(row["Mating_Housing_MPN"]) == "MOLEX430251200",
                f"{connector_id}: MAIN-PWR housing drift")
        terminals = normalized_mpn(row["Terminal_MPN"])
        require("MOLEX430300038" in terminals and "MOLEX430300001" in terminals,
                f"{connector_id}: MAIN-PWR terminal set drift")
    battery = connector_rows["CON-003"]
    require(normalized_mpn(battery["Mating_Housing_MPN"]) == "MOLEX430250200",
            "CON-003 battery-input mating housing drift")
    require(normalized_mpn(battery["Terminal_MPN"]) == "MOLEX430300038",
            "CON-003 battery-input terminal drift")

    internal_rows = [row for row in schedule if row["Harness_ID"] != "H-BAT-PWR"]
    require(all(row["Release_Status"] == "CONTROLLED_PRELIMINARY_LENGTH_OPEN"
                for row in internal_rows), "internal harness status drift")
    battery_rows = [row for row in schedule if row["Harness_ID"] == "H-BAT-PWR"]
    require(all(row["Release_Status"] == "BOARD_END_CONTROLLED_SOURCE_END_OPEN"
                for row in battery_rows), "battery harness status drift")

    labels_by_harness = {
        harness_id: {row["End_Label"] for row in schedule if row["Harness_ID"] == harness_id}
        for harness_id in counts
    }
    require(all(len(labels) == 1 for labels in labels_by_harness.values()),
            "a harness uses inconsistent end labels across conductors")
    labels = {harness_id: next(iter(values)) for harness_id, values in labels_by_harness.items()}
    require(len(set(labels.values())) == len(labels), "harness end labels are not unique")

    supplier_request = validate_supplier_request()

    deliverables = {row["ID"]: row for row in read_csv(ROOT / "docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv")}
    require(deliverables["HW-C-001"]["QG-1 полнота"] == "PASS",
            "HW-C-001 QG-1 status does not reflect controlled logical pinout")
    require(deliverables["HW-C-002"]["Статус"] == "CONTROLLED_PRELIMINARY_SUPPLIER_PACKET_READY" and
            deliverables["HW-C-002"]["QG-2 техника"] == "OPEN",
            "HW-C-002 must be controlled preliminary and QG-2 open")
    require(deliverables["HW-C-003"]["Статус"] == "CONTROLLED" and
            deliverables["HW-C-003"]["QG-2 техника"] == "OPEN",
            "HW-C-003 connector authority status drift")

    return {
        "schema": "dioneya-harness-manufacturing-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "status": "PASS_CONTROLLED_PRELIMINARY_LENGTHS_OPEN",
        "packet_complete": True,
        "manufacturing_release": False,
        "schedule": str(SCHEDULE.relative_to(ROOT)),
        "drawing": str(DRAWING.relative_to(ROOT)),
        "controlled_conductors": len(schedule),
        "harness_counts": dict(sorted(counts.items())),
        "supplier_request_status": supplier_request["status"],
        "supplier_request": supplier_request,
        "open_blockers": [
            "cut lengths and tolerances after DIM-001 DIM-005 DIM-006 DIM-012 and final enclosure routes; DIM-003 board datums accepted",
            "selected supplier legal entity assembly MPN revision and assembly temperature range; 0/16 responses accepted",
            "exact wire manufacturer and MPN AVL from the selected supplier",
            "qualified crimp tooling height pull-force and section evidence",
            "battery source connector and protection interface",
            "external PV MPPT RF coax tamper and gland endpoints",
            "voltage-drop thermal PDM AAD and I2C validation on physical harnesses",
            "100 percent lot continuity records and sample pull tests",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true",
                        help="return non-zero until physical harness manufacturing release")
    args = parser.parse_args()
    try:
        result = audit()
    except (AssertionError, KeyError, ValueError, OSError) as exc:
        result = {
            "schema": "dioneya-harness-manufacturing-audit-v1",
            "configuration": "EVT-PRE-20 Rev.A",
            "status": "FAIL",
            "packet_complete": False,
            "manufacturing_release": False,
            "error": str(exc),
        }
        exit_code = 1
    else:
        exit_code = 2 if args.strict and not result["manufacturing_release"] else 0

    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Harness manufacturing drawing: {result['status']}")
    if result.get("error"):
        print(f"- {result['error']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

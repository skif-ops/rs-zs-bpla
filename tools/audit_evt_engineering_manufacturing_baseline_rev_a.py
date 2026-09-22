#!/usr/bin/env python3
"""Audit the customer-authorized EVT public engineering manufacturing basis."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "hardware/reviews/EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.json"
MANUAL_PATH = ROOT / "hardware/reviews/EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.md"

REGISTERS = {
    "pcb_main_stackup": ("hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv", 22),
    "pcb_main_pcba": ("hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_RESPONSE_REV_A.csv", 14),
    "pcb_pwr_stackup": ("hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv", 24),
    "pcb_mic_dfm": ("hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv", 9),
    "harness": ("hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_RESPONSE_REV_A.csv", 16),
}

CONTROLLED_BASELINE_SOURCES = [
    BASELINE_PATH,
    MANUAL_PATH,
    ROOT / "config/EVT_PRE_20_BASELINE.yaml",
    ROOT / "hardware/PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv",
    ROOT / "hardware/HARNESS_EVT_LENGTH_BASIS_REV_A.csv",
    ROOT / "hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv",
    ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv",
    *(ROOT / relative for relative, _ in REGISTERS.values()),
    Path(__file__).resolve(),
]


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def validate_git_binding(
    commit_sha: str | None,
    require_clean_source: bool,
    extra_sources: Iterable[Path] = (),
) -> None:
    """Bind an emitted audit to HEAD and its controlled source set when requested."""
    if require_clean_source:
        require(bool(commit_sha), "--require-clean-source requires --commit-sha")
    if commit_sha:
        require(re.fullmatch(r"[0-9a-f]{40}", commit_sha) is not None,
                f"invalid evidence commit SHA: {commit_sha!r}")
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        require(head == commit_sha, f"evidence commit {commit_sha} != checked-out HEAD {head}")
    if require_clean_source:
        sources = list(dict.fromkeys([*CONTROLLED_BASELINE_SOURCES, *extra_sources]))
        relative_sources = [str(path.resolve().relative_to(ROOT)) for path in sources]
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *relative_sources],
            cwd=ROOT,
            text=True,
        ).strip()
        require(not dirty, f"controlled EVT engineering baseline source set is dirty: {dirty}")


def read_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def read_csv(relative: str) -> list[dict[str, str]]:
    with (ROOT / relative).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def audit() -> dict[str, object]:
    baseline = read_json(str(BASELINE_PATH.relative_to(ROOT)))
    require(
        baseline.get("schema") == "dioneya-evt-engineering-manufacturing-baseline-v1",
        "baseline schema drift",
    )
    require(baseline.get("configuration") == "EVT-PRE-20 Rev.A", "configuration drift")
    require(baseline.get("decision_date") == "2026-09-21", "decision date drift")
    require(
        baseline.get("status") ==
        "ACCEPTED_EVT_ENGINEERING_BASELINE_EXTERNAL_REPLIES_NOT_REQUIRED",
        "baseline status drift",
    )
    policy = baseline.get("policy", {})
    for key in (
        "customer_places_pcb_and_pcba_orders",
        "public_manufacturer_data_may_close_external_answer_gates",
        "order_portal_dfm_and_file_parser_must_pass",
        "factory_detected_geometry_or_process_error_is_stop_gate",
        "evt_physical_validation_required",
        "series_transfer_requires_revalidation",
    ):
        require(policy.get(key) is True, f"policy flag not enabled: {key}")
    require(policy.get("job_specific_email_or_signed_factory_reply_required") is False,
            "external reply was made mandatory again")
    require(policy.get("manufacturing_release_implied") is False,
            "engineering baseline incorrectly implies manufacturing release")

    urls = {row["id"]: row["url"] for row in baseline.get("official_sources", [])}
    for source_id in (
        "JLC-PCB-CAP", "JLC-IMP", "JLC-PCBA-CAP",
        "MOLEX-PICOLOCK-5040520098", "MOLEX-MICROFIT-430300038",
        "MOLEX-MICROFIT-430300001", "MOLEX-MICROFIT-ATS-638190000",
        "TE-SPEC55-18", "TE-SPEC55-24", "ALPHA-3051", "TE-SOLISTRAND-M8",
    ):
        require(source_id in urls and urls[source_id].startswith("https://"),
                f"official source missing: {source_id}")

    main = baseline["pcb_main"]
    require(main["stackup_id"] == "JLC06161H-3313", "MAIN stackup drift")
    require(main["layers"] == 6 and main["outer_copper_oz"] == 1.0
            and main["inner_copper_oz"] == 0.5, "MAIN construction drift")
    require(main["impedance_tolerance_percent"] == 10, "MAIN impedance tolerance drift")
    require(main["rf_50ohm"]["trace_width_mm"] == 0.1509, "MAIN RF geometry drift")
    require(main["usb_90ohm"]["trace_width_mm"] == 0.1537
            and main["usb_90ohm"]["pair_gap_mm"] == 0.2032,
            "MAIN USB geometry drift")
    require(main["external_reply_required"] is False
            and main["routing_authorized"] is True
            and main["manufacturing_release"] is False,
            "MAIN release boundary drift")

    pwr = baseline["pcb_pwr"]
    require(pwr["stackup_id"] == "JLC04161H-3313A", "PWR stackup drift")
    require(pwr["layers"] == 4 and pwr["outer_finished_copper_um"] == 70
            and pwr["inner_finished_copper_um"] == 35, "PWR copper drift")
    require(pwr["minimum_average_hole_wall_plating_um"] == 18, "PWR plating drift")
    require(pwr["numeric_power_geometry_authorized"] is True
            and pwr["routing_authorized"] is True
            and pwr["manufacturing_release"] is False,
            "PWR release boundary drift")

    geometry = read_csv(pwr["current_geometry_table"])
    expected_geometry = {
        "BATTERY_INPUT_5A": ("5.0", "2.00", "4"),
        "BUCK_RATED_4A": ("4.0", "1.50", "3"),
        "MODEM_PEAK_3P3A": ("3.3", "1.50", "3"),
        "MIC_RAIL_0P3A": ("0.3", "0.30", "2"),
    }
    by_class = {row["Path_class"]: row for row in geometry}
    for path_class, (current, width, vias) in expected_geometry.items():
        row = by_class.get(path_class, {})
        require((row.get("Current_A"), row.get("Minimum_width_or_neck_mm"),
                 row.get("Minimum_parallel_vias")) == (current, width, vias),
                f"PWR geometry drift: {path_class}")

    mic = baseline["pcb_mic"]
    require(mic["layers"] == 2 and mic["nominal_order_thickness_mm"] == 1.0,
            "MIC construction drift")
    require(mic["general_minimum_npth_to_copper_mm"] == 0.20,
            "MIC general NPTH clearance drift")
    exception = mic["acoustic_land_pattern_exception"]
    require(exception["minimum_npth_to_ground_land_mm"] == 0.10
            and exception["first_article_required"] is True
            and "GROUND LAND" in exception["scope"].upper(),
            "MIC acoustic exception is not tightly bounded")
    require(mic["external_reply_required"] is False
            and mic["dfm_baseline_accepted"] is True
            and mic["manufacturing_release"] is False,
            "MIC release boundary drift")

    pcba = baseline["pcba"]
    require(pcba["service_class"] == "standard PCBA", "PCBA class drift")
    require(pcba["paste"] == "SAC305 no-clean Type 4", "paste drift")
    require(pcba["stencil"]["thickness_um"] == 100, "stencil drift")
    require(pcba["reflow"]["peak_c"] == 240
            and pcba["reflow"]["peak_tolerance_c"] == 5,
            "reflow peak drift")
    require(pcba["first_article"] == {
        "quantity": 2,
        "remaining_lot_hold_quantity": 20,
        "release_after": "SPI/AOI/X-ray disposition plus rail-current-limited smoke and interface tests",
    }, "first-article plan drift")
    require(pcba["external_reply_required"] is False
            and pcba["manufacturing_release"] is False,
            "PCBA release boundary drift")

    harness = baseline["harness"]
    require(harness["length_margin_percent"] == 10, "harness margin drift")
    require(harness["external_reply_required"] is False
            and harness["build_authorized"] is True
            and harness["manufacturing_release"] is False,
            "harness release boundary drift")
    require(harness["wire_selections"]["microphone_24awg"]["nominal_od_mm"] == 0.94,
            "MIC wire OD drift")
    require(harness["wire_selections"]["main_power_and_battery_18awg"]["nominal_od_mm"] == 1.52,
            "18 AWG wire OD drift")
    require(harness["wire_selections"]["main_control_22awg"]["nominal_od_mm"] == 1.575,
            "22 AWG wire OD drift")

    lengths = read_csv(harness["length_table"])
    length_map = {row["Harness_ID"]: row for row in lengths}
    require(set(length_map) == {"H-MIC1", "H-MIC2", "H-MIC3", "H-MIC4", "H-MAIN-PWR", "H-BAT-PWR"},
            "harness length set drift")
    for harness_id in ("H-MIC1", "H-MIC2", "H-MIC3", "H-MIC4"):
        require(length_map[harness_id]["Base_route_mm"] == "250"
                and length_map[harness_id]["Released_cut_length_mm"] == "275",
                f"MIC length drift: {harness_id}")
    require(length_map["H-MAIN-PWR"]["Base_route_mm"] == "400"
            and length_map["H-MAIN-PWR"]["Released_cut_length_mm"] == "440",
            "MAIN-PWR length drift")
    require(length_map["H-BAT-PWR"]["Base_route_mm"] == "300"
            and length_map["H-BAT-PWR"]["Released_cut_length_mm"] == "330",
            "BAT-PWR length drift")
    require(all(row["Margin_percent"] == "10" and row["Cut_tolerance_mm"] == "5"
                for row in lengths), "harness margin/tolerance drift")

    schedule = read_csv("hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv")
    require(len(schedule) == 38, "harness conductor count drift")
    expected_lengths = {"H-MIC1": "275", "H-MIC2": "275", "H-MIC3": "275",
                        "H-MIC4": "275", "H-MAIN-PWR": "440", "H-BAT-PWR": "330"}
    require(all(row["Cut_Length_mm"] == expected_lengths[row["Harness_ID"]]
                and row["Length_Tolerance_mm"] == "5"
                and row["Release_Status"] == "EVT_BUILD_RELEASED_FIRST_ARTICLE_REQUIRED"
                for row in schedule), "manufacturing schedule did not receive released lengths")
    require(all("AWG24_TE_55A0111-24" in row["Wire_Gauge"]
                for row in schedule if row["Harness_ID"].startswith("H-MIC")),
            "MIC schedule wire selection drift")

    register_summary: dict[str, dict[str, object]] = {}
    for group, (relative, expected_count) in REGISTERS.items():
        rows = read_csv(relative)
        require(len(rows) == expected_count, f"{group}: response row count drift")
        require(all(row["Disposition"] == "CLOSED_EVT_ENGINEERING_BASELINE"
                    and row["Blocking"] == "NO"
                    and row["Response_Reference"]
                    and row["Responder"]
                    and row["Response_Date"] == "2026-09-21"
                    for row in rows), f"{group}: external wait rows are not closed")
        register_summary[group] = {
            "rows": len(rows),
            "closed": len(rows),
            "pending": 0,
            "external_reply_required": False,
        }

    baseline_config = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    for token in (
        "job_specific_manufacturing_technical_responses_required: false",
        "evt_public_engineering_baseline_authorized: true",
        "customer_order_checkout_dfm_must_pass: true",
        "series_transfer_manufacturing_revalidation_required: true",
    ):
        require(token in baseline_config, f"configuration token missing: {token}")

    bom = {row["Item_ID"]: row for row in read_csv("hardware/EVT_PRE_20_BOM_REV_A.csv")}
    for item_id in ("ASM-MAIN", "PCB-MAIN", "ASM-PWR", "PCB-PWR", "ASM-MIC", "PCB-MIC", "HARNESS"):
        row = bom[item_id]
        require(row["Manufacturer"] not in {"", "TBD", "Contract manufacturer", "Qualified PCB fab"}
                and row["MPN"] not in {"", "TBD"}, f"{item_id}: order identity is not controlled")
        require(not row["BOM_disposition"].startswith("BLOCKED"),
                f"{item_id}: old external-selection BOM blocker remains")

    require(MANUAL_PATH.is_file() and MANUAL_PATH.stat().st_size > 5000,
            "engineering manual missing or incomplete")

    return {
        "schema": "dioneya-evt-engineering-manufacturing-baseline-audit-v1",
        "configuration": baseline["configuration"],
        "status": "PASS_EVT_ENGINEERING_BASELINE_EXTERNAL_REPLIES_CLOSED",
        "decision_date": baseline["decision_date"],
        "external_response_rows_closed": sum(count for _, count in REGISTERS.values()),
        "external_response_rows_pending": 0,
        "external_reply_required": False,
        "pcb_main": {
            "stackup": main["stackup_id"],
            "stackup_accepted": True,
            "rf_50ohm_numeric_geometry_accepted": True,
            "usb_90ohm_numeric_geometry_accepted": True,
            "routing_authorized": True,
        },
        "pcb_pwr": {
            "stackup": pwr["stackup_id"],
            "stackup_accepted": True,
            "copper_weights_and_plating_accepted": True,
            "numeric_power_geometry_authorized": True,
            "routing_authorized": True,
        },
        "pcb_mic": {"dfm_baseline_accepted": True},
        "pcba": {"standard_process_accepted": True, "first_article_quantity": 2},
        "harness": {
            "controlled_conductors": len(schedule),
            "final_lengths_accepted": True,
            "wire_avl_accepted": True,
            "build_authorized": True,
            "first_article_accepted": False,
        },
        "registers": register_summary,
        "review_b_complete": False,
        "manufacturing_release": False,
        "series_revalidation_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit()
        exit_code = 0
    except Exception as exc:
        result = {
            "schema": "dioneya-evt-engineering-manufacturing-baseline-audit-v1",
            "status": "FAIL_EVT_ENGINEERING_BASELINE_AUDIT",
            "error": str(exc),
            "manufacturing_release": False,
        }
        exit_code = 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(result["status"])
    if "error" in result:
        print(result["error"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

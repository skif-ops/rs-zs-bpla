#!/usr/bin/env python3
"""Independent calculation and freeze audit for EVT-PRE-20 PCB-PWR Rev.A.

This is the first control contour for PCB-PWR and deliberately does not import any
future schematic/PCB generator. Numeric expectations are read from a machine-readable
controlled baseline and independently recomputed here. The audit can authorize native
capture, but it can never authorize FOR_MANUFACTURE while release_open_items remain.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def close(actual: float, expected: float, abs_tol: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=abs_tol):
        raise RuntimeError(
            f"{label}: actual={actual:.12g}, expected={expected:.12g}, tol={abs_tol:.12g}"
        )


def read_freeze(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    require(rows, f"empty component freeze: {path}")
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        cid = row.get("Component_ID", "").strip()
        require(cid, f"component freeze row without Component_ID: {row}")
        require(cid not in by_id, f"duplicate Component_ID in freeze: {cid}")
        by_id[cid] = row
    return by_id


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    require(rows, f"empty controlled CSV: {path}")
    return rows


def index_unique(
    rows: list[dict[str, str]], key: str, *, label: str
) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        value = row.get(key, "").strip()
        require(value, f"{label} row without {key}: {row}")
        require(value not in indexed, f"duplicate {label} {key}: {value}")
        indexed[value] = row
    return indexed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "hardware" / "POWER_DESIGN_BASELINE_REV_A.json",
    )
    ap.add_argument(
        "--freeze",
        type=Path,
        default=ROOT / "hardware" / "POWER_COMPONENT_FREEZE_REV_A.csv",
    )
    ap.add_argument(
        "--calc-doc",
        type=Path,
        default=ROOT / "hardware" / "POWER_DESIGN_CALC_REV_A.md",
    )
    ap.add_argument(
        "--primary-evidence",
        type=Path,
        default=ROOT / "hardware" / "reviews" / "PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.json",
    )
    ap.add_argument(
        "--primary-evidence-record",
        type=Path,
        default=ROOT / "hardware" / "reviews" / "PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.md",
    )
    ap.add_argument(
        "--pin-authority",
        type=Path,
        default=ROOT / "hardware" / "PCB_PWR_PIN_AUTHORITY_REV_A.csv",
    )
    ap.add_argument(
        "--passive-authority",
        type=Path,
        default=ROOT / "hardware" / "PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv",
    )
    ap.add_argument(
        "--placement-authority",
        type=Path,
        default=ROOT / "hardware" / "PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv",
    )
    ap.add_argument(
        "--capture-status",
        type=Path,
        default=ROOT / "hardware" / "PCB_PWR_CAPTURE_STATUS_REV_A.json",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "kicad-native" / "PCB-PWR" / "design_audit.json",
    )
    args = ap.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    freeze = read_freeze(args.freeze)
    calc_doc = args.calc_doc.read_text(encoding="utf-8")
    primary_evidence = json.loads(args.primary_evidence.read_text(encoding="utf-8"))
    primary_evidence_record = args.primary_evidence_record.read_text(encoding="utf-8")
    pin_rows = read_csv_rows(args.pin_authority)
    passive_by_ref = index_unique(
        read_csv_rows(args.passive_authority), "RefDes", label="PCB-PWR passive"
    )
    placement_by_ref = index_unique(
        read_csv_rows(args.placement_authority), "RefDes", label="PCB-PWR placement"
    )
    capture_status = json.loads(args.capture_status.read_text(encoding="utf-8"))
    checks: list[dict[str, object]] = []

    def record(name: str, **data: object) -> None:
        checks.append({"check": name, "status": "PASS", **data})

    require(baseline["configuration"] == "EVT-PRE-20 Rev.A", "configuration mismatch")
    require(
        baseline["status"] == "CAPTURE_BASELINE_NOT_FOR_MANUFACTURE",
        "PCB-PWR baseline must remain explicitly NOT FOR MANUFACTURE",
    )
    record("baseline_identity", configuration=baseline["configuration"], status=baseline["status"])

    # Cross-check exact component identities against the separate component-freeze file.
    expected_mpns = {
        "PWR-REV-CTL": baseline["reverse_protection"]["controller_mpn"],
        "PWR-REV-FET": baseline["reverse_protection"]["mosfet_mpn"],
        "U-PWR1": baseline["buck_3v8"]["mpn"],
        "U-PWR2": baseline["buck_3v3"]["mpn"],
        "U-PWR3": baseline["mic_ldo"]["mpn"],
        "U-MON-01": baseline["current_monitor"]["mpn"],
        "PWR-L": baseline["buck_3v8"]["inductor_mpn"],
        "R-SHUNT-01": baseline["current_monitor"]["shunt_mpn"],
    }
    for cid, mpn in expected_mpns.items():
        require(cid in freeze, f"missing frozen component {cid}")
        require(freeze[cid]["MPN"].strip() == mpn, f"{cid} MPN mismatch: {freeze[cid]['MPN']} != {mpn}")
    require("PWR-TVS-01" in freeze and "CANDIDATE" in freeze["PWR-TVS-01"]["Status"], "TVS must remain candidate until surge profile freeze")
    require("PWR-FUSE-01" in freeze and "CANDIDATE" in freeze["PWR-FUSE-01"]["Status"], "PCB fuse must remain candidate until coordination test")
    record("component_freeze_crosscheck", exact_mpns=expected_mpns)

    # Bind the disputed power-IC behavior to exact retrieved TI documents and to
    # the controlled schematic authorities. The vendor PDFs are intentionally not
    # copied into the repository; the canonical URLs, byte sizes and SHA-256 values
    # make the retrieved sources reproducible without adding third-party binaries.
    require(primary_evidence["schema_version"] == 1, "TI primary-evidence schema drift")
    require(primary_evidence["configuration"] == "EVT-PRE-20 Rev.A", "TI evidence configuration mismatch")
    require(primary_evidence["assembly"] == "PCB-PWR", "TI evidence assembly mismatch")
    require(
        primary_evidence["status"]
        == "PASS_PRIMARY_SOURCE_BINDING_SCHEMATIC_UNCHANGED_NOT_FOR_MANUFACTURE",
        "TI evidence must remain explicitly NOT FOR MANUFACTURE",
    )
    sources = primary_evidence["sources"]
    lmr = sources["lmr60440_datasheet"]
    require(lmr["publisher"] == "Texas Instruments", "LMR60440 publisher mismatch")
    require(lmr["document_id"] == "SNAS877", "LMR60440 document ID mismatch")
    require(lmr["document_date"] == "2024-12", "LMR60440 document date mismatch")
    require(
        lmr["canonical_url"] == "https://www.ti.com/lit/ds/symlink/lmr60440.pdf",
        "LMR60440 canonical URL mismatch",
    )
    require(
        lmr["sha256"] == "d2feebeb32432de6f7d7da1e45d0d7dcad01f0ddd14fc1a403941efb2c0387db",
        "LMR60440 retrieved PDF SHA-256 mismatch",
    )
    require(lmr["file_size_bytes"] == 1675183 and lmr["pages"] == 38, "LMR60440 PDF metadata mismatch")
    lmr_claims = lmr["claims"]
    orderable_claim = lmr_claims["exact_orderable_mode"]
    require(orderable_claim["pdf_page"] == 3, "LMR60440 device-comparison page mismatch")
    require(orderable_claim["orderable_part_number"] == "LMR604403SRAKR", "LMR60440 exact orderable mismatch")
    close(float(orderable_claim["output_current_a"]), 4.0, 1e-12, "LMR60440 orderable output current")
    require(orderable_claim["output_voltage_option"] == "3.3V fixed / adjustable", "LMR60440 mode option mismatch")
    require(orderable_claim["spread_spectrum"] is True, "LMR604403 spread-spectrum option mismatch")
    fixed_claim = lmr_claims["fixed_mode_selection"]
    adjustable_claim = lmr_claims["adjustable_mode_selection"]
    require(fixed_claim["pdf_page"] == 13, "LMR60440 fixed-mode page mismatch")
    close(float(fixed_claim["fb_to_vout_max_ohm_exclusive"]), 1.0, 1e-12, "LMR60440 fixed-mode threshold")
    require(adjustable_claim["pdf_page"] == 13, "LMR60440 adjustable-mode page mismatch")
    close(float(adjustable_claim["feedback_parallel_min_ohm_exclusive"]), 3000.0, 1e-9, "LMR60440 adjustable-mode threshold")
    close(float(adjustable_claim["vfb_typ_v"]), 1.0, 1e-12, "LMR60440 typical VFB")
    fixed_3v3 = lmr_claims["fixed_3v3_electrical_characteristic"]
    require(fixed_3v3["pdf_page"] == 6, "LMR60440 fixed-3V3 characteristic page mismatch")
    close(float(fixed_3v3["minimum_v"]), 3.24, 1e-12, "LMR60440 fixed-3V3 minimum")
    close(float(fixed_3v3["typical_v"]), 3.3, 1e-12, "LMR60440 fixed-3V3 typical")
    close(float(fixed_3v3["maximum_v"]), 3.35, 1e-12, "LMR60440 fixed-3V3 maximum")
    input_caps = lmr_claims["input_capacitors"]
    require(input_caps["pdf_page"] == 22, "LMR60440 input-capacitor page mismatch")
    close(float(input_caps["cin_hf_f"]), 100e-9, 1e-15, "LMR60440 CIN_HF")
    close(float(input_caps["cin_f"]), 4.7e-6, 1e-12, "LMR60440 CIN")
    close(float(input_caps["cin_hf_min_voltage_rating_v"]), 50.0, 1e-12, "LMR60440 CIN_HF voltage rating")
    close(float(input_caps["cin_min_voltage_rating_v"]), 50.0, 1e-12, "LMR60440 CIN voltage rating")

    addendum = sources["lmr60440_package_option_addendum"]
    require(addendum["publisher"] == "Texas Instruments", "LMR60440 addendum publisher mismatch")
    require(addendum["document_date"] == "2025-11-08", "LMR60440 addendum date mismatch")
    require(
        addendum["canonical_url"] == "https://www.ti.com/ods/sysadd/oa/symlink/lmr60440_oa.pdf",
        "LMR60440 addendum URL mismatch",
    )
    require(
        addendum["sha256"] == "9dfebc7b17b130ce20b3509dfa5992d8f86493511154632305df1160d03f40c5",
        "LMR60440 addendum SHA-256 mismatch",
    )
    require(addendum["file_size_bytes"] == 16856 and addendum["pages"] == 2, "LMR60440 addendum metadata mismatch")
    require(addendum["pdf_page"] == 1, "LMR60440 addendum evidence page mismatch")
    require(addendum["orderable_part_number"] == "LMR604403SRAKR", "LMR60440 addendum orderable mismatch")
    require(addendum["status"] == "Active" and addendum["material_type"] == "Production", "LMR60440 orderable is not Active Production")
    require(addendum["package"] == "WQFN-HR (RAK)" and addendum["pins"] == 9, "LMR60440 package identity mismatch")
    require(addendum["part_marking"] == "4403S", "LMR60440 part marking mismatch")

    lm74700 = sources["lm74700_q1_datasheet"]
    require(lm74700["publisher"] == "Texas Instruments", "LM74700-Q1 publisher mismatch")
    require(lm74700["document_id"] == "SNOSD17G" and lm74700["revision"] == "G", "LM74700-Q1 document identity mismatch")
    require(
        lm74700["canonical_url"] == "https://www.ti.com/lit/ds/symlink/lm74700-q1.pdf",
        "LM74700-Q1 canonical URL mismatch",
    )
    require(
        lm74700["sha256"] == "e16b3a8c0023201fafa5825436f5f2dd6f885b92b84e65602b3f50d741c58b6f",
        "LM74700-Q1 retrieved PDF SHA-256 mismatch",
    )
    require(lm74700["file_size_bytes"] == 2657068 and lm74700["pages"] == 36, "LM74700-Q1 PDF metadata mismatch")
    vcap_roc = lm74700["claims"]["vcap_recommended_operating_condition"]
    require(vcap_roc["pdf_page"] == 5 and vcap_roc["connection"] == "VCAP to ANODE", "LM74700-Q1 VCAP evidence mismatch")
    close(float(vcap_roc["capacitance_f"]), 100e-9, 1e-15, "LM74700-Q1 VCAP recommendation")
    vcap_test = lm74700["claims"]["vcap_electrical_test_condition"]
    require(vcap_test["pdf_page"] == 6, "LM74700-Q1 VCAP test-condition page mismatch")
    close(float(vcap_test["capacitance_f"]), 100e-9, 1e-15, "LM74700-Q1 VCAP test condition")

    pin_by_ref_pin: dict[tuple[str, str], dict[str, str]] = {}
    for row in pin_rows:
        key = (row["RefDes"].strip(), row["Pin"].strip())
        require(key not in pin_by_ref_pin, f"duplicate PCB-PWR pin authority row: {key}")
        pin_by_ref_pin[key] = row
    for refdes in ("U3", "U4"):
        rows = [row for row in pin_rows if row["RefDes"].strip() == refdes]
        require(len(rows) == 9, f"{refdes} does not have exactly nine controlled pins")
        require({row["MPN"].strip() for row in rows} == {"LMR604403SRAKR"}, f"{refdes} exact MPN drift")
    require(pin_by_ref_pin[("U3", "6")]["RevA_Net"].strip() == "FB_3V8", "U3 FB net mismatch")
    require(pin_by_ref_pin[("U4", "6")]["RevA_Net"].strip() == "3V3_DIGITAL", "U4 fixed FB net mismatch")

    bindings = primary_evidence["design_binding"]
    u3_binding = bindings["U3"]
    u4_binding = bindings["U4"]
    require(u3_binding["mpn"] == "LMR604403SRAKR" and u3_binding["mode"] == "ADJUSTABLE", "U3 evidence binding mismatch")
    require(u4_binding["mpn"] == "LMR604403SRAKR" and u4_binding["mode"] == "FIXED_3V3", "U4 evidence binding mismatch")
    require(u4_binding["direct_fb_to_output"] is True and u4_binding["fb_net"] == u4_binding["output_net"] == "3V3_DIGITAL", "U4 direct FB-to-output binding missing")
    require(passive_by_ref["R1"]["Value"].strip() == "100 kOhm 0.1%", "R1 feedback value mismatch")
    require(passive_by_ref["R1"]["Pin_Map"].strip() == "1=3V8_MODEM;2=FB_3V8", "R1 feedback nets mismatch")
    require(passive_by_ref["R2"]["Value"].strip() == "35.7 kOhm 0.1%", "R2 feedback value mismatch")
    require(passive_by_ref["R2"]["Pin_Map"].strip() == "1=FB_3V8;2=GND_PWR", "R2 feedback nets mismatch")
    rfbt = float(u3_binding["top_resistor"]["ohm"])
    rfbb = float(u3_binding["bottom_resistor"]["ohm"])
    feedback_parallel = rfbt * rfbb / (rfbt + rfbb)
    nominal_output = float(adjustable_claim["vfb_typ_v"]) * (1.0 + rfbt / rfbb)
    close(feedback_parallel, float(u3_binding["feedback_parallel_ohm"]), 1e-6, "U3 feedback parallel binding")
    close(nominal_output, float(u3_binding["nominal_output_v"]), 1e-9, "U3 nominal output binding")
    require(feedback_parallel > float(adjustable_claim["feedback_parallel_min_ohm_exclusive"]), "U3 does not select adjustable mode")
    require(u3_binding["mode_threshold_pass"] is True and u4_binding["mode_threshold_pass"] is True, "LMR60440 mode binding not accepted")

    expected_passives = {
        "C1": ("100 nF 25 V X7R", "1=LM74700_VCAP;2=VBAT_FUSED"),
        "C11": ("4.7 uF 50 V X7R", "1=VBAT_SYS;2=GND_PWR"),
        "C12": ("4.7 uF 50 V X7R", "1=VBAT_SYS;2=GND_PWR"),
        "C20": ("100 nF 50 V X7R", "1=VBAT_SYS;2=GND_PWR"),
        "C21": ("100 nF 50 V X7R", "1=VBAT_SYS;2=GND_PWR"),
        "C13": ("100 uF 35 V hybrid", "1=VBAT_SYS;2=GND_PWR"),
    }
    for refdes, (value, pin_map) in expected_passives.items():
        require(passive_by_ref[refdes]["Value"].strip() == value, f"{refdes} controlled value mismatch")
        require(passive_by_ref[refdes]["Pin_Map"].strip() == pin_map, f"{refdes} controlled nets mismatch")

    def xy(refdes: str) -> tuple[float, float]:
        row = placement_by_ref[refdes]
        return float(row["X_mm"]), float(row["Y_mm"])

    def distance(a: str, b: str) -> float:
        ax, ay = xy(a)
        bx, by = xy(b)
        return math.hypot(ax - bx, ay - by)

    local_inputs = bindings["local_input_networks"]
    for ic, cin, cin_hf in (("U3", "C11", "C20"), ("U4", "C12", "C21")):
        bound = local_inputs[ic]
        require(bound["cin"] == cin and bound["cin_hf"] == cin_hf, f"{ic} local input binding mismatch")
        close(distance(ic, cin), float(bound["center_distance_cin_to_ic_mm"]), 1e-9, f"{ic} CIN placement distance")
        close(distance(ic, cin_hf), float(bound["center_distance_cin_hf_to_ic_mm"]), 1e-9, f"{ic} CIN_HF placement distance")
        require(bound["routed_loop_acceptance"] is False, f"{ic} routed loop must remain unaccepted")
    central_bulk = local_inputs["central_bulk"]
    require(central_bulk["refdes"] == "C13", "central bulk binding mismatch")
    require(central_bulk["role"] == "VBAT_SYS_DAMPING_NOT_LOCAL_CIN_SUBSTITUTE", "C13 role weakened")
    close(distance("C13", "U3"), float(central_bulk["center_distance_to_u3_mm"]), 1e-6, "C13-to-U3 distance")
    close(distance("C13", "U4"), float(central_bulk["center_distance_to_u4_mm"]), 1e-6, "C13-to-U4 distance")

    release_boundary = primary_evidence["release_boundary"]
    require(release_boundary["electrical_schematic_changed_by_this_record"] is False, "TI evidence unexpectedly claims an electrical ECO")
    require(release_boundary["native_schematic_source_commit"] == "e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a", "TI evidence source-commit binding mismatch")
    require(release_boundary["review_pdf_sha256"] == "7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130", "TI evidence PDF binding mismatch")
    for field in ("independent_human_hierarchy_acceptance_complete", "routing_authorized", "procurement_authorized", "manufacturing_release"):
        require(release_boundary[field] is False, f"TI evidence release interlock weakened: {field}")
    required_open_controls = {
        "C11_C12_effective_capacitance_at_bias_and_temperature",
        "C11_C12_C20_C21_routed_hot_loop_acceptance",
        "input_filter_or_no_filter_pre_route_decision_EVT_PWR_02_03_04",
        "F1_8A_thermal_I2t_harness_and_primary_fuse_coordination",
        "BG95_end_to_end_burst_and_hot_harness_evidence",
        "PG_3V8_remains_TP5_only_by_intent",
        "DIM_003_stackup_routing_DRC_DFM_review_B",
    }
    require(required_open_controls.issubset(set(release_boundary["open_controls"])), "TI evidence open-control set weakened")
    status_traceability = capture_status["ti_primary_source_evidence"]
    require(
        status_traceability["record"]
        == "hardware/reviews/PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.md",
        "PCB-PWR capture status TI evidence record drift",
    )
    require(
        status_traceability["machine_contract"]
        == "hardware/reviews/PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.json",
        "PCB-PWR capture status TI evidence contract drift",
    )
    require(
        status_traceability["independent_audit"] == "tools/audit_pcb_pwr_design_rev_a.py",
        "PCB-PWR capture status TI evidence audit drift",
    )
    evidence_control = status_traceability["control"]
    require(
        evidence_control["state"] == "PASS_TI_PRIMARY_SOURCE_BINDING_SCHEMATIC_UNCHANGED",
        "PCB-PWR capture status TI evidence state mismatch",
    )
    require(evidence_control["exact_buck_mpn"] == "LMR604403SRAKR", "PCB-PWR status buck MPN mismatch")
    require(evidence_control["exact_buck_orderable_status"] == "Active Production", "PCB-PWR status orderable state mismatch")
    require(evidence_control["u3_mode"] == "ADJUSTABLE_3V801120", "PCB-PWR status U3 mode mismatch")
    require(evidence_control["u4_mode"] == "FIXED_3V3", "PCB-PWR status U4 mode mismatch")
    close(float(evidence_control["lm74700_vcap_f"]), 100e-9, 1e-15, "PCB-PWR status VCAP")
    require(
        evidence_control["source_sha256"]
        == {
            "SNAS877": lmr["sha256"],
            "LMR60440_PACKAGE_OPTION_ADDENDUM": addendum["sha256"],
            "SNOSD17G": lm74700["sha256"],
        },
        "PCB-PWR status TI source hashes mismatch",
    )
    for field in (
        "electrical_schematic_changed",
        "independent_human_hierarchy_acceptance_complete",
        "routing_authorized",
        "manufacturing_release",
    ):
        require(evidence_control[field] is False, f"PCB-PWR status TI evidence interlock weakened: {field}")
    required_record_tokens = [
        "LMR604403SRAKR",
        "3.3V fixed / adjustable",
        "26.308 kohm > 3 kohm",
        "3.801120 V",
        "SNOSD17G",
        "C1=100 nF, 25 V",
        "C13",
        "used as a substitute",
        "NOT FOR MANUFACTURE",
    ]
    missing_evidence_tokens = [token for token in required_record_tokens if token not in primary_evidence_record]
    require(not missing_evidence_tokens, f"TI primary-evidence record drift: {missing_evidence_tokens}")
    record(
        "ti_primary_source_binding",
        exact_orderable="LMR604403SRAKR",
        orderable_status="Active Production",
        modes={"U3": "ADJUSTABLE_3V801", "U4": "FIXED_3V3"},
        vcap_f=100e-9,
        source_sha256={
            "SNAS877": lmr["sha256"],
            "LMR60440_PACKAGE_OPTION_ADDENDUM": addendum["sha256"],
            "SNOSD17G": lm74700["sha256"],
        },
        schematic_changed=False,
        manufacturing_release=False,
    )

    # The human calculation record is a separate controlled representation. Make drift
    # between it and the machine baseline blocking before schematic capture starts.
    required_doc_tokens = [
        "CAPTURE BASELINE - NOT FOR MANUFACTURE",
        "LM74700QDBVRQ1",
        "CSD18540Q5B",
        "LMR604403SRAKR",
        "TPS7A2018PDBVR",
        "INA226AIDGSR",
        "XAL7030-472MEC",
        "WSK2512R0100FEA",
        "400 kHz",
        "4.7 uH",
        "86.6 kOhm",
        "35.7 kOhm",
        "10 mOhm",
        "2560",
    ]
    missing_tokens = [token for token in required_doc_tokens if token not in calc_doc]
    require(not missing_tokens, f"POWER_DESIGN_CALC_REV_A.md drift/missing controlled tokens: {missing_tokens}")
    record("human_calc_record_crosscheck", tokens=len(required_doc_tokens))

    inp = baseline["input"]
    rev = baseline["reverse_protection"]
    b38 = baseline["buck_3v8"]
    b33 = baseline["buck_3v3"]
    modem = baseline["modem"]
    ldo = baseline["mic_ldo"]
    mon = baseline["current_monitor"]

    require(inp["working_min_v"] < inp["working_max_v"], "invalid provisional battery working window")
    require(rev["controller_vin_min_v"] <= inp["working_min_v"] <= rev["controller_vin_max_v"], "battery low end outside LM74700 controller range")
    require(rev["controller_vin_min_v"] <= inp["working_max_v"] <= rev["controller_vin_max_v"], "battery high end outside LM74700 controller range")
    require(b38["vin_min_v"] <= inp["working_min_v"] and inp["working_max_v"] <= b38["vin_max_v"], "battery working window outside LMR60440 range")
    require(not inp["actual_battery_bms_limits_frozen"], "unexpected claim that battery/BMS limits are frozen")
    require(not inp["transient_envelope_frozen"], "unexpected claim that transient envelope is frozen")
    record("input_window", working_v=[inp["working_min_v"], inp["working_max_v"]], release_limits_frozen=False)

    require(rev["mosfet_vds_v"] >= 60.0, "reverse MOSFET VDS margin changed below 60 V")
    require(rev["mosfet_rds_on_max_mohm_at_10v"] <= 2.2, "reverse MOSFET Rds(on) exceeds baseline")
    record("reverse_protection_ratings", controller_vin_max_v=rev["controller_vin_max_v"], mosfet_vds_v=rev["mosfet_vds_v"])

    # LMR60440 3.8-V adjustable rail: recompute independently from VFB and divider.
    rfbt = float(b38["rfbt_ohm"])
    rfbb = float(b38["rfbb_ohm"])
    vfb = float(b38["vfb_typ_v"])
    calculated_vout = vfb * (1.0 + rfbt / rfbb)
    close(calculated_vout, 3.8011204481792717, 1e-9, "3V8 divider recomputation")
    require(abs(calculated_vout - b38["target_vout_v"]) <= 0.005, "3V8 nominal divider error exceeds 5 mV capture target")
    require(modem["vbat_min_v"] < calculated_vout < modem["vbat_max_v"], "3V8 nominal outside BG95-M3 VBAT range")
    require(b38["adjustable_min_v"] <= calculated_vout <= b38["adjustable_max_v"], "3V8 target outside LMR60440 adjustable range")
    record(
        "buck_3v8_feedback",
        vout_calculated_v=calculated_vout,
        low_margin_v=calculated_vout - modem["vbat_min_v"],
        high_margin_v=modem["vbat_max_v"] - calculated_vout,
    )

    # TI 400-kHz application baseline cross-checks.
    close(float(b38["switching_frequency_hz"]), 400000.0, 0.1, "3V8 switching frequency")
    close(float(b38["rt_ohm"]), 86600.0, 0.1, "3V8 RT")
    close(float(b38["inductor_h"]), 4.7e-6, 1e-12, "3V8 inductance")
    require(float(b38["cout_effective_min_f"]) >= 54e-6, "3V8 effective COUT below 54 uF")
    require(float(b38["cin_min_f"]) >= 4.7e-6, "3V8 CIN below 4.7 uF")
    close(float(b38["cboot_f"]), 100e-9, 1e-12, "3V8 CBOOT")
    require(float(b38["cboot_voltage_min_v"]) >= 10.0, "3V8 CBOOT voltage rating below 10 V")
    require(float(b38["inductor_isat_min_a"]) >= 6.0, "3V8 inductor Isat target below 6 A")
    require(float(b38["inductor_irms_min_a"]) >= 4.5, "3V8 inductor Irms target below 4.5 A")
    require(b38["inductor_mpn"] == "XAL7030-472MEC", "3V8 exact inductor MPN drift")
    require(float(b38["inductor_isat_a"]) >= float(b38["inductor_isat_min_a"]), "3V8 selected inductor Isat below target")
    require(float(b38["inductor_irms_20c_rise_a"]) >= float(b38["inductor_irms_min_a"]), "3V8 selected inductor Irms below target")
    ripple_38 = calculated_vout * (float(inp["working_max_v"]) - calculated_vout) / (
        float(inp["working_max_v"]) * float(b38["inductor_h"]) * float(b38["switching_frequency_hz"])
    )
    peak_38 = float(b38["current_a"]) + ripple_38 / 2.0
    rms_38 = math.sqrt(float(b38["current_a"]) ** 2 + ripple_38 ** 2 / 12.0)
    require(float(b38["inductor_isat_a"]) >= peak_38, "3V8 selected inductor saturates below calculated peak")
    require(float(b38["inductor_irms_20c_rise_a"]) >= rms_38, "3V8 selected inductor Irms below calculated RMS")
    dcr_loss_38 = float(b38["current_a"]) ** 2 * float(b38["inductor_dcr_max_mohm"]) / 1000.0
    record("buck_3v8_passives", frequency_hz=b38["switching_frequency_hz"], rt_ohm=b38["rt_ohm"],
           inductor_h=b38["inductor_h"], inductor_mpn=b38["inductor_mpn"], ripple_a=ripple_38,
           peak_a=peak_38, rms_a=rms_38, max_dcr_loss_w=dcr_loss_38)

    # The two BG95 supply domains can reach the documented peaks. For capture sizing,
    # verify the arithmetic sum remains below the dedicated 4-A converter rating.
    modem_peak_sum = float(modem["vbat_bb_peak_a"]) + float(modem["vbat_rf_peak_a"])
    require(modem_peak_sum <= float(b38["current_a"]), "BG95 documented peak-domain sum exceeds 3V8 converter rating")
    require(modem["star_split_required"], "BG95 VBAT_BB/VBAT_RF star split must remain required")
    require(float(modem["local_bulk_bb_min_f"]) >= 100e-6, "BG95 BB bulk below 100 uF capture baseline")
    require(float(modem["local_bulk_rf_min_f"]) >= 100e-6, "BG95 RF bulk below 100 uF capture baseline")
    record("bg95_peak_current_headroom", peak_sum_a=modem_peak_sum, converter_rating_a=b38["current_a"], headroom_a=float(b38["current_a"]) - modem_peak_sum)

    close(float(b33["fixed_output_v"]), 3.3, 1e-9, "3V3 fixed output")
    close(float(b33["switching_frequency_hz"]), 400000.0, 0.1, "3V3 switching frequency")
    close(float(b33["rt_ohm"]), 86600.0, 0.1, "3V3 RT")
    close(float(b33["inductor_h"]), 4.7e-6, 1e-12, "3V3 inductance")
    require(float(b33["cout_effective_min_f"]) >= 54e-6, "3V3 effective COUT below 54 uF")
    require(b33["inductor_mpn"] == b38["inductor_mpn"], "3V3/3V8 inductor MPN mismatch")
    ripple_33 = float(b33["fixed_output_v"]) * (float(inp["working_max_v"]) - float(b33["fixed_output_v"])) / (
        float(inp["working_max_v"]) * float(b33["inductor_h"]) * float(b33["switching_frequency_hz"])
    )
    peak_33 = float(b33["current_a"]) + ripple_33 / 2.0
    rms_33 = math.sqrt(float(b33["current_a"]) ** 2 + ripple_33 ** 2 / 12.0)
    require(float(b33["inductor_isat_a"]) >= peak_33, "3V3 selected inductor saturates below calculated peak")
    require(float(b33["inductor_irms_20c_rise_a"]) >= rms_33, "3V3 selected inductor Irms below calculated RMS")
    dcr_loss_33 = float(b33["current_a"]) ** 2 * float(b33["inductor_dcr_max_mohm"]) / 1000.0
    record("buck_3v3_fixed_mode", output_v=b33["fixed_output_v"], mpn=b33["mpn"],
           inductor_mpn=b33["inductor_mpn"], ripple_a=ripple_33, peak_a=peak_33,
           rms_a=rms_33, max_dcr_loss_w=dcr_loss_33)

    close(float(ldo["input_v"]), 3.3, 1e-9, "mic LDO input")
    close(float(ldo["output_v"]), 1.8, 1e-9, "mic LDO output")
    require(float(ldo["current_a"]) >= 0.3, "mic LDO rating below 300 mA")
    require(float(ldo["cin_effective_min_f"]) >= 1e-6, "mic LDO effective CIN below 1 uF")
    require(float(ldo["cout_effective_min_f"]) >= 1e-6, "mic LDO effective COUT below 1 uF")
    record("mic_ldo", output_v=ldo["output_v"], current_a=ldo["current_a"])

    # INA226 independent range and calibration calculations.
    ishunt = float(mon["expected_current_max_a"])
    rshunt = float(mon["shunt_ohm"])
    vshunt = ishunt * rshunt
    pshunt = ishunt * ishunt * rshunt
    min_current_lsb = ishunt / 32768.0
    max_representable_current = float(mon["current_lsb_a"]) * 32767.0
    cal = 0.00512 / (float(mon["current_lsb_a"]) * rshunt)
    power_lsb = 25.0 * float(mon["current_lsb_a"])
    require(vshunt < float(mon["shunt_input_abs_max_v"]), "INA226 5-A shunt voltage exceeds input range")
    require(pshunt <= 0.25, "10-mOhm shunt dissipation unexpectedly exceeds 0.25 W at 5 A")
    require(float(mon["shunt_power_rating_min_w"]) >= 4.0 * pshunt, "shunt rating has less than 4x nominal power margin")
    require(mon["shunt_mpn"] == "WSK2512R0100FEA", "exact four-terminal shunt MPN drift")
    require(float(mon["shunt_tolerance_pct"]) <= 1.0, "shunt tolerance exceeds 1 percent")
    require(float(mon["shunt_tcr_max_ppm_per_c"]) <= 50.0, "shunt TCR exceeds 50 ppm/C target")
    require(float(mon["current_lsb_a"]) >= min_current_lsb, "chosen INA226 Current_LSB is too small for 5-A range")
    require(max_representable_current >= ishunt, "chosen INA226 Current_LSB cannot represent 5 A")
    close(cal, float(mon["calibration_register"]), 1e-9, "INA226 CAL")
    close(power_lsb, float(mon["power_lsb_w"]), 1e-12, "INA226 Power_LSB")
    record(
        "ina226_calibration",
        vshunt_at_5a_v=vshunt,
        pshunt_at_5a_w=pshunt,
        minimum_current_lsb_a=min_current_lsb,
        selected_current_lsb_a=mon["current_lsb_a"],
        max_representable_current_a=max_representable_current,
        calibration=cal,
        power_lsb_w=power_lsb,
    )

    required_open = {
        "battery_bms_voltage_limits",
        "mppt_transient_envelope",
        "tvs_final_value_and_pulse_coordination",
        "pcb_fuse_final_value_and_fault_energy_coordination",
        "inductor_in_application_thermal_and_emi_validation",
        "mlcc_and_bulk_exact_mpn_with_dc_bias_and_cold_esr",
        "shunt_kelvin_layout_and_reference_calibration",
        "reverse_mosfet_soa_and_gate_transient_review",
        "plus70c_thermal_test",
        "minus40c_cold_start_test",
        "load_step_and_bg95_pulse_test",
        "standby_s0_measurement",
        "emc_emi_evidence",
        "review_a",
        "review_b",
    }
    open_items = set(baseline.get("release_open_items", []))
    require(required_open.issubset(open_items), f"release blocker set weakened: missing {sorted(required_open - open_items)}")
    record("manufacturing_release_blockers_preserved", count=len(open_items))

    result = {
        "configuration": baseline["configuration"],
        "audit": "PCB-PWR Rev.A independent calculation/freeze audit",
        "capture_gate": "PASS_NATIVE_CAPTURE_ALLOWED",
        "manufacturing_release": "BLOCKED_NOT_FOR_MANUFACTURE",
        "checks": checks,
        "derived": {
            "buck_3v8_nominal_v": calculated_vout,
            "bg95_peak_domain_sum_a": modem_peak_sum,
            "ina226_vshunt_at_5a_v": vshunt,
            "ina226_pshunt_at_5a_w": pshunt,
            "ina226_min_current_lsb_a": min_current_lsb,
            "ina226_calibration": cal,
            "ina226_power_lsb_w": power_lsb,
            "buck_3v8_inductor_ripple_a": ripple_38,
            "buck_3v8_inductor_peak_a": peak_38,
            "buck_3v8_inductor_rms_a": rms_38,
            "buck_3v8_inductor_max_dcr_loss_w": dcr_loss_38,
            "buck_3v3_inductor_ripple_a": ripple_33,
            "buck_3v3_inductor_peak_a": peak_33,
            "buck_3v3_inductor_rms_a": rms_33,
            "buck_3v3_inductor_max_dcr_loss_w": dcr_loss_33,
        },
        "release_open_items": sorted(open_items),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("PCB-PWR independent calculation/freeze audit PASS")
    print(f"3V8 nominal={calculated_vout:.6f} V; BG95 peak sum={modem_peak_sum:.3f} A")
    print(f"INA226: Vshunt={vshunt:.6f} V Pshunt={pshunt:.6f} W CAL={cal:.1f}")
    print(f"Manufacturing release remains BLOCKED with {len(open_items)} open controls")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

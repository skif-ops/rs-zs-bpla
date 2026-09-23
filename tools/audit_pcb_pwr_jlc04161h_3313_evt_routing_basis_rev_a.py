#!/usr/bin/env python3
"""Audit the bounded numeric EVT routing basis for PCB-PWR.

The PASS state authorizes only an engineering routing candidate. The external
reply wait gate is closed by the project-owner-authorized public/process
baseline; checkout DFM, fault energy, +70 C physical evidence, DRC, Review B
and manufacturing release remain open.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


from pcb_pwr_hot_loop_006_board import historical_basis_board

ROOT = Path(__file__).resolve().parents[1]
BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"
RECORD = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.md"
RULES = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
CAPTURE = ROOT / "hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv"
ROUTING = ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
STACKUP = ROOT / "hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json"
RESPONSE = ROOT / "hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"

STATE = (
    "PASS_EVT_ENGINEERING_STACKUP_AND_NUMERIC_ROUTING_INPUT_"
    "JOB_DFM_PENDING"
)
ROW_STATUS = (
    "EVT_ENGINEERING_CANDIDATE_ONLY_FINAL_FABRICATOR_"
    "FAULT_THERMAL_REVIEW_PENDING"
)

FIELDS = [
    "Net_Name", "Numeric_Class", "Width_mm", "Clearance_mm",
    "Via_Diameter_mm", "Via_Drill_mm", "Min_Parallel_Vias_If_Transition",
    "Max_One_Way_Length_mm", "Layer_Policy", "Via_Policy", "Status",
]

EXPECTED_NETS = {
    "PWR_INPUT_5A": {"VBAT_RAW", "VBAT_FUSED", "VBAT_PROTECTED", "VBAT_SYS"},
    "PWR_RETURN_5A": {"GND_PWR"},
    "PWR_RAIL_4A": {"3V3_DIGITAL", "3V8_MODEM", "GND_DIGITAL", "GND_MODEM"},
    "PWR_RAIL_0P3A": {"1V8_MIC", "GND_MIC"},
    "PWR_SWITCH_4A": {"SW_3V3", "SW_3V8"},
    "PWR_LOCAL": {
        "BOOT_3V3", "BOOT_3V8", "LM74700_VCAP", "MODE_3V3", "MODE_3V8",
        "REV_GATE", "RT_3V3", "RT_3V8",
    },
    "PWR_SENSE": {"FB_3V8", "SHUNT_LOAD_SENSE", "SHUNT_SOURCE_SENSE"},
    "CONTROL": {"EN_AUX", "EN_MODEM", "FAULT", "I2C2_SCL", "I2C2_SDA", "PG_3V8", "PWR_GOOD"},
}

EXPECTED_RULES = {
    "PWR_INPUT_5A": (5.0, 4.0, 0.3, 12, 0.05, 67.870035,
                     "OUTER_COPPER_PREFERRED_SAME_LAYER_CONTINUOUS",
                     "AVOID_TRANSITION_OTHERWISE_MIN_12_PARALLEL_PROVISIONAL"),
    "PWR_RETURN_5A": (5.0, 4.0, 0.3, 12, 0.05, 67.870035,
                      "CONTINUOUS_GND_PWR_PLANE_PLUS_OUTER_COPPER",
                      "AVOID_TRANSITION_OTHERWISE_MIN_12_PARALLEL_PROVISIONAL"),
    "PWR_RAIL_4A": (4.0, 3.0, 0.3, 10, 0.05, 63.628158,
                    "OUTER_COPPER_AND_DEDICATED_RETURN_ZONE",
                    "AVOID_TRANSITION_OTHERWISE_MIN_10_PARALLEL_PROVISIONAL"),
    "PWR_RAIL_0P3A": (0.3, 0.5, 0.25, 2, 0.02, 56.558362,
                      "OUTER_COPPER_AND_DEDICATED_RETURN_ZONE",
                      "AVOID_TRANSITION_OTHERWISE_MIN_2_PARALLEL_PROVISIONAL"),
    "PWR_SWITCH_4A": (4.0, 2.1, 0.4, 0, None, None,
                      "F_CU_LOCAL_ONLY_MINIMUM_AREA",
                      "ZERO_VIA_TARGET_EXCEPTION_REQUIRES_REVIEW_B"),
    "PWR_LOCAL": (None, 0.5, 0.25, 1, None, None,
                  "F_CU_LOCAL_PREFERRED",
                  "MINIMIZE_TRANSITIONS_BOOTSTRAP_ZERO_VIA_TARGET"),
    "PWR_SENSE": (None, 0.25, 0.3, 0, None, None,
                  "F_CU_PAIRED_QUIET_CORRIDOR",
                  "ZERO_VIA_TARGET_NO_SHARED_LOAD_COPPER"),
    "CONTROL": (None, 0.25, 0.2, 1, None, None,
                "SIGNAL_LAYER_OVER_CONTROLLED_RETURN",
                "MINIMIZE_TRANSITIONS_ADD_LOCAL_RETURN_VIA"),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def close(actual: float, expected: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance)


def required_width_mm(current_a: float, copper_um: float, delta_t_c: float) -> float:
    area_mil2 = (current_a / (0.048 * delta_t_c ** 0.44)) ** (1.0 / 0.725)
    copper_thickness_mil = copper_um / 25.4
    return area_mil2 / copper_thickness_mil * 0.0254


def resistance_per_mm_ohm(width_mm: float, copper_um: float, rho_ohm_m: float) -> float:
    return rho_ohm_m * 0.001 / (width_mm * 0.001 * copper_um * 1e-6)


def audit() -> dict[str, Any]:
    basis = json.loads(BASIS.read_text(encoding="utf-8"))
    require(basis["schema"] == "dioneya-pcb-pwr-evt-routing-design-basis-v1", "schema drift")
    require(basis["configuration"] == "EVT-PRE-20 Rev.A", "configuration drift")
    require(basis["board"] == "PCB-PWR", "board drift")
    require(basis["status"] == STATE, "basis status drift")
    require(basis["retrieval_utc_date"] == "2026-09-21", "retrieval date drift")
    require(basis["fabricator_public_reference"] == "JLCPCB", "public reference drift")
    require(basis["official_sources"] == [
        "https://jlcpcb.com/impedance",
        "https://jlcpcb.com/capabilities/pcb-capabilities",
    ], "official source drift")

    binding = basis["source_binding"]
    require(binding["native_board"] == str(BOARD.relative_to(ROOT)),
            "native board path drift")
    expected_bindings = {
        "capture_nets": CAPTURE,
        "routing_authority": ROUTING,
        "stackup_request": STACKUP,
        "stackup_response": RESPONSE,
        "rule_manifest": RULES,
    }
    for key, path in expected_bindings.items():
        require(binding[key] == str(path.relative_to(ROOT)), f"{key} path drift")
        require(binding[f"{key}_sha256"] == sha256(path), f"{key} SHA-256 drift")

    board = Board.from_file(str(historical_basis_board(BOARD)), encoding="utf-8")
    require(binding["native_board_semantic_sha256"] == semantic_board_sha256(board),
            "native board semantic SHA-256 drift")
    require(len(board.traceItems) in {0, 2, 3, 4, 8, 14} and len(board.zones) == 0,
            "numeric routing basis does not cover copper beyond accepted buck power-stage ECO-002")

    public = basis["public_four_layer_reference"]
    require(public["stackup_id"] == "JLC04161H-3313", "public stackup ID drift")
    require(public["nominal_finished_thickness_mm"] == 1.6, "nominal thickness drift")
    require(public["published_finished_thickness_tolerance_percent"] == 10.0,
            "published thickness tolerance drift")
    require(public["displayed_outer_copper_oz"] == 1.0 and
            public["displayed_inner_copper_oz"] == 0.5,
            "displayed public copper reference drift")
    require(public["published_outer_copper_options_oz"] == [1.0, 2.0] and
            public["published_inner_copper_options_oz"] == [0.5, 1.0, 2.0],
            "published copper option drift")
    require(public["project_job_target_outer_copper_oz"] == 2.0 and
            public["project_job_target_inner_copper_oz"] == 1.0 and
            public["job_specific_stackup_selected"] is True and
            public["selection_scope"] == "EVT_ENGINEERING_AND_ORDERING_PROFILE" and
            public["selection_basis"] ==
            "PROJECT_OWNER_AUTHORIZED_STANDARD_PROCESS_AND_CALCULATED_VALUES" and
            public["routing_design_copper_lower_bound_um"] == 35.0 and
            public["ordering_profile_requires_outer_copper_oz"] == 2.0 and
            public["ordering_profile_requires_inner_copper_oz"] == 1.0,
            "EVT stackup/order profile boundary drift")
    require(public["layers"] == [
        {"name": "L1", "kind": "copper", "thickness_mm": 0.0350},
        {"name": "PP1", "kind": "prepreg", "material": "3313", "thickness_mm": 0.0994},
        {"name": "L2", "kind": "copper", "thickness_mm": 0.0152},
        {"name": "CORE", "kind": "core", "material": "H/H without copper", "thickness_mm": 1.2650},
        {"name": "L3", "kind": "copper", "thickness_mm": 0.0152},
        {"name": "PP2", "kind": "prepreg", "material": "3313", "thickness_mm": 0.0994},
        {"name": "L4", "kind": "copper", "thickness_mm": 0.0350},
    ], "public four-layer construction drift")

    stackup = json.loads(STACKUP.read_text(encoding="utf-8"))
    target = stackup["board_request_basis"]["copper_weight_targets"]
    require(target == {"outer_oz": 2.0, "inner_oz": 1.0,
                       "status": "EVT_FROZEN"},
            "stackup request target copper drift")

    assumptions = basis["calculation_assumptions"]
    require(assumptions["conductor_method"] ==
            "LEGACY_IPC_2221_EXTERNAL_CONDUCTOR_EMPIRICAL_SCREEN_ENGINEERING_ONLY",
            "conductor screen identity drift")
    require(assumptions["conductor_formula"] ==
            "I_A=0.048*DELTA_T_C^0.44*AREA_MIL2^0.725", "conductor formula drift")
    require(assumptions["screen_finished_copper_um"] == 35.0 and
            assumptions["screen_temperature_rise_c"] == 10.0 and
            assumptions["ambient_requirement_c"] == 70.0,
            "conductor screen assumptions drift")
    expected_rho70 = 1.724e-8 * (1.0 + 0.00393 * 50.0)
    require(close(assumptions["copper_resistivity_70c_ohm_m"], expected_rho70, 1e-15),
            "70 C copper resistivity calculation drift")
    via_area_m2 = math.pi * 0.3e-3 * 20e-6
    via_resistance_mohm = expected_rho70 * 1.6e-3 / via_area_m2 * 1000.0
    require(close(assumptions["via_screen_resistance_70c_mohm_each"],
                  via_resistance_mohm, 1e-5), "via resistance screen drift")
    require(assumptions["via_plating_is_job_specific_and_unaccepted"] is True,
            "job-specific via-plating interlock removed")

    screens = {item["current_a"]: item["minimum_width_mm"]
               for item in basis["current_width_screens"]}
    for current, expected in ((5.0, 2.765521), (4.0, 2.032863),
                              (3.3, 1.559093), (0.3, 0.057078)):
        calculated = required_width_mm(current, 35.0, 10.0)
        require(close(screens[current], calculated, 1e-6),
                f"{current} A width screen drift")
        require(close(screens[current], expected, 1e-6),
                f"{current} A committed width differs")

    classes = {item["name"]: item for item in basis["numeric_classes"]}
    require(set(classes) == set(EXPECTED_RULES) and len(classes) == 8,
            "numeric class inventory drift")
    for name, expected in EXPECTED_RULES.items():
        current, width, clearance, vias, drop, length, layer, via_policy = expected
        rule = classes[name]
        require(rule["current_screen_a"] == current and
                rule["selected_width_mm"] == width and
                rule["clearance_mm"] == clearance and
                rule["via_diameter_mm"] == 0.6 and
                rule["via_drill_mm"] == 0.3 and
                rule["minimum_parallel_vias_if_transition"] == vias and
                rule["dc_drop_budget_v"] == drop and
                rule["max_one_way_length_at_drop_budget_mm"] == length and
                rule["layer_policy"] == layer and rule["via_policy"] == via_policy,
                f"numeric rule drift: {name}")
        if current is not None:
            require(width + 1e-9 >= required_width_mm(current, 35.0, 10.0),
                    f"selected width fails conservative screen: {name}")
        if drop is not None:
            expected_length = drop / current / resistance_per_mm_ohm(
                width, 35.0, expected_rho70
            )
            require(close(length, expected_length, 1e-6), f"DC length budget drift: {name}")

    assignments = {name: set(nets) for name, nets in basis["netclass_assignments"].items()}
    require(assignments == EXPECTED_NETS, "numeric net-class assignment drift")
    expected_names = set().union(*EXPECTED_NETS.values())
    require(len(expected_names) == 31, "independent expected net count drift")
    _, capture_rows = read_csv(CAPTURE)
    capture_names = {row["Net"] for row in capture_rows}
    require(capture_names == expected_names, "numeric classes differ from capture net authority")

    fields, rows = read_csv(RULES)
    require(fields == FIELDS and len(rows) == 31, "rule manifest shape drift")
    require([row["Net_Name"] for row in rows] == sorted(expected_names),
            "rule manifest must be unique and sorted")
    class_by_net = {net: name for name, nets in EXPECTED_NETS.items() for net in nets}
    for row in rows:
        name = class_by_net[row["Net_Name"]]
        rule = classes[name]
        require(row["Numeric_Class"] == name, f"class mismatch: {row['Net_Name']}")
        require(float(row["Width_mm"]) == rule["selected_width_mm"] and
                float(row["Clearance_mm"]) == rule["clearance_mm"] and
                float(row["Via_Diameter_mm"]) == 0.6 and
                float(row["Via_Drill_mm"]) == 0.3 and
                int(row["Min_Parallel_Vias_If_Transition"]) ==
                rule["minimum_parallel_vias_if_transition"],
                f"numeric manifest mismatch: {row['Net_Name']}")
        expected_length = rule["max_one_way_length_at_drop_budget_mm"]
        require((not row["Max_One_Way_Length_mm"] if expected_length is None else
                 float(row["Max_One_Way_Length_mm"]) == expected_length),
                f"length budget mismatch: {row['Net_Name']}")
        require(row["Layer_Policy"] == rule["layer_policy"] and
                row["Via_Policy"] == rule["via_policy"] and
                row["Status"] == ROW_STATUS,
                f"policy/status mismatch: {row['Net_Name']}")

    _, response_rows = read_csv(RESPONSE)
    require(len(response_rows) == 24 and
            {row["Fabricator_Slot"] for row in response_rows} == {"FAB-A", "FAB-B"},
            "two-fabricator response shape drift")
    require(all(row["Disposition"] == "CLOSED_EVT_ENGINEERING_BASELINE" and
                all(row[field].strip() for field in (
                    "Response_Value", "Response_Reference", "Responder", "Response_Date"
                )) and row["Blocking"] == "NO" and
                "EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.json" in
                row["Response_Reference"] for row in response_rows),
            "EVT engineering-baseline response closure drift")

    boundary = basis["acceptance_boundary"]
    require(boundary["numeric_input_for_evt_engineering_routing_candidate"] is True and
            boundary["conservative_35um_screen_pass"] is True,
            "EVT numeric engineering input was not released")
    require(boundary["public_reference_selected_as_evt_ordering_profile"] is True and
            boundary["target_2oz_1oz_selected_as_evt_ordering_profile"] is True and
            boundary["two_fabricator_responses_required_before_routing"] is False and
            boundary["job_specific_dfm_required_before_fabrication"] is True,
            "EVT ordering profile or job-DFM boundary drift")
    for field in (
        "two_fabricator_response_sets_accepted",
        "fault_energy_calculation_accepted",
        "plus70c_physical_thermal_evidence_accepted",
        "via_current_capacity_accepted",
        "routing_complete",
        "review_b_complete",
        "manufacturing_release",
    ):
        require(boundary[field] is False, f"{field} was incorrectly promoted")
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    trace = status.get("evt_routing_basis", {})
    require(trace.get("record") == str(RECORD.relative_to(ROOT)) and
            trace.get("machine_contract") == str(BASIS.relative_to(ROOT)) and
            trace.get("rule_manifest") == str(RULES.relative_to(ROOT)) and
            trace.get("generator") ==
            "tools/generate_pcb_pwr_evt_route_rules_rev_a.py" and
            trace.get("independent_audit") ==
            "tools/audit_pcb_pwr_jlc04161h_3313_evt_routing_basis_rev_a.py",
            "PCB-PWR status routing-basis traceability drift")
    control = trace.get("control", {})
    require(control == {
        "state": STATE,
        "public_dielectric_reference": "JLC04161H-3313",
        "screen_finished_copper_um": 35.0,
        "screen_temperature_rise_c": 10.0,
        "job_target_outer_copper_oz": 2.0,
        "job_target_inner_copper_oz": 1.0,
        "net_count": 31,
        "numeric_class_count": 8,
        "rule_manifest_sha256": sha256(RULES),
        "engineering_routing_candidate_authorized": True,
        "evt_ordering_profile_selected": True,
        "final_stackup_accepted": False,
        "final_numeric_power_geometry_authorized": False,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }, "PCB-PWR status routing-basis control drift")

    record = RECORD.read_text(encoding="utf-8")
    for token in (
        "2.765521 mm", "4.0 mm", "2.032863 mm", "3.0 mm",
        "67.870035 mm", "24/24", "Manufacturing release: `false`",
    ):
        require(token in record, f"routing-basis record token missing: {token}")

    return {
        "schema": "dioneya-pcb-pwr-evt-routing-design-basis-audit-v1",
        "configuration": basis["configuration"],
        "board": basis["board"],
        "status": STATE,
        "public_stackup_id": public["stackup_id"],
        "screen_finished_copper_um": assumptions["screen_finished_copper_um"],
        "net_count": len(rows),
        "numeric_class_count": len(classes),
        "input_5a_width_mm": classes["PWR_INPUT_5A"]["selected_width_mm"],
        "rail_4a_width_mm": classes["PWR_RAIL_4A"]["selected_width_mm"],
        "accepted_fabricator_response_rows": 0,
        "engineering_baseline_closed_rows": len(response_rows),
        "external_fabricator_reply_required": False,
        "engineering_routing_candidate_authorized": True,
        "evt_ordering_profile_selected": True,
        "final_stackup_accepted": False,
        "routing_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        "PCB-PWR conservative EVT routing basis PASS: "
        "31 nets / 8 classes; 5 A=4.0 mm; 4 A=3.0 mm; "
        "external reply wait gate closed; checkout DFM and physical thermal acceptance remain open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

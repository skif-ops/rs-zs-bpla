#!/usr/bin/env python3
"""Independently audit PCB-PWR Rev.A pre-route constraint coverage.

The audit proves complete constraint coverage and simultaneously proves that
the committed placement candidate is still unrouted.  A PASS is not DRC, CAM,
Review-B or manufacturing-release evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from kiutils.board import Board

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
DEFAULT_AUTHORITY = ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv"
DEFAULT_STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
CAPTURE_NETS = ROOT / "hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv"
BASELINE = ROOT / "hardware/POWER_DESIGN_BASELINE_REV_A.json"
LAYERS = ROOT / "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv"
OPEN_DIMENSIONS = ROOT / "mechanics/common/OPEN_DIMENSIONS.csv"
REVIEW_B = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_CHECKLIST_REV_A.md"

STATE = "PASS_PRE_ROUTE_CONSTRAINT_COVERAGE_ROUTING_OPEN"
ROW_STATUS = "PRE_ROUTE_CONSTRAINT_CONTROLLED_ROUTING_NOT_COMPLETE"
NUMERIC_GEOMETRY = "OPEN_FINAL_STACKUP_COPPER_THERMAL_CURRENT_DENSITY"

FIELDS = [
    "Net_Name",
    "Route_Class",
    "Reference_Domain",
    "Topology",
    "Current_Basis",
    "Geometry_Rule",
    "Layer_Rule",
    "Via_Rule",
    "Separation_Rule",
    "Priority",
    "Source_Authority",
    "Status",
]

# Deliberately duplicated instead of imported from the generator.
EXPECTED_CLASS_NETS = {
    "POWER_INPUT_HIGH_CURRENT": {
        "VBAT_RAW", "VBAT_FUSED", "VBAT_PROTECTED", "VBAT_SYS",
    },
    "POWER_OUTPUT_HIGH_CURRENT": {"3V8_MODEM"},
    "POWER_RAIL": {"3V3_DIGITAL", "1V8_MIC"},
    "POWER_RETURN_PLANE": {"GND_PWR"},
    "SEPARATE_HARNESS_RETURN": {"GND_MODEM", "GND_DIGITAL", "GND_MIC"},
    "SWITCH_NODE": {"SW_3V8", "SW_3V3"},
    "BOOTSTRAP_LOOP": {"BOOT_3V8", "BOOT_3V3"},
    "KELVIN_SENSE": {"SHUNT_SOURCE_SENSE", "SHUNT_LOAD_SENSE"},
    "FEEDBACK_SENSE": {"FB_3V8"},
    "ANALOG_TIMING": {"LM74700_VCAP", "RT_3V8", "RT_3V3"},
    "GATE_DRIVE": {"REV_GATE"},
    "MODE_CONTROL": {"MODE_3V8", "MODE_3V3"},
    "LOW_SPEED_CONTROL": {"EN_MODEM", "EN_AUX"},
    "OPEN_DRAIN_STATUS": {"PG_3V8", "PWR_GOOD", "FAULT"},
    "I2C_OPEN_DRAIN": {"I2C2_SCL", "I2C2_SDA"},
}

TOPOLOGY = {
    "POWER_INPUT_HIGH_CURRENT": "SERIES_INPUT_PROTECTION_AND_SHUNT_CHAIN",
    "POWER_OUTPUT_HIGH_CURRENT": "BUCK_OUTPUT_TO_HARNESS_STAR_LOAD",
    "POWER_RAIL": "REGULATED_OUTPUT_TO_HARNESS_AND_LOCAL_LOADS",
    "POWER_RETURN_PLANE": "CONTINUOUS_PRIMARY_RETURN_AND_THERMAL_PLANE",
    "SEPARATE_HARNESS_RETURN": "HARNESS_RETURN_TO_ONE_EXPLICIT_NET_TIE",
    "SWITCH_NODE": "LOCAL_BUCK_SW_TO_INDUCTOR_AND_BOOTSTRAP_ONLY",
    "BOOTSTRAP_LOOP": "LOCAL_CONTROLLER_CAPACITOR_SWITCH_NODE_LOOP",
    "KELVIN_SENSE": "TRUE_KELVIN_SHUNT_TERMINAL_TO_INA226_WITH_HI_Z_TP_BRANCH",
    "FEEDBACK_SENSE": "QUIET_POST_INDUCTOR_OUTPUT_SENSE_TO_FEEDBACK_DIVIDER",
    "ANALOG_TIMING": "LOCAL_POINT_TO_POINT_ANALOG_NETWORK",
    "GATE_DRIVE": "LOCAL_CONTROLLER_TO_REVERSE_MOSFET_GATE",
    "MODE_CONTROL": "LOCAL_STATIC_MODE_STRAP_NETWORK",
    "LOW_SPEED_CONTROL": "HARNESS_CONTROL_TO_LOCAL_ENABLE_RECEIVER",
    "OPEN_DRAIN_STATUS": "OPEN_DRAIN_STATUS_TO_LOCAL_TP_OR_MAIN_HARNESS",
    "I2C_OPEN_DRAIN": "OPEN_DRAIN_POINT_TO_POINT_HARNESS_BUS_MAIN_PULLUPS_ONLY",
}

LAYER_RULE = {
    "POWER_INPUT_HIGH_CURRENT": "OUTER_AND_PLANE_COPPER_AFTER_CURRENT_DENSITY_AND_STACKUP_ACCEPTANCE",
    "POWER_OUTPUT_HIGH_CURRENT": "OUTER_AND_PLANE_COPPER_AFTER_CURRENT_DENSITY_AND_STACKUP_ACCEPTANCE",
    "POWER_RAIL": "OUTER_AND_PLANE_COPPER_AFTER_CURRENT_DENSITY_AND_STACKUP_ACCEPTANCE",
    "POWER_RETURN_PLANE": "CONTINUOUS_GND_PWR_REFERENCE_AND_THERMAL_PLANES_REVIEW_B",
    "SEPARATE_HARNESS_RETURN": "CONTROLLED_RETURN_COPPER_TO_ASSIGNED_NET_TIE_NO_CROSS_JOIN",
    "SWITCH_NODE": "F_CU_LOCAL_ONLY_NO_COPPER_BELOW_UNLESS_DATASHEET_THERMAL_REVIEWED",
    "BOOTSTRAP_LOOP": "F_CU_LOCAL_SAME_LAYER_CONTROLLER_AND_CAPACITOR",
    "KELVIN_SENSE": "PAIRED_SAME_LAYER_QUIET_CORRIDOR_TO_INA226",
    "FEEDBACK_SENSE": "F_CU_QUIET_CORRIDOR_FROM_OUTPUT_CAP_TO_CONTROLLER",
    "ANALOG_TIMING": "F_CU_LOCAL_TO_CONTROLLER",
    "GATE_DRIVE": "F_CU_LOCAL_TO_CONTROLLER_AND_MOSFET",
    "MODE_CONTROL": "F_CU_LOCAL_TO_CONTROLLER",
    "LOW_SPEED_CONTROL": "SIGNAL_LAYER_OVER_CONTINUOUS_GND_PWR_REFERENCE",
    "OPEN_DRAIN_STATUS": "SIGNAL_LAYER_OVER_CONTINUOUS_GND_PWR_REFERENCE",
    "I2C_OPEN_DRAIN": "SIGNAL_LAYER_OVER_CONTINUOUS_GND_PWR_REFERENCE",
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def expected_class_by_net() -> dict[str, str]:
    result: dict[str, str] = {}
    for route_class, nets in EXPECTED_CLASS_NETS.items():
        for net in nets:
            require(net not in result, f"independent class expectation overlaps at {net}")
            result[net] = route_class
    require(len(result) == 31, f"independent class map has {len(result)} nets")
    return result


def expected_domain(net: str) -> str:
    return {
        "GND_PWR": "SELF_GND_PWR",
        "GND_MODEM": "SELF_TO_GND_PWR_ONLY_AT_NT1",
        "GND_DIGITAL": "SELF_TO_GND_PWR_ONLY_AT_NT2",
        "GND_MIC": "SELF_TO_GND_PWR_ONLY_AT_NT3",
        "3V8_MODEM": "GND_PWR_TO_GND_MODEM_AT_NT1",
        "3V3_DIGITAL": "GND_PWR_TO_GND_DIGITAL_AT_NT2",
        "1V8_MIC": "GND_PWR_TO_GND_MIC_AT_NT3",
        "EN_MODEM": "CROSS_GND_DIGITAL_GND_PWR_VIA_NT2",
        "EN_AUX": "CROSS_GND_DIGITAL_GND_PWR_VIA_NT2",
        "PWR_GOOD": "CROSS_GND_DIGITAL_GND_PWR_VIA_NT2",
        "FAULT": "CROSS_GND_DIGITAL_GND_PWR_VIA_NT2",
        "I2C2_SCL": "CROSS_GND_DIGITAL_GND_PWR_VIA_NT2",
        "I2C2_SDA": "CROSS_GND_DIGITAL_GND_PWR_VIA_NT2",
    }.get(net, "GND_PWR")


def expected_current(net: str, route_class: str) -> str:
    if route_class == "POWER_INPUT_HIGH_CURRENT":
        return "SYSTEM_EXPECTED_MAX_5A_FAULT_AND_TRANSIENT_ENVELOPE_OPEN"
    if net in {"3V8_MODEM", "GND_MODEM"}:
        return "LMR60440_4A_RATED_BG95_BB_PLUS_RF_PEAK_3P3A"
    if net in {"3V3_DIGITAL", "GND_DIGITAL"}:
        return "LMR60440_4A_RATED_ACTUAL_LOAD_ENVELOPE_OPEN"
    if net in {"1V8_MIC", "GND_MIC"}:
        return "TPS7A20_0P3A_RATED_ACTUAL_LOAD_ENVELOPE_OPEN"
    if net == "GND_PWR":
        return "SYSTEM_EXPECTED_MAX_5A_PLUS_FAULT_RETURN_ENVELOPE_OPEN"
    if net in {"SW_3V8", "BOOT_3V8"}:
        return "LMR60440_3V8_CHANNEL_4A_RATED_SWITCHING_LOOP"
    if net in {"SW_3V3", "BOOT_3V3"}:
        return "LMR60440_3V3_CHANNEL_4A_RATED_SWITCHING_LOOP"
    if route_class == "KELVIN_SENSE":
        return "MEASURES_SYSTEM_5A_BASIS_NO_LOAD_CURRENT_IN_SENSE_TRACE"
    return "SIGNAL_OR_BIAS_CURRENT_NOT_LOAD_CURRENT"


def expected_geometry(net: str, route_class: str) -> str:
    if route_class == "POWER_INPUT_HIGH_CURRENT":
        return "WIDTH_AND_COPPER_FROM_5A_DC_DROP_FAULT_ENERGY_PLUS70C_THERMAL_REVIEW"
    if net == "3V8_MODEM":
        return "WIDTH_AND_COPPER_FROM_4A_RATING_3P3A_PEAK_DC_DROP_AND_PLUS70C_THERMAL_REVIEW"
    if net == "3V3_DIGITAL":
        return "WIDTH_PENDING_LOAD_AND_THERMAL_REVIEW_QUIET_U4_FB_SENSE_FROM_OUTPUT_CAP_NOT_SW"
    if net == "1V8_MIC":
        return "WIDTH_FROM_0P3A_LOAD_DC_DROP_AND_LOW_NOISE_THERMAL_REVIEW"
    if route_class == "POWER_RETURN_PLANE":
        return "PLANE_GEOMETRY_CURRENT_DENSITY_VOID_AND_THERMAL_REVIEW_REQUIRED"
    if route_class == "SEPARATE_HARNESS_RETURN":
        return "COPPER_EQUIVALENT_TO_ASSOCIATED_RAIL_NO_NECKDOWN_JOIN_ONLY_AT_ASSIGNED_NET_TIE"
    if route_class == "SWITCH_NODE":
        return "SHORTEST_PRACTICAL_MINIMUM_AREA_NO_PLANE_NO_TEST_STUB"
    if route_class == "BOOTSTRAP_LOOP":
        return "SHORTEST_PRACTICAL_CONTROLLER_CAP_TO_SW_LOOP"
    if route_class == "KELVIN_SENSE":
        return "TRUE_KELVIN_FROM_SHUNT_SENSE_TERMINAL_NO_SHARED_LOAD_COPPER_HI_Z_TP_BRANCH_ONLY"
    if route_class == "FEEDBACK_SENSE":
        return "QUIET_POST_INDUCTOR_SENSE_FROM_OUTPUT_CAP_NO_SWITCH_NODE_PICKUP"
    if route_class == "I2C_OPEN_DRAIN":
        return "FABRICATOR_MINIMUMS_FINAL_HARNESS_CAPACITANCE_AND_PULLUP_REVIEW"
    return "FABRICATOR_MINIMUMS_AND_REVIEW_B"


def expected_via(route_class: str) -> str:
    if route_class in {
        "POWER_INPUT_HIGH_CURRENT", "POWER_OUTPUT_HIGH_CURRENT", "POWER_RAIL",
        "POWER_RETURN_PLANE", "SEPARATE_HARNESS_RETURN",
    }:
        return "VIA_ARRAY_COUNT_FROM_CURRENT_DENSITY_AND_THERMAL_REVIEW_NO_SINGLE_VIA_NECKDOWN"
    if route_class in {"SWITCH_NODE", "BOOTSTRAP_LOOP"}:
        return "ZERO_VIA_TARGET_ANY_EXCEPTION_REQUIRES_REVIEW_B"
    if route_class == "KELVIN_SENSE":
        return "ZERO_VIA_TARGET_NO_SHARED_LOAD_OR_PLANE_VIA"
    return "MINIMIZE_TRANSITIONS_ADD_LOCAL_RETURN_VIA_IF_LAYER_CHANGES"


def expected_separation(route_class: str) -> str:
    if route_class == "SWITCH_NODE":
        return "KEEP_AWAY_FROM_KELVIN_FEEDBACK_I2C_CONNECTORS_AND_BOARD_EDGE"
    if route_class == "BOOTSTRAP_LOOP":
        return "COLOCATE_WITH_ASSIGNED_SWITCH_LOOP_KEEP_AWAY_FROM_SENSE_AND_I2C"
    if route_class in {"KELVIN_SENSE", "FEEDBACK_SENSE"}:
        return "KEEP_AWAY_FROM_SWITCH_NODES_INDUCTORS_GATE_DRIVE_AND_HIGH_DI_DT_LOOPS"
    if route_class == "I2C_OPEN_DRAIN":
        return "KEEP_AWAY_FROM_SWITCH_NODES_AND_INDUCTORS_ROUTE_WITH_DIGITAL_RETURN_PATH"
    if route_class == "SEPARATE_HARNESS_RETURN":
        return "NO_CROSS_DOMAIN_JOIN_EXCEPT_ASSIGNED_NT1_NT2_OR_NT3"
    return "KEEP_CLEAR_OF_SWITCH_NODE_AND_UNRELATED_SENSITIVE_NETWORKS"


def expected_sources(route_class: str) -> list[str]:
    sources = [
        "hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv",
        "hardware/POWER_DESIGN_BASELINE_REV_A.json",
        "hardware/kicad/PCB_RULES.md",
    ]
    if route_class in {
        "POWER_INPUT_HIGH_CURRENT", "POWER_OUTPUT_HIGH_CURRENT", "POWER_RAIL",
        "POWER_RETURN_PLANE", "SEPARATE_HARNESS_RETURN", "SWITCH_NODE",
        "BOOTSTRAP_LOOP", "KELVIN_SENSE", "FEEDBACK_SENSE",
    }:
        sources.append("hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv")
    if route_class in {
        "SEPARATE_HARNESS_RETURN", "LOW_SPEED_CONTROL", "OPEN_DRAIN_STATUS",
        "I2C_OPEN_DRAIN",
    }:
        sources.append("hardware/PWR_MAIN_12PIN_I2C_FREEZE_REV_A.md")
    sources.append("hardware/PCB_PWR_REVIEW_A_PIN_NET_REV_A.md")
    return sources


def validate_row(row: dict[str, str], route_class: str) -> None:
    net = row["Net_Name"]
    require(all(value.strip() for value in row.values()), f"{net}: blank authority field")
    require(row["Route_Class"] == route_class, f"{net}: route-class drift")
    require(row["Reference_Domain"] == expected_domain(net), f"{net}: reference-domain drift")
    require(row["Topology"] == TOPOLOGY[route_class], f"{net}: topology drift")
    require(row["Current_Basis"] == expected_current(net, route_class), f"{net}: current basis drift")
    require(row["Geometry_Rule"] == expected_geometry(net, route_class), f"{net}: geometry rule drift")
    require(row["Layer_Rule"] == LAYER_RULE[route_class], f"{net}: layer rule drift")
    require(row["Via_Rule"] == expected_via(route_class), f"{net}: via rule drift")
    require(row["Separation_Rule"] == expected_separation(route_class), f"{net}: separation rule drift")
    expected_priority = "P0" if route_class in {
        "POWER_INPUT_HIGH_CURRENT", "POWER_OUTPUT_HIGH_CURRENT", "POWER_RAIL",
        "POWER_RETURN_PLANE", "SEPARATE_HARNESS_RETURN", "SWITCH_NODE",
        "BOOTSTRAP_LOOP", "KELVIN_SENSE", "FEEDBACK_SENSE",
    } else "P1"
    require(row["Priority"] == expected_priority, f"{net}: priority drift")
    require(row["Status"] == ROW_STATUS, f"{net}: release-boundary status drift")
    sources = row["Source_Authority"].split(";")
    require(sources == expected_sources(route_class), f"{net}: source-authority binding drift")
    for source in sources:
        pure = PurePosixPath(source)
        require(not pure.is_absolute() and ".." not in pure.parts,
                f"{net}: source path escapes repository: {source}")
        require(ROOT.joinpath(*pure.parts).is_file(), f"{net}: source is missing: {source}")


def expected_status_control(board_digest: str, authority_digest: str,
                            class_counts: dict[str, int],
                            domain_counts: dict[str, int]) -> dict[str, Any]:
    return {
        "state": STATE,
        "board_sha256": board_digest,
        "authority_sha256": authority_digest,
        "net_count": 31,
        "class_counts": class_counts,
        "reference_domain_counts": domain_counts,
        "trace_items": 0,
        "copper_zones": 0,
        "dim_003": "OPEN_REQUIRED_BEFORE_ROUTING",
        "numeric_power_geometry": NUMERIC_GEOMETRY,
        "routing_complete": False,
        "manufacturing_release": False,
    }


def audit(board_path: Path, authority_path: Path, status_path: Path | None) -> dict[str, Any]:
    board_path = board_path.resolve()
    authority_path = authority_path.resolve()
    require(board_path.is_file(), f"native board is missing: {board_path}")
    require(authority_path.is_file(), f"routing authority is missing: {authority_path}")

    with authority_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == FIELDS, f"routing authority fields differ: {reader.fieldnames}")
        rows = list(reader)
    require(len(rows) == 31, f"expected 31 routing rows, got {len(rows)}")
    names = [row["Net_Name"] for row in rows]
    require(names == sorted(names) and len(names) == len(set(names)),
            "routing rows must be unique and sorted by net name")

    expected_by_net = expected_class_by_net()
    capture_names = {row["Net"] for row in read_csv(CAPTURE_NETS)}
    require(len(capture_names) == 31 and capture_names == set(expected_by_net),
            "independent class map differs from capture-net authority")

    board = Board.from_file(str(board_path), encoding="utf-8")
    board_nets = {
        str(net.name) for net in board.nets
        if int(net.number) != 0 and str(net.name)
    }
    require(len(board_nets) == 31 and board_nets == capture_names,
            "native board net set differs from the 31 reviewed capture nets")
    require(set(names) == board_nets, "routing authority does not cover the exact native net set")

    by_net = {row["Net_Name"]: row for row in rows}
    for net in names:
        validate_row(by_net[net], expected_by_net[net])

    class_counts = dict(sorted(Counter(row["Route_Class"] for row in rows).items()))
    expected_class_counts = dict(sorted(
        (name, len(nets)) for name, nets in EXPECTED_CLASS_NETS.items()
    ))
    require(class_counts == expected_class_counts, f"route-class inventory drift: {class_counts}")
    domain_counts = dict(sorted(Counter(row["Reference_Domain"] for row in rows).items()))

    copper_layers = [layer.name for layer in board.layers if layer.name.endswith(".Cu")]
    require(copper_layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
            f"PCB-PWR layer-count drift: {copper_layers}")
    trace_items = len(board.traceItems)
    copper_zones = len(board.zones)
    require(trace_items == 0 and copper_zones == 0,
            "pre-route authority must be revised when routing or copper zones appear")

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    require(baseline["input"]["actual_battery_bms_limits_frozen"] is False and
            baseline["input"]["transient_envelope_frozen"] is False,
            "input/fault envelope must remain explicitly open")
    require(baseline["current_monitor"]["expected_current_max_a"] == 5.0,
            "5 A system current basis drift")
    require(baseline["buck_3v8"]["current_a"] == 4.0 and
            round(baseline["modem"]["vbat_bb_peak_a"] +
                  baseline["modem"]["vbat_rf_peak_a"], 6) == 3.3,
            "3V8 converter/modem current basis drift")
    require(baseline["buck_3v3"]["current_a"] == 4.0 and
            baseline["mic_ldo"]["current_a"] == 0.3,
            "3V3/1V8 current basis drift")
    require(baseline["current_monitor"]["i2c_speed_hz_initial"] == 100000 and
            baseline["current_monitor"]["pullup_location"] == "PCB-MAIN" and
            baseline["current_monitor"]["pwr_side_pullup_default"] == "DNP",
            "I2C speed or pull-up authority drift")
    require(baseline["ground_return_policy"] == {
        "GND_MODEM": "explicit_net_tie_to_GND_PWR",
        "GND_DIGITAL": "explicit_net_tie_to_GND_PWR",
        "GND_MIC": "explicit_net_tie_to_GND_PWR",
        "join_region": "controlled_low_impedance_source_region",
        "ambiguous_NET_TIE_OR_PLANE_policy": "prohibited",
    }, "ground-return authority drift")

    layer_rows = {row["Board"]: row for row in read_csv(LAYERS)}
    pwr_layer = layer_rows["PCB-PWR"]
    require(pwr_layer["Copper_Layers"] == "4" and
            pwr_layer["Copper_Weight_Status"] == "TARGET_ONLY_NOT_FROZEN" and
            pwr_layer["Final_Stackup_Status"] == "OPEN_DIM_003_THERMAL_DFM",
            "PCB-PWR layer/stackup release boundary drift")
    dimensions = {row["ID"]: row for row in read_csv(OPEN_DIMENSIONS)}
    require(dimensions["DIM-003"]["Status"] == "OPEN",
            "DIM-003 must remain open before PCB-PWR routing")

    review_text = REVIEW_B.read_text(encoding="utf-8")
    for marker in (
        "Status: `OPEN / PROVISIONAL PRE-ROUTE CANDIDATE / NOT FOR MANUFACTURE`",
        "- [x] All 31 native/capture nets",
        "- [ ] `DIM-003` freezes",
        "- [ ] KiCad 9 DRC passes",
        "`HOLD`",
    ):
        require(marker in review_text, f"PCB-PWR Review B boundary marker missing: {marker}")

    board_digest = sha256(board_path)
    authority_digest = sha256(authority_path)
    control = expected_status_control(board_digest, authority_digest, class_counts, domain_counts)
    if status_path is not None:
        status = json.loads(status_path.resolve().read_text(encoding="utf-8"))
        traceability = status.get("pre_route_constraints", {})
        require(traceability.get("authority") == "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv" and
                traceability.get("record") == "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.md" and
                traceability.get("generator") == "tools/generate_pcb_pwr_routing_authority_rev_a.py" and
                traceability.get("independent_audit") == "tools/audit_pcb_pwr_routing_authority_rev_a.py",
                "PCB_PWR_CAPTURE_STATUS pre-route traceability drift")
        require(traceability.get("control") == control,
                "PCB_PWR_CAPTURE_STATUS pre-route control differs from audit")
        require(status.get("manufacturing_release") is False and
                status.get("native_layout", {}).get("routing_present") is False and
                status.get("native_layout", {}).get("copper_zones_present") is False and
                status.get("review_b", {}).get("complete") is False,
                "PCB-PWR release interlock drift")

    return {
        "schema": "dioneya-pcb-pwr-routing-authority-audit-v1",
        "status": STATE,
        "board": {
            "path": relative(board_path),
            "sha256": board_digest,
            "net_count": len(board_nets),
            "copper_layers": len(copper_layers),
            "trace_items": trace_items,
            "copper_zones": copper_zones,
        },
        "authority": {
            "path": relative(authority_path),
            "sha256": authority_digest,
            "row_count": len(rows),
        },
        "class_counts": class_counts,
        "reference_domain_counts": domain_counts,
        "current_basis": {
            "system_expected_max_a": 5.0,
            "buck_3v8_rated_a": 4.0,
            "modem_bb_plus_rf_peak_a": 3.3,
            "buck_3v3_rated_a": 4.0,
            "mic_ldo_rated_a": 0.3,
        },
        "i2c_initial_hz": 100000,
        "dim_003": "OPEN_REQUIRED_BEFORE_ROUTING",
        "numeric_power_geometry": NUMERIC_GEOMETRY,
        "routing_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--no-status-check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.board, args.authority, None if args.no_status_check else args.status)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    print("PCB-PWR routing authority audit: PASS")
    print("nets=31 classes=15 trace_items=0 copper_zones=0 DIM-003=open routing_complete=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

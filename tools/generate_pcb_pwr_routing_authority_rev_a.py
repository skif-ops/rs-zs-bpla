#!/usr/bin/env python3
"""Generate the PCB-PWR Rev.A pre-route constraint manifest.

The manifest classifies every reviewed power-board net without inventing final
stackup, copper-weight, width, via-array or thermal geometry.  It is a routing
input only and is never manufacturing-release evidence.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_NETS = ROOT / "hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv"
OUT = ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv"
STATUS = "PRE_ROUTE_CONSTRAINT_CONTROLLED_ROUTING_NOT_COMPLETE"

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

CLASS_NETS = {
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

BASE_SOURCES = (
    "hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv",
    "hardware/POWER_DESIGN_BASELINE_REV_A.json",
    "hardware/kicad/PCB_RULES.md",
)


def capture_nets() -> list[str]:
    with CAPTURE_NETS.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    nets = [row["Net"].strip() for row in rows]
    if len(nets) != 31 or any(not net for net in nets) or len(set(nets)) != 31:
        raise RuntimeError("PCB-PWR capture authority must contain 31 unique non-empty nets")
    return sorted(nets)


def route_class(net: str) -> str:
    matches = [name for name, members in CLASS_NETS.items() if net in members]
    if len(matches) != 1:
        raise RuntimeError(f"{net}: expected one route class, got {matches}")
    return matches[0]


def reference_domain(net: str, route_class_name: str) -> str:
    explicit = {
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
    }
    if net in explicit:
        return explicit[net]
    if route_class_name == "SEPARATE_HARNESS_RETURN":
        raise RuntimeError(f"{net}: missing explicit net-tie reference-domain rule")
    return "GND_PWR"


def current_basis(net: str, route_class_name: str) -> str:
    if route_class_name == "POWER_INPUT_HIGH_CURRENT":
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
    if route_class_name == "KELVIN_SENSE":
        return "MEASURES_SYSTEM_5A_BASIS_NO_LOAD_CURRENT_IN_SENSE_TRACE"
    return "SIGNAL_OR_BIAS_CURRENT_NOT_LOAD_CURRENT"


def geometry_rule(net: str, route_class_name: str) -> str:
    if route_class_name == "POWER_INPUT_HIGH_CURRENT":
        return "WIDTH_AND_COPPER_FROM_5A_DC_DROP_FAULT_ENERGY_PLUS70C_THERMAL_REVIEW"
    if net == "3V8_MODEM":
        return "WIDTH_AND_COPPER_FROM_4A_RATING_3P3A_PEAK_DC_DROP_AND_PLUS70C_THERMAL_REVIEW"
    if net == "3V3_DIGITAL":
        return "WIDTH_PENDING_LOAD_AND_THERMAL_REVIEW_QUIET_U4_FB_SENSE_FROM_OUTPUT_CAP_NOT_SW"
    if net == "1V8_MIC":
        return "WIDTH_FROM_0P3A_LOAD_DC_DROP_AND_LOW_NOISE_THERMAL_REVIEW"
    if route_class_name == "POWER_RETURN_PLANE":
        return "PLANE_GEOMETRY_CURRENT_DENSITY_VOID_AND_THERMAL_REVIEW_REQUIRED"
    if route_class_name == "SEPARATE_HARNESS_RETURN":
        return "COPPER_EQUIVALENT_TO_ASSOCIATED_RAIL_NO_NECKDOWN_JOIN_ONLY_AT_ASSIGNED_NET_TIE"
    if route_class_name == "SWITCH_NODE":
        return "SHORTEST_PRACTICAL_MINIMUM_AREA_NO_PLANE_NO_TEST_STUB"
    if route_class_name == "BOOTSTRAP_LOOP":
        return "SHORTEST_PRACTICAL_CONTROLLER_CAP_TO_SW_LOOP"
    if route_class_name == "KELVIN_SENSE":
        return "TRUE_KELVIN_FROM_SHUNT_SENSE_TERMINAL_NO_SHARED_LOAD_COPPER_HI_Z_TP_BRANCH_ONLY"
    if route_class_name == "FEEDBACK_SENSE":
        return "QUIET_POST_INDUCTOR_SENSE_FROM_OUTPUT_CAP_NO_SWITCH_NODE_PICKUP"
    if route_class_name == "I2C_OPEN_DRAIN":
        return "FABRICATOR_MINIMUMS_FINAL_HARNESS_CAPACITANCE_AND_PULLUP_REVIEW"
    return "FABRICATOR_MINIMUMS_AND_REVIEW_B"


def layer_rule(route_class_name: str) -> str:
    return {
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
    }[route_class_name]


def via_rule(route_class_name: str) -> str:
    if route_class_name in {
        "POWER_INPUT_HIGH_CURRENT", "POWER_OUTPUT_HIGH_CURRENT", "POWER_RAIL",
        "POWER_RETURN_PLANE", "SEPARATE_HARNESS_RETURN",
    }:
        return "VIA_ARRAY_COUNT_FROM_CURRENT_DENSITY_AND_THERMAL_REVIEW_NO_SINGLE_VIA_NECKDOWN"
    if route_class_name in {"SWITCH_NODE", "BOOTSTRAP_LOOP"}:
        return "ZERO_VIA_TARGET_ANY_EXCEPTION_REQUIRES_REVIEW_B"
    if route_class_name == "KELVIN_SENSE":
        return "ZERO_VIA_TARGET_NO_SHARED_LOAD_OR_PLANE_VIA"
    return "MINIMIZE_TRANSITIONS_ADD_LOCAL_RETURN_VIA_IF_LAYER_CHANGES"


def separation_rule(route_class_name: str) -> str:
    if route_class_name == "SWITCH_NODE":
        return "KEEP_AWAY_FROM_KELVIN_FEEDBACK_I2C_CONNECTORS_AND_BOARD_EDGE"
    if route_class_name == "BOOTSTRAP_LOOP":
        return "COLOCATE_WITH_ASSIGNED_SWITCH_LOOP_KEEP_AWAY_FROM_SENSE_AND_I2C"
    if route_class_name in {"KELVIN_SENSE", "FEEDBACK_SENSE"}:
        return "KEEP_AWAY_FROM_SWITCH_NODES_INDUCTORS_GATE_DRIVE_AND_HIGH_DI_DT_LOOPS"
    if route_class_name == "I2C_OPEN_DRAIN":
        return "KEEP_AWAY_FROM_SWITCH_NODES_AND_INDUCTORS_ROUTE_WITH_DIGITAL_RETURN_PATH"
    if route_class_name == "SEPARATE_HARNESS_RETURN":
        return "NO_CROSS_DOMAIN_JOIN_EXCEPT_ASSIGNED_NT1_NT2_OR_NT3"
    return "KEEP_CLEAR_OF_SWITCH_NODE_AND_UNRELATED_SENSITIVE_NETWORKS"


def source_authority(route_class_name: str) -> str:
    sources = list(BASE_SOURCES)
    if route_class_name in {
        "POWER_INPUT_HIGH_CURRENT", "POWER_OUTPUT_HIGH_CURRENT", "POWER_RAIL",
        "POWER_RETURN_PLANE", "SEPARATE_HARNESS_RETURN", "SWITCH_NODE",
        "BOOTSTRAP_LOOP", "KELVIN_SENSE", "FEEDBACK_SENSE",
    }:
        sources.append("hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv")
    if route_class_name in {
        "SEPARATE_HARNESS_RETURN", "LOW_SPEED_CONTROL", "OPEN_DRAIN_STATUS",
        "I2C_OPEN_DRAIN",
    }:
        sources.append("hardware/PWR_MAIN_12PIN_I2C_FREEZE_REV_A.md")
    sources.append("hardware/PCB_PWR_REVIEW_A_PIN_NET_REV_A.md")
    return ";".join(sources)


def row_for(net: str) -> dict[str, str]:
    route_class_name = route_class(net)
    priority = (
        "P0" if route_class_name in {
            "POWER_INPUT_HIGH_CURRENT", "POWER_OUTPUT_HIGH_CURRENT", "POWER_RAIL",
            "POWER_RETURN_PLANE", "SEPARATE_HARNESS_RETURN", "SWITCH_NODE",
            "BOOTSTRAP_LOOP", "KELVIN_SENSE", "FEEDBACK_SENSE",
        } else "P1"
    )
    return {
        "Net_Name": net,
        "Route_Class": route_class_name,
        "Reference_Domain": reference_domain(net, route_class_name),
        "Topology": TOPOLOGY[route_class_name],
        "Current_Basis": current_basis(net, route_class_name),
        "Geometry_Rule": geometry_rule(net, route_class_name),
        "Layer_Rule": layer_rule(route_class_name),
        "Via_Rule": via_rule(route_class_name),
        "Separation_Rule": separation_rule(route_class_name),
        "Priority": priority,
        "Source_Authority": source_authority(route_class_name),
        "Status": STATUS,
    }


def render() -> str:
    nets = capture_nets()
    assigned = [net for members in CLASS_NETS.values() for net in members]
    duplicates = sorted({net for net in assigned if assigned.count(net) > 1})
    if duplicates:
        raise RuntimeError(f"routing class overlap: {duplicates}")
    if set(assigned) != set(nets):
        raise RuntimeError(
            "routing class coverage drift: "
            f"missing={sorted(set(nets) - set(assigned))} "
            f"extra={sorted(set(assigned) - set(nets))}"
        )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(row_for(net) for net in nets)
    return stream.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    expected = render()
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != expected:
            print(f"PCB-PWR routing authority drift: {output}", file=sys.stderr)
            return 1
        print("PCB-PWR routing authority generator: PASS (31 nets)")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8", newline="")
    print(f"PCB-PWR routing authority written: {output}")
    print("nets=31 status=PRE_ROUTE_CONSTRAINT_CONTROLLED_ROUTING_NOT_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate the numeric PCB-PWR EVT engineering route-rule manifest."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"
CAPTURE = ROOT / "hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv"
OUT = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
STATUS = "EVT_ENGINEERING_CANDIDATE_ONLY_FINAL_FABRICATOR_FAULT_THERMAL_REVIEW_PENDING"

FIELDS = [
    "Net_Name",
    "Numeric_Class",
    "Width_mm",
    "Clearance_mm",
    "Via_Diameter_mm",
    "Via_Drill_mm",
    "Min_Parallel_Vias_If_Transition",
    "Max_One_Way_Length_mm",
    "Layer_Policy",
    "Via_Policy",
    "Status",
]


def format_number(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def render() -> str:
    basis = json.loads(BASIS.read_text(encoding="utf-8"))
    classes = {item["name"]: item for item in basis["numeric_classes"]}
    assignments = basis["netclass_assignments"]

    with CAPTURE.open(encoding="utf-8-sig", newline="") as stream:
        capture_nets = {row["Net"] for row in csv.DictReader(stream)}
    assigned = [net for nets in assignments.values() for net in nets]
    if len(capture_nets) != 31 or len(assigned) != 31 or len(set(assigned)) != 31:
        raise RuntimeError("PCB-PWR numeric rule coverage must be exactly 31 unique nets")
    if set(assigned) != capture_nets:
        raise RuntimeError("PCB-PWR numeric rule assignments differ from capture authority")
    if set(assignments) != set(classes):
        raise RuntimeError("PCB-PWR numeric class assignment set differs from class definitions")

    class_by_net = {
        net: class_name
        for class_name, nets in assignments.items()
        for net in nets
    }
    rows = []
    for net in sorted(capture_nets):
        rule = classes[class_by_net[net]]
        rows.append({
            "Net_Name": net,
            "Numeric_Class": rule["name"],
            "Width_mm": format_number(rule["selected_width_mm"]),
            "Clearance_mm": format_number(rule["clearance_mm"]),
            "Via_Diameter_mm": format_number(rule["via_diameter_mm"]),
            "Via_Drill_mm": format_number(rule["via_drill_mm"]),
            "Min_Parallel_Vias_If_Transition": format_number(
                rule["minimum_parallel_vias_if_transition"]
            ),
            "Max_One_Way_Length_mm": format_number(
                rule["max_one_way_length_at_drop_budget_mm"]
            ),
            "Layer_Policy": rule["layer_policy"],
            "Via_Policy": rule["via_policy"],
            "Status": STATUS,
        })

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    output = args.output.resolve()
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != expected:
            print(f"PCB-PWR EVT route-rule manifest drift: {output}", file=sys.stderr)
            return 1
        print("PCB-PWR EVT route-rule generator: PASS (31 nets / 8 numeric classes)")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8", newline="")
    print(f"PCB-PWR EVT route-rule manifest written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

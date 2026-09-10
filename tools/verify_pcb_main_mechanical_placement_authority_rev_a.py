#!/usr/bin/env python3
"""Second independent control for PCB-MAIN MAIN-AUTH-011 geometry."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
REVIEW_PATH = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md"
STATUS_PATH = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CONNECTOR_FREEZE_PATH = ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv"
CONNECTOR_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv"
BLE_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv"
OPEN_DIMENSIONS_PATH = ROOT / "mechanics/common/OPEN_DIMENSIONS.csv"
CAPTURE_SPEC_PATH = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
PCB_RULES_PATH = ROOT / "hardware/kicad/PCB_RULES.md"

FIELDS = [
    "Record_ID", "Feature_Type", "RefDes", "Contact", "Side",
    "Anchor_Definition", "X_mm", "Y_mm", "Rotation_deg", "Geometry",
    "Extent_X_mm", "Extent_Y_mm", "Z_Min_mm", "Z_Max_mm",
    "Access_Direction", "Layer_Scope", "Clearance_Rule", "Disposition",
    "Authority", "Notes",
]

EXPECTED_COUNTS = Counter({
    "BOARD_OUTLINE": 1,
    "ASSEMBLED_ENVELOPE": 1,
    "MOUNTING_HOLE": 4,
    "CONNECTOR_PLACEMENT": 13,
    "MODULE_PLACEMENT": 4,
    "RF_ZONE": 4,
    "KEEP_OUT": 7,
    "QUIET_ZONE": 1,
    "DFT_ZONE": 1,
    "FIDUCIAL": 3,
    "TEST_PAD": 31,
})

EXPECTED_CONNECTORS = {
    "J_PWR": (0.0, 13.0, 90.0, "OUTBOARD_WEST"),
    "J_MIC1": (0.0, 30.0, 90.0, "OUTBOARD_WEST"),
    "J_MIC2": (40.0, 75.0, 0.0, "OUTBOARD_NORTH"),
    "J_MIC3": (92.0, 75.0, 0.0, "OUTBOARD_NORTH"),
    "J_MIC4": (110.0, 54.0, 270.0, "OUTBOARD_EAST"),
    "J6": (18.0, 2.5, 180.0, "OUTBOARD_SOUTH"),
    "J7": (64.0, 2.5, 180.0, "OUTBOARD_SOUTH"),
    "J8": (16.0, 68.0, 0.0, "UP_Z"),
    "J9": (53.5, 68.0, 0.0, "UP_Z"),
    "J10": (74.0, 68.0, 0.0, "UP_Z"),
    "J11": (42.0, 0.0, 180.0, "OUTBOARD_SOUTH"),
    "J12": (87.0, 2.5, 180.0, "OUTBOARD_SOUTH"),
    "J13": (110.0, 13.0, 270.0, "OUTBOARD_EAST"),
}

EXPECTED_MODULES = {
    "U8": (24.0, 53.0, 0.0, 23.6, 19.9),
    "U9": (53.5, 58.0, 0.0, 9.7, 10.1),
    "U10": (74.0, 55.0, 0.0, 20.0, 14.0),
    "U11": (102.25, 35.25, 270.0, 15.5, 10.5),
}

EXPECTED_REGIONS = {
    "ZONE_CELL": (10.0, 42.0, 26.0, 30.0),
    "ZONE_GNSS": (44.0, 51.0, 19.0, 21.0),
    "ZONE_LORA": (64.0, 46.0, 21.5, 26.0),
    "ZONE_BLE_BODY": (94.5, 30.0, 15.5, 10.5),
    "KO_BLE_ANT_BOARD": (106.2, 30.0, 3.8, 10.5),
    "KO_BLE_ANT_VOLUME": (106.2, 27.0, 18.8, 16.5),
    "KO_GNSS_UPPER_VIEW": (44.0, 51.0, 19.0, 24.0),
    "ZONE_AUDIO_DIGITAL": (37.0, 39.0, 29.0, 11.0),
    "ZONE_DFT_BOTTOM": (27.0, 15.0, 67.0, 25.0),
}

EXPECTED_TEST_GROUPS = {
    "TP_EOL": (13, 33.0, 23.0),
    "TP_MCU_SWD": (5, 69.0, 23.0),
    "TP_BLE_SWD": (4, 84.0, 23.0),
    "TP_CELL_USB": (4, 33.0, 30.0),
    "TP_CELL_DBG": (5, 47.0, 30.0),
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], field: str) -> float:
    try:
        return float(row[field])
    except ValueError as exc:
        raise AssertionError(f"{row['Record_ID']}: {field} is not numeric") from exc


def close(actual: float, expected: float, label: str, tolerance: float = 0.001) -> None:
    require(abs(actual - expected) <= tolerance, f"{label}: expected {expected}, got {actual}")


def rect(row: dict[str, str]) -> tuple[float, float, float, float]:
    x = number(row, "X_mm")
    y = number(row, "Y_mm")
    return x, y, x + number(row, "Extent_X_mm"), y + number(row, "Extent_Y_mm")


def contains(region: dict[str, str], x: float, y: float) -> bool:
    x0, y0, x1, y1 = rect(region)
    return x0 <= x <= x1 and y0 <= y <= y1


def rectangles_overlap(a: dict[str, str], b: dict[str, str]) -> bool:
    ax0, ay0, ax1, ay1 = rect(a)
    bx0, by0, bx1, by1 = rect(b)
    return max(ax0, bx0) < min(ax1, bx1) and max(ay0, by0) < min(ay1, by1)


def contact_map(path: Path, refdes: str) -> dict[str, str]:
    return {
        row["Pin"]: row["RevA_Net"]
        for row in read_rows(path)
        if row["RefDes"] == refdes
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/pcb_main_mechanical_placement_authority_rev_a.json",
    )
    args = parser.parse_args()

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == FIELDS, "mechanical authority header mismatch")
        rows = list(reader)
    require(len(rows) == 70, "mechanical authority must contain exactly 70 records")
    require(all(all(row[field].strip() for field in FIELDS) for row in rows), "blank mechanical authority field")
    require(Counter(row["Feature_Type"] for row in rows) == EXPECTED_COUNTS, "mechanical feature count mismatch")
    require(all(row["Authority"] == "MAIN-AUTH-011" for row in rows), "authority ID drift")

    by_id = {row["Record_ID"]: row for row in rows}
    require(len(by_id) == len(rows), "duplicate mechanical authority Record_ID")
    require(set(by_id) == {f"MECH-{index:03d}" for index in range(1, 71)}, "mechanical Record_ID sequence mismatch")

    outline = by_id["MECH-001"]
    require(outline["RefDes"] == "PCB-MAIN" and outline["Geometry"] == "ROUNDED_RECT_R3", "board outline identity mismatch")
    for field, expected in {
        "X_mm": 0.0, "Y_mm": 0.0, "Extent_X_mm": 110.0,
        "Extent_Y_mm": 75.0, "Z_Min_mm": 0.0, "Z_Max_mm": 1.6,
    }.items():
        close(number(outline, field), expected, f"outline {field}")
    require(outline["Layer_Scope"] == "Edge.Cuts", "outline layer mismatch")

    envelope = by_id["MECH-002"]
    require(envelope["Disposition"] == "LOCKED_ALLOCATION_PENDING_STEP_CHECK", "PCBA envelope validation boundary missing")
    close(number(envelope, "Extent_X_mm"), 110.0, "assembled envelope X")
    close(number(envelope, "Extent_Y_mm"), 75.0, "assembled envelope Y")
    close(number(envelope, "Z_Max_mm"), 12.0, "assembled envelope Z")

    holes = {row["RefDes"]: row for row in rows if row["Feature_Type"] == "MOUNTING_HOLE"}
    expected_holes = {"H1": (5.0, 5.0), "H2": (105.0, 5.0), "H3": (105.0, 70.0), "H4": (5.0, 70.0)}
    require(set(holes) == set(expected_holes), "mounting-hole identity mismatch")
    for refdes, (x, y) in expected_holes.items():
        row = holes[refdes]
        close(number(row, "X_mm"), x, f"{refdes} X")
        close(number(row, "Y_mm"), y, f"{refdes} Y")
        require(row["Geometry"] == "CIRCLE_D3.2" and row["Disposition"] == "LOCKED_NPTH", f"{refdes} geometry mismatch")
        require(row["Clearance_Rule"] == "NO_COPPER_D8.0_NO_COMPONENT_D10.0", f"{refdes} keepout mismatch")

    connectors = {row["RefDes"]: row for row in rows if row["Feature_Type"] == "CONNECTOR_PLACEMENT"}
    require(set(connectors) == set(EXPECTED_CONNECTORS), "connector placement set mismatch")
    for refdes, (x, y, rotation, access) in EXPECTED_CONNECTORS.items():
        row = connectors[refdes]
        close(number(row, "X_mm"), x, f"{refdes} X")
        close(number(row, "Y_mm"), y, f"{refdes} Y")
        close(number(row, "Rotation_deg"), rotation, f"{refdes} rotation")
        require(row["Access_Direction"] == access, f"{refdes} access direction mismatch")
        require(row["Geometry"] == "MANUFACTURER_LAND_PATTERN", f"{refdes} land-pattern authority mismatch")

    modules = {row["RefDes"]: row for row in rows if row["Feature_Type"] == "MODULE_PLACEMENT"}
    require(set(modules) == set(EXPECTED_MODULES), "RF module placement set mismatch")
    for refdes, expected in EXPECTED_MODULES.items():
        actual = tuple(number(modules[refdes], field) for field in (
            "X_mm", "Y_mm", "Rotation_deg", "Extent_X_mm", "Extent_Y_mm"
        ))
        require(all(abs(a - b) <= 0.001 for a, b in zip(actual, expected)), f"{refdes} module anchor or extent mismatch")

    regions = {row["RefDes"]: row for row in rows if row["Feature_Type"] in {"RF_ZONE", "KEEP_OUT", "QUIET_ZONE", "DFT_ZONE"}}
    for refdes, expected in EXPECTED_REGIONS.items():
        require(refdes in regions, f"missing mechanical region {refdes}")
        actual = tuple(number(regions[refdes], field) for field in ("X_mm", "Y_mm", "Extent_X_mm", "Extent_Y_mm"))
        require(all(abs(a - b) <= 0.001 for a, b in zip(actual, expected)), f"{refdes} geometry mismatch")

    rf_zones = [regions[name] for name in ("ZONE_CELL", "ZONE_GNSS", "ZONE_LORA", "ZONE_BLE_BODY")]
    for index, first in enumerate(rf_zones):
        for second in rf_zones[index + 1:]:
            require(not rectangles_overlap(first, second), f"RF zones overlap: {first['RefDes']} / {second['RefDes']}")

    for module, zone in (("U8", "ZONE_CELL"), ("U9", "ZONE_GNSS"), ("U10", "ZONE_LORA"), ("U11", "ZONE_BLE_BODY")):
        row = modules[module]
        x0, y0, x1, y1 = rect(regions[zone])
        half_x = number(row, "Extent_X_mm") / 2.0
        half_y = number(row, "Extent_Y_mm") / 2.0
        x = number(row, "X_mm")
        y = number(row, "Y_mm")
        require(x - half_x >= x0 and x + half_x <= x1 and y - half_y >= y0 and y + half_y <= y1,
                f"{module} body escapes {zone}")
    for connector, zone in (("J8", "ZONE_CELL"), ("J9", "ZONE_GNSS"), ("J10", "ZONE_LORA")):
        row = connectors[connector]
        require(contains(regions[zone], number(row, "X_mm"), number(row, "Y_mm")), f"{connector} escapes {zone}")

    ble_board = regions["KO_BLE_ANT_BOARD"]
    _, _, ble_x1, ble_y1 = rect(ble_board)
    close(ble_x1, 110.0, "BLE board keepout east edge")
    close(ble_y1, 40.5, "BLE board keepout north edge")
    require(ble_board["Layer_Scope"] == "ALL_LAYERS", "BLE keepout is not all-layer")
    require("NO_COPPER_VIA_COMPONENT_TRACE_OR_PLANE" == ble_board["Clearance_Rule"], "BLE copper exclusion weakened")
    ble_volume = regions["KO_BLE_ANT_VOLUME"]
    close(rect(ble_volume)[2], 125.0, "BLE external keepout reach")
    close(number(ble_volume, "Z_Max_mm"), 40.0, "BLE external keepout height")
    gnss_upper = regions["KO_GNSS_UPPER_VIEW"]
    close(number(gnss_upper, "Z_Max_mm"), 150.0, "GNSS upper-view exclusion height")
    require("NO_SOLAR_METAL_OR_CABLE_BUNDLE_ABOVE" == gnss_upper["Clearance_Rule"], "GNSS upper-view rule weakened")

    test_rows = [row for row in rows if row["Feature_Type"] == "TEST_PAD"]
    by_group: dict[str, list[dict[str, str]]] = {}
    for row in test_rows:
        by_group.setdefault(row["RefDes"], []).append(row)
        require(row["Side"] == "BOTTOM" and row["Access_Direction"] == "DOWN_Z", f"{row['RefDes']}.{row['Contact']} is not bottom-access")
        require(row["Geometry"] == "CIRCLE_D1.7" and row["Clearance_Rule"] == "NO_PASTE_MASK_OPEN_D2.1", f"{row['RefDes']}.{row['Contact']} pogo geometry mismatch")
        require(contains(regions["ZONE_DFT_BOTTOM"], number(row, "X_mm"), number(row, "Y_mm")), f"{row['RefDes']}.{row['Contact']} outside fixture window")
    require(set(by_group) == set(EXPECTED_TEST_GROUPS), "fixture group set mismatch")

    electrical_maps = {
        "TP_EOL": contact_map(CONNECTOR_AUTHORITY_PATH, "TP_EOL"),
        "TP_MCU_SWD": contact_map(CONNECTOR_AUTHORITY_PATH, "TP_MCU_SWD"),
        "TP_BLE_SWD": contact_map(BLE_AUTHORITY_PATH, "TP_BLE_SWD"),
        "TP_CELL_USB": contact_map(CONNECTOR_AUTHORITY_PATH, "TP_CELL_USB"),
        "TP_CELL_DBG": contact_map(CONNECTOR_AUTHORITY_PATH, "TP_CELL_DBG"),
    }
    for group, (count, x0, y) in EXPECTED_TEST_GROUPS.items():
        group_rows = sorted(by_group[group], key=lambda row: int(row["Contact"]))
        require([int(row["Contact"]) for row in group_rows] == list(range(1, count + 1)), f"{group} contact sequence mismatch")
        require(set(electrical_maps[group]) == {str(index) for index in range(1, count + 1)}, f"{group} electrical authority contact mismatch")
        for index, row in enumerate(group_rows):
            close(number(row, "X_mm"), x0 + 2.54 * index, f"{group}.{index + 1} X")
            close(number(row, "Y_mm"), y, f"{group}.{index + 1} Y")
            require(electrical_maps[group][str(index + 1)] in row["Notes"], f"{group}.{index + 1} net marker mismatch")

    pad_centres = [(number(row, "X_mm"), number(row, "Y_mm"), row) for row in test_rows]
    for index, (x1, y1, first) in enumerate(pad_centres):
        for x2, y2, second in pad_centres[index + 1:]:
            require(math.hypot(x2 - x1, y2 - y1) >= 2.54 - 0.001,
                    f"pogo pads too close: {first['RefDes']}.{first['Contact']} / {second['RefDes']}.{second['Contact']}")

    fiducials = {(number(row, "X_mm"), number(row, "Y_mm")) for row in rows if row["Feature_Type"] == "FIDUCIAL"}
    require(fiducials == {(29.0, 16.5), (92.0, 16.5), (92.0, 39.0)}, "fixture fiducial coordinates mismatch")

    digest = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    review = REVIEW_PATH.read_text(encoding="utf-8")
    require(f"Authority CSV SHA-256: `{digest}`" in review, "mechanical authority SHA marker mismatch")
    for marker in (
        "MECHANICAL_PLACEMENT_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        "110 x 75 x 1.60 mm", "70 records", "31 individual pogo pads", "2.54 mm",
        "CONTROLLED_PENDING_NATIVE_STEP", "All physical tests remain `NOT RUN`",
    ):
        require(marker in review, f"mechanical authority review marker missing: {marker}")

    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    inputs = set(status["source_control"]["authoritative_inputs"])
    require({
        "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv",
        "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md",
    }.issubset(inputs), "mechanical authority files missing from status inputs")
    readiness = status["capture_readiness"]
    closed = {item["id"]: item for item in readiness["closed_authorities"]}
    require(set(closed) == {f"MAIN-AUTH-{index:03d}" for index in range(1, 12)}, "closed authority set mismatch")
    require(set(closed["MAIN-AUTH-011"]["evidence"]) == {
        "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv",
        "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md",
    }, "MAIN-AUTH-011 evidence set mismatch")
    require(readiness["complete"] is True and not readiness["open_authorities"], "capture authority is not complete")
    require(status["manufacturing_release"] is False, "mechanical authority prematurely released manufacturing")
    require(status["native_schematic"]["status"] == "ABSENT", "native schematic state unexpectedly changed")
    require(status["review_a"]["status"] == "BLOCKED_NATIVE_SCHEMATIC_ABSENT", "Review A blocker changed incorrectly")

    connector_freeze = {row["Connector_ID"]: row for row in read_rows(CONNECTOR_FREEZE_PATH)}
    pcb_main_connector_ids = {
        "CON-004B", "CON-MIC", "CON-RF-CELL", "CON-RF-GNSS", "CON-RF-LORA",
        "CON-USB", "CON-SD", "CON-TAMPER", "CON-SIM1", "CON-SIM2",
        "CON-SWD-MCU", "CON-SWD-BLE", "CON-EOL", "CON-CELL-USB", "CON-CELL-DBG",
    }
    for connector_id in pcb_main_connector_ids:
        row = connector_freeze[connector_id]
        require("PENDING_MECHANICS" not in row["Status"] and "PENDING_RF_LAYOUT" not in row["Status"],
                f"{connector_id} status still claims missing MAIN-AUTH-011 geometry")
        require("PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv" in row["Notes"],
                f"{connector_id} does not cite mechanical placement authority")

    dimensions = {row["ID"]: row for row in read_rows(OPEN_DIMENSIONS_PATH)}
    require(dimensions["DIM-001"]["Status"] == "CONTROLLED_PENDING_NATIVE_STEP", "DIM-001 status mismatch")
    require(dimensions["DIM-002"]["Status"] == "CLOSED_AUTHORITY_INPUT", "DIM-002 status mismatch")
    require("110x75x12" in dimensions["DIM-001"]["Required_input"], "DIM-001 envelope marker missing")
    require("H1-H4" in dimensions["DIM-002"]["Required_input"], "DIM-002 mounting marker missing")

    capture_spec = CAPTURE_SPEC_PATH.read_text(encoding="utf-8")
    pcb_rules = PCB_RULES_PATH.read_text(encoding="utf-8")
    for marker in (
        "PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv", "MAIN-AUTH-011",
        "110 x 75", "31 production pogo pads", "capture-authority input set is complete",
    ):
        require(marker in capture_spec, f"capture spec missing mechanical marker: {marker}")
    require("Main board target: 6 layers" in pcb_rules, "six-layer PCB-MAIN target missing")
    require("no guessed trace width" in pcb_rules, "stackup-dependent impedance boundary missing")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "mechanical placement second independent control",
        "status": "PASS_MECHANICAL_PLACEMENT_AUTHORITY_ONLY",
        "records_verified": len(rows),
        "board_mm": [110.0, 75.0, 1.6],
        "mounting_holes_verified": len(holes),
        "connector_placements_verified": len(connectors),
        "rf_module_anchors_verified": len(modules),
        "production_pogo_pads_verified": len(test_rows),
        "fixture_fiducials_verified": len(fiducials),
        "authority_sha256": digest,
        "open_authorities": [],
        "native_schematic": "ABSENT",
        "physical_tests": "NOT_RUN",
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(
        "PCB-MAIN MAIN-AUTH-011 mechanical placement verification: PASS "
        "(110 x 75 x 1.6 mm; four holes; 13 connectors; four RF zones; "
        "31 pogo pads; native capture/reviews remain blocking)"
    )
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()

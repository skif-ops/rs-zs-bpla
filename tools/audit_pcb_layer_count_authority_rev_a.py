#!/usr/bin/env python3
"""Independently audit the EVT-PRE-20 Rev.A PCB layer-count authority."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv"

EXPECTED = {
    "PCB-MAIN": {
        "layers": ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"],
        "thickness": 1.6,
        "thickness_status": "FROZEN_MECHANICAL_AUTHORITY",
    },
    "PCB-PWR": {
        "layers": ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
        "thickness": 1.6,
        "thickness_status": "PROVISIONAL_DIM_003_OPEN",
    },
    "PCB-MIC": {
        "layers": ["F.Cu", "B.Cu"],
        "thickness": 1.0,
        "thickness_status": "FROZEN_MECHANICAL_AUTHORITY",
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def native_board_state(board: str) -> dict[str, object]:
    path = ROOT / f"hardware/kicad/native/{board}/{board}.kicad_pcb"
    text = path.read_text(encoding="utf-8", errors="strict")
    thickness_match = re.search(r"\(thickness\s+([0-9.]+)\)", text)
    require(thickness_match is not None, f"{board}: native thickness missing")
    layers_match = re.search(r"\(layers\s+(.*?)\n\s*\)\s*\n\s*\(setup", text, re.S)
    require(layers_match is not None, f"{board}: native layer table missing")
    layers = re.findall(r'\(\d+\s+"([^"]+\.Cu)"\s+signal\)', layers_match.group(1))
    return {
        "path": str(path.relative_to(ROOT)),
        "layers": layers,
        "copper_layers": len(layers),
        "thickness_mm": float(thickness_match.group(1)),
    }


def require_pwr_spec(value: str, context: str) -> None:
    normalized = value.lower()
    require("4-layer" in normalized, f"{context}: four-layer statement missing")
    require("outer 2 oz target" in normalized, f"{context}: outer-copper target missing")
    require("inner 1 oz target" in normalized, f"{context}: inner-copper target missing")
    require("pending dfm" in normalized, f"{context}: final-stackup DFM interlock missing")


def audit() -> dict[str, object]:
    rows = read_csv(AUTHORITY)
    require(len(rows) == 3, "layer-count authority must contain exactly three boards")
    by_board = {row["Board"]: row for row in rows}
    require(set(by_board) == set(EXPECTED), "layer-count authority board set drift")
    require(len(by_board) == len(rows), "duplicate board in layer-count authority")

    native: dict[str, object] = {}
    for board, expected in EXPECTED.items():
        row = by_board[board]
        expected_layers = expected["layers"]
        require(row["Layer_Count_Status"] == "FROZEN_REV_A",
                f"{board}: layer count is not frozen")
        require(int(row["Copper_Layers"]) == len(expected_layers),
                f"{board}: authority copper-layer count drift")
        require(row["Native_Layer_Order"].split(";") == expected_layers,
                f"{board}: authority layer order drift")
        require(abs(float(row["Board_Thickness_mm"]) - float(expected["thickness"])) < 1e-9,
                f"{board}: authority thickness drift")
        require(row["Thickness_Status"] == expected["thickness_status"],
                f"{board}: thickness-status drift")
        require(row["Final_Stackup_Status"].startswith("OPEN_"),
                f"{board}: final stackup must remain explicitly open")
        require(bool(row["Release_Blockers"].strip()),
                f"{board}: release blockers missing")

        state = native_board_state(board)
        native[board] = state
        require(state["layers"] == expected_layers,
                f"{board}: native layer order differs from authority")
        require(abs(float(state["thickness_mm"]) - float(expected["thickness"])) < 1e-9,
                f"{board}: native thickness differs from authority")

    pwr_row = by_board["PCB-PWR"]
    require(pwr_row["Copper_Weight_Status"] == "TARGET_ONLY_NOT_FROZEN",
            "PCB-PWR copper weights must remain target-only")
    require("outer 2 oz target" in pwr_row["Copper_Weight_Target"],
            "PCB-PWR outer-copper target missing")
    require("inner 1 oz target" in pwr_row["Copper_Weight_Target"],
            "PCB-PWR inner-copper target missing")

    pwr_status = json.loads(
        (ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json").read_text(encoding="utf-8")
    )
    layout = pwr_status["native_layout"]
    require(layout["copper_layers"] == 4, "PCB-PWR status layer count drift")
    require(layout["layer_count_status"] == "FROZEN_REV_A_FINAL_STACKUP_OPEN",
            "PCB-PWR status must separate frozen layer count from open final stackup")
    require(layout["thickness_status"] == "PROVISIONAL_DIM_003_OPEN",
            "PCB-PWR thickness must remain provisional")

    pcb_set = (ROOT / "hardware/EVT_PRE_20_PCB_SET.md").read_text(encoding="utf-8")
    rules = (ROOT / "hardware/kicad/PCB_RULES.md").read_text(encoding="utf-8")
    placement = (ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.md").read_text(
        encoding="utf-8"
    )
    require("Технология Rev.A: 6 медных слоёв" in pcb_set,
            "PCB set does not state six-layer PCB-MAIN")
    require("Технология Rev.A: 4 медных слоя" in pcb_set,
            "PCB set does not state four-layer PCB-PWR")
    require("PCB-MAIN 6, PCB-PWR 4 and PCB-MIC 2 layers" in rules,
            "routing rules do not reference the controlled layer counts")
    require("four-copper-layer count is frozen for Rev.A" in placement,
            "PCB-PWR placement document still treats layer count as provisional")

    bom_draft = {row["Item_ID"]: row for row in read_csv(ROOT / "hardware/EVT_PRE_20_BOM_DRAFT.csv")}
    bom_release = {row["Item_ID"]: row for row in read_csv(ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv")}
    procurement = {
        row["Item_IDs"]: row for row in read_csv(ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv")
    }
    rfq = {row["BOM_Item_IDs"]: row for row in read_csv(ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv")}
    for item_id in ("ASM-PWR", "PCB-PWR"):
        require_pwr_spec(bom_draft[item_id]["Package"], f"draft BOM {item_id}")
        require_pwr_spec(bom_release[item_id]["Package"], f"release BOM {item_id}")
        require_pwr_spec(procurement[item_id]["Package"], f"procurement BOM {item_id}")
        require_pwr_spec(rfq[item_id]["MPN_or_spec"], f"RFQ {item_id}")

    scanned_paths = [
        "hardware/EVT_PRE_20_PCB_SET.md",
        "hardware/EVT_PRE_20_BOM_DRAFT.csv",
        "hardware/EVT_PRE_20_BOM_REV_A.csv",
        "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
        "hardware/CHINA_PROCUREMENT_RFQ.csv",
    ]
    for relative in scanned_paths:
        text = (ROOT / relative).read_text(encoding="utf-8")
        require("2-layer 2 oz candidate" not in text,
                f"{relative}: obsolete PCB-PWR layer claim remains")
    require("Целевая технология: 4 слоя" not in pcb_set,
            "obsolete four-layer PCB-MAIN claim remains")

    return {
        "schema": "dioneya-pcb-layer-count-authority-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "status": "PASS_CONTROLLED_LAYER_COUNTS_FINAL_STACKUPS_OPEN",
        "manufacturing_release": False,
        "authority": str(AUTHORITY.relative_to(ROOT)),
        "native_boards": native,
        "controlled_counts": {board: len(data["layers"]) for board, data in EXPECTED.items()},
        "open_interlocks": {
            board: by_board[board]["Release_Blockers"] for board in EXPECTED
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = audit()
    except (AssertionError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        result = {
            "schema": "dioneya-pcb-layer-count-authority-audit-v1",
            "configuration": "EVT-PRE-20 Rev.A",
            "status": "FAIL",
            "manufacturing_release": False,
            "error": str(exc),
        }
        exit_code = 1
    else:
        exit_code = 0

    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PCB layer-count authority: {result['status']}")
    if result.get("error"):
        print(f"- {result['error']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

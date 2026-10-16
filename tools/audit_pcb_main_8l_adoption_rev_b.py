#!/usr/bin/env python3
"""Audit the controlled PCB-MAIN 8-layer adoption and current layer authority."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_B.csv"
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
ADOPTION = ROOT / "hardware/PCB_MAIN_8L_ADOPTION_DECISION_REV_B.json"
EXPECTED_BOARD_SHA = "47b1c8dd391aabd6339c878ac4baff4f8fdf4f82d6ab588c13f7437552ea1f77"
EXPECTED_LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu", "In6.Cu", "B.Cu"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def board_layers(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    table = re.search(r"\(layers\s+(.*?)\n\s*\)\s*\n\s*\(setup", text, re.S)
    require(table is not None, "native PCB-MAIN layer table missing")
    return re.findall(r'\(\d+\s+"([^"]+\.Cu)"\s+signal\)', table.group(1))


def audit() -> dict[str, object]:
    rows = read_csv(AUTHORITY)
    by_board = {row["Board"]: row for row in rows}
    require(set(by_board) == {"PCB-MAIN", "PCB-PWR", "PCB-MIC"}, "authority board set drift")
    require(by_board["PCB-MAIN"]["Copper_Layers"] == "8", "PCB-MAIN authority is not 8L")
    require(by_board["PCB-MAIN"]["Native_Layer_Order"].split(";") == EXPECTED_LAYERS,
            "PCB-MAIN authority layer order drift")
    require(by_board["PCB-MAIN"]["Layer_Count_Status"] == "FROZEN_REV_B_USER_ACCEPTED",
            "PCB-MAIN Rev.B acceptance missing")
    require("JLC08161H_3313" in by_board["PCB-MAIN"]["Final_Stackup_Status"],
            "PCB-MAIN JLC08161H-3313 order basis missing")
    require(by_board["PCB-PWR"]["Copper_Layers"] == "4", "PCB-PWR authority drift")
    require(by_board["PCB-MIC"]["Copper_Layers"] == "2", "PCB-MIC authority drift")

    actual_layers = board_layers(BOARD)
    actual_hash = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    require(actual_layers == EXPECTED_LAYERS, "native PCB-MAIN is not the accepted 8L board")
    require(actual_hash == EXPECTED_BOARD_SHA, "native PCB-MAIN hash differs from accepted COMPLETE-105")

    adoption = json.loads(ADOPTION.read_text(encoding="utf-8"))
    require(adoption["decision"] == "ADOPT_8L_COMPLETE_105_REV_B_AS_PRIMARY",
            "8L adoption decision missing")
    require(adoption["native_board_sha256"] == actual_hash, "adoption hash mismatch")
    require(adoption["copper_layers"] == 8, "adoption layer count mismatch")
    require(adoption["manufacturing_authorized"] is False,
            "adoption must not bypass manufacturing gates")

    retired = ROOT / "hardware/kicad/retired/PCB-MAIN-6L-REV-A-2026-10-16/PCB-MAIN.kicad_pcb"
    require(retired.is_file(), "retired 6L KiCad source is not preserved")
    require(len(board_layers(retired)) == 6, "retired source is not the former 6L board")

    checks = {
        "hardware/EVT_PRE_20_BOM_DRAFT.csv": "Item_ID",
        "hardware/EVT_PRE_20_BOM_REV_A.csv": "Item_ID",
        "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv": "Item_IDs",
        "hardware/EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv": "Item_IDs",
    }
    for relative, key in checks.items():
        rows = read_csv(ROOT / relative)
        selected = [row for row in rows if row.get(key) in {"ASM-MAIN", "PCB-MAIN"}]
        require(len(selected) == 2, f"{relative}: PCB-MAIN build-to-print rows missing")
        require(all("8-layer" in row["Package"] for row in selected),
                f"{relative}: primary PCB-MAIN rows are not 8-layer")
        require(all("6-layer" not in row["Package"] for row in selected),
                f"{relative}: active PCB-MAIN 6-layer package remains")

    rfq = read_csv(ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv")
    selected_rfq = [row for row in rfq if row["BOM_Item_IDs"] in {"ASM-MAIN", "PCB-MAIN"}]
    require(len(selected_rfq) == 2, "PCB-MAIN RFQ rows missing")
    require(all("8-layer" in row["MPN_or_spec"] and "JLC08161H-3313" in row["MPN_or_spec"]
                for row in selected_rfq), "PCB-MAIN RFQ is not bound to 8L JLC08161H-3313")

    return {
        "schema": "dioneya-pcb-main-8l-adoption-audit-v1",
        "configuration": "EVT-PRE-20 Rev.B",
        "status": "PASS_CONTROLLED_LAYER_COUNTS_EVT_STACKUPS_ACCEPTED",
        "manufacturing_release": False,
        "authority": str(AUTHORITY.relative_to(ROOT)),
        "controlled_counts": {"PCB-MAIN": 8, "PCB-PWR": 4, "PCB-MIC": 2},
        "pcb_main": {
            "source": str(BOARD.relative_to(ROOT)),
            "sha256": actual_hash,
            "layers": actual_layers,
            "retired_6l_preserved": True,
            "decision": str(ADOPTION.relative_to(ROOT)),
        },
        "open_interlocks": by_board["PCB-MAIN"]["Release_Blockers"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = audit()
    except (AssertionError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        result = {
            "schema": "dioneya-pcb-main-8l-adoption-audit-v1",
            "configuration": "EVT-PRE-20 Rev.B",
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
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"PCB-MAIN 8L adoption: {result['status']}")
    if result.get("error"):
        print(f"- {result['error']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

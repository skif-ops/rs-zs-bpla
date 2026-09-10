#!/usr/bin/env python3
"""Block stale PCB-PWR pre-schematic input from re-entering Rev.A capture.

This audit is intentionally separate from the numeric power-design audit. It verifies
that the human/machine capture sheet expresses the current architecture and explicitly
rejects superseded integrated-MPPT, legacy-buck and 10-contact MAIN/PWR concepts.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sheet",
        type=Path,
        default=ROOT / "hardware" / "kicad" / "sheets" / "01_POWER.csv",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "kicad-native" / "PCB-PWR" / "preschematic_audit.json",
    )
    args = ap.parse_args()

    with args.sheet.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError("01_POWER.csv is empty")

    text = "\n".join(
        f"{row.get('Sheet','')} {row.get('Item','')} {row.get('Requirement','')}"
        for row in rows
    )

    required = [
        "external LiFePO4/BMS/MPPT",
        "MPPT charger is external",
        "LM74700QDBVRQ1",
        "CSD18540Q5B",
        "LMR604403SRAKR",
        "3.8 V nominal",
        "100 kOhm",
        "35.7 kOhm",
        "400 kHz",
        "86.6 kOhm",
        "4.7 uH",
        "TPS7A2018PDBVR",
        "INA226AIDGSR",
        "address 0x40",
        "10 mOhm",
        "CAL 2560",
        "12-contact MAIN/PWR contract",
        "43045-1202",
        "11 I2C2_SCL",
        "12 I2C2_SDA",
        "100 kHz",
        "pull-ups are on PCB-MAIN",
        "NOT FOR MANUFACTURE",
    ]
    forbidden = [
        "BQ24650",
        "TPS62135",
        "panel cold Voc",
        "battery float/current resistor options",
        "MPPT input set by resistor",
        "10-16.8 V operating pack",
        "10-contact MAIN/PWR contract",
        "10-pin MAIN/PWR",
    ]

    missing = [token for token in required if token not in text]
    stale = [token for token in forbidden if token in text]
    if missing or stale:
        raise RuntimeError(
            f"PCB-PWR pre-schematic drift: missing_current={missing}, stale_forbidden={stale}"
        )

    items = [row.get("Item", "") for row in rows]
    if len(items) != len(set(items)):
        raise RuntimeError(f"duplicate PCB-PWR pre-schematic item IDs: {items}")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "audit": "PCB-PWR independent pre-schematic drift audit",
        "status": "PASS_CURRENT_12PIN_INA226_ARCHITECTURE_ONLY",
        "sheet": str(args.sheet.relative_to(ROOT)),
        "row_count": len(rows),
        "required_tokens_verified": required,
        "forbidden_legacy_tokens_absent": forbidden,
        "manufacturing_release": "BLOCKED_NOT_FOR_MANUFACTURE",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("PCB-PWR pre-schematic drift audit PASS: 12-pin + INA226 I2C authority")
    print(f"rows={len(rows)}; legacy forbidden tokens absent={len(forbidden)}")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

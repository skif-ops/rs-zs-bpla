#!/usr/bin/env python3
"""Audit mandatory PCB-PWR Rev.A DFT access against the controlled net authority."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NETS = ROOT / "hardware" / "PCB_PWR_CAPTURE_NETS_REV_A.csv"

REQUIRED = {
    "VBAT_PROTECTED": "TP_VBAT_PROTECTED",
    "SHUNT_SOURCE_SENSE": "TP_SHUNT_SRC",
    "SHUNT_LOAD_SENSE": "TP_SHUNT_LOAD",
    "3V8_MODEM": "TP_3V8",
    "PG_3V8": "TP_PG_3V8",
    "PWR_GOOD": "TP_PWR_GOOD",
    "1V8_MIC": "TP_1V8",
    "FAULT": "TP_FAULT",
    "I2C2_SCL": "TP_SCL",
    "I2C2_SDA": "TP_SDA",
}


def main() -> int:
    with NETS.open(encoding="utf-8-sig", newline="") as f:
        rows = {r["Net"]: r for r in csv.DictReader(f)}
    missing_nets = sorted(set(REQUIRED) - set(rows))
    if missing_nets:
        raise RuntimeError(f"DFT authority nets missing: {missing_nets}")
    failures = []
    for net, token in REQUIRED.items():
        targets = {x.strip() for x in rows[net]["To"].split(";") if x.strip()}
        if token not in targets:
            failures.append(f"{net} missing {token}")
    if failures:
        raise RuntimeError("PCB-PWR DFT authority incomplete: " + "; ".join(failures))
    for net in ("SHUNT_SOURCE_SENSE", "SHUNT_LOAD_SENSE"):
        if rows[net]["Class"] != "KELVIN" or "No load current" not in rows[net]["Notes"]:
            raise RuntimeError(f"{net}: Kelvin/no-load-current policy weakened")
    print("PCB-PWR Rev.A DFT authority audit PASS")
    print("mandatory test points:", ", ".join(REQUIRED.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

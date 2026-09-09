#!/usr/bin/env python3
"""QG-1 structural and quantity validation for the controlled Rev.A BOM."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOM = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
OUT = ROOT / "artifacts/evt_pre_20_bom_qg1.json"

REQUIRED_FIELDS = {
    "Item_ID", "Assembly", "RefDes", "Category", "Description", "Manufacturer",
    "MPN", "Package", "Qty_per_station", "Qty_20", "Spares", "Procure_qty",
    "Variant", "Status", "Value", "Line_class", "Population", "Temperature_C",
    "BOM_disposition",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def main() -> None:
    with BOM.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        require(reader.fieldnames is not None, "BOM header missing")
        require(
            REQUIRED_FIELDS.issubset(reader.fieldnames),
            f"BOM fields missing: {sorted(REQUIRED_FIELDS - set(reader.fieldnames))}",
        )
        rows = list(reader)

    require(rows, "BOM is empty")
    by_id = {row["Item_ID"]: row for row in rows}
    require(len(by_id) == len(rows), "duplicate or empty Item_ID in BOM")

    for row in rows:
        item = row["Item_ID"]
        require(item, "empty Item_ID")
        for field in (
            "Assembly", "Description", "Variant", "Status",
            "Line_class", "Population", "BOM_disposition",
        ):
            require(row[field], f"{item}: required field {field} is empty")
        numbers = {}
        for field in ("Qty_per_station", "Qty_20", "Spares", "Procure_qty"):
            require(row[field].isdigit(), f"{item}: {field} is not a non-negative integer")
            numbers[field] = int(row[field])
        require(
            numbers["Qty_20"] == 20 * numbers["Qty_per_station"],
            f"{item}: Qty_20 does not equal 20 x Qty_per_station",
        )
        require(
            numbers["Procure_qty"] == numbers["Qty_20"] + numbers["Spares"],
            f"{item}: Procure_qty does not equal Qty_20 + Spares",
        )
        if row["Population"] in {"DNP", "PCB_FEATURE"}:
            require(
                numbers["Spares"] == 0,
                f"{item}: {row['Population']} line must not carry procurement spares",
            )

    expected_pwr_refs = {
        "PWR-REV-CTL": "U1", "PWR-REV-FET": "Q1", "U-MON-01": "U2",
        "U-PWR1": "U3", "U-PWR2": "U4", "U-PWR3": "U5",
        "R-SHUNT-01": "RSH1", "PWR-TVS-01": "D1", "PWR-FUSE-01": "F1",
        "J-PWR-IN": "J1", "J-PWR-PWR": "J2",
    }
    for item, ref in expected_pwr_refs.items():
        require(item in by_id, f"missing PCB-PWR BOM item {item}")
        require(by_id[item]["Assembly"] == "PCB-PWR", f"{item}: wrong assembly")
        require(by_id[item]["RefDes"] == ref, f"{item}: expected native PCB-PWR RefDes {ref}")

    expected_quantities = {
        "J-MIC": 4,
        "J-MIC-MAIN": 4,
        "H-MIC": 8,
        "T-MIC": 48,
        "H-PWR-MAIN": 2,
        "T-PWR-MAIN-PWR": 12,
        "T-PWR-MAIN-CTL": 12,
        "C-MIC": 4,
        "R-MIC": 4,
    }
    for item, qty in expected_quantities.items():
        require(item in by_id, f"missing quantity-controlled BOM item {item}")
        require(
            int(by_id[item]["Qty_per_station"]) == qty,
            f"{item}: expected {qty} per station, got {by_id[item]['Qty_per_station']}",
        )

    require(
        by_id["J-MIC"]["MPN"] == by_id["J-MIC-MAIN"]["MPN"] == "5040500691",
        "MIC board headers are not one frozen 6-pin MPN",
    )
    require(by_id["H-MIC"]["MPN"] == "5040510601", "MIC housing MPN mismatch")
    require(by_id["T-MIC"]["MPN"] == "5040520098", "MIC terminal MPN mismatch")
    require(by_id["PWR-L"]["Spares"] == "10", "PCB-PWR inductor spare policy mismatch")

    serialized = "\n".join(",".join(row.values()) for row in rows)
    for forbidden in ("ESP32-C3", "JST_BM05B", "GHR-05V-S", "5040500591", "5040510501"):
        require(forbidden not in serialized, f"superseded token in BOM: {forbidden}")

    result = {
        "gate": "QG-1",
        "status": "PASS",
        "rows": len(rows),
        "quantity_formula_rows": len(rows),
        "pcb_pwr_refdes_checked": len(expected_pwr_refs),
        "controlled_quantity_lines": expected_quantities,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"EVT-PRE-20 production BOM QG-1 structural/quantity gate: PASS ({len(rows)} rows)")


if __name__ == "__main__":
    main()

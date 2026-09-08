#!/usr/bin/env python3
"""Generate the unified EVT-PRE-20 Rev.A BOM from the draft + authoritative freezes.

The draft keeps the full system-level item inventory. MAIN/POWER/CONNECTOR freeze tables
are authoritative for exact MPNs and release blockers. This script deterministically
merges them and fails on known superseded parts.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "hardware/EVT_PRE_20_BOM_DRAFT.csv"
OUT = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def freeze_map(path: str, key: str) -> dict[str, dict[str, str]]:
    return {r[key]: r for r in read_csv(ROOT / path)}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def main() -> None:
    rows = read_csv(DRAFT)
    require(rows, "draft BOM is empty")
    fields = list(rows[0].keys())
    by_id = {r["Item_ID"]: r for r in rows}

    main_parts = freeze_map("hardware/MAIN_COMPONENT_FREEZE_REV_A.csv", "RefDes")
    power_parts = freeze_map("hardware/POWER_COMPONENT_FREEZE_REV_A.csv", "Component_ID")
    connectors = freeze_map("hardware/CONNECTOR_FREEZE_REV_A.csv", "Connector_ID")

    def update_existing(item_id: str, *, manufacturer: str, mpn: str, package: str, status: str, notes: str) -> None:
        require(item_id in by_id, f"draft BOM item missing: {item_id}")
        r = by_id[item_id]
        r["Manufacturer"] = manufacturer
        r["MPN"] = mpn
        r["Package"] = package
        r["Status"] = status
        r["Notes"] = notes

    for item_id, ref in {
        "U1": "U1", "U2": "U2", "U3": "U3", "U4": "U4", "U7": "U7",
        "U8": "U8", "U9": "U9", "U10": "U10", "U11": "U11", "U13": "U13", "X1": "X1",
    }.items():
        p = main_parts[ref]
        update_existing(
            item_id,
            manufacturer=p["Manufacturer"],
            mpn=p["MPN"],
            package=p["Package_or_Module"],
            status=p["Status"],
            notes=f"Rev.A freeze source MAIN_COMPONENT_FREEZE_REV_A.csv; blockers: {p['Release_Blockers']}",
        )

    require(main_parts["U14"]["MPN"] == main_parts["U15"]["MPN"], "SIM ESD MPNs differ")
    p14 = main_parts["U14"]
    update_existing(
        "U14-U15",
        manufacturer=p14["Manufacturer"], mpn=p14["MPN"], package=p14["Package_or_Module"],
        status="SELECTED_PENDING_SIM_REVIEW",
        notes="Two identical low-capacitance SIM ESD arrays; Rev.A freeze source MAIN_COMPONENT_FREEZE_REV_A.csv",
    )

    for item_id, comp_id in {"U-PWR1": "U-PWR1", "U-PWR2": "U-PWR2", "U-PWR3": "U-PWR3"}.items():
        p = power_parts[comp_id]
        update_existing(
            item_id,
            manufacturer=p["Manufacturer"], mpn=p["MPN"], package=p["Package"], status=p["Status"],
            notes=f"Rev.A freeze source POWER_COMPONENT_FREEZE_REV_A.csv; {p['Electrical_Baseline']}; blockers: {p['Release_Blockers']}",
        )

    mic = connectors["CON-MIC"]
    require(mic["Positions"] == "6", "Rev.A MIC connector must be 6 positions")
    update_existing(
        "J-MIC", manufacturer="Molex", mpn=mic["Board_MPN"].removeprefix("Molex_"),
        package="Pico-Lock 1.50 mm 6-circuit right-angle SMT", status=mic["Status"],
        notes=(f"Mating housing {mic['Mating_Housing_MPN'].removeprefix('Molex_')}; "
               f"terminal {mic['Terminal_MPN'].removeprefix('Molex_')}; "
               "pinout 1V8/GND/CLK/DATA/WAKE/AAD_CFG(THSEL); -40..105 C"),
    )

    for item_id, cid in {"J-SIM1": "CON-SIM1", "J-SIM2": "CON-SIM2"}.items():
        c = connectors[cid]
        update_existing(
            item_id, manufacturer="TE Connectivity", mpn=c["Board_MPN"].removeprefix("TE_"),
            package="Nano-SIM 4FF connector with DET", status=c["Status"],
            notes=f"Rev.A connector freeze; blockers: {c['Release_Blockers']}",
        )

    for item_id, cid in {"J-RF-CELL": "CON-RF-CELL", "J-RF-GNSS": "CON-RF-GNSS", "J-RF-LORA": "CON-RF-LORA"}.items():
        c = connectors[cid]
        update_existing(
            item_id, manufacturer="Hirose", mpn="U.FL-R-SMT-1(60)", package="U.FL SMT receptacle",
            status=c["Status"], notes=f"Rev.A connector freeze; exact coax assembly temperature/RF validation remains blocking: {c['Release_Blockers']}",
        )

    def append_item(*, item_id: str, assembly: str, refdes: str, category: str, description: str,
                    manufacturer: str, mpn: str, package: str, qty: int, spares: int,
                    status: str, notes: str, variant: str = "COMMON") -> None:
        if item_id in by_id:
            return
        row = {field: "" for field in fields}
        row.update({
            "Item_ID": item_id, "Assembly": assembly, "RefDes": refdes, "Category": category,
            "Description": description, "Manufacturer": manufacturer, "MPN": mpn, "Package": package,
            "Qty_per_station": str(qty), "Qty_20": str(qty * 20), "Spares": str(spares),
            "Procure_qty": str(qty * 20 + spares), "Variant": variant, "Status": status,
            "China_source_policy": "Authorized or traceable tier-1 channel",
            "Incoming_control": "Marking MPN package orientation electrical functional sample",
            "Notes": notes,
        })
        rows.append(row)
        by_id[item_id] = row

    for ref in ("U16", "U17", "U18"):
        p = main_parts[ref]
        append_item(
            item_id=ref, assembly="PCB-MAIN", refdes=ref, category="Logic",
            description=p["Function"], manufacturer=p["Manufacturer"], mpn=p["MPN"],
            package=p["Package_or_Module"], qty=1, spares=5, status=p["Status"],
            notes=f"Rev.A MAIN freeze; blockers: {p['Release_Blockers']}",
        )

    for comp_id, refdes, category in (
        ("PWR-REV-CTL", "U4", "Protection"), ("PWR-REV-FET", "Q1", "Protection"),
        ("PWR-TVS-01", "D1", "Protection"), ("PWR-FUSE-01", "F1", "Protection"),
        ("U-MON-01", "U5", "Monitor"),
    ):
        p = power_parts[comp_id]
        append_item(
            item_id=comp_id, assembly="PCB-PWR", refdes=refdes, category=category,
            description=p["Function"], manufacturer=p["Manufacturer"], mpn=p["MPN"], package=p["Package"],
            qty=int(p["Qty_per_station"] or "1"), spares=5, status=p["Status"],
            notes=f"Rev.A POWER freeze; {p['Electrical_Baseline']}; blockers: {p['Release_Blockers']}",
        )

    for item_id, cid, assembly, refdes in (
        ("J-USB", "CON-USB", "PCB-MAIN", "J_USB"),
        ("J-PWR-IN", "CON-003", "PCB-PWR", "J_PWR_IN"),
        ("J-PWR-PWR", "CON-004A", "PCB-PWR", "J_MAIN_PWR"),
        ("J-PWR-MAIN", "CON-004B", "PCB-MAIN", "J_PWR"),
    ):
        c = connectors[cid]
        manufacturer = "Molex" if c["Board_MPN"].startswith("Molex_") else "GCT"
        append_item(
            item_id=item_id, assembly=assembly, refdes=refdes, category="Connector",
            description=c["Function"], manufacturer=manufacturer,
            mpn=c["Board_MPN"].split("_", 1)[1] if "_" in c["Board_MPN"] else c["Board_MPN"],
            package=f"{c['Positions']} positions", qty=1, spares=5, status=c["Status"],
            notes=f"Mating {c['Mating_Housing_MPN']}; terminal {c['Terminal_MPN']}; blockers: {c['Release_Blockers']}",
        )

    full_text = "\n".join(",".join(r.get(f, "") for f in fields) for r in rows)
    for forbidden in ("ESP32-C3", "JST_BM05B", "GHR-05V-S", "5040500591", "5040510501"):
        require(forbidden not in full_text, f"superseded token remains in generated BOM: {forbidden}")
    require(by_id["J-MIC"]["MPN"] == "5040500691", "generated 6-pin MIC connector MPN mismatch")
    require("AAD_CFG" in by_id["J-MIC"]["Notes"], "generated MIC connector BOM line omits THSEL/AAD_CFG")
    for key in ("U16", "U17", "U18", "PWR-REV-CTL", "PWR-REV-FET"):
        require(key in by_id, f"generated BOM missing {key}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {OUT.relative_to(ROOT)} with {len(rows)} rows")


if __name__ == "__main__":
    main()

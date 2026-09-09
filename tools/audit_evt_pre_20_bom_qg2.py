#!/usr/bin/env python3
"""QG-2 independent technical completeness audit of the Rev.A BOM.

Default mode records blockers without failing engineering CI. --strict is the actual
production-BOM release gate and must remain non-zero until the schematic-derived BOM,
exact system SKUs and verification evidence are complete.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOM = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", default="artifacts/evt_pre_20_bom_qg2.json")
    args = parser.parse_args()

    rows = read(BOM)
    by_id = {row["Item_ID"]: row for row in rows}
    blockers: list[str] = []
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "pass": ok, "detail": detail})
        if not ok:
            blockers.append(detail)

    main_freeze = read(ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv")
    main_item_for_ref = {
        **{f"U{i}": f"U{i}" for i in (1, 2, 3, 4, 7, 8, 9, 10, 11, 13, 16, 17, 18)},
        "U14": "U14-U15", "U15": "U14-U15", "X1": "X1",
    }
    main_mismatch = []
    for frozen in main_freeze:
        ref = frozen["RefDes"]
        item = main_item_for_ref.get(ref)
        if not item or item not in by_id or by_id[item]["MPN"] != frozen["MPN"]:
            main_mismatch.append(f"{ref}:{frozen['MPN']}")
    check("main_active_mpn_freeze", not main_mismatch,
          "PCB-MAIN active MPN freeze mismatch: " + ", ".join(main_mismatch) if main_mismatch else "all active MAIN MPNs match")

    power_expected = {
        "PWR-REV-CTL": ("U1", "LM74700QDBVRQ1"),
        "PWR-REV-FET": ("Q1", "CSD18540Q5B"),
        "U-MON-01": ("U2", "INA226AIDGSR"),
        "U-PWR1": ("U3", "LMR604403SRAKR"),
        "U-PWR2": ("U4", "LMR604403SRAKR"),
        "U-PWR3": ("U5", "TPS7A2018PDBVR"),
        "R-SHUNT-01": ("RSH1", "WSK2512R0100FEA"),
        "PWR-TVS-01": ("D1", "SMBJ18A"),
        "PWR-FUSE-01": ("F1", "0451005.MRL"),
    }
    power_mismatch = [
        item for item, (ref, mpn) in power_expected.items()
        if item not in by_id or by_id[item]["RefDes"] != ref or by_id[item]["MPN"] != mpn
    ]
    check("power_identity_and_refdes", not power_mismatch,
          "PCB-PWR identity/RefDes mismatch: " + ", ".join(power_mismatch) if power_mismatch else "power IC/protection identity and RefDes match")

    mic_expected = {
        "MK1": "MMICT5838-00-012", "J-MIC": "5040500691",
        "C-MIC": "CGA2B3X7R1E104K050BB", "R-MIC": "ERJ-2GE0R00X",
    }
    mic_mismatch = [item for item, mpn in mic_expected.items() if item not in by_id or by_id[item]["MPN"] != mpn]
    check("mic_native_component_identity", not mic_mismatch,
          "PCB-MIC component identity mismatch: " + ", ".join(mic_mismatch) if mic_mismatch else "four native PCB-MIC fitted identities match")

    mic_native = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.sch"
    mic_native_text = mic_native.read_text(encoding="utf-8") if mic_native.is_file() else ""
    check("mic_native_exact_orderable_mpn", "MMICT5838-00-012" in mic_native_text,
          "native PCB-MIC does not bind MK1 to exact orderable MMICT5838-00-012")

    exact_fields_missing = []
    for row in rows:
        if row["Population"] != "FITTED":
            continue
        for field in ("Manufacturer", "MPN", "Package", "Temperature_C"):
            if row[field] in ("", "TBD", "OPEN"):
                exact_fields_missing.append(f"{row['Item_ID']}:{field}")
    check("fitted_line_exact_fields", not exact_fields_missing,
          "fitted lines missing exact production fields: " + ", ".join(exact_fields_missing) if exact_fields_missing else "all fitted lines have exact identity/package/rating")

    passive_value_missing = [
        row["Item_ID"] for row in rows
        if row["Population"] in {"FITTED", "DNP"}
        and row["Category"] in {"Passive", "Shunt"}
        and not row["Value"]
    ]
    check("passive_values", not passive_value_missing,
          "passive lines missing explicit value: " + ", ".join(passive_value_missing) if passive_value_missing else "all passive values are explicit")

    blocked_rows = [row["Item_ID"] for row in rows if row["BOM_disposition"].startswith("BLOCKED")]
    check("bom_dispositions_released", not blocked_rows,
          "BOM selections or supplier releases still blocked: " + ", ".join(blocked_rows) if blocked_rows else "all BOM dispositions released")

    # This independent list comes from the native PCB-PWR generator. Every physical
    # fitted/DNP designator must be represented before a factory BOM can be released.
    required_pwr_passives = {
        "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13",
        "C14", "C15", "C16", "C17", "C18", "C19",
        "L1", "L2", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12",
        "R13", "R14", "R15", "NT1", "NT2", "NT3",
    }
    represented_pwr_refs: set[str] = set()
    for row in rows:
        if row["Assembly"] != "PCB-PWR":
            continue
        for token in row["RefDes"].split(";"):
            ref = token.strip().removesuffix(" bank")
            if ref in required_pwr_passives:
                represented_pwr_refs.add(ref)
    missing_pwr_passives = sorted(required_pwr_passives - represented_pwr_refs)
    check("power_schematic_refdes_coverage", not missing_pwr_passives,
          "PCB-PWR BOM missing schematic RefDes: " + ", ".join(missing_pwr_passives) if missing_pwr_passives else "all PCB-PWR passive/net-tie RefDes represented")

    bank_rows = [row["Item_ID"] for row in rows if row["Assembly"] == "PCB-PWR" and " bank" in row["RefDes"]]
    check("power_cap_bank_native_expansion", not bank_rows,
          "PCB-PWR capacitor bank symbols still require individual native RefDes: " + ", ".join(bank_rows) if bank_rows else "all power capacitors have individual native RefDes")

    main_native = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_sch"
    check("main_native_schematic_source", main_native.is_file(),
          "native PCB-MAIN schematic is absent; a complete schematic-derived production BOM cannot be proven")

    system_open = [
        row["Item_ID"] for row in rows
        if row["Line_class"] in {"SYSTEM_ITEM", "MECHANICAL_OPTION"}
        and int(row["Qty_per_station"]) > 0
        and row["BOM_disposition"] != "CONTROLLED"
    ]
    check("system_sku_release", not system_open,
          "system/mechanical SKUs not released: " + ", ".join(system_open) if system_open else "system SKUs released")

    result = {
        "gate": "QG-2",
        "status": "PASS" if not blockers else "BLOCKED",
        "production_bom_complete": not blockers,
        "checks": checks,
        "blockers": blockers,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"EVT-PRE-20 production BOM QG-2 technical gate: {result['status']}")
    for blocker in blockers:
        print(f"- {blocker}")
    print(f"report: {output.relative_to(ROOT)}")
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())

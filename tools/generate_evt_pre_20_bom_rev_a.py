#!/usr/bin/env python3
"""Generate the controlled EVT-PRE-20 Rev.A BOM from authoritative freezes.

The draft keeps the system-level inventory. MAIN/POWER/CONNECTOR freeze tables are
authoritative for selected MPNs and release blockers. This script deterministically
merges them, fixes assembly reference/quantity mappings, expands connector consumables,
and fails on known superseded parts. It is a controlled engineering BOM, not a release
waiver: open and candidate rows remain visible until the strict BOM gates can pass.
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
    fields.extend(["Value", "Line_class", "Population", "Temperature_C", "BOM_disposition"])
    for row in rows:
        for field in fields:
            row.setdefault(field, "")
    by_id = {r["Item_ID"]: r for r in rows}

    main_parts = freeze_map("hardware/MAIN_COMPONENT_FREEZE_REV_A.csv", "RefDes")
    power_parts = freeze_map("hardware/POWER_COMPONENT_FREEZE_REV_A.csv", "Component_ID")
    connectors = freeze_map("hardware/CONNECTOR_FREEZE_REV_A.csv", "Connector_ID")

    def set_quantities(row: dict[str, str], qty: int, spares: int) -> None:
        row["Qty_per_station"] = str(qty)
        row["Qty_20"] = str(qty * 20)
        row["Spares"] = str(spares)
        row["Procure_qty"] = str(qty * 20 + spares)

    def update_existing(
        item_id: str, *, manufacturer: str, mpn: str, package: str,
        status: str, notes: str, refdes: str | None = None,
        description: str | None = None, qty: int | None = None,
        spares: int | None = None, value: str | None = None,
    ) -> None:
        require(item_id in by_id, f"draft BOM item missing: {item_id}")
        row = by_id[item_id]
        row["Manufacturer"] = manufacturer
        row["MPN"] = mpn
        row["Package"] = package
        row["Status"] = status
        row["Notes"] = notes
        if refdes is not None:
            row["RefDes"] = refdes
        if description is not None:
            row["Description"] = description
        if value is not None:
            row["Value"] = value
        if qty is not None:
            set_quantities(row, qty, int(row["Spares"] if spares is None else spares))

    for item_id, ref in {
        "U1": "U1", "U2": "U2", "U3": "U3", "U4": "U4", "U7": "U7",
        "U8": "U8", "U9": "U9", "U10": "U10", "U11": "U11", "U13": "U13", "X1": "X1",
    }.items():
        part = main_parts[ref]
        update_existing(
            item_id,
            manufacturer=part["Manufacturer"],
            mpn=part["MPN"],
            package=part["Package_or_Module"],
            status=part["Status"],
            notes=f"Rev.A freeze source MAIN_COMPONENT_FREEZE_REV_A.csv; blockers: {part['Release_Blockers']}",
        )

    require(main_parts["U14"]["MPN"] == main_parts["U15"]["MPN"], "SIM ESD MPNs differ")
    part14 = main_parts["U14"]
    update_existing(
        "U14-U15",
        manufacturer=part14["Manufacturer"], mpn=part14["MPN"], package=part14["Package_or_Module"],
        status="SELECTED_PENDING_SIM_REVIEW",
        notes="Two identical low-capacitance SIM ESD arrays; Rev.A freeze source MAIN_COMPONENT_FREEZE_REV_A.csv",
    )

    for item_id, comp_id, refdes in (
        ("PWR-REV-CTL", "PWR-REV-CTL", "U1"),
        ("PWR-REV-FET", "PWR-REV-FET", "Q1"),
        ("U-MON-01", "U-MON-01", "U2"),
        ("U-PWR1", "U-PWR1", "U3"),
        ("U-PWR2", "U-PWR2", "U4"),
        ("U-PWR3", "U-PWR3", "U5"),
        ("PWR-TVS-01", "PWR-TVS-01", "D1"),
        ("PWR-FUSE-01", "PWR-FUSE-01", "F1"),
    ):
        part = power_parts[comp_id]
        update_existing(
            item_id,
            manufacturer=part["Manufacturer"], mpn=part["MPN"], package=part["Package"],
            status=part["Status"], refdes=refdes,
            notes=f"Rev.A freeze source POWER_COMPONENT_FREEZE_REV_A.csv; {part['Electrical_Baseline']}; blockers: {part['Release_Blockers']}",
        )

    update_existing(
        "R-SHUNT-01", manufacturer="Vishay Dale", mpn="WSK2512R0100FEA",
        package="WSK2512 4-terminal 6432 metric", status="SELECTED_PENDING_KELVIN_LAYOUT_SAMPLE",
        refdes="RSH1", value="10 mOhm 1% 1 W",
        notes="10 mOhm, 1%, 1 W, four-terminal current-sense resistor; exact land pattern and Kelvin layout remain Review B blockers",
    )

    mic = connectors["CON-MIC"]
    require(mic["Positions"] == "6", "Rev.A MIC connector must be 6 positions")
    update_existing(
        "J-MIC", manufacturer="Molex", mpn=mic["Board_MPN"].removeprefix("Molex_"),
        package="Pico-Lock 1.50 mm 6-circuit right-angle SMT", status=mic["Status"],
        refdes="PCB-MIC:J1 x4", description="6-position microphone leaf board header",
        qty=4, spares=12,
        notes=(
            f"Mating housing {mic['Mating_Housing_MPN'].removeprefix('Molex_')}; "
            f"terminal {mic['Terminal_MPN'].removeprefix('Molex_')}; "
            "pinout 1V8/GND/CLK/DATA/WAKE/AAD_CFG(THSEL); -40..105 C"
        ),
    )

    for item_id, cid in {"J-SIM1": "CON-SIM1", "J-SIM2": "CON-SIM2"}.items():
        connector = connectors[cid]
        update_existing(
            item_id, manufacturer="TE Connectivity", mpn=connector["Board_MPN"].removeprefix("TE_"),
            package="Nano-SIM 4FF connector with DET", status=connector["Status"],
            notes=f"Rev.A connector freeze; blockers: {connector['Release_Blockers']}",
        )

    for item_id, cid in {
        "J-RF-CELL": "CON-RF-CELL", "J-RF-GNSS": "CON-RF-GNSS", "J-RF-LORA": "CON-RF-LORA"
    }.items():
        connector = connectors[cid]
        update_existing(
            item_id, manufacturer="Hirose", mpn="U.FL-R-SMT-1(60)", package="U.FL SMT receptacle",
            status=connector["Status"],
            notes=f"Rev.A connector freeze; exact coax assembly temperature/RF validation remains blocking: {connector['Release_Blockers']}",
        )

    def append_item(
        *, item_id: str, assembly: str, refdes: str, category: str, description: str,
        manufacturer: str, mpn: str, package: str, qty: int, spares: int,
        status: str, notes: str, variant: str = "COMMON",
        source_policy: str = "Authorized or traceable tier-1 channel",
        incoming_control: str = "Marking MPN package orientation electrical functional sample",
        value: str = "", line_class: str = "", population: str = "",
        temperature: str = "", disposition: str = "",
    ) -> None:
        if item_id in by_id:
            return
        row = {field: "" for field in fields}
        row.update({
            "Item_ID": item_id, "Assembly": assembly, "RefDes": refdes, "Category": category,
            "Description": description, "Manufacturer": manufacturer, "MPN": mpn, "Package": package,
            "Value": value,
            "Qty_per_station": str(qty), "Qty_20": str(qty * 20), "Spares": str(spares),
            "Procure_qty": str(qty * 20 + spares), "Variant": variant, "Status": status,
            "China_source_policy": source_policy, "Incoming_control": incoming_control,
            "Notes": notes, "Line_class": line_class, "Population": population,
            "Temperature_C": temperature, "BOM_disposition": disposition,
        })
        rows.append(row)
        by_id[item_id] = row

    for ref in ("U16", "U17", "U18"):
        part = main_parts[ref]
        append_item(
            item_id=ref, assembly="PCB-MAIN", refdes=ref, category="Logic",
            description=part["Function"], manufacturer=part["Manufacturer"], mpn=part["MPN"],
            package=part["Package_or_Module"], qty=1, spares=5, status=part["Status"],
            notes=f"Rev.A MAIN freeze; blockers: {part['Release_Blockers']}",
        )

    for item_id, cid, assembly, refdes in (
        ("J-USB", "CON-USB", "PCB-MAIN", "J_USB"),
        ("J-PWR-IN", "CON-003", "PCB-PWR", "J1"),
        ("J-PWR-PWR", "CON-004A", "PCB-PWR", "J2"),
        ("J-PWR-MAIN", "CON-004B", "PCB-MAIN", "J_PWR"),
    ):
        connector = connectors[cid]
        manufacturer = "Molex" if connector["Board_MPN"].startswith("Molex_") else "GCT"
        kwargs = dict(
            manufacturer=manufacturer,
            mpn=connector["Board_MPN"].split("_", 1)[1] if "_" in connector["Board_MPN"] else connector["Board_MPN"],
            package=f"{connector['Positions']} positions", status=connector["Status"],
            notes=f"Mating {connector['Mating_Housing_MPN']}; terminal {connector['Terminal_MPN']}; blockers: {connector['Release_Blockers']}",
        )
        if item_id in by_id:
            update_existing(
                item_id, refdes=refdes, description=connector["Function"],
                qty=1, spares=5, **kwargs,
            )
        else:
            append_item(
                item_id=item_id, assembly=assembly, refdes=refdes, category="Connector",
                description=connector["Function"], qty=1, spares=5, **kwargs,
            )

    append_item(
        item_id="J-MIC-MAIN", assembly="PCB-MAIN", refdes="J_MIC1;J_MIC2;J_MIC3;J_MIC4",
        category="Connector", description="Four 6-position microphone MAIN board headers",
        manufacturer="Molex", mpn="5040500691",
        package="Pico-Lock 1.50 mm 6-circuit right-angle SMT", qty=4, spares=12,
        status=mic["Status"], notes="MAIN-side mates of four PCB-MIC harnesses; same header MPN and pin order as every leaf",
    )
    append_item(
        item_id="H-MIC", assembly="HARNESS-MIC",
        refdes="H_MIC1:A/B;H_MIC2:A/B;H_MIC3:A/B;H_MIC4:A/B",
        category="Housing", description="Pico-Lock 6-position cable housings, two per MIC harness",
        manufacturer="Molex", mpn="5040510601", package="Pico-Lock 1.50 mm 6-circuit housing",
        qty=8, spares=16, status="SELECTED_PENDING_HARNESS_LENGTH_PULL_TEST",
        notes="Two housings per cable x four cables; keyed to 5040500691 board headers",
    )
    append_item(
        item_id="T-MIC", assembly="HARNESS-MIC", refdes="H_MIC1..H_MIC4 contacts",
        category="Terminal", description="Pico-Lock crimp terminals, twelve per MIC harness",
        manufacturer="Molex", mpn="5040520098", package="Pico-Lock crimp terminal 28-24 AWG",
        qty=48, spares=48, status="SELECTED_PENDING_CRIMP_PULL_TEST",
        notes="6 contacts x 2 ends x 4 harnesses; procurement includes one-station terminal spare set",
    )
    append_item(
        item_id="H-PWR-MAIN", assembly="HARNESS-PWR-MAIN", refdes="H_PWR_MAIN:A/B",
        category="Housing", description="Micro-Fit 3.0 12-position cable housings, two per MAIN-PWR harness",
        manufacturer="Molex", mpn="43025-1200", package="Micro-Fit 3.0 12-circuit housing",
        qty=2, spares=4, status="SELECTED_PENDING_MECHANICS_I2C_TEST",
        notes="One housing at PCB-MAIN and one at PCB-PWR",
    )
    append_item(
        item_id="T-PWR-MAIN-PWR", assembly="HARNESS-PWR-MAIN", refdes="H_PWR_MAIN power contacts",
        category="Terminal", description="Micro-Fit crimp terminals for six power/ground conductors at both ends",
        manufacturer="Molex", mpn="43030-0038", package="Micro-Fit female crimp terminal 18 AWG class",
        qty=12, spares=12, status="SELECTED_PENDING_CURRENT_PULL_TEST",
        notes="Pins 1-6 x two cable ends; final wire construction must match approved terminal range",
    )
    append_item(
        item_id="T-PWR-MAIN-CTL", assembly="HARNESS-PWR-MAIN", refdes="H_PWR_MAIN control contacts",
        category="Terminal", description="Micro-Fit crimp terminals for six control/I2C conductors at both ends",
        manufacturer="Molex", mpn="43030-0001", package="Micro-Fit female crimp terminal 20-24 AWG class",
        qty=12, spares=12, status="SELECTED_PENDING_I2C_PULL_TEST",
        notes="Pins 7-12 x two cable ends; includes I2C2 SCL/SDA on pins 11/12",
    )

    update_existing(
        "C-MIC", manufacturer="TDK", mpn="CGA2B3X7R1E104K050BB",
        package="0402 1005 metric", status="SELECTED_PENDING_SAMPLE",
        refdes="PCB-MIC:C1 x4", description="100 nF 25 V X7R microphone VDD decoupling",
        qty=4, spares=40, value="100 nF 25 V X7R",
        notes="One C1 per PCB-MIC leaf; exact native schematic reference and automotive-grade MLCC",
    )
    append_item(
        item_id="R-MIC", assembly="PCB-MIC", refdes="PCB-MIC:R1 x4", category="Passive",
        description="0 ohm PDM DATA source-termination/tuning link", manufacturer="Panasonic Industry",
        mpn="ERJ-2GE0R00X", package="0402 1005 metric", qty=4, spares=40,
        status="SELECTED_POPULATED_BASELINE_PENDING_SI", value="0 ohm",
        notes="One populated R1 per PCB-MIC leaf; any DNP/value change requires SI review and BOM revision",
    )

    pwr_lines = [
        ("PWR-C-100N", "C1;C2;C4;C6", "100 nF 25 V X7R", "TDK", "CGA2B3X7R1E104K050BB", "0402", 4, "FITTED"),
        ("PWR-C-LDO", "C7;C8", "2.2 uF 10 V X7R", "TDK", "CGA3E1X7R1A225K080AC", "0603", 2, "FITTED"),
        ("PWR-C-CIN-HF", "C9", "100 nF 50 V X7R", "TDK", "CGA3E2X7R1H104K080AA", "0603", 1, "FITTED"),
        ("PWR-C-INPUT", "C10;C11;C12", "4.7 uF 50 V X7R", "TDK", "CGA6P3X7R1H475K250AB", "1210", 3, "FITTED"),
        ("PWR-C-BULK", "C13", "100 uF 35 V hybrid", "Panasonic Industry", "EEH-ZK1V101XP", "SMD can 6.3x8.0 mm", 1, "FITTED"),
        ("PWR-COUT-3V8", "C3 bank", "22 uF 25 V X7R", "TDK", "CGA6P3X7R1E226M250AB", "1210", 4, "FITTED"),
        ("PWR-COUT-3V3", "C5 bank", "22 uF 25 V X7R", "TDK", "CGA6P3X7R1E226M250AB", "1210", 4, "FITTED"),
        ("PWR-L", "L1;L2", "4.7 uH +/-20%", "Coilcraft", "XAL7030-472MEC", "XAL7030 7.5x7.2 mm", 2, "FITTED"),
        ("PWR-R-100K-01", "R1", "100 kOhm 0.1%", "Panasonic Industry", "ERA-2AEB104X", "0402", 1, "FITTED"),
        ("PWR-R-35K7", "R2", "35.7 kOhm 0.1%", "Panasonic Industry", "ERA-2AEB3572X", "0402", 1, "FITTED"),
        ("PWR-R-86K6", "R3;R7", "86.6 kOhm 0.1%", "Panasonic Industry", "ERA-2AEB8662X", "0402", 2, "FITTED"),
        ("PWR-R-0R", "R4;R8", "0 ohm", "Panasonic Industry", "ERJ-2GE0R00X", "0402", 2, "FITTED"),
        ("PWR-R-0R-DNP", "R5;R9", "0 ohm", "Panasonic Industry", "ERJ-2GE0R00X", "0402", 0, "DNP"),
        ("PWR-R-100K", "R6;R11", "100 kOhm 1%", "Panasonic Industry", "ERJ-2RKF1003X", "0402", 2, "FITTED"),
        ("PWR-R-10K", "R10;R12", "10 kOhm 1%", "Panasonic Industry", "ERJ-2RKF1002X", "0402", 2, "FITTED"),
        ("PWR-R-4K7-DNP", "R13;R14", "4.7 kOhm 1%", "Panasonic Industry", "ERJ-2RKF4701X", "0402", 0, "DNP"),
        ("PWR-R-10K-DNP", "R15", "10 kOhm 1%", "Panasonic Industry", "ERJ-2RKF1002X", "0402", 0, "DNP"),
        ("PWR-NET-TIE", "NT1;NT2;NT3", "2-pad copper net tie", "PCB fabrication", "NET_TIE_COPPER_REV_A", "NetTie-2 SMD pad 0.5 mm", 3, "PCB_FEATURE"),
    ]
    for item_id, refdes, value, manufacturer, mpn, package, qty, population in pwr_lines:
        selected = population != "DNP"
        if population in {"DNP", "PCB_FEATURE"}:
            spares = 0
        elif item_id == "PWR-L":
            spares = 10
        else:
            spares = 40
        append_item(
            item_id=item_id, assembly="PCB-PWR", refdes=refdes,
            category="PCB feature" if item_id == "PWR-NET-TIE" else "Passive",
            description=f"PCB-PWR {value}", manufacturer=manufacturer, mpn=mpn, package=package,
            qty=qty, spares=spares,
            status="SELECTED_PENDING_NATIVE_FOOTPRINT_DERATING",
            notes="Exact candidate identity frozen for BOM control; native footprint, DC-bias/thermal margin and Review B remain blocking",
            value=value, population=population,
            line_class="PCB_FEATURE" if population == "PCB_FEATURE" else "ELECTRICAL_COMPONENT",
            temperature="N/A" if population == "PCB_FEATURE" else "-55..125",
            disposition="CONTROLLED_PENDING_VERIFICATION" if selected else "CONTROLLED_DNP",
        )

    full_text = "\n".join(",".join(row.get(field, "") for field in fields) for row in rows)
    for forbidden in ("ESP32-C3", "JST_BM05B", "GHR-05V-S", "5040500591", "5040510501"):
        require(forbidden not in full_text, f"superseded token remains in generated BOM: {forbidden}")
    require(by_id["J-MIC"]["MPN"] == "5040500691", "generated 6-pin MIC connector MPN mismatch")
    require("AAD_CFG" in by_id["J-MIC"]["Notes"], "generated MIC connector BOM line omits THSEL/AAD_CFG")
    for key in ("U16", "U17", "U18", "PWR-REV-CTL", "PWR-REV-FET", "J-MIC-MAIN", "H-MIC", "T-MIC"):
        require(key in by_id, f"generated BOM missing {key}")

    expected_refdes = {
        "PWR-REV-CTL": "U1", "PWR-REV-FET": "Q1", "U-MON-01": "U2",
        "U-PWR1": "U3", "U-PWR2": "U4", "U-PWR3": "U5",
        "R-SHUNT-01": "RSH1", "PWR-TVS-01": "D1", "PWR-FUSE-01": "F1",
        "J-PWR-IN": "J1", "J-PWR-PWR": "J2",
    }
    for item_id, refdes in expected_refdes.items():
        require(by_id[item_id]["RefDes"] == refdes, f"{item_id} native PCB-PWR RefDes mismatch")

    for row in rows:
        qty = int(row["Qty_per_station"])
        qty20 = int(row["Qty_20"])
        spares = int(row["Spares"])
        procure = int(row["Procure_qty"])
        require(qty20 == qty * 20, f"{row['Item_ID']}: Qty_20 formula mismatch")
        require(procure == qty20 + spares, f"{row['Item_ID']}: Procure_qty formula mismatch")
    require(by_id["J-MIC"]["Qty_per_station"] == "4", "leaf MIC header quantity mismatch")
    require(by_id["J-MIC-MAIN"]["Qty_per_station"] == "4", "MAIN MIC header quantity mismatch")
    require(by_id["H-MIC"]["Qty_per_station"] == "8", "MIC housing quantity must be 8 per station")
    require(by_id["T-MIC"]["Qty_per_station"] == "48", "MIC terminal quantity must be 48 per station")

    main_temp = {part["MPN"]: part["Temperature_C"] for part in main_parts.values()}
    power_temp = {part["MPN"]: part["Temperature_C"] for part in power_parts.values()}
    connector_temp = {
        connector["Board_MPN"].split("_", 1)[-1]: connector["Temperature_C"]
        for connector in connectors.values() if connector["Board_MPN"] not in ("", "TEST_PADS")
    }
    known_temp = {
        "WSK2512R0100FEA": "-65..170",
        "CGA2B3X7R1E104K050BB": "-55..125",
        "ERJ-2GE0R00X": "-55..155",
        "5040510601": "-40..105",
        "5040520098": "-40..105",
        "43025-1200": "-40..105",
        "43030-0038": "-40..105",
        "43030-0001": "-40..105",
    }
    known_temp.update(main_temp)
    known_temp.update(power_temp)
    known_temp.update(connector_temp)

    service_ids = {"ASM-MAIN", "ASM-PWR", "ASM-MIC"}
    pcb_ids = {"PCB-MAIN", "PCB-PWR", "PCB-MIC"}
    system_ids = {"BAT1", "PV1", "MPPT1", "ANT-CELL", "ANT-GNSS", "ANT-LORA", "HARNESS"}
    for row in rows:
        item_id = row["Item_ID"]
        if row["Line_class"] and row["Population"] and row["Temperature_C"] and row["BOM_disposition"]:
            continue
        if item_id in service_ids:
            row["Line_class"], row["Population"], row["Temperature_C"] = "PCBA_SERVICE", "N/A", "N/A"
        elif item_id in pcb_ids:
            row["Line_class"], row["Population"], row["Temperature_C"] = "BARE_PCB", "N/A", "N/A"
        elif item_id.startswith("HSG-"):
            row["Line_class"], row["Population"], row["Temperature_C"] = "MECHANICAL_OPTION", "N/A", "OPEN"
        elif item_id in system_ids:
            row["Line_class"], row["Population"], row["Temperature_C"] = "SYSTEM_ITEM", "FITTED", "OPEN"
        elif row["Assembly"].startswith("HARNESS-"):
            row["Line_class"], row["Population"] = "HARNESS_COMPONENT", "FITTED"
            row["Temperature_C"] = known_temp.get(row["MPN"], "OPEN")
        else:
            row["Line_class"], row["Population"] = "ELECTRICAL_COMPONENT", "FITTED"
            row["Temperature_C"] = known_temp.get(row["MPN"], "OPEN")

        status = row["Status"]
        exact_identity = row["Manufacturer"] not in ("", "TBD") and row["MPN"] not in ("", "TBD")
        if row["Line_class"] in {"PCBA_SERVICE", "BARE_PCB"}:
            row["BOM_disposition"] = "BLOCKED_SUPPLIER_RELEASE" if status == "RFQ_REQUIRED" else "CONTROLLED"
        elif row["Line_class"] == "MECHANICAL_OPTION":
            row["BOM_disposition"] = "CONDITIONAL_NOT_RELEASED"
        elif not exact_identity or status.startswith(("OPEN", "RFQ_REQUIRED", "SOURCE_PACKAGE_REQUIRED")):
            row["BOM_disposition"] = "BLOCKED_SELECTION"
        elif status.startswith("CANDIDATE") or "REGION_OPERATOR" in status:
            row["BOM_disposition"] = "BLOCKED_ENGINEERING_SELECTION"
        elif row["Temperature_C"] in ("", "OPEN", "TBD") or "TEMP_VERIFY" in status:
            row["BOM_disposition"] = "BLOCKED_RATING_VERIFICATION"
        elif "PENDING" in status or status.startswith("TECHNICALLY_SELECTED"):
            row["BOM_disposition"] = "CONTROLLED_PENDING_VERIFICATION"
        else:
            row["BOM_disposition"] = "CONTROLLED"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {OUT.relative_to(ROOT)} with {len(rows)} rows")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate the controlled EVT-PRE-20 Rev.A BOM from authoritative freezes.

The draft keeps the system-level inventory. MAIN/POWER/CONNECTOR freeze tables and the
PCB-PWR passive authority are authoritative for selected MPNs and release blockers.
This script deterministically merges them, fixes assembly reference/quantity mappings,
expands connector consumables, and fails on known superseded parts. It is a controlled
engineering BOM, not a release waiver: open and candidate rows remain visible until
the strict BOM gates can pass.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "hardware/EVT_PRE_20_BOM_DRAFT.csv"
OUT = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
MAIN_PASSIVE_SUPPORT = ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv"
PWR_PASSIVE_AUTHORITY = ROOT / "hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv"


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
    main_passive_support = freeze_map(
        "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv", "RefDes"
    )
    pwr_passive_authority = read_csv(PWR_PASSIVE_AUTHORITY)

    def set_quantities(row: dict[str, str], qty: int, spares: int) -> None:
        row["Qty_per_station"] = str(qty)
        row["Qty_20"] = str(qty * 20)
        row["Spares"] = str(spares)
        row["Procure_qty"] = str(qty * 20 + spares)

    def update_existing(item_id: str, *, manufacturer: str, mpn: str, package: str,
                        status: str, notes: str, refdes: str | None = None,
                        description: str | None = None, qty: int | None = None,
                        spares: int | None = None, value: str | None = None) -> None:
        require(item_id in by_id, f"draft BOM item missing: {item_id}")
        r = by_id[item_id]
        r["Manufacturer"] = manufacturer
        r["MPN"] = mpn
        r["Package"] = package
        r["Status"] = status
        r["Notes"] = notes
        if refdes is not None:
            r["RefDes"] = refdes
        if description is not None:
            r["Description"] = description
        if value is not None:
            r["Value"] = value
        if qty is not None:
            set_quantities(r, qty, int(r["Spares"] if spares is None else spares))

    for item_id, ref in {
        "U1": "U1", "U2": "U2", "U3": "U3", "U4": "U4", "U7": "U7",
        "U8": "U8", "U9": "U9", "U10": "U10", "U11": "U11", "U12": "U12", "U13": "U13", "X1": "X1",
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
        status=p14["Status"],
        notes="Two identical five-line SIM ESD arrays; exact maps in PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv",
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
        p = power_parts[comp_id]
        update_existing(
            item_id,
            manufacturer=p["Manufacturer"], mpn=p["MPN"], package=p["Package"], status=p["Status"],
            refdes=refdes,
            notes=f"Rev.A freeze source POWER_COMPONENT_FREEZE_REV_A.csv; {p['Electrical_Baseline']}; blockers: {p['Release_Blockers']}",
        )

    shunt = power_parts["R-SHUNT-01"]
    update_existing(
        "R-SHUNT-01", manufacturer=shunt["Manufacturer"], mpn=shunt["MPN"],
        package=shunt["Package"], status=shunt["Status"],
        refdes="RSH1", value="10 mOhm 1% 1 W",
        notes=("Rev.A freeze source POWER_COMPONENT_FREEZE_REV_A.csv; exact four-terminal "
               f"land pattern controlled; blockers: {shunt['Release_Blockers']}"),
    )

    mic = connectors["CON-MIC"]
    require(mic["Positions"] == "6", "Rev.A MIC connector must be 6 positions")
    update_existing(
        "J-MIC", manufacturer="Molex", mpn=mic["Board_MPN"].removeprefix("Molex_"),
        package="Pico-Lock 1.50 mm 6-circuit right-angle SMT", status=mic["Status"],
        refdes="PCB-MIC:J1 x4", description="6-position microphone leaf board header",
        qty=4, spares=12,
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

    for item_id, cid, refdes, manufacturer, package in (
        ("J-SD1", "CON-SD", "J12", "GCT", "microSD push-push SMT 1.95 mm with detect"),
        ("J-TAMPER", "CON-TAMPER", "J13", "Molex", "Pico-Lock 1.50 mm 2-circuit right-angle SMT"),
    ):
        c = connectors[cid]
        update_existing(
            item_id, manufacturer=manufacturer,
            mpn=c["Board_MPN"].split("_", 1)[1] if "_" in c["Board_MPN"] else c["Board_MPN"],
            package=package, status=c["Status"], refdes=refdes,
            notes=f"Rev.A connector freeze; exact electrical map in PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv; blockers: {c['Release_Blockers']}",
        )

    for item_id, cid in {"J-RF-CELL": "CON-RF-CELL", "J-RF-GNSS": "CON-RF-GNSS", "J-RF-LORA": "CON-RF-LORA"}.items():
        c = connectors[cid]
        update_existing(
            item_id, manufacturer="Hirose", mpn="U.FL-R-SMT-1(60)", package="U.FL SMT receptacle",
            status=c["Status"], notes=f"Rev.A connector freeze; exact coax assembly temperature/RF validation remains blocking: {c['Release_Blockers']}",
        )

    def append_item(*, item_id: str, assembly: str, refdes: str, category: str, description: str,
                    manufacturer: str, mpn: str, package: str, qty: int, spares: int,
                    status: str, notes: str, variant: str = "COMMON",
                    source_policy: str = "Authorized or traceable tier-1 channel",
                    incoming_control: str = "Marking MPN package orientation electrical functional sample",
                    value: str = "", line_class: str = "", population: str = "",
                    temperature: str = "", disposition: str = "") -> None:
        if item_id in by_id:
            return
        row = {field: "" for field in fields}
        row.update({
            "Item_ID": item_id, "Assembly": assembly, "RefDes": refdes, "Category": category,
            "Description": description, "Manufacturer": manufacturer, "MPN": mpn, "Package": package,
            "Value": value,
            "Qty_per_station": str(qty), "Qty_20": str(qty * 20), "Spares": str(spares),
            "Procure_qty": str(qty * 20 + spares), "Variant": variant, "Status": status,
            "China_source_policy": source_policy,
            "Incoming_control": incoming_control,
            "Notes": notes,
            "Line_class": line_class, "Population": population,
            "Temperature_C": temperature, "BOM_disposition": disposition,
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

    for item_id, ref in (
        ("Q-MODEM-PWRKEY", "Q1"),
        ("Q-MODEM-RESET", "Q2"),
        ("Q-SIM-MUX-EN", "Q3"),
    ):
        p = main_parts[ref]
        append_item(
            item_id=item_id, assembly="PCB-MAIN", refdes=ref, category="Transistor",
            description=p["Function"], manufacturer=p["Manufacturer"], mpn=p["MPN"],
            package=p["Package_or_Module"], qty=1, spares=5, status=p["Status"],
            notes=f"Rev.A MAIN freeze; blockers: {p['Release_Blockers']}",
        )

    # MAIN-AUTH-010 is normalized one physical PCB-MAIN component per line so the
    # controlled BOM can be compared directly with future schematic-derived RefDes.
    x1_support = main_passive_support["X1"]
    require(by_id["X1"]["MPN"] == x1_support["MPN"], "X1 authority MPN divergence")
    by_id["X1"].update({
        "Value": x1_support["Value"],
        "Line_class": "ELECTRICAL_COMPONENT",
        "Population": x1_support["Population"],
        "Temperature_C": x1_support["Temperature_C"],
        "BOM_disposition": "CONTROLLED_PENDING_VERIFICATION",
    })
    by_id["X1"]["Notes"] += (
        "; complete physical pins and no-external-bypass decision in "
        "PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv; physical pins: "
        f"{x1_support['Pin_Map']}"
    )

    for refdes, part in main_passive_support.items():
        if refdes == "X1":
            continue
        fitted = part["Population"] == "FITTED"
        append_item(
            item_id=f"MAIN-010-{refdes}", assembly="PCB-MAIN", refdes=refdes,
            category=part["Category"], description=part["Electrical_Path"],
            manufacturer=part["Manufacturer"], mpn=part["MPN"], package=part["Package"],
            qty=1 if fitted else 0, spares=0,
            status="SELECTED_PENDING_REVIEW_A" if fitted else "CONTROLLED_DNP",
            notes=("MAIN-AUTH-010 exact capture authority; physical pins: "
                   f"{part['Pin_Map']}; {part['Notes']}"),
            value=part["Value"], line_class="ELECTRICAL_COMPONENT",
            population=part["Population"], temperature=part["Temperature_C"],
            disposition="CONTROLLED_PENDING_VERIFICATION" if fitted else "CONTROLLED_DNP",
        )

    for item_id, cid, assembly, refdes in (
        ("J-USB", "CON-USB", "PCB-MAIN", "J11"),
        ("J-PWR-IN", "CON-003", "PCB-PWR", "J1"),
        ("J-PWR-PWR", "CON-004A", "PCB-PWR", "J2"),
        ("J-PWR-MAIN", "CON-004B", "PCB-MAIN", "J_PWR"),
    ):
        c = connectors[cid]
        manufacturer = "Molex" if c["Board_MPN"].startswith("Molex_") else "GCT"
        kwargs = dict(
            manufacturer=manufacturer,
            mpn=c["Board_MPN"].split("_", 1)[1] if "_" in c["Board_MPN"] else c["Board_MPN"],
            package=f"{c['Positions']} positions", status=c["Status"],
            notes=f"Mating {c['Mating_Housing_MPN']}; terminal {c['Terminal_MPN']}; blockers: {c['Release_Blockers']}",
        )
        if item_id in by_id:
            update_existing(item_id, refdes=refdes, description=c["Function"], qty=1, spares=5, **kwargs)
        else:
            append_item(
                item_id=item_id, assembly=assembly, refdes=refdes, category="Connector",
                description=c["Function"], qty=1, spares=5, **kwargs,
            )

    # One connector is fitted on each end of each of the four MIC harnesses. The old
    # aggregate line counted only the leaf-board ends and under-reported board headers,
    # housings and crimp terminals.
    append_item(
        item_id="J-MIC-MAIN", assembly="PCB-MAIN", refdes="J_MIC1;J_MIC2;J_MIC3;J_MIC4",
        category="Connector", description="Four 6-position microphone MAIN board headers",
        manufacturer="Molex", mpn="5040500691",
        package="Pico-Lock 1.50 mm 6-circuit right-angle SMT", qty=4, spares=12,
        status=mic["Status"], notes="MAIN-side mates of four PCB-MIC harnesses; same header MPN and pin order as every leaf",
    )
    append_item(
        item_id="H-MIC", assembly="HARNESS-MIC", refdes="H_MIC1:A/B;H_MIC2:A/B;H_MIC3:A/B;H_MIC4:A/B",
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

    # PCB-MIC native schematic contains exactly C1 and R1 per leaf.
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
        status="SELECTED_POPULATED_BASELINE_PENDING_SI",
        notes="One populated R1 per PCB-MIC leaf; any DNP/value change requires SI review and BOM revision", value="0 ohm",
    )

    # PCB-PWR passives come only from the per-reference authority. This prevents the
    # generated BOM from silently outrunning schematic MPN, population or footprint
    # control. DFT rows have no BOM_Item_ID and remain non-procured board features.
    pwr_groups: dict[str, list[dict[str, str]]] = {}
    for part in pwr_passive_authority:
        item_id = part["BOM_Item_ID"]
        if item_id:
            pwr_groups.setdefault(item_id, []).append(part)
    require(len(pwr_groups) == 17, "PCB-PWR passive authority group count drift")
    for item_id, members in pwr_groups.items():
        first = members[0]
        invariant_fields = {
            "Category", "Manufacturer", "MPN", "Package", "Value", "Population",
            "Temperature_C", "Footprint",
        }
        for field in invariant_fields:
            require(len({member[field] for member in members}) == 1,
                    f"{item_id}: passive authority group {field} mismatch")
        refdes = ";".join(member["RefDes"] for member in members)
        population = first["Population"]
        qty = 0 if population == "DNP" else len(members)
        spares = 0 if population in {"DNP", "PCB_FEATURE"} else 40
        selected = population != "DNP"
        statuses = sorted({member["Authority_Status"] for member in members})
        status = statuses[0] if len(statuses) == 1 else "CONTROLLED_CANDIDATE_PENDING_MULTIPLE_REVIEWS"
        release_blockers = sorted({member["Release_Blockers"] for member in members})
        notes = (
            f"Rev.A source PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv; footprint {first['Footprint']}; "
            f"blockers: {'; '.join(release_blockers)}"
        )
        append_item(
            item_id=item_id, assembly="PCB-PWR", refdes=refdes, category=first["Category"],
            description=f"PCB-PWR {first['Value']}", manufacturer=first["Manufacturer"],
            mpn=first["MPN"], package=first["Package"],
            qty=qty, spares=spares, status=status, notes=notes,
            value=first["Value"], population=population,
            line_class="PCB_FEATURE" if population == "PCB_FEATURE" else "ELECTRICAL_COMPONENT",
            temperature=first["Temperature_C"],
            disposition="CONTROLLED_PENDING_VERIFICATION" if selected else "CONTROLLED_DNP",
        )

    pwr_l = power_parts["PWR-L"]
    append_item(
        item_id="PWR-L", assembly="PCB-PWR", refdes="L1;L2", category="Passive",
        description="PCB-PWR 4.7 uH +/-20%", manufacturer=pwr_l["Manufacturer"],
        mpn=pwr_l["MPN"], package=pwr_l["Package"], qty=2, spares=10,
        status=pwr_l["Status"],
        notes=("Rev.A freeze source POWER_COMPONENT_FREEZE_REV_A.csv; exact land pattern "
               f"controlled; blockers: {pwr_l['Release_Blockers']}"),
        value="4.7 uH +/-20%", population="FITTED", line_class="ELECTRICAL_COMPONENT",
        temperature=pwr_l["Temperature_C"], disposition="CONTROLLED_PENDING_VERIFICATION",
    )

    full_text = "\n".join(",".join(r.get(f, "") for f in fields) for r in rows)
    for forbidden in ("ESP32-C3", "JST_BM05B", "GHR-05V-S", "5040500591", "5040510501"):
        require(forbidden not in full_text, f"superseded token remains in generated BOM: {forbidden}")
    require(by_id["J-MIC"]["MPN"] == "5040500691", "generated 6-pin MIC connector MPN mismatch")
    require("AAD_CFG" in by_id["J-MIC"]["Notes"], "generated MIC connector BOM line omits THSEL/AAD_CFG")
    for key in ("U16", "U17", "U18", "PWR-REV-CTL", "PWR-REV-FET", "J-MIC-MAIN", "H-MIC", "T-MIC", "MAIN-010-C1", "MAIN-010-R103", "MAIN-010-D11"):
        require(key in by_id, f"generated BOM missing {key}")
    require(sum(item.startswith("MAIN-010-") for item in by_id) == 210,
            "generated BOM must contain 210 new MAIN-AUTH-010 physical lines plus existing X1")
    for refdes, part in main_passive_support.items():
        item_id = "X1" if refdes == "X1" else f"MAIN-010-{refdes}"
        row = by_id[item_id]
        require(row["RefDes"] == refdes and row["MPN"] == part["MPN"],
                f"{refdes}: MAIN-AUTH-010 BOM identity mismatch")
        require(row["Value"] == part["Value"] and row["Population"] == part["Population"],
                f"{refdes}: MAIN-AUTH-010 BOM value/population mismatch")

    expected_refdes = {
        "PWR-REV-CTL": "U1", "PWR-REV-FET": "Q1", "U-MON-01": "U2",
        "U-PWR1": "U3", "U-PWR2": "U4", "U-PWR3": "U5",
        "R-SHUNT-01": "RSH1", "PWR-TVS-01": "D1", "PWR-FUSE-01": "F1",
        "J-PWR-IN": "J1", "J-PWR-PWR": "J2",
    }
    for item_id, refdes in expected_refdes.items():
        require(by_id[item_id]["RefDes"] == refdes, f"{item_id} native PCB-PWR RefDes mismatch")

    for r in rows:
        qty = int(r["Qty_per_station"])
        qty20 = int(r["Qty_20"])
        spares = int(r["Spares"])
        procure = int(r["Procure_qty"])
        require(qty20 == qty * 20, f"{r['Item_ID']}: Qty_20 formula mismatch")
        require(procure == qty20 + spares, f"{r['Item_ID']}: Procure_qty formula mismatch")
    require(by_id["J-MIC"]["Qty_per_station"] == "4", "leaf MIC header quantity mismatch")
    require(by_id["J-MIC-MAIN"]["Qty_per_station"] == "4", "MAIN MIC header quantity mismatch")
    require(by_id["H-MIC"]["Qty_per_station"] == "8", "MIC housing quantity must be 8 per station")
    require(by_id["T-MIC"]["Qty_per_station"] == "48", "MIC terminal quantity must be 48 per station")

    main_temp = {p["MPN"]: p["Temperature_C"] for p in main_parts.values()}
    power_temp = {p["MPN"]: p["Temperature_C"] for p in power_parts.values()}
    connector_temp = {
        c["Board_MPN"].split("_", 1)[-1]: c["Temperature_C"]
        for c in connectors.values() if c["Board_MPN"] not in ("", "TEST_PADS")
    }
    known_temp = {
        "WSK2512R0100FEA": "-65..170",
        "CGA2B3X7R1E104K050BB": "-55..125",
        "ERJ-2GE0R00X": "-55..155",
        "MMICT5838-00-012": "-40..85",
        "U.FL-R-SMT-1(60)": "-40..90",
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
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {OUT.relative_to(ROOT)} with {len(rows)} rows")


if __name__ == "__main__":
    main()

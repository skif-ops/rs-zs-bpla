#!/usr/bin/env python3
"""Generate a budgetary price layer for the controlled EVT-PRE-20 BOM.

The exact MPN and quantity authorities remain in the procurement BOM.  This
supplement deliberately treats supplier choice as advisory and attaches a
rounded, landed-RUB planning price to every procurement row.  Published price
snapshots are used for the eight high-value system articles; remaining values
are conservative engineering estimates until a quotation replaces them.
"""
from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv"
OUT = ROOT / "hardware/EVT_PRE_20_BOM_PRICE_ESTIMATE_REV_A.csv"
CHECKED_ON = "2026-09-18"
LOTS = (4, 10, 20)


# Public unit prices observed on the check date.  Planning RUB values include a
# deliberately rounded FX/import/logistics allowance; VAT and destination
# delivery still require the final cart or quotation.
PUBLIC_PRICES = {
    "RB40": (60000, "$479.95", "USD", "PUBLIC_MANUFACTURER_PRICE",
             "https://relionbattery.com/products/lithium/rb40"),
    "SLP080S-12M": (22200, "$177.63", "USD", "PUBLIC_DISTRIBUTOR_PRICE",
                    "https://www.mrsolar.com/solarland-slp080-12m-80w-12v-skinny-solar-panel-w-pro-charge-jbox/"),
    "SCC075010060R": (8200, "$65.45", "USD", "PUBLIC_DISTRIBUTOR_PRICE",
                      "https://www.invertersupply.com/index.php?main_page=product_info&products_id=31070"),
    "SBS050150200": (4900, "$39.10", "USD", "PUBLIC_DISTRIBUTOR_PRICE",
                     "https://www.invertersupply.com/index.php?main_page=product_info&products_id=194069"),
    "G30.B.108111": (4050, "$32.38 at qty 10", "USD", "PUBLIC_AUTHORIZED_CHANNEL_PRICE",
                     "https://www.mouser.com/"),
    "AA.166.A.301111": (3300, "EUR 23.80 at qty 10", "EUR", "PUBLIC_AUTHORIZED_CHANNEL_PRICE",
                        "https://www.mouser.lu/en/ProductDetail/Taoglas/AA.166.A.301111?qs=MLItCLRbWsy9cGP7TTjqEA%3D%3D"),
    "TI.89.B.2111W": (1350, "EUR 9.673 at qty 10", "EUR", "PUBLIC_DISTRIBUTOR_PRICE",
                      "https://www.digikey.ee/"),
    "CAB.0243": (650, "$5.2068 at qty 50", "USD", "PUBLIC_AUTHORIZED_CHANNEL_PRICE",
                 "https://www.digikey.com/en/products/detail/taoglas-limited/CAB-0243/24770240"),
}


# Exact-MPN engineering estimates for the material cost drivers.  These are
# rounded planning values in RUB per piece, not supplier quotations.
MPN_ESTIMATES = {
    "0451008.MRL": 250,
    "2336582-1": 550,
    "43025-1200": 500,
    "43030-0001": 45,
    "43030-0038": 55,
    "430450213": 350,
    "430451202": 900,
    "5040500291": 250,
    "5040500691": 480,
    "5040510601": 180,
    "5040520098": 35,
    "ABSES5AF-L100KM": 550,
    "BG95-M3": 3500,
    "CSD18540Q5B": 450,
    "E22-900M22S": 1500,
    "EEH-ZK1V101XP": 120,
    "ESDALC6V1-5P6": 140,
    "INA226AIDGSR": 550,
    "LIS2DW12TR": 350,
    "LM74700QDBVRQ1": 600,
    "LMR604403SRAKR": 950,
    "LT6000IDCB#TRMPBF": 650,
    "MAX-M10S-00B": 2500,
    "MDBT50Q-P1MV2": 2200,
    "MEM2052-00-195-00-A": 550,
    "MMICT5838-00-012": 500,
    "SDCIT2/32GB": 2600,
    "SMBJ18A": 120,
    "SN74AXC1T45DRLR": 180,
    "SN74AXC8T245PWR": 600,
    "SN74LVC1G07DBVR": 100,
    "SN74LVC32APWR": 220,
    "STM32U585VIT6Q": 2500,
    "STTS22HTR": 250,
    "Si1016X-T1-GE3": 180,
    "SiT1552AI-JE-DCC-32.768D": 500,
    "T520D107M006ATE015": 300,
    "TPD1E05U06DYAR": 100,
    "TPD2EUSB30DRTR": 180,
    "TPD4E05U06DQAR": 250,
    "TPS7A2018PDBVR": 160,
    "TS3A27518EPWR": 550,
    "U.FL-R-SMT-1(60)": 250,
    "USB4105-GF-A-120": 650,
    "W25Q512JVFIQ": 800,
    "WSK2512R0100FEA": 450,
    "XAL7030-472MEC": 420,
}


ID_ESTIMATES = {
    "PR-001": 3500,   # PCB-MAIN assembly service, components excluded
    "PR-002": 700,    # PCB-MIC assembly service, components excluded
    "PR-003": 2800,   # PCB-PWR assembly service, components excluded
    "PR-004": 4500,   # complete labelled station harness set
    "PR-005": 12000,  # inactive printed housing fallback
    "PR-006": 250000, # inactive injection source/DFM package
    "PR-007": 18000,  # selected vacuum-cast housing set
    "PR-008": 2200,   # six-layer bare PCB at EVT quantity
    "PR-009": 350,    # two-layer MIC bare PCB
    "PR-010": 1600,   # four-layer heavy-copper PWR bare PCB
}


CATEGORY_ESTIMATES = {
    "Passive": 25,
    "Resistor": 12,
    "Capacitor": 30,
    "Ferrite_Bead": 45,
    "Inductor": 180,
    "Protection": 250,
    "ESD": 120,
    "ESD_Diode": 100,
    "ESD_Array": 220,
    "USB_ESD_Array": 180,
    "RF_ESD": 120,
    "Supply_TVS": 100,
    "Connector": 500,
    "RF connector": 250,
    "Terminal": 45,
    "Housing": 500,
    "SIM": 550,
    "SAW_Filter": 550,
    "Cellular": 3500,
    "LoRa": 1500,
    "Monitor": 550,
    "Motion": 350,
    "Power": 700,
    "Operational_Amplifier": 650,
    "GNSS": 2500,
    "BLE": 2200,
    "Transistor": 30,
    "Microphone": 500,
    "Storage": 2600,
    "Logic": 250,
    "Level translator | Logic": 600,
    "Open_Drain_Buffer": 100,
    "MCU": 2500,
    "Temperature": 250,
    "Dual_MOSFET": 180,
    "Clock": 500,
    "Memory": 800,
    "Shunt": 450,
    "PCB feature": 0,
}


FIELDS = [
    "Procurement_ID", "Manufacturer", "MPN", "Category",
    "Unit_price_RUB_estimate", "Price_basis", "Displayed_source_price",
    "Source_currency", "Source_URL", "Checked_on", "Estimate_confidence",
]
for lot in LOTS:
    FIELDS += [f"Procure_qty_{lot}", f"Line_cost_{lot}_RUB_estimate"]
FIELDS.append("Estimate_note")


def generate() -> str:
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        source_rows = list(csv.DictReader(stream))
    if not source_rows:
        raise RuntimeError("procurement BOM is empty")

    output_rows = []
    for row in source_rows:
        procurement_id = row["Procurement_ID"]
        mpn = row["MPN"]
        category = row["Category"]
        if mpn in PUBLIC_PRICES:
            unit, displayed, currency, basis, url = PUBLIC_PRICES[mpn]
            confidence = "MEDIUM"
            note = "Published price converted to a rounded landed-RUB planning value; final cart/quote controls."
        else:
            unit = ID_ESTIMATES.get(
                procurement_id,
                MPN_ESTIMATES.get(mpn, CATEGORY_ESTIMATES.get(category, 1000)),
            )
            displayed = ""
            currency = "RUB"
            basis = "ENGINEERING_BUDGETARY_ESTIMATE"
            url = ""
            confidence = "LOW"
            note = "Rounded engineering estimate pending supplier quotation."

        if procurement_id in {"PR-001", "PR-002", "PR-003"}:
            note = (
                "Primary full-PCBA procurement track; assembly and EOL service estimate "
                "excludes components and remains subject to the CM quotation."
            )
        elif procurement_id in {"PR-008", "PR-009", "PR-010"}:
            note = (
                "Alternative bare-PCB quotation track only; do not add to the selected "
                "full-PCBA purchase set."
            )

        out = {
            "Procurement_ID": procurement_id,
            "Manufacturer": row["Manufacturer"],
            "MPN": mpn,
            "Category": category,
            "Unit_price_RUB_estimate": str(unit),
            "Price_basis": basis,
            "Displayed_source_price": displayed,
            "Source_currency": currency,
            "Source_URL": url,
            "Checked_on": CHECKED_ON,
            "Estimate_confidence": confidence,
            "Estimate_note": note,
        }
        for lot in LOTS:
            qty = int(row[f"Procure_qty_{lot}"])
            out[f"Procure_qty_{lot}"] = str(qty)
            out[f"Line_cost_{lot}_RUB_estimate"] = str(qty * unit)
        output_rows.append(out)

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(output_rows)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = generate()
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"price estimate drift: run {Path(__file__).relative_to(ROOT)}")
        action = "Verified"
    else:
        OUT.write_text(text, encoding="utf-8")
        action = "Generated"

    rows = list(csv.DictReader(io.StringIO(text)))
    totals = {
        lot: sum(int(row[f"Line_cost_{lot}_RUB_estimate"]) for row in rows)
        for lot in LOTS
    }
    print(f"{action} {OUT.relative_to(ROOT)} with {len(rows)} priced procurement rows")
    print("; ".join(f"EVT-{lot}={totals[lot]:,} RUB" for lot in LOTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

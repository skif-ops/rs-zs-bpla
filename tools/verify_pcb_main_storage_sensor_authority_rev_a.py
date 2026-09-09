#!/usr/bin/env python3
"""Second independent control of PCB-MAIN U2/U3/U4 capture authority."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_STORAGE_SENSOR_PIN_AUTHORITY_REV_A.csv"
REVIEW = ROOT / "hardware/PCB_MAIN_STORAGE_SENSOR_AUTHORITY_REV_A.md"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
POWER_BASELINE = ROOT / "hardware/POWER_DESIGN_BASELINE_REV_A.json"
POWER_NETS = ROOT / "hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"

EXPECTED_IDENTITY = {
    "U2": ("W25Q512JVFIQ", "SOIC-16_300mil_F", {str(index) for index in range(1, 17)}),
    "U3": ("LIS2DW12TR", "LGA-12_2x2mm", {str(index) for index in range(1, 13)}),
    "U4": ("STTS22HTR", "UDFN-6L_2x2mm", {str(index) for index in range(1, 7)} | {"EP"}),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/pcb_main_storage_sensor_authority_rev_a.json",
    )
    args = parser.parse_args()

    authority_rows = read_csv(AUTHORITY)
    by_key = {(row["RefDes"], row["Pin"]): row for row in authority_rows}
    require(len(authority_rows) == len(by_key) == 35, "device authority must contain 35 unique physical pins or pads")
    for ref, (mpn, package, pins) in EXPECTED_IDENTITY.items():
        actual = [row for row in authority_rows if row["RefDes"] == ref]
        require({row["Pin"] for row in actual} == pins, f"{ref} physical pin set mismatch")
        require(all(row["MPN"] == mpn and row["Package"] == package for row in actual), f"{ref} identity or package drift")

    u2 = {pin: by_key[("U2", pin)] for pin in EXPECTED_IDENTITY["U2"][2]}
    require(
        {pin: u2[pin]["RevA_Net"] for pin in ("1", "7", "8", "9", "15", "16")}
        == {
            "1": "NOR_IO3", "7": "NOR_NCS", "8": "NOR_IO1",
            "9": "NOR_IO2", "15": "NOR_IO0", "16": "NOR_CLK",
        },
        "U2 Quad-SPI endpoint mapping mismatch",
    )
    require({pin for pin, row in u2.items() if row["Disposition"] == "DNU_NO_CONNECT"} == {"4", "5", "6", "11", "12", "13", "14"}, "U2 N/C-DNU set mismatch")
    require(u2["2"]["RevA_Net"] == "3V3_DIGITAL" and u2["10"]["RevA_Net"] == "GND", "U2 power pins mismatch")
    require(u2["3"]["Disposition"] == "STRAP_DIRECT_HIGH", "U2 dedicated reset is not held inactive")
    require("10 kOhm pull-up" in u2["7"]["Required_Network"], "U2 /CS power-transition pull-up missing")
    require("100 nF plus 1 uF" in u2["2"]["Required_Network"], "U2 local decoupling mismatch")
    require("factory default QE=1" in u2["1"]["Notes"] and "factory default QE=1" in u2["9"]["Notes"], "U2 exact IQ Quad-Enable behavior is not recorded")

    u3 = {pin: by_key[("U3", pin)] for pin in EXPECTED_IDENTITY["U3"][2]}
    require(u3["1"]["RevA_Net"] == "I2C2_SCL" and u3["4"]["RevA_Net"] == "I2C2_SDA", "U3 I2C endpoints mismatch")
    require(u3["2"]["Disposition"] == "STRAP_DIRECT_HIGH", "U3 CS does not force I2C mode")
    require(u3["3"]["Disposition"] == "STRAP_DIRECT_LOW", "U3 SA0 address strap mismatch")
    u3_address = 0x18 if u3["3"]["RevA_Net"] == "GND" else 0x19
    require(u3_address == 0x18, "U3 derived 7-bit I2C address mismatch")
    require(u3["7"]["RevA_Net"] == "GND", "U3 reserved input is not grounded")
    require(u3["12"]["RevA_Net"] == "ACCEL_INT" and u3["11"]["RevA_Net"] == "NC", "U3 interrupt routing mismatch")
    require(u3["5"]["RevA_Net"] == "NC", "U3 internally unconnected pin is not NC")
    require("100 nF plus 10 uF" in u3["9"]["Required_Network"] and "100 nF" in u3["10"]["Required_Network"], "U3 dual-supply decoupling mismatch")

    u4 = {pin: by_key[("U4", pin)] for pin in EXPECTED_IDENTITY["U4"][2]}
    require(u4["1"]["RevA_Net"] == "I2C2_SCL" and u4["6"]["RevA_Net"] == "I2C2_SDA", "U4 I2C endpoints mismatch")
    require(u4["4"]["Disposition"] == "STRAP_DIRECT_LOW", "U4 address strap mismatch")
    u4_address = 0x3F if u4["4"]["RevA_Net"] == "GND" else 0x38
    require(u4_address == 0x3F, "U4 derived 7-bit I2C address mismatch")
    require(u4["2"]["RevA_Net"] == "NC", "U4 unused ALERT/INT output is not NC")
    require(u4["3"]["RevA_Net"] == "3V3_DIGITAL" and u4["5"]["RevA_Net"] == "GND", "U4 supply mapping mismatch")
    require("100 nF" in u4["3"]["Required_Network"], "U4 local decoupling mismatch")
    require(u4["EP"]["Disposition"] == "MECHANICAL_PAD_NO_NET" and u4["EP"]["RevA_Net"] == "NC", "U4 exposed-pad policy mismatch")

    source_nets = {row["Net"] for row in read_csv(PIN_MAP)}
    require({"NOR_CLK", "NOR_NCS", "NOR_IO0", "NOR_IO1", "NOR_IO2", "NOR_IO3", "I2C2_SCL", "I2C2_SDA", "ACCEL_INT"}.issubset(source_nets), "functional source lacks a U2/U3/U4 endpoint")

    freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE)}
    for ref, (mpn, package, _) in EXPECTED_IDENTITY.items():
        require(freeze[ref]["MPN"] == mpn and freeze[ref]["Package_or_Module"] == package.removesuffix("_F"), f"{ref} freeze identity mismatch")

    power = json.loads(POWER_BASELINE.read_text(encoding="utf-8"))
    current_monitor = power["current_monitor"]
    ina226_address = int(current_monitor["i2c_address_7bit_hex"], 16)
    require(len({u3_address, u4_address, ina226_address}) == 3, "I2C2 address collision")
    require(current_monitor["i2c_speed_hz_initial"] == 100000, "shared I2C2 initial speed drift")
    require(current_monitor["pullup_location"] == "PCB-MAIN", "I2C2 pull-up ownership drift")
    pwr_nets = {row["Net"]: row for row in read_csv(POWER_NETS)}
    for net in ("I2C2_SCL", "I2C2_SDA"):
        require(pwr_nets[net]["Population"] == "DNP_PULLUP", f"PCB-PWR {net} pull-up unexpectedly populated")
        require("authoritative pull-up is on PCB-MAIN" in pwr_nets[net]["Notes"], f"PCB-PWR {net} pull-up ownership note missing")

    review = REVIEW.read_text(encoding="utf-8")
    for marker in (
        "2.2 kOhm, 1%", "0.746 us", "1.32 mA", "22 Ohm series-damping", "Initial bus speed is 100 kHz",
        "JEDEC/SFDP", "0x18", "0x3F", "0x40", "MAIN-AUTH-010",
    ):
        require(marker in review, f"device review record missing electrical marker: {marker}")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    closed = {item["id"] for item in status["capture_readiness"]["closed_authorities"]}
    open_ids = {item["id"] for item in status["capture_readiness"]["open_authorities"]}
    require(closed == {"MAIN-AUTH-001", "MAIN-AUTH-002"}, "closed authority set mismatch")
    require(open_ids == {f"MAIN-AUTH-{index:03d}" for index in range(3, 12)}, "remaining authority set mismatch")
    require(status["manufacturing_release"] is False, "manufacturing release asserted with open authorities")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "second independent U2/U3/U4 electrical authority control",
        "status": "PASS_DEVICE_AUTHORITY_ONLY",
        "physical_pins_or_pads": len(authority_rows),
        "i2c_addresses": {
            "LIS2DW12TR": f"0x{u3_address:02X}",
            "STTS22HTR": f"0x{u4_address:02X}",
            "INA226AIDGSR": f"0x{ina226_address:02X}",
        },
        "closed_authorities": sorted(closed),
        "open_authorities": sorted(open_ids),
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN U2/U3/U4 second independent control: PASS_DEVICE_AUTHORITY_ONLY")
    print("- 35 physical pins or pads and all OCTOSPI/I2C/interrupt endpoints verified")
    print("- I2C2 addresses 0x18, 0x3F and 0x40 are unique; pull-up ownership verified")
    print("- production BOM remains BLOCKED by 9 open PCB-MAIN authorities")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()

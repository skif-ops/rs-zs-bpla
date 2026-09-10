#!/usr/bin/env python3
"""Independent structural audit of PCB-PWR Rev.A pin and net capture authorities."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / "hardware" / "PCB_PWR_PIN_AUTHORITY_REV_A.csv"
NET_PATH = ROOT / "hardware" / "PCB_PWR_CAPTURE_NETS_REV_A.csv"
HARNESS_PATH = ROOT / "hardware" / "HARNESS_LOGICAL_PINOUT_REV_A.csv"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def pins_for(pin_rows: list[dict[str, str]], ref: str) -> dict[str, dict[str, str]]:
    selected = [r for r in pin_rows if r["RefDes"] == ref]
    return {r["Pin"]: r for r in selected}


def main() -> None:
    pin_rows = rows(PIN_PATH)
    net_rows = rows(NET_PATH)
    harness = rows(HARNESS_PATH)

    require(pin_rows, "PCB-PWR pin authority is empty")
    require(net_rows, "PCB-PWR net authority is empty")

    expected_pinsets = {
        "U1": {str(i) for i in range(1, 7)},
        "Q1": {str(i) for i in range(1, 9)},
        "U2": {str(i) for i in range(1, 11)},
        "U3": {str(i) for i in range(1, 10)},
        "U4": {str(i) for i in range(1, 10)},
        "U5": {str(i) for i in range(1, 6)},
    }
    for ref, expected in expected_pinsets.items():
        actual = set(pins_for(pin_rows, ref))
        require(actual == expected, f"{ref} pin-set mismatch: expected {sorted(expected)}, got {sorted(actual)}")

    u1 = pins_for(pin_rows, "U1")
    require(u1["1"]["Pin_Name"] == "VCAP", "LM74700 pin1 must be VCAP")
    require(u1["3"]["RevA_Net"] == "VBAT_FUSED", "LM74700 EN must be tied to ANODE/input node")
    require(u1["4"]["Pin_Name"] == "CATHODE" and u1["4"]["RevA_Net"] == "VBAT_PROTECTED", "LM74700 cathode mapping mismatch")
    require(u1["5"]["Pin_Name"] == "GATE" and u1["5"]["RevA_Net"] == "REV_GATE", "LM74700 gate mapping mismatch")
    require(u1["6"]["Pin_Name"] == "ANODE" and u1["6"]["RevA_Net"] == "VBAT_FUSED", "LM74700 anode mapping mismatch")

    q1 = pins_for(pin_rows, "Q1")
    require(all(q1[str(i)]["Pin_Name"] == "SOURCE" for i in (1, 2, 3)), "CSD18540 source pins mismatch")
    require(q1["4"]["Pin_Name"] == "GATE", "CSD18540 gate pin mismatch")
    require(all(q1[str(i)]["Pin_Name"] == "DRAIN" for i in (5, 6, 7, 8)), "CSD18540 drain pins mismatch")

    for ref in ("U3", "U4"):
        u = pins_for(pin_rows, ref)
        expected_names = {
            "1": "VIN", "2": "PGND", "3": "SW", "4": "BOOT", "5": "PG",
            "6": "FB", "7": "MODE/SYNC", "8": "RT", "9": "EN",
        }
        require({p: u[p]["Pin_Name"] for p in expected_names} == expected_names, f"{ref} LMR60440 pinout mismatch")
        require(u["8"]["Notes"].startswith("86.6 kOhm"), f"{ref} 400 kHz RT baseline lost")
    require(pins_for(pin_rows, "U3")["6"]["RevA_Net"] == "FB_3V8", "3V8 buck must use adjustable divider")
    require(pins_for(pin_rows, "U4")["6"]["RevA_Net"] == "3V3_DIGITAL", "3V3 buck must use fixed-output FB connection")
    require(pins_for(pin_rows, "U4")["5"]["RevA_Net"] == "PWR_GOOD", "PWR_GOOD must originate from 3V3 PG")
    require(pins_for(pin_rows, "U3")["5"]["RevA_Net"] == "PG_3V8", "modem PG must remain diagnostic-only")
    require(pins_for(pin_rows, "U4")["9"]["RevA_Net"] == "VBAT_SYS", "3V3 MAIN/AON buck EN must be tied to VIN/VBAT_SYS to avoid startup deadlock")
    require(pins_for(pin_rows, "U4")["9"]["RevA_Net"] != "EN_AUX", "EN_AUX must never gate the rail that powers MAIN")

    u5 = pins_for(pin_rows, "U5")
    require(u5["1"]["Pin_Name"] == "IN" and u5["5"]["Pin_Name"] == "OUT", "TPS7A2018 IN/OUT pinout mismatch")
    require(u5["3"]["RevA_Net"] == "EN_AUX", "TPS7A2018 EN must be controlled by EN_AUX after MAIN boot")
    require(u5["4"]["Pin_Name"] == "NC", "TPS7A2018 pin4 must be NC")

    u2 = pins_for(pin_rows, "U2")
    expected_ina = {
        "1": ("A1", "GND_PWR"),
        "2": ("A0", "GND_PWR"),
        "3": ("ALERT", "FAULT"),
        "4": ("SDA", "I2C2_SDA"),
        "5": ("SCL", "I2C2_SCL"),
        "6": ("VS", "3V3_DIGITAL"),
        "7": ("GND", "GND_PWR"),
        "8": ("VBUS", "VBAT_SYS"),
        "9": ("IN-", "SHUNT_LOAD_SENSE"),
        "10": ("IN+", "SHUNT_SOURCE_SENSE"),
    }
    for pin, (name, net) in expected_ina.items():
        require((u2[pin]["Pin_Name"], u2[pin]["RevA_Net"]) == (name, net), f"INA226 pin {pin} mismatch")
    require("0x40" in u2["2"]["Notes"], "INA226 0x40 address strap evidence missing")

    by_net = {r["Net"]: r for r in net_rows}
    for net in (
        "VBAT_RAW", "VBAT_FUSED", "VBAT_PROTECTED", "VBAT_SYS",
        "SHUNT_SOURCE_SENSE", "SHUNT_LOAD_SENSE", "3V8_MODEM", "3V3_DIGITAL",
        "1V8_MIC", "PWR_GOOD", "FAULT", "I2C2_SCL", "I2C2_SDA",
        "EN_MODEM", "EN_AUX", "GND_MODEM", "GND_DIGITAL", "GND_MIC",
    ):
        require(net in by_net, f"required PCB-PWR net authority missing: {net}")

    require("RSH1.CURRENT_SOURCE" in by_net["VBAT_PROTECTED"]["To"], "total-current shunt is not after reverse protection")
    require("U3.1_VIN" in by_net["VBAT_SYS"]["To"] and "U4.1_VIN" in by_net["VBAT_SYS"]["To"], "both buck rails do not branch after INA226 shunt")
    require("U4.9_EN" in by_net["VBAT_SYS"]["To"], "always-on 3V3 buck EN is not explicitly tied to VBAT_SYS")
    require(by_net["SHUNT_SOURCE_SENSE"]["Class"] == "KELVIN", "source sense is not Kelvin-class")
    require(by_net["SHUNT_LOAD_SENSE"]["Class"] == "KELVIN", "load sense is not Kelvin-class")
    require("authoritative pull-up is on PCB-MAIN" in by_net["I2C2_SCL"]["Notes"], "SCL PWR-side DNP pull-up policy missing")
    require("authoritative pull-up is on PCB-MAIN" in by_net["I2C2_SDA"]["Notes"], "SDA PWR-side DNP pull-up policy missing")
    require("3V3 rail PG only" in by_net["PWR_GOOD"]["Notes"], "PWR_GOOD source policy is ambiguous")
    require("never replaces I2C" in by_net["FAULT"]["Notes"], "FAULT incorrectly substitutes for INA226 telemetry")
    require("U5.3_EN" in by_net["EN_AUX"]["To"], "EN_AUX must gate the 1V8 microphone LDO")
    require("U4.9_EN" not in by_net["EN_AUX"]["To"], "startup deadlock: EN_AUX still gates U4 3V3 buck")
    require("U5.3_EN" not in by_net["3V3_DIGITAL"]["To"], "TPS7A20 EN must not be hard-tied to 3V3 after Review A")

    expected_net_ties = {
        "GND_MODEM": "NT_GND_MODEM.1",
        "GND_DIGITAL": "NT_GND_DIGITAL.1",
        "GND_MIC": "NT_GND_MIC.1",
    }
    for net, target in expected_net_ties.items():
        require(by_net[net]["Population"] == "NET_TIE", f"{net} must use an explicit net-tie")
        require(by_net[net]["To"] == target, f"{net} net-tie endpoint mismatch")
        require("joins GND_PWR" in by_net[net]["Notes"], f"{net} does not document its controlled join to GND_PWR")

    main_pwr = [r for r in harness if r["Interface"] == "MAIN_PWR"]
    require([r["Pin"] for r in main_pwr] == [str(i) for i in range(1, 13)], "harness MAIN_PWR is not 12-pin")
    expected_harness = {
        "1": "3V8_MODEM", "2": "GND_MODEM", "3": "3V3_DIGITAL", "4": "GND_DIGITAL",
        "5": "1V8_MIC", "6": "GND_MIC", "7": "PWR_GOOD", "8": "FAULT",
        "9": "EN_MODEM", "10": "EN_AUX", "11": "I2C2_SCL", "12": "I2C2_SDA",
    }
    require({r["Pin"]: r["Net"] for r in main_pwr} == expected_harness, "capture/harness 12-pin net contract mismatch")

    combined = "\n".join(
        ",".join(row.values()) for row in pin_rows + net_rows
    )
    for stale in (
        "10-contact MAIN/PWR contract",
        "INA226_without_I2C",
        "ALERT_only",
        "NET_TIE_OR_PLANE",
    ):
        require(stale not in combined, f"stale PCB-PWR capture token present: {stale}")

    print("PCB-PWR Rev.A Review-A pin/net authority audit PASS")
    print("12-pin MAIN/PWR + INA226 I2C + Kelvin total-current topology locked")
    print("startup-safe always-on 3V3 MAIN/AON rail + EN_AUX-gated 1V8_MIC locked")
    print("GND_MODEM/GND_DIGITAL/GND_MIC controlled joins use explicit net-ties")


if __name__ == "__main__":
    main()

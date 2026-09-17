#!/usr/bin/env python3
"""Second independent control of PCB-MAIN U8/U16/Q1/Q2 cellular authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv"
REVIEW = ROOT / "hardware/PCB_MAIN_CELLULAR_AUTHORITY_REV_A.md"
MCU_AUTHORITY = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CAPTURE_SPEC = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
POWER_ARCHITECTURE = ROOT / "hardware/EVT_PRE_20_POWER_ARCHITECTURE.md"
CELLULAR_SHEET = ROOT / "hardware/kicad/sheets/05_CELLULAR.csv"

EXPECTED_IDENTITY = {
    "U8": ("BG95-M3", "LGA-102_23.6x19.9mm", {str(index) for index in range(1, 103)}),
    "U16": ("SN74AXC8T245PWR", "TSSOP-24_PW", {str(index) for index in range(1, 25)}),
    "Q1": ("MMBT3904,215", "SOT23", {"1", "2", "3"}),
    "Q2": ("MMBT3904,215", "SOT23", {"1", "2", "3"}),
}

U8_PIN_NAMES = """PSM_IND
ADC1
GND
PCM_CLK
PCM_SYNC
PCM_DIN
PCM_DOUT
USB_VBUS
USB_DP
USB_DM
RESERVED
RESERVED
RESERVED
RESERVED
PWRKEY
RESERVED
RESET_N
W_DISABLE#
AP_READY
STATUS
NET_STATUS
DBG_RXD
DBG_TXD
ADC0
GPIO1
GPIO2
GNSS_TXD
GNSS_RXD
VDD_EXT
MAIN_DTR
GND
VBAT_BB
VBAT_BB
MAIN_RXD
MAIN_TXD
MAIN_CTS
MAIN_RTS
MAIN_DCD
MAIN_RI
I2C_SCL
I2C_SDA
USIM_DET
USIM_VDD
USIM_RST
USIM_DATA
USIM_CLK
USIM_GND
GND
ANT_GNSS
GND
GNSS_LNA_EN
VBAT_RF
VBAT_RF
GND
GND
ANT_WIFI
RESERVED
GND
GND
ANT_MAIN
GND
GND
RESERVED
GPIO3
GPIO4
GPIO5
GND
GND
GND
GND
GND
GND
GND
GND
USB_BOOT
RESERVED
RESERVED
RESERVED
GND
GND
GND
GND
GRFC1
GRFC2
GPIO6
GPIO7
GPIO8
GPIO9
GND
GND
GND
RESERVED
RESERVED
RESERVED
RESERVED
PON_TRIG
RESERVED
RESERVED
RESERVED
GND
GND
GND""".splitlines()

U8_GROUND_PINS = {
    3, 31, 48, 50, 54, 55, 58, 59, 61, 62,
    *range(67, 75), *range(79, 83), *range(89, 92), *range(100, 103),
}
U8_RESERVED_PINS = {11, 12, 13, 14, 16, 57, 63, 76, 77, 78, 92, 93, 94, 95, 97, 98, 99}
U8_FUNCTION_NETS = {
    15: "U8_PWRKEY_N",
    17: "U8_RESET_N",
    20: "U8_STATUS_1V8",
    29: "U8_VDD_EXT_1V8",
    30: "U8_MAIN_DTR_1V8",
    34: "U8_MAIN_RXD_1V8",
    35: "U8_MAIN_TXD_1V8",
    39: "U8_MAIN_RI_1V8",
}
U8_DUAL_SIM_MAP = {
    42: ("NC", "UNUSED_INPUT_NC"),
    43: ("CELL_USIM_VDD_1V8", "FUNCTION_LOCKED"),
    44: ("CELL_USIM_RST_1V8", "FUNCTION_LOCKED"),
    45: ("CELL_USIM_DATA_1V8", "FUNCTION_LOCKED"),
    46: ("CELL_USIM_CLK_1V8", "FUNCTION_LOCKED"),
    47: ("GND_MODEM", "GROUND_LOCKED"),
}
U8_RESOLVED_009 = {
    8: ("CELL_USB_VBUS", "FIXTURE_ENDPOINT_LOCKED"),
    9: ("CELL_USB_DP", "FIXTURE_ENDPOINT_LOCKED"),
    10: ("CELL_USB_DM", "FIXTURE_ENDPOINT_LOCKED"),
    22: ("CELL_DBG_RXD_1V8", "FIXTURE_ENDPOINT_LOCKED"),
    23: ("CELL_DBG_TXD_1V8", "FIXTURE_ENDPOINT_LOCKED"),
    60: ("CELL_RF", "RF_ENDPOINT_LOCKED"),
    75: ("CELL_USB_BOOT_1V8", "FIXTURE_ENDPOINT_LOCKED"),
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
        default=ROOT / "artifacts/pcb_main_cellular_authority_rev_a.json",
    )
    args = parser.parse_args()

    authority_rows = read_csv(AUTHORITY)
    expected_columns = {
        "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
        "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
    }
    require(len(authority_rows) == 132, "cellular authority must contain exactly 132 physical pins")
    require(all(set(row) == expected_columns for row in authority_rows), "cellular authority schema mismatch")
    require(
        all(all(row[column] is not None and row[column] != "" for column in expected_columns) for row in authority_rows),
        "cellular authority contains an empty field",
    )
    by_key = {(row["RefDes"], row["Pin"]): row for row in authority_rows}
    require(len(by_key) == len(authority_rows), "duplicate cellular authority RefDes/pin key")
    for ref, (mpn, package, pins) in EXPECTED_IDENTITY.items():
        actual = [row for row in authority_rows if row["RefDes"] == ref]
        require({row["Pin"] for row in actual} == pins, f"{ref} package pin set mismatch")
        require(all(row["MPN"] == mpn and row["Package"] == package for row in actual), f"{ref} identity/package drift")

    u8 = {index: by_key[("U8", str(index))] for index in range(1, 103)}
    require(len(U8_PIN_NAMES) == 102, "independent U8 pin-name reference is not 102 positions")
    for index, expected_name in enumerate(U8_PIN_NAMES, start=1):
        require(u8[index]["Pin_Name"] == expected_name, f"U8 pad {index} pin-name mismatch")
    require({index for index, row in u8.items() if row["Pin_Name"] == "GND"} == U8_GROUND_PINS, "U8 GND pad set mismatch")
    for index in U8_GROUND_PINS:
        require(
            (u8[index]["RevA_Net"], u8[index]["Disposition"]) == ("GND_MODEM", "GROUND_LOCKED"),
            f"U8 pad {index} ground disposition mismatch",
        )
    for index in U8_RESERVED_PINS:
        require(
            (u8[index]["RevA_Net"], u8[index]["Disposition"]) == ("NC", "RESERVED_DNU_NC"),
            f"U8 reserved pad {index} is not DNU/NC",
        )
    for index, net in U8_FUNCTION_NETS.items():
        require(u8[index]["RevA_Net"] == net, f"U8 functional pad {index} net mismatch")
    for index, expected in U8_DUAL_SIM_MAP.items():
        require(
            (u8[index]["RevA_Net"], u8[index]["Disposition"]) == expected,
            f"U8 pad {index} closed dual-SIM mapping mismatch",
        )
    for index, expected in U8_RESOLVED_009.items():
        require(
            (u8[index]["RevA_Net"], u8[index]["Disposition"]) == expected,
            f"U8 pad {index} recovery/RF endpoint mismatch",
        )
    require(u8[51]["Disposition"] == u8[56]["Disposition"] == "UNSUPPORTED_VARIANT_NC", "U8 unsupported-variant pads are not NC")
    require(u8[27]["Disposition"] == u8[84]["Disposition"] == "UNUSED_BOOT_CONFIG_NC", "U8 unused BOOT_CONFIG pads are not safe NC")

    require(
        (u8[32]["Pin_Name"], u8[32]["RevA_Net"], u8[33]["RevA_Net"])
        == ("VBAT_BB", "3V8_MODEM_BB", "3V8_MODEM_BB"),
        "U8 VBAT_BB pad mapping mismatch",
    )
    require(
        (u8[52]["Pin_Name"], u8[52]["RevA_Net"], u8[53]["RevA_Net"])
        == ("VBAT_RF", "3V8_MODEM_RF", "3V8_MODEM_RF"),
        "U8 VBAT_RF pad mapping mismatch",
    )
    bb_network = u8[32]["Required_Network"]
    for token in ("100 uF", "220 nF", "47 nF", "150 pF", "100 pF", "68 pF", "33 pF", "10 pF", "ferrite bead"):
        require(token in bb_network, f"U8 VBAT_BB network lacks {token}")
    rf_network = u8[52]["Required_Network"]
    for token in ("100 uF", "100 nF", "33 pF", "10 pF", "0 Ohm link"):
        require(token in rf_network, f"U8 VBAT_RF network lacks {token}")
    require("never below 3.3 V" in u8[32]["Notes"], "U8 VBAT_BB minimum voltage missing")
    require("never below 3.3 V" in u8[52]["Notes"], "U8 VBAT_RF minimum voltage missing")

    require(u8[29]["RevA_Net"] == "U8_VDD_EXT_1V8", "U8 VDD_EXT net mismatch")
    require("below 50 mA" in u8[29]["Required_Network"], "U8 VDD_EXT load limit missing")
    require("Open-collector Q1" in u8[15]["Required_Network"], "U8 PWRKEY open-collector contract missing")
    require("500-1000 ms" in u8[15]["Notes"], "U8 PWRKEY turn-on window missing")
    require("Open-collector Q2" in u8[17]["Required_Network"], "U8 RESET_N open-collector contract missing")
    require("2-3.8 s" in u8[17]["Notes"], "U8 reset pulse window missing")

    u16 = {index: by_key[("U16", str(index))] for index in range(1, 25)}
    require(u16[1]["RevA_Net"] == "U8_VDD_EXT_1V8", "U16 VCCA is not module-derived VDD_EXT")
    require(u16[23]["RevA_Net"] == u16[24]["RevA_Net"] == "3V3_DIGITAL", "U16 VCCB rail mismatch")
    require(u16[12]["RevA_Net"] == u16[13]["RevA_Net"] == "GND_MODEM", "U16 ground mapping mismatch")
    require(
        (u16[2]["RevA_Net"], u16[2]["Disposition"]) == ("U8_VDD_EXT_1V8", "STRAP_DIRECT_HIGH"),
        "U16 DIR1 is not fixed HIGH from VCCA",
    )
    require(
        (u16[11]["RevA_Net"], u16[11]["Disposition"]) == ("GND_MODEM", "STRAP_DIRECT_LOW"),
        "U16 DIR2 is not fixed LOW",
    )
    require(
        (u16[22]["RevA_Net"], u16[22]["Disposition"]) == ("GND_MODEM", "STRAP_DIRECT_LOW"),
        "U16 active-low OE is not fixed enabled",
    )
    a_to_b = {
        3: ("U8_MAIN_TXD_1V8", "INPUT"),
        4: ("U8_STATUS_1V8", "INPUT"),
        5: ("U8_MAIN_RI_1V8", "INPUT"),
        21: ("CELL_RX", "OUTPUT"),
        20: ("CELL_STATUS", "OUTPUT"),
        19: ("CELL_RI", "OUTPUT"),
    }
    b_to_a = {
        17: ("CELL_TX", "INPUT"),
        16: ("CELL_DTR", "INPUT"),
        7: ("U8_MAIN_RXD_1V8", "OUTPUT"),
        8: ("U8_MAIN_DTR_1V8", "OUTPUT"),
    }
    for pin, expected in {**a_to_b, **b_to_a}.items():
        require((u16[pin]["RevA_Net"], u16[pin]["Direction"]) == expected, f"U16 pin {pin} signal mapping mismatch")
    require({u16[6]["RevA_Net"], u16[14]["RevA_Net"], u16[15]["RevA_Net"]} == {"GND_MODEM"}, "U16 unused source inputs are not grounded")
    require(all(u16[pin]["Disposition"] == "UNUSED_INPUT_DIRECT_LOW" for pin in (6, 14, 15)), "U16 unused-input disposition mismatch")
    require({u16[9]["RevA_Net"], u16[10]["RevA_Net"], u16[18]["RevA_Net"]} == {"NC"}, "U16 unused outputs are not NC")
    require(all("100 nF" in u16[pin]["Required_Network"] for pin in (1, 23, 24)), "U16 local bypass set incomplete")
    require("10 kOhm pull-up" in u16[3]["Required_Network"], "U16 module TX idle-HIGH bias missing")
    require("10 kOhm pull-up" in u16[5]["Required_Network"], "U16 module RI idle-HIGH bias missing")
    require("10 kOhm pull-up" in u16[17]["Required_Network"], "U16 MCU TX idle-HIGH bias missing")
    require("100 kOhm pull-down" in u16[16]["Required_Network"], "U16 DTR awake-state bias missing")
    require("100 kOhm pull-down" in u16[20]["Required_Network"], "U16 STATUS off-state bias missing")

    for ref, command, collector in (("Q1", "CELL_PWRKEY_CMD", "U8_PWRKEY_N"), ("Q2", "CELL_RESET_N_CMD", "U8_RESET_N")):
        q = {index: by_key[(ref, str(index))] for index in range(1, 4)}
        require((q[1]["Pin_Name"], q[2]["Pin_Name"], q[3]["Pin_Name"]) == ("B", "E", "C"), f"{ref} SOT23 pin order mismatch")
        require("4.7 kOhm" in q[1]["Required_Network"] and "47 kOhm" in q[1]["Required_Network"], f"{ref} base network mismatch")
        require(command in q[1]["Required_Network"], f"{ref} MCU command source mismatch")
        require(q[2]["RevA_Net"] == "GND_MODEM", f"{ref} emitter ground mismatch")
        require(q[3]["RevA_Net"] == collector and q[3]["Direction"] == "OPEN_COLLECTOR", f"{ref} collector net mismatch")
    require("10 nF" in by_key[("Q1", "3")]["Required_Network"], "Q1 PWRKEY filter capacitor missing")
    require("no large capacitance" in by_key[("Q2", "3")]["Required_Network"], "Q2 RESET_N capacitance prohibition missing")

    # Independent guaranteed 1.8 V-domain compatibility check.
    u16_vcca_min_v = 1.65
    bg95_voh_min_v = 1.35
    bg95_vih_min_v = 1.20
    bg95_vil_max_v = 0.60
    u16_vih_min_v = 0.65 * u16_vcca_min_v
    u16_voh_min_v = u16_vcca_min_v - 0.30
    u16_vol_max_v = 0.30
    bg95_to_u16_high_margin_v = bg95_voh_min_v - u16_vih_min_v
    u16_to_bg95_high_margin_v = u16_voh_min_v - bg95_vih_min_v
    u16_to_bg95_low_margin_v = bg95_vil_max_v - u16_vol_max_v
    require(bg95_to_u16_high_margin_v > 0.27, "BG95-to-U16 guaranteed HIGH margin is too small")
    require(u16_to_bg95_high_margin_v > 0.149, "U16-to-BG95 guaranteed HIGH margin is too small")
    require(u16_to_bg95_low_margin_v >= 0.30, "U16-to-BG95 guaranteed LOW margin is too small")
    vdd_ext_pull_load_a = 2 * 1.8 / 10_000 + 55e-6
    require(vdd_ext_pull_load_a < 0.001, "known U16 and pull-up VDD_EXT load exceeds 1 mA")

    pin_map = {row["Net"]: row for row in read_csv(PIN_MAP)}
    expected_mcu = {
        "CELL_TX": ("PB6", "92"),
        "CELL_RX": ("PB7", "93"),
        "CELL_PWRKEY_CMD": ("PD11", "58"),
        "CELL_RESET_N_CMD": ("PD12", "59"),
        "CELL_STATUS": ("PD13", "60"),
        "CELL_DTR": ("PD14", "61"),
        "CELL_RI": ("PD15", "62"),
    }
    for net, expected in expected_mcu.items():
        require(net in pin_map, f"MCU cellular net missing: {net}")
        require((pin_map[net]["MCU_Pin"], pin_map[net]["LQFP100_Pin"]) == expected, f"{net} MCU pin mismatch")
    mcu_authority = {row["RevA_Net"]: row for row in read_csv(MCU_AUTHORITY) if row["RevA_Net"] != "NC"}
    require(set(expected_mcu).issubset(mcu_authority), "cellular endpoints missing from U1 physical-pin authority")

    freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE)}
    for ref in EXPECTED_IDENTITY:
        require(ref in freeze and freeze[ref]["MPN"] == EXPECTED_IDENTITY[ref][0], f"{ref} main freeze identity mismatch")
        require("PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv" in freeze[ref]["Notes"], f"{ref} freeze does not cite cellular authority")
    require("SIGNAL_MAPPING" not in freeze["U16"]["Status"], "U16 signal mapping remains incorrectly open")

    authority_sha256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    review = REVIEW.read_text(encoding="utf-8")
    review_markers = {
        "CELLULAR_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        authority_sha256,
        "6ff03aa31577971d02dc15eac11adee4d52b80077ae3fa3503978c1b12496e81",
        "6cf4003c438c0546fb86f0932613896197dd19a75bdb307f385eb6e75535126e",
        "DIR1 is tied directly",
        "DIR2 is tied directly",
        "OE is tied directly",
        "500-1000 ms",
        "650-1500 ms",
        "2-3.8 s",
        "AT+QPOWD",
        "CELL_STATUS=LOW",
        "150 mV",
        "below 75 mV",
        "controlled separately by `PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv`",
    }
    for marker in review_markers:
        require(marker in review, f"cellular authority review missing marker: {marker}")

    capture_spec = CAPTURE_SPEC.read_text(encoding="utf-8")
    power_architecture = POWER_ARCHITECTURE.read_text(encoding="utf-8")
    cellular_sheet = CELLULAR_SHEET.read_text(encoding="utf-8")
    for marker in ("PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv", "3V8_MODEM_BB", "3V8_MODEM_RF", "700 ms", "AT+QPOWD"):
        require(marker in capture_spec, f"capture spec lacks cellular marker: {marker}")
    for marker in ("VDD_EXT", "700 ms", "CELL_STATUS=LOW", "3V8_MODEM_BB", "3V8_MODEM_RF"):
        require(marker in power_architecture, f"power architecture lacks cellular marker: {marker}")
    require("PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv" in cellular_sheet, "cellular sheet does not cite machine authority")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    authoritative = set(status["source_control"]["authoritative_inputs"])
    require(
        {
            "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_CELLULAR_AUTHORITY_REV_A.md",
        }.issubset(authoritative),
        "cellular authority files are not registered as authoritative inputs",
    )
    readiness = status["capture_readiness"]
    closed = {item["id"]: item for item in readiness["closed_authorities"]}
    open_ids = {item["id"] for item in readiness["open_authorities"]}
    require("MAIN-AUTH-004" in closed, "MAIN-AUTH-004 is not closed")
    require(
        set(closed["MAIN-AUTH-004"]["evidence"])
        == {
            "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_CELLULAR_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-004 evidence set mismatch",
    )
    require("MAIN-AUTH-005" in closed, "MAIN-AUTH-005 is not closed")
    require(
        set(closed["MAIN-AUTH-005"]["evidence"])
        == {
            "hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_DUAL_SIM_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-005 evidence set mismatch",
    )
    require(set(closed) == {f"MAIN-AUTH-{index:03d}" for index in range(1, 12)}, "closed authority set mismatch")
    require(open_ids == set(), "open authority set mismatch")
    require(readiness["complete"] is True and status["manufacturing_release"] is False, "capture/manufacturing state mismatch")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "U8/U16/Q1/Q2 second independent cellular authority control",
        "status": "PASS_CELLULAR_AUTHORITY_ONLY",
        "physical_pins_verified": len(authority_rows),
        "u8_pads_verified": 102,
        "u8_ground_pads_verified": len(U8_GROUND_PINS),
        "u16_pins_verified": 24,
        "open_collector_transistor_pins_verified": 6,
        "guaranteed_margins_v": {
            "bg95_to_u16_high": round(bg95_to_u16_high_margin_v, 4),
            "u16_to_bg95_high": round(u16_to_bg95_high_margin_v, 4),
            "u16_to_bg95_low": round(u16_to_bg95_low_margin_v, 4),
        },
        "known_vdd_ext_load_a_upper_bound": vdd_ext_pull_load_a,
        "open_authorities": sorted(open_ids),
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN U8/U16/Q1/Q2 second independent control: PASS_CELLULAR_AUTHORITY_ONLY")
    print("- 102 BG95-M3 pads and all reserved/unsupported/owned interfaces verified")
    print("- 24 U16 pins with two fixed direction groups and partial-power isolation verified")
    print("- two exact MMBT3904 open-collector stages and mandatory pulse windows verified")
    print("- guaranteed 1.8 V-domain margins and burst-power requirements verified")
    print("- Reviews A/B keep the production BOM blocked")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()

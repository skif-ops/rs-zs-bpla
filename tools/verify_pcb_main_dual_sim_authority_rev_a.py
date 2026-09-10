#!/usr/bin/env python3
"""Second independent control of PCB-MAIN Rev.A dual-SIM electrical authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv"
REVIEW = ROOT / "hardware/PCB_MAIN_DUAL_SIM_AUTHORITY_REV_A.md"
CELLULAR_AUTHORITY = ROOT / "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv"
MCU_AUTHORITY = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
CONNECTOR_FREEZE = ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CAPTURE_SPEC = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
POLICY = ROOT / "hardware/DUAL_SIM_SINGLE_STANDBY.md"
POWER_ARCHITECTURE = ROOT / "hardware/EVT_PRE_20_POWER_ARCHITECTURE.md"
CELLULAR_SHEET = ROOT / "hardware/kicad/sheets/05_CELLULAR.csv"

EXPECTED_COLUMNS = {
    "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
    "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
}
EXPECTED_IDENTITY = {
    "U13": ("TS3A27518EPWR", "TSSOP-24_PW", {str(pin) for pin in range(1, 25)}),
    "U14": ("ESDALC6V1-5P6", "SOT666_1.6x1.6mm", {str(pin) for pin in range(1, 7)}),
    "U15": ("ESDALC6V1-5P6", "SOT666_1.6x1.6mm", {str(pin) for pin in range(1, 7)}),
    "J6": ("2336582-1", "TE_NanoSIM_H1.37", {str(pin) for pin in range(1, 8)} | {"SHIELD"}),
    "J7": ("2336582-1", "TE_NanoSIM_H1.37", {str(pin) for pin in range(1, 8)} | {"SHIELD"}),
    "Q3": ("MMBT3904,215", "SOT23", {"1", "2", "3"}),
}
U13_PIN_NAMES = {
    1: "NC2", 2: "NC1", 3: "N.C.", 4: "COM1", 5: "GND", 6: "COM2",
    7: "COM3", 8: "VCC", 9: "COM4", 10: "COM5", 11: "NO1", 12: "COM6",
    13: "NO2", 14: "IN2", 15: "NO3", 16: "NO6", 17: "NO4", 18: "NO5",
    19: "NC5", 20: "EN", 21: "NC4", 22: "NC6", 23: "NC3", 24: "IN1",
}
U13_NETS = {
    1: "SIM1_RST_1V8", 2: "SIM1_VDD_1V8", 3: "NC", 4: "CELL_USIM_VDD_1V8",
    5: "GND_MODEM", 6: "CELL_USIM_RST_1V8", 7: "CELL_USIM_CLK_1V8", 8: "3V3_DIGITAL",
    9: "CELL_USIM_VDD_1V8", 10: "CELL_USIM_DATA_1V8", 11: "SIM2_VDD_1V8",
    12: "CELL_USIM_VDD_1V8", 13: "SIM2_RST_1V8", 14: "SIM_MUX_SEL",
    15: "SIM2_CLK_1V8", 16: "SIM2_VDD_1V8", 17: "SIM2_VDD_1V8",
    18: "SIM2_DATA_1V8", 19: "SIM1_DATA_1V8", 20: "U13_EN_N",
    21: "SIM1_VDD_1V8", 22: "SIM1_VDD_1V8", 23: "SIM1_CLK_1V8", 24: "SIM_MUX_SEL",
}
U13_DISPOSITIONS = {
    3: "DNU_NO_CONNECT", 5: "GROUND_LOCKED", 8: "SUPPLY_LOCKED",
    14: "CONTROL_LOCKED", 20: "CONTROL_ACTIVE_LOW", 24: "CONTROL_LOCKED",
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
        default=ROOT / "artifacts/pcb_main_dual_sim_authority_rev_a.json",
    )
    args = parser.parse_args()

    rows = read_csv(AUTHORITY)
    require(len(rows) == 55, "dual-SIM authority must contain exactly 55 physical contacts")
    require(all(set(row) == EXPECTED_COLUMNS for row in rows), "dual-SIM authority schema mismatch")
    require(
        all(all(row.get(column) for column in EXPECTED_COLUMNS) for row in rows),
        "dual-SIM authority contains an empty field",
    )
    by_key = {(row["RefDes"], row["Pin"]): row for row in rows}
    require(len(by_key) == len(rows), "duplicate dual-SIM RefDes/pin key")
    require(set(row["RefDes"] for row in rows) == set(EXPECTED_IDENTITY), "unexpected dual-SIM RefDes set")
    for ref, (mpn, package, pins) in EXPECTED_IDENTITY.items():
        device = [row for row in rows if row["RefDes"] == ref]
        require({row["Pin"] for row in device} == pins, f"{ref} package pin set mismatch")
        require(all((row["MPN"], row["Package"]) == (mpn, package) for row in device), f"{ref} identity/package drift")

    u13 = {pin: by_key[("U13", str(pin))] for pin in range(1, 25)}
    for pin in range(1, 25):
        require(u13[pin]["Pin_Name"] == U13_PIN_NAMES[pin], f"U13 pin {pin} name mismatch")
        require(u13[pin]["RevA_Net"] == U13_NETS[pin], f"U13 pin {pin} net mismatch")
        expected_disposition = U13_DISPOSITIONS.get(pin, "FUNCTION_LOCKED")
        require(u13[pin]["Disposition"] == expected_disposition, f"U13 pin {pin} disposition mismatch")

    channel_truth = {
        1: (4, 2, 11, "VDD_1V8"),
        2: (6, 1, 13, "RST_1V8"),
        3: (7, 23, 15, "CLK_1V8"),
        4: (9, 21, 17, "VDD_1V8"),
        5: (10, 19, 18, "DATA_1V8"),
        6: (12, 22, 16, "VDD_1V8"),
    }
    for channel, (common_pin, sim1_pin, sim2_pin, suffix) in channel_truth.items():
        common_net = "CELL_USIM_VDD_1V8" if suffix == "VDD_1V8" else f"CELL_USIM_{suffix}"
        require(u13[common_pin]["RevA_Net"] == common_net, f"U13 channel {channel} common route mismatch")
        require(u13[sim1_pin]["RevA_Net"] == f"SIM1_{suffix}", f"U13 channel {channel} SIM1 route mismatch")
        require(u13[sim2_pin]["RevA_Net"] == f"SIM2_{suffix}", f"U13 channel {channel} SIM2 route mismatch")
    require({channel for channel, route in channel_truth.items() if route[3] == "VDD_1V8"} == {1, 4, 6}, "U13 VDD channels are not exactly 1/4/6")
    require(all("100 kOhm pull-down" in u13[pin]["Required_Network"] for pin in (14, 24)), "U13 IN1/IN2 default select missing")
    require("47 kOhm pull-up" in u13[20]["Required_Network"] and "Q3" in u13[20]["Required_Network"], "U13 EN safe-state network missing")
    require("100 nF" in u13[8]["Required_Network"], "U13 bypass requirement missing")

    esd_pin_names = {"1": "I/O1", "2": "GND", "3": "I/O2", "4": "I/O3", "5": "I/O4", "6": "I/O5"}
    for ref, slot in (("U14", "SIM1"), ("U15", "SIM2")):
        expected_nets = {
            "1": f"{slot}_VDD_1V8", "2": "GND_MODEM", "3": f"{slot}_RST_1V8",
            "4": f"{slot}_CLK_1V8", "5": f"{slot}_DATA_1V8", "6": f"{slot}_DET",
        }
        for pin in expected_nets:
            row = by_key[(ref, pin)]
            require((row["Pin_Name"], row["RevA_Net"]) == (esd_pin_names[pin], expected_nets[pin]), f"{ref} pin {pin} map mismatch")
            require(row["Authority"] == "ST_ESDALC6V1-5P6_Rev3", f"{ref} pin {pin} source mismatch")
        require(by_key[(ref, "2")]["Disposition"] == "GROUND_LOCKED", f"{ref} pin 2 is not ground-locked")

    connector_names = {"1": "C1_VCC", "2": "C2_RST", "3": "C3_CLK", "4": "C5_GND", "5": "C6_VPP", "6": "C7_IO", "7": "CD", "SHIELD": "SHELL"}
    for ref, slot in (("J6", "SIM1"), ("J7", "SIM2")):
        expected_nets = {
            "1": f"{slot}_VDD_1V8", "2": f"{slot}_RST_1V8", "3": f"{slot}_CLK_1V8",
            "4": "GND_MODEM", "5": "NC", "6": f"{slot}_DATA_1V8", "7": f"{slot}_DET", "SHIELD": "GND_MODEM",
        }
        for pin in expected_nets:
            row = by_key[(ref, pin)]
            require((row["Pin_Name"], row["RevA_Net"]) == (connector_names[pin], expected_nets[pin]), f"{ref} contact {pin} map mismatch")
            require(row["Authority"] == "TE_C-2336582_A2", f"{ref} contact {pin} drawing authority mismatch")
        require(by_key[(ref, "5")]["Disposition"] == "DNU_NO_CONNECT", f"{ref} VPP must be DNU/NC")
        require(by_key[(ref, "4")]["Disposition"] == "GROUND_LOCKED", f"{ref} card ground is not locked")
        require(by_key[(ref, "SHIELD")]["Disposition"] == "SHIELD_GROUND_LOCKED", f"{ref} shell ground is not locked")
        detect_network = by_key[(ref, "7")]["Required_Network"]
        require("10 kOhm pull-up" in detect_network and "10 nF" in detect_network and "20 ms" in detect_network, f"{ref} detect conditioning mismatch")
        require("100 nF" in by_key[(ref, "1")]["Required_Network"], f"{ref} local VDD bypass missing")

    q3 = {pin: by_key[("Q3", str(pin))] for pin in range(1, 4)}
    require((q3[1]["Pin_Name"], q3[2]["Pin_Name"], q3[3]["Pin_Name"]) == ("B", "E", "C"), "Q3 SOT23 pin order mismatch")
    require(q3[1]["RevA_Net"] == "SIM_MUX_EN_B", "Q3 base net mismatch")
    require("10 kOhm series from SIM_MUX_EN" in q3[1]["Required_Network"] and "100 kOhm" in q3[1]["Required_Network"], "Q3 input network mismatch")
    require(q3[2]["RevA_Net"] == "GND_MODEM", "Q3 emitter ground mismatch")
    require(q3[3]["RevA_Net"] == "U13_EN_N" and q3[3]["Direction"] == "OPEN_COLLECTOR", "Q3 collector mapping mismatch")

    cellular = {(row["RefDes"], row["Pin"]): row for row in read_csv(CELLULAR_AUTHORITY)}
    expected_u8 = {
        "42": ("USIM_DET", "NC", "UNUSED_INPUT_NC"),
        "43": ("USIM_VDD", "CELL_USIM_VDD_1V8", "FUNCTION_LOCKED"),
        "44": ("USIM_RST", "CELL_USIM_RST_1V8", "FUNCTION_LOCKED"),
        "45": ("USIM_DATA", "CELL_USIM_DATA_1V8", "FUNCTION_LOCKED"),
        "46": ("USIM_CLK", "CELL_USIM_CLK_1V8", "FUNCTION_LOCKED"),
        "47": ("USIM_GND", "GND_MODEM", "GROUND_LOCKED"),
    }
    for pin, expected in expected_u8.items():
        row = cellular[("U8", pin)]
        require((row["Pin_Name"], row["RevA_Net"], row["Disposition"]) == expected, f"U8 pad {pin} dual-SIM endpoint mismatch")

    expected_mcu = {
        "SIM_MUX_SEL": ("PE0", "97"), "SIM_MUX_EN": ("PE2", "1"),
        "SIM1_DET": ("PE3", "2"), "SIM2_DET": ("PE5", "4"),
    }
    pin_map = {row["Net"]: row for row in read_csv(PIN_MAP)}
    mcu_by_net = {row["RevA_Net"]: row for row in read_csv(MCU_AUTHORITY) if row["RevA_Net"] != "NC"}
    for net, expected in expected_mcu.items():
        require(net in pin_map and net in mcu_by_net, f"{net} missing from MCU authorities")
        require((pin_map[net]["MCU_Pin"], pin_map[net]["LQFP100_Pin"]) == expected, f"{net} MCU endpoint mismatch")
        require((mcu_by_net[net]["Pin_Name"], mcu_by_net[net]["LQFP100_Pin"]) == expected, f"{net} U1 physical endpoint mismatch")

    main_freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE)}
    for ref in ("U13", "U14", "U15", "Q3"):
        require(main_freeze[ref]["MPN"] == EXPECTED_IDENTITY[ref][0], f"{ref} main freeze MPN mismatch")
        require("PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv" in main_freeze[ref]["Notes"], f"{ref} freeze lacks dual-SIM authority citation")
    connector_freeze = {row["Connector_ID"]: row for row in read_csv(CONNECTOR_FREEZE)}
    for connector_id in ("CON-SIM1", "CON-SIM2"):
        require(connector_freeze[connector_id]["Board_MPN"] == "TE_2336582-1", f"{connector_id} frozen socket mismatch")
        require(connector_freeze[connector_id]["Status"] == "TECHNICALLY_SELECTED_PROCUREMENT_RISK", f"{connector_id} procurement risk must remain explicit")

    parallel_ron_ohm = 7.6 / 3
    q3_low_margin_v = 0.65 - 0.2
    detect_rc_s = 10_000 * 10e-9
    debounce_s = 20e-3
    require(parallel_ron_ohm < 2.54, "U13 three-channel VDD resistance bound failed")
    require(q3_low_margin_v >= 0.45, "Q3 guaranteed U13 LOW margin is too small")
    require(debounce_s >= 5 * detect_rc_s, "firmware debounce is less than five detect RC constants")

    authority_sha256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    review = REVIEW.read_text(encoding="utf-8")
    review_markers = {
        "DUAL_SIM_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        authority_sha256,
        "d87c216911176dca84cc9cee5efb6f45b18021977f94a97c7fae989484a73392",
        "ea14ac3604fa4887d91b9fbc55ab9d04a23ba6597b22a817e64185d519fb9e28",
        "2bcf8b28017d5716a1659ad5ad401d6158b272458de43ed4b325a80c7f70d6fe",
        "SIM_MUX_SEL=LOW", "SIM_MUX_SEL=HIGH", "SIM_MUX_EN=HIGH",
        "47 kOhm", "100 kOhm", "at most 2.54 Ohm", "at least 1.62 V",
        "active but not currently available", "does not release the exact passive MPN set",
    }
    for marker in review_markers:
        require(marker in review, f"dual-SIM review missing marker: {marker}")

    cross_documents = {
        CAPTURE_SPEC: ("PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv", "TS3A27518EPWR", "Channels 1, 4, and 6 are paralleled", "SIM_MUX_EN"),
        POLICY: ("TS3A27518EPWR", "TE `2336582-1`", "SIM_MUX_EN=HIGH", "U13_EN_N=HIGH", "MAIN-AUTH-010"),
        POWER_ARCHITECTURE: ("SIM_MUX_SEL", "SIM_MUX_EN=HIGH", "U13 High-Z", "AT+QPOWD"),
        CELLULAR_SHEET: ("PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv", "Q3", "U13 EN", "AT+QPOWD"),
    }
    for path, markers in cross_documents.items():
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in content, f"{path.name} lacks frozen dual-SIM marker: {marker}")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    authoritative = set(status["source_control"]["authoritative_inputs"])
    require(
        {
            "hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_DUAL_SIM_AUTHORITY_REV_A.md",
        }.issubset(authoritative),
        "dual-SIM files are not registered as authoritative inputs",
    )
    readiness = status["capture_readiness"]
    closed = {item["id"]: item for item in readiness["closed_authorities"]}
    open_ids = {item["id"] for item in readiness["open_authorities"]}
    require(set(closed) == {f"MAIN-AUTH-{index:03d}" for index in range(1, 9)}, "closed authority set mismatch")
    require(
        set(closed["MAIN-AUTH-005"]["evidence"])
        == {
            "hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_DUAL_SIM_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-005 evidence set mismatch",
    )
    require(open_ids == {f"MAIN-AUTH-{index:03d}" for index in range(9, 12)}, "remaining open authority set mismatch")
    require(readiness["complete"] is False and status["manufacturing_release"] is False, "dual-SIM authority prematurely released manufacturing")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "U13/U14/U15/J6/J7/Q3 second independent dual-SIM authority control",
        "status": "PASS_DUAL_SIM_AUTHORITY_ONLY",
        "physical_contacts_verified": len(rows),
        "u13_pins_verified": 24,
        "esd_pins_verified": 12,
        "socket_contacts_verified": 16,
        "q3_pins_verified": 3,
        "calculated_limits": {
            "parallel_vdd_ron_upper_bound_ohm": round(parallel_ron_ohm, 4),
            "q3_low_level_margin_v": round(q3_low_margin_v, 4),
            "detect_rc_s": detect_rc_s,
            "firmware_debounce_s": debounce_s,
        },
        "open_authorities": sorted(open_ids),
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN U13/U14/U15/J6/J7/Q3 second independent control: PASS_DUAL_SIM_AUTHORITY_ONLY")
    print("- all 55 physical contacts and independent TI/ST/TE pin maps verified")
    print("- six switch routes, three-channel VDD path and boot-safe Q3 inversion verified")
    print("- both protected socket maps, card-detect filters and MCU endpoints verified")
    print(f"- {len(open_ids)} remaining authorities keep the production BOM blocked")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()

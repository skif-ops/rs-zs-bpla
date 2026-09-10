#!/usr/bin/env python3
"""Second independent control of PCB-MAIN U7/U17/U18 audio logic authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv"
REVIEW = ROOT / "hardware/PCB_MAIN_AUDIO_LOGIC_AUTHORITY_REV_A.md"
MCU_AUTHORITY = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
ADDENDUM = ROOT / "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv"
HARNESS = ROOT / "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CAPTURE_SPEC = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
AUDIO_INTERFACE = ROOT / "hardware/T5838_AAD_INTERFACE_REV_A.md"
POWER_ARCHITECTURE = ROOT / "hardware/EVT_PRE_20_POWER_ARCHITECTURE.md"

EXPECTED_IDENTITY = {
    "U7": ("SN74AXC8T245PWR", "TSSOP-24_PW", {str(index) for index in range(1, 25)}),
    "U17": ("SN74LVC32APWR", "TSSOP-14_PW", {str(index) for index in range(1, 15)}),
    "U18": ("SN74AXC1T45DRLR", "SOT-5X3-6_DRL", {str(index) for index in range(1, 7)}),
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
        default=ROOT / "artifacts/pcb_main_audio_logic_authority_rev_a.json",
    )
    args = parser.parse_args()

    authority_rows = read_csv(AUTHORITY)
    expected_columns = {
        "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
        "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
    }
    require(len(authority_rows) == 44, "audio authority must contain exactly 44 physical pins")
    require(all(set(row) == expected_columns for row in authority_rows), "audio authority schema mismatch")
    require(
        all(all(row[column] is not None and row[column] != "" for column in expected_columns) for row in authority_rows),
        "audio authority contains an empty field",
    )
    by_key = {(row["RefDes"], row["Pin"]): row for row in authority_rows}
    require(len(by_key) == len(authority_rows), "duplicate audio authority RefDes/pin key")
    for ref, (mpn, package, pins) in EXPECTED_IDENTITY.items():
        actual = [row for row in authority_rows if row["RefDes"] == ref]
        require({row["Pin"] for row in actual} == pins, f"{ref} package pin set mismatch")
        require(all(row["MPN"] == mpn and row["Package"] == package for row in actual), f"{ref} identity/package drift")

    u7 = {pin: by_key[("U7", pin)] for pin in EXPECTED_IDENTITY["U7"][2]}
    require(u7["1"]["RevA_Net"] == "1V8_MIC", "U7 VCCA rail mismatch")
    require(u7["23"]["RevA_Net"] == u7["24"]["RevA_Net"] == "3V3_DIGITAL", "U7 VCCB rail mismatch")
    require(u7["12"]["RevA_Net"] == u7["13"]["RevA_Net"] == "GND", "U7 ground pins mismatch")
    require(
        (u7["2"]["Pin_Name"], u7["2"]["RevA_Net"], u7["2"]["Disposition"])
        == ("DIR1", "1V8_MIC", "STRAP_DIRECT_HIGH"),
        "U7 DIR1 is not a VCCA-referenced fixed HIGH",
    )
    require(
        (u7["11"]["Pin_Name"], u7["11"]["RevA_Net"], u7["11"]["Disposition"])
        == ("DIR2", "GND", "STRAP_DIRECT_LOW"),
        "U7 DIR2 is not fixed LOW",
    )
    require(
        (u7["22"]["Pin_Name"], u7["22"]["RevA_Net"], u7["22"]["Disposition"])
        == ("OE", "GND", "STRAP_DIRECT_LOW"),
        "U7 active-low OE is not always enabled",
    )

    data_pairs = {
        1: ("3", "21"),
        2: ("4", "20"),
        3: ("5", "19"),
        4: ("6", "18"),
    }
    for channel, (a_pin, b_pin) in data_pairs.items():
        require(
            (u7[a_pin]["Pin_Name"], u7[a_pin]["Direction"], u7[a_pin]["RevA_Net"])
            == (f"A{channel}", "INPUT", f"PDM_DATA{channel}_1V8"),
            f"U7 channel {channel} 1.8 V input mismatch",
        )
        require(
            (u7[b_pin]["Pin_Name"], u7[b_pin]["Direction"], u7[b_pin]["RevA_Net"])
            == (f"B{channel}", "OUTPUT", f"PDM_DATA{channel}"),
            f"U7 channel {channel} 3.3 V output mismatch",
        )
        require("no external pull" in u7[a_pin]["Required_Network"], f"PDM DATA{channel} external-pull prohibition missing")

    require(
        (u7["17"]["Pin_Name"], u7["17"]["Direction"], u7["17"]["RevA_Net"])
        == ("B5", "INPUT", "PDM_CLK"),
        "U7 MCU-side PDM clock input mismatch",
    )
    require(
        (u7["7"]["Pin_Name"], u7["7"]["Direction"], u7["7"]["RevA_Net"])
        == ("A5", "OUTPUT", "PDM_CLK_1V8"),
        "U7 microphone-side PDM clock output mismatch",
    )
    require(
        (u7["16"]["Pin_Name"], u7["16"]["Direction"], u7["16"]["RevA_Net"])
        == ("B6", "INPUT", "AAD_CFG"),
        "U7 MCU-side AAD configuration input mismatch",
    )
    require(
        (u7["8"]["Pin_Name"], u7["8"]["Direction"], u7["8"]["RevA_Net"])
        == ("A6", "OUTPUT", "AAD_CFG_1V8"),
        "U7 microphone-side AAD configuration output mismatch",
    )
    require({u7[pin]["RevA_Net"] for pin in ("14", "15")} == {"GND"}, "U7 unused source inputs are not grounded")
    require(all(u7[pin]["Disposition"] == "UNUSED_INPUT_DIRECT_LOW" for pin in ("14", "15")), "U7 unused input disposition mismatch")
    require({u7[pin]["RevA_Net"] for pin in ("9", "10")} == {"NC"}, "U7 unused outputs are not NC")
    require(all("100 nF" in u7[pin]["Required_Network"] for pin in ("1", "23", "24")), "U7 local bypass set incomplete")

    u17 = {pin: by_key[("U17", pin)] for pin in EXPECTED_IDENTITY["U17"][2]}
    gate_contract = (
        ("1", "2", "3", "MIC_WAKE1", "MIC_WAKE2", "MIC_WAKE12_OR_1V8"),
        ("4", "5", "6", "MIC_WAKE3", "MIC_WAKE4", "MIC_WAKE34_OR_1V8"),
        ("9", "10", "8", "MIC_WAKE12_OR_1V8", "MIC_WAKE34_OR_1V8", "MIC_WAKE_OR_1V8"),
    )
    for a_pin, b_pin, y_pin, a_net, b_net, y_net in gate_contract:
        require(u17[a_pin]["Direction"] == u17[b_pin]["Direction"] == "INPUT", f"U17 gate inputs {a_pin}/{b_pin} direction mismatch")
        require(u17[y_pin]["Direction"] == "OUTPUT", f"U17 gate output {y_pin} direction mismatch")
        require(
            (u17[a_pin]["RevA_Net"], u17[b_pin]["RevA_Net"], u17[y_pin]["RevA_Net"])
            == (a_net, b_net, y_net),
            f"U17 OR gate {a_pin}/{b_pin}/{y_pin} net mismatch",
        )
    for pin in ("1", "2", "4", "5"):
        require("100 kOhm pull-down" in u17[pin]["Required_Network"], f"U17 wake input {pin} lacks open-harness LOW bias")
        require("test point" in u17[pin]["Required_Network"], f"U17 wake input {pin} lacks individual test point")
    require(u17["7"]["RevA_Net"] == "GND" and u17["14"]["RevA_Net"] == "1V8_MIC", "U17 supply mapping mismatch")
    require("100 nF" in u17["14"]["Required_Network"], "U17 bypass capacitor missing")
    require(u17["12"]["RevA_Net"] == u17["13"]["RevA_Net"] == "GND", "U17 unused inputs are not grounded")
    require(u17["11"]["RevA_Net"] == "NC" and u17["11"]["Disposition"] == "UNUSED_OUTPUT_NC", "U17 unused output policy mismatch")

    # Independent guaranteed-level compatibility check using the datasheet limits
    # recorded in the review, at the minimum shared rail of 1.65 V.
    shared_rail_min_v = 1.65
    t5838_voh_min_v = 0.70 * shared_rail_min_v
    u17_vih_min_v = 0.65 * shared_rail_min_v
    u17_voh_min_v = shared_rail_min_v - 0.30
    u17_vol_max_v = 0.30
    u18_vih_min_v = 0.65 * shared_rail_min_v
    u18_vil_max_v = 0.35 * shared_rail_min_v
    require(t5838_voh_min_v > u17_vih_min_v, "T5838-to-U17 guaranteed HIGH-level margin is non-positive")
    require(u17_voh_min_v > u18_vih_min_v, "U17-to-U18 guaranteed HIGH-level margin is non-positive")
    require(u17_vol_max_v < u18_vil_max_v, "U17-to-U18 guaranteed LOW-level margin is non-positive")
    require(1.98 / 100_000 < 0.0005, "100 kOhm wake pull-down exceeds T5838 0.5 mA output test load")

    u18 = {pin: by_key[("U18", pin)] for pin in EXPECTED_IDENTITY["U18"][2]}
    require(u18["1"]["RevA_Net"] == "1V8_MIC" and u18["6"]["RevA_Net"] == "3V3_DIGITAL", "U18 supply-domain mapping mismatch")
    require(u18["2"]["RevA_Net"] == "GND", "U18 ground mapping mismatch")
    require(u18["5"]["RevA_Net"] == "1V8_MIC" and u18["5"]["Disposition"] == "STRAP_DIRECT_HIGH", "U18 A-to-B direction strap mismatch")
    require(u18["3"]["RevA_Net"] == u17["8"]["RevA_Net"] == "MIC_WAKE_OR_1V8", "U17-to-U18 aggregate net mismatch")
    require(u18["4"]["RevA_Net"] == "MIC_WAKE" and u18["4"]["Direction"] == "OUTPUT", "U18 MCU-side output mismatch")
    require("100 kOhm pull-down" in u18["4"]["Required_Network"], "U18 output safe-state pull-down missing")
    require(all("100 nF" in u18[pin]["Required_Network"] for pin in ("1", "6")), "U18 local bypass set incomplete")

    source_rows = read_csv(PIN_MAP) + read_csv(ADDENDUM)
    source_by_net = {row["Net"]: row for row in source_rows}
    mcu_expected = {
        "PDM_CLK": ("PE9", "37"),
        "PDM_DATA1": ("PB1", "33"),
        "PDM_DATA2": ("PD6", "87"),
        "PDM_DATA3": ("PE7", "35"),
        "PDM_DATA4": ("PE4", "3"),
        "MIC_WAKE": ("PA8", "67"),
        "AAD_CFG": ("PA15", "77"),
    }
    for net, expected in mcu_expected.items():
        require(net in source_by_net, f"MCU functional source lacks {net}")
        require((source_by_net[net]["MCU_Pin"], source_by_net[net]["LQFP100_Pin"]) == expected, f"MCU source endpoint mismatch for {net}")
    mcu_authority = {row["RevA_Net"]: row for row in read_csv(MCU_AUTHORITY) if row["RevA_Net"] != "NC"}
    for net, (_, position) in mcu_expected.items():
        require(net in mcu_authority and mcu_authority[net]["LQFP100_Pin"] == position, f"U1 package authority endpoint mismatch for {net}")

    harness_rows = read_csv(HARNESS)
    for channel in range(1, 5):
        connector = f"J_MIC{channel}"
        physical = {row["Pin"]: row["Net"] for row in harness_rows if row["Connector_Ref"] == connector}
        require(
            physical == {
                "1": "1V8_MIC",
                "2": "GND",
                "3": "PDM_CLK",
                "4": f"PDM_DATA{channel}",
                "5": f"MIC_WAKE{channel}",
                "6": "AAD_CFG",
            },
            f"{connector} six-pin logical contract mismatch",
        )

    freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE)}
    for ref, (mpn, _, _) in EXPECTED_IDENTITY.items():
        require(freeze[ref]["MPN"] == mpn, f"{ref} freeze MPN mismatch")
        require("PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv" in freeze[ref]["Notes"], f"{ref} freeze does not cite the pin authority")

    review = REVIEW.read_text(encoding="utf-8")
    authority_sha256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    for marker in (
        authority_sha256,
        "SCES875C, Revision C",
        "SCAS286U, Revision U",
        "SCES882E, Revision E",
        "DS-000383, Revision 1.2",
        "288 kOhm",
        "55 uA",
        "16 uA",
        "0.7 x VDD",
        "0.65 x VCC",
        "does not release native PCB-MAIN capture",
    ):
        require(marker in review, f"audio authority review missing independent marker: {marker}")

    capture_spec = CAPTURE_SPEC.read_text(encoding="utf-8")
    audio_interface = AUDIO_INTERFACE.read_text(encoding="utf-8")
    power_architecture = POWER_ARCHITECTURE.read_text(encoding="utf-8")
    for text, name in ((capture_spec, "capture spec"), (audio_interface, "AAD interface")):
        for marker in ("PDM_DATA1_1V8", "PDM_CLK_1V8", "AAD_CFG_1V8", "MIC_WAKE_OR_1V8", "100 kOhm"):
            require(marker in text, f"{name} lacks frozen marker: {marker}")
    require("disabled/high-Z state" not in power_architecture, "power architecture contains stale U7 disable policy")
    require("фиксированном `OE=LOW`" in power_architecture, "power architecture lacks fixed U7 OE policy")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    closed_items = status["capture_readiness"]["closed_authorities"]
    open_items = status["capture_readiness"]["open_authorities"]
    closed = {item["id"] for item in closed_items}
    open_ids = {item["id"] for item in open_items}
    require(closed == {f"MAIN-AUTH-{index:03d}" for index in range(1, 12)}, "closed authority identity mismatch")
    require(open_ids == set() and status["capture_readiness"]["complete"] is True, "capture authority completion mismatch")
    evidence = {item["id"]: set(item["evidence"]) for item in closed_items}
    require(
        evidence["MAIN-AUTH-003"]
        == {
            "hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_AUDIO_LOGIC_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-003 evidence set mismatch",
    )
    require(status["manufacturing_release"] is False, "manufacturing release asserted before remaining authorities close")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "second independent U7/U17/U18 audio and AAD electrical authority control",
        "status": "PASS_AUDIO_LOGIC_AUTHORITY_ONLY",
        "physical_pins": len(authority_rows),
        "u7_channels": {
            "pdm_data_1v8_to_3v3": 4,
            "pdm_clock_3v3_to_1v8": 1,
            "aad_cfg_3v3_to_1v8": 1,
            "unused_defined": 2,
        },
        "wake_inputs": 4,
        "wake_or_stages": 2,
        "level_margin_v_at_1v65": {
            "t5838_to_u17_high": round(t5838_voh_min_v - u17_vih_min_v, 4),
            "u17_to_u18_high": round(u17_voh_min_v - u18_vih_min_v, 4),
            "u17_to_u18_low": round(u18_vil_max_v - u17_vol_max_v, 4),
        },
        "closed_authorities": sorted(closed),
        "open_authorities": sorted(open_ids),
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN U7/U17/U18 second independent control: PASS_AUDIO_LOGIC_AUTHORITY_ONLY")
    print("- 44 physical pins, six used U7 translation channels, two defined unused channels")
    print("- four active-high wake inputs, two-stage OR, U18 up-translation and guaranteed logic margins verified")
    print("- production BOM remains BLOCKED by Reviews A/B")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()

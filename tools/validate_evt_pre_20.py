#!/usr/bin/env python3
"""Validate locked EVT-PRE-20 configuration and hardware baseline using stdlib only."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SERIALS = [f"DIO-EVT-{index:03d}" for index in range(1, 21)]


def read_csv(relative_path: str) -> list[dict[str, str]]:
    path = ROOT / relative_path
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_csv_shapes() -> None:
    for path in sorted(ROOT.rglob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
        require(bool(rows), f"empty CSV: {path.relative_to(ROOT)}")
        width = len(rows[0])
        for line_number, row in enumerate(rows[1:], start=2):
            require(
                len(row) == width,
                f"CSV width mismatch: {path.relative_to(ROOT)}:{line_number}",
            )


def validate_lot() -> None:
    lot = read_csv("manufacturing/LOT_SERIAL_REGISTER.csv")
    require([row["Serial"] for row in lot] == EXPECTED_SERIALS, "lot serial range mismatch")
    require(len({row["Serial"] for row in lot}) == 20, "lot serials are not unique")
    require(
        all(row["Housing_Technology"] == "VACUUM_CASTING_PRIMARY" for row in lot),
        "not all 20 units use the primary vacuum-casting allocation",
    )
    require(all(row["APN_Mode"] == "PUBLIC_ONLY" for row in lot), "pilot APN is not PUBLIC_ONLY")
    require(all(row["LoRa_Profile"] == "RU868_LOCKED" for row in lot), "pilot LoRa is not RU868")

    housing = read_csv("manufacturing/HOUSING_LOT_PLAN.csv")
    require([row["Serial"] for row in housing] == EXPECTED_SERIALS, "housing serial range mismatch")
    require(sum(int(row["Primary_Qty"]) for row in housing) == 20, "primary housing total is not 20")
    require(
        sum(int(row["Fallback_Qty_if_Activated"]) for row in housing) == 20,
        "full-lot 3D fallback total is not 20",
    )
    require(all(row["Primary_Process"] == "VACUUM_CASTING" for row in housing), "primary process mismatch")
    require(all(row["Fallback_Process"] == "3D_PRINT" for row in housing), "fallback process mismatch")
    require(
        all(row["Injection_Molding_Scope"] == "SOURCE_DATA_AND_DFM_ONLY" for row in housing),
        "injection molding exceeds source-data-only scope",
    )


def validate_procurement() -> None:
    bom = {row["Item_ID"]: row for row in read_csv("hardware/EVT_PRE_20_BOM_DRAFT.csv")}
    require(bom["HSG-VC"]["Qty_20"] == "20", "BOM vacuum housing quantity is not 20")
    require(bom["HSG-VC"]["Procure_qty"] == "20", "BOM vacuum procurement quantity is not 20")
    require(bom["HSG-3D"]["Procure_qty"] == "0", "3D fallback was ordered before activation")
    require(bom["HSG-IM"]["Procure_qty"] == "0", "injection-molding pilot hardware was ordered")

    rfq = {row["RFQ_ID"]: row for row in read_csv("hardware/CHINA_PROCUREMENT_RFQ.csv")}
    require(rfq["RFQ-017"]["Required_qty"] == "20", "vacuum-casting RFQ quantity is not 20")
    require(rfq["RFQ-018"]["Required_qty"] == "0", "3D fallback procurement is active")
    require(rfq["RFQ-019"]["Required_qty"] == "0", "TPA procurement is active")


def validate_decisions_and_tests() -> None:
    decisions = {row["Decision_ID"]: row for row in read_csv("docs/DECISION_LOG.csv")}
    for decision_id in ("DEC-014", "DEC-015", "DEC-016", "DEC-017", "DEC-018"):
        require(decisions[decision_id]["Status"] == "LOCKED", f"{decision_id} is not locked")
    require(decisions["DEC-010"]["Status"] == "SUPERSEDED", "old housing decision remains active")
    require(decisions["DEC-012"]["Status"] == "SUPERSEDED", "old private APN decision remains active")

    inputs = {row["Input_ID"]: row for row in read_csv("docs/OPEN_INPUTS_FOR_FREEZE.csv")}
    require(inputs["IN-004"]["Status"] == "LOCKED", "three housing source packages are not locked")
    require(inputs["IN-005"]["Status"] == "LOCKED", "housing lot allocation is not locked")

    tests = {row["Test_ID"]: row for row in read_csv("tests/EVT_MATRIX.csv")}
    require(tests["EVT-MECH-VC"]["Population"] == "20_of_20", "vacuum housing EVT is not 20 of 20")
    require(tests["EVT-MECH-IM"]["Population"] == "Source_package_only", "TPA test scope is not source-only")
    require("reject private APN" in tests["EVT-CELL-04"]["Method"], "private APN rejection test missing")


def validate_pinmap() -> None:
    pinmap = read_csv("hardware/EVT_PRE_20_PIN_MAP_REV_A.csv")
    require(len(pinmap) >= 50, "Rev.A pin map is unexpectedly incomplete")

    mcu_pins = [row["MCU_Pin"] for row in pinmap]
    duplicates = sorted({pin for pin in mcu_pins if mcu_pins.count(pin) > 1})
    require(not duplicates, f"MCU pins are assigned more than once: {duplicates}")

    forbidden_absent = {"PB12", "PE1", "PC4", "PC5"}
    used_forbidden = sorted(forbidden_absent.intersection(mcu_pins))
    require(not used_forbidden, f"pins absent from STM32U585VITxQ Q-package are used: {used_forbidden}")

    by_net = {row["Net"]: row for row in pinmap}
    expected = {
        "PDM_CLK": ("PE9", "MDF1_CCK0"),
        "PDM_DATA1": ("PB1", "MDF1_SDI0"),
        "PDM_DATA2": ("PD6", "MDF1_SDI1"),
        "PDM_DATA3": ("PE7", "MDF1_SDI2"),
        "PDM_DATA4": ("PE4", "MDF1_SDI3"),
        "NOR_CLK": ("PE10", "OCTOSPIM_P1_CLK"),
        "NOR_NCS": ("PE11", "OCTOSPIM_P1_NCS"),
        "NOR_IO0": ("PE12", "OCTOSPIM_P1_IO0"),
        "NOR_IO1": ("PE13", "OCTOSPIM_P1_IO1"),
        "NOR_IO2": ("PE14", "OCTOSPIM_P1_IO2"),
        "NOR_IO3": ("PE15", "OCTOSPIM_P1_IO3"),
        "SD_D0": ("PC8", "SDMMC1_D0"),
        "SD_D1": ("PC9", "SDMMC1_D1"),
        "SD_D2": ("PC10", "SDMMC1_D2"),
        "SD_D3": ("PC11", "SDMMC1_D3"),
        "SD_CK": ("PC12", "SDMMC1_CK"),
        "SD_CMD": ("PD2", "SDMMC1_CMD"),
        "GNSS_TX": ("PA2", "USART2_TX"),
        "GNSS_RX": ("PA3", "USART2_RX"),
        "GNSS_PPS": ("PA0", "TIM2_CH1"),
        "LORA_NSS": ("PA4", "SPI1_NSS"),
        "LORA_SCK": ("PA5", "SPI1_SCK"),
        "LORA_MISO": ("PA6", "SPI1_MISO"),
        "LORA_MOSI": ("PA7", "SPI1_MOSI"),
        "LORA_DIO1": ("PC2", "GPIO"),
        "CELL_TX": ("PB6", "USART1_TX"),
        "CELL_RX": ("PB7", "USART1_RX"),
        "BLE_TX": ("PB10", "USART3_TX"),
        "BLE_RX": ("PB11", "USART3_RX"),
        "I2C2_SCL": ("PB13", "I2C2_SCL"),
        "I2C2_SDA": ("PB14", "I2C2_SDA"),
        "USB_DM": ("PA11", "USB_OTG_FS_DM"),
        "USB_DP": ("PA12", "USB_OTG_FS_DP"),
        "SWDIO": ("PA13", "DEBUG_JTMS-SWDIO"),
        "SWCLK": ("PA14", "DEBUG_JTCK-SWCLK"),
    }
    for net, (pin, signal) in expected.items():
        require(net in by_net, f"required net missing from Rev.A pin map: {net}")
        require(by_net[net]["MCU_Pin"] == pin, f"{net} expected on {pin}, got {by_net[net]['MCU_Pin']}")
        require(by_net[net]["CubeMX_Signal"] == signal, f"{net} signal mismatch")

    pdm = [by_net["PDM_CLK"], *(by_net[f"PDM_DATA{i}"] for i in range(1, 5))]
    require(all(row["External_Domain"] == "1V8" for row in pdm), "PDM external voltage domain must be 1V8")
    require(by_net["CELL_TX"]["External_Domain"] == "1V8", "BG95 main UART must remain a 1V8 external domain")
    require(by_net["CELL_RX"]["External_Domain"] == "1V8", "BG95 main UART must remain a 1V8 external domain")
    require("nRF52840" in by_net["BLE_TX"]["External_Device"], "BLE TX is not bound to nRF52840 module")
    require("nRF52840" in by_net["BLE_RX"]["External_Device"], "BLE RX is not bound to nRF52840 module")
    require("BLE_DFU_REQ" in by_net, "nRF52840 DFU request line missing")
    require(not any("ESP32-C3" in row["External_Device"] for row in pinmap), "ESP32-C3 remains active in Rev.A pin map")
    require(by_net["MIC_WAKE"]["MCU_Pin"] == "PA8", "MIC_WAKE must remain on PA8/EXTI8")
    require(by_net["LORA_DIO1"]["LQFP100_Pin"] == "17", "LORA_DIO1 PC2 package pin mismatch")
    require(by_net["MIC_WAKE"]["MCU_Pin"][2:] != by_net["LORA_DIO1"]["MCU_Pin"][2:], "MIC_WAKE and LORA_DIO1 share an EXTI line")

    target = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    require("source: hardware/EVT_PRE_20_PIN_MAP_REV_A.csv" in target, "firmware target does not bind Rev.A pin map")
    require("forbidden_absent_gpio: [PB12, PE1, PC4, PC5]" in target, "exact-package absent GPIO guard is missing")


def validate_hardware_baseline() -> None:
    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    target = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    kicad_readme = (ROOT / "hardware/kicad/README.md").read_text(encoding="utf-8")
    capture_spec = (ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md").read_text(encoding="utf-8")
    pwr_addendum = (ROOT / "hardware/kicad/REV_A_CAPTURE_ADDENDUM_002_PWR12_INA226.md").read_text(encoding="utf-8")
    gate = (ROOT / "hardware/PCB_DOUBLE_REVIEW_GATE.md").read_text(encoding="utf-8")

    require("mcu_exact_mpn: STM32U585VIT6Q" in baseline, "baseline MCU is not STM32U585VIT6Q")
    require("mcu: STM32U585VIT6Q" in target, "firmware target MCU does not match baseline")
    require("package: LQFP100_14x14" in target, "firmware target package does not match baseline")
    require("exact_pin_database_ref: STM32U585VITxQ" in target, "exact Q-package pin database ref missing")
    require("MCU: `STM32U585VIT6Q`" in kicad_readme, "KiCad active MCU is not explicit")
    require("MDBT50Q-P1MV2" in kicad_readme and "nRF52840" in kicad_readme, "KiCad active BLE module is not nRF52840")
    require("ESP32-C3-MINI-1-N4` is superseded" in kicad_readme, "superseded ESP32-C3 history is not documented")
    require("STM32U585CIU6" in kicad_readme and "superseded" in kicad_readme, "superseded 48-pin MCU history is not documented")
    require("Do not reintroduce" in kicad_readme and "BQ24650/CN3791" in kicad_readme, "obsolete charger prohibition is missing")
    require("STM32U585VIT6Q" in capture_spec, "capture spec missing current MCU")
    require("12-pin" in pwr_addendum and "INA226" in pwr_addendum, "Rev.A 12-pin/INA226 capture addendum missing")
    require("Review A" in gate and "Review B" in gate, "double-review PCB gate is incomplete")
    require("FOR_MANUFACTURE" in gate, "PCB release state is not defined")

    bom = {row["Item_ID"]: row for row in read_csv("hardware/EVT_PRE_20_BOM_DRAFT.csv")}
    require(bom["U1"]["MPN"] == "STM32U585VIT6Q", "BOM MCU does not match baseline")
    require(bom["U11"]["MPN"] == "MDBT50Q-P1MV2", "BOM BLE module does not match locked nRF52840 module")
    require("nRF52840" in bom["U11"]["Package"], "BOM BLE module package does not identify nRF52840")
    require(bom["MK1"]["MPN"] == "MMICT5838-00-012", "BOM microphone does not match exact orderable baseline")
    require(bom["U-MON-01"]["MPN"] == "INA226AIDGSR", "BOM total battery monitor is not INA226AIDGSR")
    require(bom["J-PWR-MAIN"]["MPN"] == "43045-1202", "PCB-MAIN PWR connector is not 12-pin Micro-Fit")
    require(bom["J-PWR-PWR"]["MPN"] == "43045-1202", "PCB-PWR MAIN connector is not 12-pin Micro-Fit")

    harness = read_csv("hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv")
    for index in range(1, 5):
        ref = f"J_MIC{index}"
        rows = [row for row in harness if row["Connector_Ref"] == ref]
        require([row["Pin"] for row in rows] == ["1", "2", "3", "4", "5", "6"], f"{ref} pin order mismatch")
        require(rows[0]["Net"] == "1V8_MIC" and rows[1]["Net"] == "GND", f"{ref} power pinout mismatch")
        require(rows[2]["Net"] == "PDM_CLK", f"{ref} clock pinout mismatch")
        require(rows[3]["Net"] == f"PDM_DATA{index}", f"{ref} data pinout mismatch")
        require(rows[4]["Net"] == f"MIC_WAKE{index}", f"{ref} AAD WAKE pinout mismatch")
        require(rows[5]["Net"] == "AAD_CFG", f"{ref} shared AAD_CFG/THSEL pinout mismatch")

    main_pwr = [row for row in harness if row["Interface"] == "MAIN_PWR"]
    require([row["Pin"] for row in main_pwr] == [str(i) for i in range(1, 13)], "MAIN-PWR is not the frozen 12-pin contract")
    require(main_pwr[10]["Net"] == "I2C2_SCL", "MAIN-PWR pin 11 must be I2C2_SCL")
    require(main_pwr[11]["Net"] == "I2C2_SDA", "MAIN-PWR pin 12 must be I2C2_SDA")
    require("INA226" in main_pwr[10]["Notes"] and "INA226" in main_pwr[11]["Notes"], "MAIN-PWR I2C rows are not bound to INA226")


def validate_policy_text() -> None:
    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    require("pilot_apn_policy: public_only" in baseline, "baseline public-only APN policy missing")
    require("pilot_primary_quantity: 20" in baseline, "baseline vacuum quantity missing")
    require("pilot_fallback_quantity_if_activated: 20" in baseline, "baseline 3D fallback quantity missing")
    require("authoritative_position_source: configured_installation_coordinates" in baseline, "configured installation coordinates are not authoritative")
    require("wifi_positioning_required: false" in baseline, "Wi-Fi positioning unexpectedly required")
    require("server_tdoa_station_position_source: configured_installation_coordinates" in baseline, "TDOA position source is not configured installation position")
    require("module_primary: Raytac_MDBT50Q-P1MV2" in baseline, "nRF52840 BLE module not locked in baseline")
    require("esp32_c3_status: SUPERSEDED_NOT_IN_REV_A" in baseline, "ESP32-C3 is not explicitly superseded")

    cellular = (ROOT / "config/cellular/dual_sim_apn_profiles.yaml").read_text(encoding="utf-8")
    require("pilot_apn_policy: public_only" in cellular, "cellular public-only policy missing")
    require("allowed_in_pilot: false" in cellular, "private APN is not explicitly disabled")

    android = (ROOT / "android/app/src/main/java/ru/dioneya/commissioning/core/StationModels.kt").read_text(encoding="utf-8")
    require("private_apn_not_allowed_in_pilot" in android, "Android private APN rejection missing")
    require("missing_installation_position" in android, "Android does not require installation position")
    require("PositionTrustPolicy" in android, "Android position trust policy model missing")

    position_doc = (ROOT / "protocols/POSITION_TIME_TRUST_REV_A.md").read_text(encoding="utf-8")
    require("installation_position" in position_doc, "position trust architecture missing installation position")
    require("GNSS_TIME_SUSPECT" in position_doc, "time trust is not separated from position trust")

    operational_files = [
        ROOT / "README.md",
        ROOT / "protocols/CELLULAR_CONNECTIVITY_BASELINE.md",
        ROOT / "manufacturing/LOT_SERIAL_REGISTER.csv",
        ROOT / "tests/EVT_MATRIX.csv",
    ]
    forbidden = [
        "PUBLIC_PRIMARY_PRIVATE_IF_PROVISIONED",
        "10 printed plus 10 vacuum cast",
        "public/private APN failover",
    ]
    for path in operational_files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            require(token not in text, f"superseded token in {path.relative_to(ROOT)}: {token}")


def main() -> None:
    validate_csv_shapes()
    validate_lot()
    validate_procurement()
    validate_decisions_and_tests()
    validate_pinmap()
    validate_hardware_baseline()
    validate_policy_text()
    print("EVT-PRE-20 configuration + exact-package hardware baseline: PASS")


if __name__ == "__main__":
    main()

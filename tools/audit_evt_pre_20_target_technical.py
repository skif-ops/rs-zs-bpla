#!/usr/bin/env python3
"""QG-2: independent technical audit of the EVT-PRE-20 STM32 target contract."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_PINMAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
ADDENDUM = ROOT / "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv"
BOARD_HEADER = ROOT / "firmware/targets/evt_pre_20/include/evt_pre_20_board_pins.h"
CLOCK_HEADER = ROOT / "firmware/targets/evt_pre_20/include/evt_pre_20_clock_policy.h"

GENERATED_ROW_PATTERN = re.compile(
    r'^\s*\{"(?P<net>[A-Z0-9_]+)",\s*"(?:\\.|[^\"])*",\s*'
    r"'(?P<port>[A-H])',\s*(?P<pin>\d+)u,\s*(?P<package>\d+)u,\s*"
    r'"(?P<signal>[A-Z0-9_\-]+)",\s*(?P<af>-?\d+),\s*'
    r"EVT_PRE_20_DIRECTION_(?P<direction>[A-Z_]+)\},$",
    re.MULTILINE,
)

AF_NUMBERS = {"GPIO": -1, "RCC": -2, "SYS": -3}

CRITICAL_ASSIGNMENTS = {
    "PDM_CLK": ("PE9", 37, "MDF1_CCK0", "AF6", "OUT"),
    "PDM_DATA1": ("PB1", 33, "MDF1_SDI0", "AF6", "IN"),
    "PDM_DATA2": ("PD6", 87, "MDF1_SDI1", "AF6", "IN"),
    "PDM_DATA3": ("PE7", 35, "MDF1_SDI2", "AF6", "IN"),
    "PDM_DATA4": ("PE4", 3, "MDF1_SDI3", "AF6", "IN"),
    "MIC_WAKE": ("PA8", 67, "GPIO", "GPIO", "IN"),
    "AAD_CFG": ("PA15", 77, "GPIO", "GPIO", "OUT"),
    "NOR_CLK": ("PE10", 38, "OCTOSPIM_P1_CLK", "AF10", "OUT"),
    "NOR_NCS": ("PE11", 39, "OCTOSPIM_P1_NCS", "AF10", "OUT"),
    "NOR_IO0": ("PE12", 40, "OCTOSPIM_P1_IO0", "AF10", "BIDIR"),
    "NOR_IO1": ("PE13", 41, "OCTOSPIM_P1_IO1", "AF10", "BIDIR"),
    "NOR_IO2": ("PE14", 42, "OCTOSPIM_P1_IO2", "AF10", "BIDIR"),
    "NOR_IO3": ("PE15", 43, "OCTOSPIM_P1_IO3", "AF10", "BIDIR"),
    "SD_D0": ("PC8", 65, "SDMMC1_D0", "AF12", "BIDIR"),
    "SD_D1": ("PC9", 66, "SDMMC1_D1", "AF12", "BIDIR"),
    "SD_D2": ("PC10", 78, "SDMMC1_D2", "AF12", "BIDIR"),
    "SD_D3": ("PC11", 79, "SDMMC1_D3", "AF12", "BIDIR"),
    "SD_CK": ("PC12", 80, "SDMMC1_CK", "AF12", "OUT"),
    "SD_CMD": ("PD2", 83, "SDMMC1_CMD", "AF12", "BIDIR"),
    "GNSS_TX": ("PA2", 24, "USART2_TX", "AF7", "OUT"),
    "GNSS_RX": ("PA3", 25, "USART2_RX", "AF7", "IN"),
    "GNSS_PPS": ("PA0", 22, "TIM2_CH1", "AF1", "IN"),
    "LORA_NSS": ("PA4", 28, "SPI1_NSS", "AF5", "OUT"),
    "LORA_SCK": ("PA5", 29, "SPI1_SCK", "AF5", "OUT"),
    "LORA_MISO": ("PA6", 30, "SPI1_MISO", "AF5", "IN"),
    "LORA_MOSI": ("PA7", 31, "SPI1_MOSI", "AF5", "OUT"),
    "LORA_DIO1": ("PC2", 17, "GPIO", "GPIO", "IN"),
    "CELL_TX": ("PB6", 92, "USART1_TX", "AF7", "OUT"),
    "CELL_RX": ("PB7", 93, "USART1_RX", "AF7", "IN"),
    "BLE_TX": ("PB10", 44, "USART3_TX", "AF7", "OUT"),
    "BLE_RX": ("PB11", 45, "USART3_RX", "AF7", "IN"),
    "I2C2_SCL": ("PB13", 52, "I2C2_SCL", "AF4", "BIDIR_OD"),
    "I2C2_SDA": ("PB14", 53, "I2C2_SDA", "AF4", "BIDIR_OD"),
    "PWR_GOOD": ("PD0", 81, "GPIO", "GPIO", "IN"),
    "PWR_FAULT": ("PD1", 82, "GPIO", "GPIO", "IN"),
    "EN_MODEM": ("PD4", 85, "GPIO", "GPIO", "OUT"),
    "EN_AUX": ("PD5", 86, "GPIO", "GPIO", "OUT"),
    "USB_DM": ("PA11", 70, "USB_OTG_FS_DM", "AF10", "BIDIR"),
    "USB_DP": ("PA12", 71, "USB_OTG_FS_DP", "AF10", "BIDIR"),
    "SWDIO": ("PA13", 72, "DEBUG_JTMS-SWDIO", "SYS", "BIDIR"),
    "SWCLK": ("PA14", 76, "DEBUG_JTCK-SWCLK", "SYS", "IN"),
    "BOOT0": ("PH3", 94, "GPIO", "GPIO", "IN"),
    "LSE_IN": ("PC14", 8, "RCC_OSC32_IN", "RCC", "IN"),
    "LSE_OUT": ("PC15", 9, "RCC_OSC32_OUT", "RCC", "OUT"),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def main() -> None:
    base_rows = load_csv(BASE_PINMAP)
    addendum_rows = load_csv(ADDENDUM)
    require(len(base_rows) == 64, f"base pin map expected 64 rows, got {len(base_rows)}")
    require(len(addendum_rows) == 1, f"AAD addendum expected one row, got {len(addendum_rows)}")
    require(addendum_rows[0]["Net"] == "AAD_CFG", "AAD addendum no longer defines AAD_CFG")

    rows = base_rows + addendum_rows
    by_net = {row["Net"]: row for row in rows}
    require(len(by_net) == 65, "net names are not unique")
    require(len({row["MCU_Pin"] for row in rows}) == 65, "MCU GPIO assignments overlap")
    require(len({row["LQFP100_Pin"] for row in rows}) == 65, "LQFP100 package pins overlap")

    for row in rows:
        gpio_match = re.fullmatch(r"P([A-H])(\d{1,2})", row["MCU_Pin"])
        require(gpio_match is not None and int(gpio_match.group(2)) <= 15, f"invalid GPIO {row['MCU_Pin']}")
        require(1 <= int(row["LQFP100_Pin"]) <= 100, f"invalid package pin {row['LQFP100_Pin']}")
        require(row["Direction_at_MCU"] in {"IN", "OUT", "BIDIR", "OUT_OD", "BIDIR_OD"}, f"bad direction for {row['Net']}")
        if row["AF"].startswith("AF"):
            require(0 <= int(row["AF"][2:]) <= 15, f"invalid AF for {row['Net']}")
        else:
            require(row["AF"] in {"GPIO", "RCC", "SYS"}, f"invalid AF marker for {row['Net']}")

    absent_q_package_pins = {"PB12", "PE1", "PC4", "PC5"}
    require(absent_q_package_pins.isdisjoint(row["MCU_Pin"] for row in rows), "absent Q-package GPIO used")

    for net, expected in CRITICAL_ASSIGNMENTS.items():
        require(net in by_net, f"critical net missing: {net}")
        row = by_net[net]
        actual = (
            row["MCU_Pin"],
            int(row["LQFP100_Pin"]),
            row["CubeMX_Signal"],
            row["AF"],
            row["Direction_at_MCU"],
        )
        require(actual == expected, f"critical assignment mismatch for {net}: {actual}")

    require(all(by_net[f"PDM_DATA{i}"]["External_Domain"] == "1V8" for i in range(1, 5)), "PDM data domain mismatch")
    require(by_net["PDM_CLK"]["External_Domain"] == "1V8", "PDM clock domain mismatch")
    require("THSEL" in by_net["AAD_CFG"]["Function"], "AAD_CFG is not bound to T5838 THSEL")
    require("INA226" in by_net["I2C2_SCL"]["External_Device"], "I2C2 SCL lost INA226 binding")
    require("INA226" in by_net["I2C2_SDA"]["External_Device"], "I2C2 SDA lost INA226 binding")
    exti_nets = ("LORA_DIO1", "ACCEL_INT", "TAMPER_IN", "MIC_WAKE")
    exti_lines = [int(by_net[net]["MCU_Pin"][2:]) for net in exti_nets]
    require(len(set(exti_lines)) == len(exti_lines), f"planned EXTI GPIO lines collide: {exti_lines}")

    board = BOARD_HEADER.read_text(encoding="utf-8")
    clock = CLOCK_HEADER.read_text(encoding="utf-8")
    require('#define EVT_PRE_20_MCU_MPN "STM32U585VIT6Q"' in board, "generated MCU identity mismatch")
    require('#define EVT_PRE_20_MCU_PACKAGE "LQFP100_14x14"' in board, "generated package identity mismatch")
    require("#define EVT_PRE_20_PIN_ASSIGNMENT_COUNT 65u" in board, "generated pin count mismatch")
    generated = {match.group("net"): match.groupdict() for match in GENERATED_ROW_PATTERN.finditer(board)}
    require(len(generated) == 65, f"generated technical rows expected 65, got {len(generated)}")
    for row in rows:
        net = row["Net"]
        require(net in generated, f"generated contract lost net {net}")
        actual = generated[net]
        af = int(row["AF"][2:]) if row["AF"].startswith("AF") else AF_NUMBERS[row["AF"]]
        expected = {
            "port": row["MCU_Pin"][1],
            "pin": str(int(row["MCU_Pin"][2:])),
            "package": str(int(row["LQFP100_Pin"])),
            "signal": row["CubeMX_Signal"],
            "af": str(af),
            "direction": row["Direction_at_MCU"],
        }
        require(
            all(actual[key] == value for key, value in expected.items()),
            f"generated technical mapping mismatch for {net}",
        )

    require('#define EVT_PRE_20_CLOCK_POLICY_ID "REV_A_INTERNAL_HSI_MSI_PLL_NO_HSE"' in clock, "clock policy id mismatch")
    require("#define EVT_PRE_20_EXTERNAL_HSE_ALLOWED 0" in clock, "external HSE must remain forbidden")
    require("#define EVT_PRE_20_LOW_SPEED_REFERENCE_HZ UINT32_C(32768)" in clock, "32.768 kHz reference mismatch")
    require("#define EVT_PRE_20_RUNTIME_CLOCK_FREQUENCIES_RELEASED 0" in clock, "unmeasured clock profiles were released")
    for profile in ("S0_SLEEP", "S1_LISTEN", "S2_DSP", "S3_COMMS", "S4_SERVICE"):
        require(f"EVT_PRE_20_CLOCK_PROFILE_{profile}" in clock, f"clock profile missing: {profile}")

    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    status = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    policy = (ROOT / "hardware/CLOCKING_REV_A.md").read_text(encoding="utf-8")
    require("mcu_exact_mpn: STM32U585VIT6Q" in baseline, "baseline MCU identity mismatch")
    require("mcu: STM32U585VIT6Q" in status and "package: LQFP100_14x14" in status, "target status identity mismatch")
    require("external_hse: DISABLED_NOT_FITTED" in status, "target status permits external HSE")
    require("shall not use an external HSE crystal or HSE oscillator" in policy, "source clock policy no longer forbids HSE")
    require("SiT1552AI-JE-DCC-32.768D" in policy, "source clock policy reference mismatch")
    require("do_not_release: true" in status, "incomplete target is not release-blocked")

    combined = (board + clock).lower()
    for forbidden in ("stm32u585ciu6", "stm32u585zit6q", "ufqfpn48", "lqfp144"):
        require(forbidden not in combined, f"foreign/superseded target marker leaked into contract: {forbidden}")

    print("EVT-PRE-20 target contract QG-2 independent technical audit: PASS")
    print("- package pins, unique EXTI sources, peripheral groups, I2C power binding and no-HSE clock policy verified")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""QG-2 independent technical audit of the EVT-PRE-20 CubeMX pinout IOC."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware/targets/evt_pre_20"
IOC = TARGET / "dioneya_evt_pre_20_rev_a.ioc"

CRITICAL = {
    "PDM_CLK": ("PE9", "MDF1_CCK0"),
    "PDM_DATA1": ("PB1", "MDF1_SDI0"),
    "PDM_DATA2": ("PD6", "MDF1_SDI1"),
    "PDM_DATA3": ("PE7", "MDF1_SDI2"),
    "PDM_DATA4": ("PE4", "MDF1_SDI3"),
    "MIC_WAKE": ("PA8", "GPXTI8"),
    "LORA_DIO1": ("PC2", "GPXTI2"),
    "LORA_TXEN": ("PB15", "GPIO_Output"),
    "LORA_RXEN": ("PD8", "GPIO_Output"),
    "GNSS_PPS": ("PA0", "S_TIM2_CH1"),
    "I2C2_SCL": ("PB13", "I2C2_SCL"),
    "I2C2_SDA": ("PB14", "I2C2_SDA"),
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
    "CELL_TX": ("PB6", "USART1_TX"),
    "CELL_RX": ("PB7", "USART1_RX"),
    "BLE_TX": ("PB10", "USART3_TX"),
    "BLE_RX": ("PB11", "USART3_RX"),
    "TEST_UART_RX": ("PC0", "LPUART1_RX"),
    "TEST_UART_TX": ("PC1", "LPUART1_TX"),
    "USB_VBUS": ("PA9", "USB_OTG_FS_VBUS"),
    "USB_DM": ("PA11", "USB_OTG_FS_DM"),
    "USB_DP": ("PA12", "USB_OTG_FS_DP"),
    "SWDIO": ("PA13 (JTMS/SWDIO)", "DEBUG_JTMS-SWDIO"),
    "SWCLK": ("PA14 (JTCK/SWCLK)", "DEBUG_JTCK-SWCLK"),
    "LSE_IN": ("PC14-OSC32_IN (PC14)", "RCC_OSC32_IN"),
    "LSE_OUT": ("PC15-OSC32_OUT (PC15)", "RCC_OSC32_OUT"),
}

REQUIRED_IPS = {
    "CORTEX_M33_NS",
    "I2C2",
    "LPUART1",
    "MDF1",
    "NVIC",
    "OCTOSPI1",
    "OCTOSPIM",
    "PWR",
    "RCC",
    "SDMMC1",
    "SPI1",
    "SYS",
    "TIM2",
    "USART1",
    "USART2",
    "USART3",
    "USB_OTG_FS",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def parse_ioc() -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in IOC.read_text(encoding="utf-8").splitlines():
        if raw and not raw.startswith("#"):
            key, value = raw.split("=", 1)
            require(key not in result, f"duplicate IOC key: {key}")
            result[key] = value
    return result


def normalize_pin_key(key: str) -> str:
    return key.replace(r"\ ", " ")


def main() -> None:
    require(IOC.is_file(), "generated CubeMX IOC missing")
    values = parse_ioc()
    require(values["Mcu.CPN"] == "STM32U585VIT6Q", "wrong MCU CPN")
    require(values["Mcu.Name"] == "STM32U585VITxQ", "wrong MCU database identity")
    require(values["Mcu.Package"] == "LQFP100", "wrong MCU package")
    require(values["Mcu.ContextProject"] == "TrustZoneDisabled", "engineering TrustZone context changed")

    ips = {
        value
        for key, value in values.items()
        if re.fullmatch(r"Mcu\.IP\d+", key)
    }
    require(ips == REQUIRED_IPS, f"IOC peripheral set mismatch: {sorted(ips ^ REQUIRED_IPS)}")
    require(int(values["Mcu.IPNb"]) == len(REQUIRED_IPS), "IOC peripheral count mismatch")

    label_to_pin: dict[str, str] = {}
    for key, label in values.items():
        if key.endswith(".GPIO_Label"):
            label_to_pin[label] = normalize_pin_key(key.removesuffix(".GPIO_Label"))
    require(len(label_to_pin) == 67, f"expected 67 labeled physical pins, got {len(label_to_pin)}")

    for net, (pin, signal) in CRITICAL.items():
        require(label_to_pin.get(net) == pin, f"critical IOC pin mismatch for {net}")
        encoded_pin = pin.replace(" ", r"\ ")
        require(values.get(f"{encoded_pin}.Signal") == signal, f"critical IOC signal mismatch for {net}")

    exti = {}
    for net in ("LORA_DIO1", "ACCEL_INT", "TAMPER_IN", "MIC_WAKE"):
        pin = label_to_pin[net]
        encoded_pin = pin.replace(" ", r"\ ")
        signal = values[f"{encoded_pin}.Signal"]
        match = re.fullmatch(r"GPXTI(\d+)", signal)
        require(match is not None, f"{net} is not configured as GPIO EXTI")
        exti[net] = int(match.group(1))
    require(exti == {"LORA_DIO1": 2, "ACCEL_INT": 6, "TAMPER_IN": 7, "MIC_WAKE": 8}, f"EXTI mapping mismatch: {exti}")
    require(len(set(exti.values())) == len(exti), "multiple GPIO ports compete for one EXTI line")
    require(label_to_pin["LORA_TXEN"] == "PB15", "LoRa TXEN output mapping drift")
    require(label_to_pin["LORA_RXEN"] == "PD8", "LoRa RXEN output mapping drift")
    require(values["PB15.PinState"] == "GPIO_PIN_RESET", "LoRa TXEN does not initialize LOW")
    require(values["PD8.PinState"] == "GPIO_PIN_RESET", "LoRa RXEN does not initialize LOW")

    require(values["PC14-OSC32_IN\\ (PC14).Mode"] == "LSE-External-Clock-Source", "LSE bypass source mode missing")
    require(values["PC15-OSC32_OUT\\ (PC15).Signal"] == "RCC_OSC32_OUT", "LSE output pin is not reserved")
    require(values["RCC.LSE_VALUE"] == "32768", "low-speed reference mismatch")
    require(values["RCC.SYSCLKSource"] == "RCC_SYSCLKSOURCE_MSI", "unreviewed high-speed clock selected")
    require(values["RCC.SYSCLKFreq_VALUE"] == "4000000", "engineering reset clock is not 4 MHz MSI")
    require("PWR.PowerMode" not in values, "unreviewed internal power mode was released")

    ioc_text = IOC.read_text(encoding="utf-8")
    for forbidden in (
        "HSE-External-Oscillator",
        "HSE-External-Clock-Source",
        "RCC_OSC_IN",
        "RCC_OSC_OUT",
        "STM32U585CIU6",
        "STM32U585ZIT6Q",
        "UFQFPN48",
        "LQFP144",
    ):
        require(forbidden not in ioc_text, f"forbidden IOC marker present: {forbidden}")

    contract = json.loads((TARGET / "cubemx_generation_contract.json").read_text(encoding="utf-8"))
    require(contract["release_gate"]["status"] == "BLOCKED", "IOC release block missing")
    require("opened and regenerated" in contract["release_gate"]["reason"], "CubeMX open/regenerate requirement missing")
    status = (TARGET / "target_status.yaml").read_text(encoding="utf-8")
    require("do_not_release: true" in status, "target is not release-blocked")
    require("CUBEMX_OPEN_REGENERATE_BLOCKER" in status, "target status lost CubeMX validation blocker")
    decisions = (ROOT / "docs/DECISION_LOG.csv").read_text(encoding="utf-8")
    require("DEC-022" in decisions and "PD8 to PC2" in decisions, "EXTI conflict decision is not traceable")
    require(
        "DEC-023" in decisions and "PB15 pin54 drives active-HIGH LORA_TXEN" in decisions
        and "PD8 pin55 drives active-HIGH LORA_RXEN" in decisions,
        "separate fail-closed LoRa RF-switch decision is not traceable",
    )

    print("EVT-PRE-20 CubeMX IOC QG-2 independent technical audit: PASS")
    print("- 67 pins, fail-closed LoRa TXEN/RXEN, 17 IPs, unique EXTI2/6/7/8 sources, no HSE and unreleased PWR/clock settings verified")


if __name__ == "__main__":
    main()

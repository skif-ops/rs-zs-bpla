#!/usr/bin/env python3
"""QG-2 independent technical audit of STM32U585 startup and memory scaffold."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware/targets/evt_pre_20"
STARTUP = TARGET / "vendor/cmsis_device_u5/startup_stm32u585xx.s"
SYSTEM = TARGET / "vendor/cmsis_device_u5/system_stm32u5xx.c"
LINKER = TARGET / "ld/STM32U585VITXQ_ENGINEERING_FLASH.ld"

EXPECTED_VENDOR_HASHES = {
    "startup_stm32u585xx.s": "4ae0cd22ada97562acab345fd37495c9129742ed01212402620e8054cdf8cda3",
    "system_stm32u5xx.c": "28d00434c85c76af756649577d6b2096f3810e2adb137203b5ebe4c33020622f",
}

CRITICAL_VECTORS = {
    "TIM2_IRQHandler",
    "I2C2_EV_IRQHandler",
    "I2C2_ER_IRQHandler",
    "SPI1_IRQHandler",
    "USART1_IRQHandler",
    "USART2_IRQHandler",
    "USART3_IRQHandler",
    "LPUART1_IRQHandler",
    "OTG_FS_IRQHandler",
    "OCTOSPI1_IRQHandler",
    "SDMMC1_IRQHandler",
    "MDF1_FLT0_IRQHandler",
    "MDF1_FLT1_IRQHandler",
    "MDF1_FLT2_IRQHandler",
    "MDF1_FLT3_IRQHandler",
    "LSECSSD_IRQHandler",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_size(value: str) -> int:
    match = re.fullmatch(r"(\d+)([KkMm]?)", value)
    require(match is not None, f"invalid linker length: {value}")
    scale = {"": 1, "K": 1024, "k": 1024, "M": 1024 * 1024, "m": 1024 * 1024}[match.group(2)]
    return int(match.group(1)) * scale


def linker_regions(text: str) -> dict[str, tuple[int, int]]:
    pattern = re.compile(
        r"^\s*(FLASH|RAM123|SRAM4)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*"
        r"(0x[0-9A-Fa-f]+),\s*LENGTH\s*=\s*(\d+[KkMm]?)\s*$",
        re.MULTILINE,
    )
    return {name: (int(origin, 16), parse_size(length)) for name, origin, length in pattern.findall(text)}


def main() -> None:
    require(sha256(STARTUP) == EXPECTED_VENDOR_HASHES[STARTUP.name], "official startup bytes changed")
    require(sha256(SYSTEM) == EXPECTED_VENDOR_HASHES[SYSTEM.name], "official system template bytes changed")

    startup = STARTUP.read_text(encoding="utf-8")
    require(".cpu cortex-m33" in startup and ".thumb" in startup, "startup architecture mismatch")
    require("startup_stm32u585xx.s" in startup, "startup device family mismatch")
    for symbol in ("_estack", "_sidata", "_sdata", "_edata", "_sbss", "_ebss"):
        require(symbol in startup, f"startup/linker symbol missing: {symbol}")
    for call in ("bl  SystemInit", "bl __libc_init_array", "bl\tmain"):
        require(call in startup, f"startup reset sequence missing: {call}")
    require("CopyDataInit:" in startup and "FillZerobss:" in startup, "startup data/BSS initialization missing")

    vector_body = startup.split("g_pfnVectors:", 1)[1].split(".size\tg_pfnVectors", 1)[0]
    vector_entries = [line.split(None, 1)[1] for line in vector_body.splitlines() if line.strip().startswith(".word")]
    require(len(vector_entries) == 142, f"STM32U585 vector count mismatch: {len(vector_entries)}")
    require(vector_entries[0] == "_estack" and vector_entries[1] == "Reset_Handler", "vector table prefix mismatch")
    require(CRITICAL_VECTORS.issubset(vector_entries), "target peripheral vector coverage incomplete")

    system = SYSTEM.read_text(encoding="utf-8")
    require('#include "stm32u5xx.h"' in system, "CMSIS system device header mismatch")
    require("uint32_t SystemCoreClock = 4000000U;" in system, "reset MSI clock mismatch")
    require("RCC->CR = RCC_CR_MSISON;" in system, "SystemInit does not force MSI reset source")
    require("RCC_CR_HSEON" in system and "RCC_CR_HSEBYP" in system, "SystemInit HSE reset handling missing")
    require("SCB->VTOR = FLASH_BASE | VECT_TAB_OFFSET" in system, "flash vector relocation missing")

    linker = LINKER.read_text(encoding="utf-8")
    regions = linker_regions(linker)
    require(regions == {
        "FLASH": (0x08000000, 2 * 1024 * 1024),
        "RAM123": (0x20000000, 768 * 1024),
        "SRAM4": (0x28000000, 16 * 1024),
    }, f"engineering linker regions mismatch: {regions}")
    require("ENTRY(Reset_Handler)" in linker, "linker entry point mismatch")
    require("KEEP(*(.isr_vector))" in linker and ".isr_vector : ALIGN(512)" in linker, "vector placement/alignment missing")
    require("_sidata = LOADADDR(.data);" in linker and "> RAM123 AT> FLASH" in linker, "initialized data mapping mismatch")
    require(".bss (NOLOAD)" in linker and ".retained (NOLOAD)" in linker, "BSS/retained semantics missing")
    require("> SRAM4" in linker and "RAM123 heap/stack collision" in linker, "SRAM4 or collision guard missing")

    memory = load_json(TARGET / "stm32_memory_contract.json")
    by_name = {region["name"]: region for region in memory["regions"]}
    require(by_name["FLASH"]["length_bytes"] == 2 * 1024 * 1024, "flash capacity mismatch")
    require(by_name["SRAM1"]["origin"] == "0x20000000" and by_name["SRAM1"]["length_bytes"] == 192 * 1024, "SRAM1 mismatch")
    require(by_name["SRAM2"]["origin"] == "0x20030000" and by_name["SRAM2"]["length_bytes"] == 64 * 1024, "SRAM2 mismatch")
    require(by_name["SRAM3"]["origin"] == "0x20040000" and by_name["SRAM3"]["length_bytes"] == 512 * 1024, "SRAM3 mismatch")
    require(by_name["SRAM4"]["origin"] == "0x28000000" and by_name["SRAM4"]["length_bytes"] == 16 * 1024, "SRAM4 mismatch")
    require(by_name["BKPSRAM"]["length_bytes"] == 2 * 1024, "backup SRAM mismatch")
    require(memory["combined_link_regions"][0]["length_bytes"] == 768 * 1024, "RAM123 combined size mismatch")

    cubemx = load_json(TARGET / "cubemx_generation_contract.json")
    require(cubemx["device"]["cpn"] == "STM32U585VIT6Q", "CubeMX CPN mismatch")
    require(cubemx["device"]["name"] == "STM32U585VITxQ", "CubeMX database device mismatch")
    require(cubemx["device"]["package"] == "LQFP100_14x14", "CubeMX package mismatch")
    require(cubemx["pin_assignment_count"] == 67, "CubeMX technical pin count mismatch")
    required_ips = {"MDF1", "OCTOSPI1", "OCTOSPIM", "SDMMC1", "USART1", "USART2", "USART3", "LPUART1", "SPI1", "I2C2", "TIM2", "USB_OTG_FS"}
    require(required_ips.issubset(cubemx["required_ips"]), "CubeMX peripheral set incomplete")
    clock = cubemx["clock_invariants"]
    require(clock["external_hse"] == "DISABLED_NOT_FITTED", "CubeMX preflight permits HSE")
    require(clock["low_speed_reference_hz"] == 32768, "CubeMX low-speed reference mismatch")
    require(clock["runtime_frequencies"] == "NOT_RELEASED_MEASUREMENT_REQUIRED", "unmeasured clocks were released")

    status = (TARGET / "target_status.yaml").read_text(encoding="utf-8")
    require("do_not_release: true" in status, "engineering scaffold is not release-blocked")
    require("secure_boot: MISSING_BLOCKER" in status and "ota_ab: MISSING_BLOCKER" in status, "production partition blockers missing")

    identity_text = linker + json.dumps(memory) + json.dumps(cubemx)
    for forbidden in ("STM32U585CIU6", "STM32U585ZIT6Q", "UFQFPN48", "LQFP144"):
        require(forbidden not in identity_text, f"foreign target identity leaked into scaffold: {forbidden}")

    print("EVT-PRE-20 STM32 scaffold QG-2 independent technical audit: PASS")
    print("- official 142-entry vector, reset flow, 2 MiB flash and 784 KiB system SRAM verified")


if __name__ == "__main__":
    main()

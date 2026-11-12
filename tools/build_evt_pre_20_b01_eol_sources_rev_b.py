#!/usr/bin/env python3
"""Build corrected Rev B machine-readable EOL sources for DIO-EVT-B01."""

from __future__ import annotations

import json

import build_evt_pre_20_b01_eol_sources as rev_a


PROGRAM_OUT = rev_a.MFG / "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_B.json"
REGISTER_OUT = rev_a.MFG / "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B.csv"


def corrected_steps() -> list[dict[str, object]]:
    steps = rev_a.build_steps()
    for item in steps:
        if item["test_id"] == "CELL-DBG-01":
            item.update(
                {
                    "action_ru": (
                        "После valid VREF подключить только вход изолированного UART 1,8 В "
                        "к TP_CELL_DBG.2 и GND к TP_CELL_DBG.5. Захватить boot или debug log "
                        "на 115200, 8N1. TP_CELL_DBG.3 оставить high-Z. AT, QFUPL, QFLST и "
                        "QSSLCFG через TP_CELL_DBG запрещены."
                    ),
                    "action_en": (
                        "After valid VREF connect only the isolated 1.8 V UART receiver to "
                        "TP_CELL_DBG.2 and ground to TP_CELL_DBG.5. Capture the boot or debug "
                        "log at 115200 8N1. Keep TP_CELL_DBG.3 high impedance. Do not issue AT, "
                        "QFUPL, QFLST or QSSLCFG through TP_CELL_DBG."
                    ),
                    "contacts": "2,5; contact 3 high-Z",
                    "instrument": "isolated 1.8 V UART receiver and log capture",
                    "metric": "bg95_debug_log",
                    "engineering_target": (
                        "Valid 1.8 V electrical levels; log captured when enabled; no framing "
                        "damage; absent optional debug output is recorded and is not a failure"
                    ),
                    "expected_discrete": "LOG_CAPTURED_OR_OUTPUT_DISABLED",
                    "evidence_required": "debug log or signed output-disabled record plus waveform",
                    "safety_note": (
                        "DEBUG UART is not the MAIN UART. Fixture TX remains high impedance. "
                        "Never send AT or TLS file-transfer commands through this header."
                    ),
                }
            )
        elif item["test_id"] == "LORA-01":
            item.update(
                {
                    "action_ru": (
                        "На J10 в проводной или экранированной оснастке прочитать подписанный "
                        "RF test profile DIONEA-RU868-v0.1 и проверить разрешенные центры каналов "
                        "864,1; 864,3; 864,5; 864,7; 864,9; 868,9 и 869,1 МГц, полосу 125 кГц, "
                        "SPI, целостность пакета, мощность, occupied bandwidth, spurious и duty-cycle. "
                        "Полевой TX должен остаться выключенным."
                    ),
                    "action_en": (
                        "At J10 in a conducted or shielded fixture read back the signed RF test "
                        "profile DIONEA-RU868-v0.1 and verify the allowed channel centers 864.1, "
                        "864.3, 864.5, 864.7, 864.9, 868.9 and 869.1 MHz, 125 kHz bandwidth, SPI, "
                        "packet integrity, power, occupied bandwidth, spurious emissions and duty "
                        "cycle. Field TX shall remain disabled."
                    ),
                    "engineering_target": (
                        "Accepted RU868 frequency plan and signed RF test profile; numerical RF "
                        "limits remain OPEN_B01_FREEZE until calibrated B01 measurements"
                    ),
                    "safety_note": (
                        "Use only a conducted or shielded RF setup with a 50 ohm load. Restore the "
                        "field profile with tx_enabled false after the test."
                    ),
                }
            )

    provision = rev_a.step(
        "CELL-MAIN-PROV-01",
        515,
        "BG95 MAIN UART provisioning",
        (
            "Через сервисную команду TEST_UART запустить функцию STM32, которая по штатному MAIN "
            "UART BG95 удаляет старые файлы, загружает dioneya-root, station.crt и station.key, "
            "проверяет размер и checksum, выполняет QFLST и read-back QSSLCFG. Закрытый ключ в лог "
            "не выводить."
        ),
        (
            "Use the TEST_UART service command to start the STM32 function that uses the normal "
            "BG95 MAIN UART to remove old files, upload dioneya-root, station.crt and station.key, "
            "verify size and checksum, run QFLST and read back QSSLCFG. Never print the private key "
            "to a log."
        ),
        "STM32 USART1 to BG95 MAIN UART",
        "U8 pads 34 and 35 through U16; not exposed to fixture",
        "released STM32 service command, TEST_UART and secure EOL file source",
        "bg95_tls_material_provisioning",
        "result",
        (
            "New signed target release contains the zs_bg95_provision binding; exact file names, "
            "sizes and checksums match; QSSLCFG read-back matches; secrets are absent from logs"
        ),
        expected_discrete="PASS",
        limit_state="SOFTWARE_INTEGRATION_PENDING",
        evidence="redacted service log, file metadata and QSSLCFG read-back",
        safety=(
            "Do not connect an external UART to the unexposed MAIN UART nets. Do not mark PASS "
            "until a newly signed target release implements and tests this binding."
        ),
    )
    steps.append(provision)
    steps.sort(key=lambda item: int(item["order"]))
    ids = [str(item["test_id"]) for item in steps]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate EOL test ID")
    return steps


def build_program() -> tuple[dict[str, object], list[dict[str, object]]]:
    contacts = rev_a.build_contact_map()
    steps = corrected_steps()
    program = rev_a.build_program(contacts, steps)
    program.update(
        {
            "program_id": "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_B",
            "revision": "B",
            "date": "2026-11-12",
            "status": "READY_FOR_FIXTURE_BUILD_SOFTWARE_INTEGRATION_AND_HARDWARE_RESULTS_PENDING",
            "references": {
                "operator_manual": "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx",
                "physical_program": "docs/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B.docx",
                "contact_map": "manufacturing/MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv",
            },
            "rev_b_changes": [
                "TP_CELL_DBG corrected to DEBUG UART log capture only",
                "TLS file provisioning assigned to STM32 over BG95 MAIN UART",
                "RU868 frequency plan fixed while field tx_enabled remains false pending RF PASS",
            ],
        }
    )
    return program, rev_a.build_register_rows(steps)


def audit(program: dict[str, object], register: list[dict[str, object]]) -> None:
    steps = {str(item["test_id"]): item for item in program["steps"]}
    debug = steps["CELL-DBG-01"]
    provision = steps["CELL-MAIN-PROV-01"]
    lora = steps["LORA-01"]
    assert "Run AT" not in str(debug)
    assert "Выполнить AT" not in str(debug)
    assert "Fixture TX remains high impedance" in str(debug["safety_note"])
    assert provision["limit_state"] == "SOFTWARE_INTEGRATION_PENDING"
    assert "station.key" in str(provision["action_ru"])
    assert "tx_enabled false" in str(lora["safety_note"])
    assert len(register) == len(program["steps"])
    serialized = json.dumps(program, ensure_ascii=False)
    if any(char in serialized for char in ("\u2013", "\u2014", "\u2011", "\u2212")):
        raise RuntimeError("forbidden dash in Rev B machine-readable program")


def main() -> None:
    program, register = build_program()
    audit(program, register)
    PROGRAM_OUT.write_text(
        json.dumps(program, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rev_a.write_csv(REGISTER_OUT, list(register[0]), register)
    print(f"wrote {PROGRAM_OUT} ({len(program['steps'])} steps)")
    print(f"wrote {REGISTER_OUT} ({len(register)} rows)")
    print("Rev B machine-readable EOL audit: PASS")


if __name__ == "__main__":
    main()

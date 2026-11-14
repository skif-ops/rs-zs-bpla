#!/usr/bin/env python3
"""Build the controlled contact map and machine-readable EOL program for DIO-EVT-B01."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MFG = ROOT / "manufacturing"
HW = ROOT / "hardware"
CONTACT_OUT = MFG / "MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv"
PROGRAM_OUT = MFG / "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json"
REGISTER_OUT = MFG / "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv"
BOARD_WIDTH_MM = 110.0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_contact_map() -> list[dict[str, object]]:
    pins = read_csv(HW / "PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv")
    pins += read_csv(HW / "PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv")
    mechanical = read_csv(HW / "PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv")
    groups = {"TP_EOL", "TP_MCU_SWD", "TP_BLE_SWD", "TP_CELL_USB", "TP_CELL_DBG"}
    pin_index: dict[tuple[str, str], dict[str, str]] = {}
    for item in pins:
        key = (item.get("RefDes", ""), item.get("Pin", ""))
        if key[0] in groups:
            if key in pin_index:
                raise ValueError(f"duplicate pin authority {key}")
            pin_index[key] = item

    rows: list[dict[str, object]] = []
    for item in mechanical:
        group = item.get("RefDes", "")
        contact = item.get("Contact", "")
        if group not in groups:
            continue
        authority = pin_index.get((group, contact))
        if authority is None:
            raise ValueError(f"missing electrical authority for {group}.{contact}")
        x_board = float(item["X_mm"])
        y_board = float(item["Y_mm"])
        rows.append(
            {
                "Fixture_Group": group,
                "Contact": int(contact),
                "Board_View_X_mm": f"{x_board:.2f}",
                "Board_View_Y_mm": f"{y_board:.2f}",
                "Bottom_Fixture_View_X_mm": f"{BOARD_WIDTH_MM - x_board:.2f}",
                "Bottom_Fixture_View_Y_mm": f"{y_board:.2f}",
                "Pad": item["Geometry"],
                "Pitch_mm": "2.54",
                "Pin_Name": authority["Pin_Name"],
                "Direction_at_DUT": authority["Direction"],
                "Net": authority["RevA_Net"],
                "Required_Network": authority["Required_Network"],
                "Safety_Class": safety_class(group, contact, authority["Direction"], authority["Pin_Name"]),
                "Initial_State": "NOT_RUN",
            }
        )
    rows.sort(key=lambda row: (str(row["Fixture_Group"]), int(row["Contact"])))
    expected = {"TP_EOL": 13, "TP_MCU_SWD": 5, "TP_BLE_SWD": 4, "TP_CELL_USB": 4, "TP_CELL_DBG": 5}
    actual = {group: sum(1 for row in rows if row["Fixture_Group"] == group) for group in expected}
    if actual != expected:
        raise ValueError(f"fixture contact count mismatch: {actual}")
    return rows


def safety_class(group: str, contact: str, direction: str, pin_name: str) -> str:
    if pin_name in {"GND", "GND_MODEM"}:
        return "GROUND_FIRST"
    if "SENSE" in direction or pin_name.startswith("VTREF") or pin_name.startswith("VSENSE") or pin_name == "VREF_1V8":
        return "SENSE_ONLY_NEVER_SOURCE"
    if group == "TP_CELL_USB" and contact == "1":
        return "ONLY_CONTROLLED_CURRENT_LIMITED_SOURCE"
    if pin_name == "BOOT0":
        return "DRIVE_ONLY_WHILE_NRST_ASSERTED"
    if pin_name == "USB_BOOT":
        return "CURRENT_LIMITED_1V8_RECOVERY_ONLY"
    if direction in {"INPUT", "DEBUG_INPUT"}:
        return "DRIVE_AFTER_VTREF_VALID"
    if direction in {"BIDIR_OD"}:
        return "OPEN_DRAIN_NO_EXTRA_PULLUP"
    return "HIGH_IMPEDANCE_UNTIL_DOMAIN_VALID"


def step(
    test_id: str,
    order: int,
    phase: str,
    action_ru: str,
    action_en: str,
    fixture_group: str = "",
    contacts: str = "",
    instrument: str = "",
    metric: str = "",
    unit: str = "",
    engineering_target: str = "",
    lower_limit: object = "",
    upper_limit: object = "",
    expected_discrete: str = "",
    limit_state: str = "APPROVED_DOCUMENTARY",
    evidence: str = "log_or_photo",
    safety: str = "",
) -> dict[str, object]:
    return {
        "test_id": test_id,
        "order": order,
        "phase": phase,
        "mandatory": True,
        "fixture_group": fixture_group,
        "contacts": contacts,
        "action_ru": action_ru,
        "action_en": action_en,
        "instrument": instrument,
        "metric": metric,
        "unit": unit,
        "engineering_target": engineering_target,
        "lower_limit": lower_limit,
        "upper_limit": upper_limit,
        "expected_discrete": expected_discrete,
        "limit_state": limit_state,
        "initial_status": "NOT_RUN",
        "evidence_required": evidence,
        "safety_note": safety,
    }


def build_steps() -> list[dict[str, object]]:
    rows = [
        step("FIX-ID-01", 10, "Оснастка", "Сверить ID MFG-004, ревизию, серийный номер, схему каналов и дату калибровки.", "Verify MFG-004 ID, revision, serial number, channel map and calibration date.", instrument="visual and registry", metric="identity_match", expected_discrete="MATCH"),
        step("FIX-CONT-01", 20, "Оснастка", "Без DUT измерить сопротивление каждого pogo до соответствующего контакта интерфейсного разъема.", "Without a DUT, measure resistance from every pogo pin to its interface connector contact.", instrument="4-wire DMM where available", metric="fixture_path_resistance", unit="ohm", upper_limit=1.0, engineering_target="<= 1 ohm including fixture leads", evidence="raw CSV and fixture serial"),
        step("FIX-ISO-01", 30, "Оснастка", "Без DUT проверить отсутствие замыкания каждого сигнального канала на соседние каналы и землю.", "Without a DUT, verify isolation from every signal channel to adjacent channels and ground.", instrument="insulation DMM, test voltage <= 5 V", metric="fixture_isolation", unit="ohm", lower_limit=10000000, engineering_target=">= 10 Mohm for fixture wiring only", evidence="raw CSV", safety="Do not perform insulation mode with a DUT installed."),
        step("FIX-MECH-01", 40, "Оснастка", "Проверить базирование по H1-H4, ориентационный ключ, совпадение 31 pogo с площадками и ход контактов.", "Verify H1-H4 datum, orientation key, alignment of all 31 pogo pins and contact travel.", instrument="optical inspection and feeler gauge", metric="alignment", expected_discrete="ALL_CONTACTS_ALIGNED", evidence="top and bottom fixture photos"),
        step("FIX-SAFE-01", 50, "Оснастка", "Проверить, что все выходы оснастки высокоомны до valid VTREF, а аварийное отключение снимает питание DUT и CELL_USB_VBUS.", "Verify all fixture outputs remain high impedance until valid VTREF and the emergency stop removes DUT and CELL_USB_VBUS power.", instrument="oscilloscope and DMM", metric="safe_state", expected_discrete="PASS", evidence="waveforms and interlock log"),
        step("PRE-ID-01", 100, "DUT до питания", "Сверить DIO-EVT-B01, station ID 901, tenant bench, PCB serials, ревизии и release manifest.", "Verify DIO-EVT-B01, station ID 901, bench tenant, PCB serials, revisions and release manifest.", instrument="traveller and manifest", metric="configuration_match", expected_discrete="MATCH", evidence="identity photo and manifest verification log"),
        step("PRE-R-3V3", 110, "DUT до питания", "Измерить сопротивление TP_EOL.2 относительно TP_EOL.1 на обесточенной плате.", "Measure resistance from TP_EOL.2 to TP_EOL.1 on the unpowered board.", "TP_EOL", "2-1", "DMM, low test voltage", "3V3_to_GND_resistance", "ohm", "Characterize and approve from B01 plus golden unit", limit_state="OPEN_B01_FREEZE", evidence="raw measurement and polarity"),
        step("PRE-R-3V8", 120, "DUT до питания", "Измерить сопротивление TP_EOL.3 относительно TP_EOL.1 на обесточенной плате.", "Measure resistance from TP_EOL.3 to TP_EOL.1 on the unpowered board.", "TP_EOL", "3-1", "DMM, low test voltage", "3V8_to_GND_resistance", "ohm", "Characterize and approve from B01 plus golden unit", limit_state="OPEN_B01_FREEZE", evidence="raw measurement and polarity"),
        step("PRE-R-1V8", 130, "DUT до питания", "Измерить сопротивление TP_EOL.4 относительно TP_EOL.1 на обесточенной плате.", "Measure resistance from TP_EOL.4 to TP_EOL.1 on the unpowered board.", "TP_EOL", "4-1", "DMM, low test voltage", "1V8_to_GND_resistance", "ohm", "Characterize and approve from B01 plus golden unit", limit_state="OPEN_B01_FREEZE", evidence="raw measurement and polarity"),
        step("PWR-IN-01", 200, "Первое питание", "Подать питание через штатный J_PWR_IN от лабораторного источника с утвержденным ограничением тока. Зафиксировать пусковой и установившийся ток.", "Power through the normal J_PWR_IN input using a current-limited bench supply. Record inrush and steady current.", instrument="bench supply, current logger, thermal camera", metric="input_current", unit="A", engineering_target="10.0 to 14.6 V provisional input envelope; current limit from approved power traveller", limit_state="OPEN_B01_FREEZE", evidence="current trace and thermal image", safety="Stop immediately on current limit, odor, hot spot or reset loop."),
        step("PWR-3V3-01", 210, "Первое питание", "Измерить 3V3_DIGITAL на TP_EOL.2 относительно TP_EOL.1 во время старта и после стабилизации.", "Measure 3V3_DIGITAL at TP_EOL.2 relative to TP_EOL.1 during startup and steady state.", "TP_EOL", "2-1", "oscilloscope plus DMM", "3V3_DIGITAL", "V", "3.3 V nominal", limit_state="OPEN_B01_FREEZE", evidence="startup waveform and settled value"),
        step("PWR-3V8-01", 220, "Первое питание", "Измерить 3V8_MODEM на TP_EOL.3 относительно TP_EOL.1 в состояниях modem off, startup и traffic burst.", "Measure 3V8_MODEM at TP_EOL.3 relative to TP_EOL.1 with modem off, during startup and during a traffic burst.", "TP_EOL", "3-1", "oscilloscope plus DMM", "3V8_MODEM", "V", "3.8 V nominal; every U8 VBAT pad must remain >= 3.3 V in EVT-PWR-01", lower_limit=3.3, limit_state="PARTIAL_APPROVED_MIN_ONLY", evidence="off, startup and burst waveforms"),
        step("PWR-1V8-01", 230, "Первое питание", "Измерить 1V8_MIC на TP_EOL.4 относительно TP_EOL.1 в AAD idle, PDM start и active capture.", "Measure 1V8_MIC at TP_EOL.4 relative to TP_EOL.1 in AAD idle, PDM startup and active capture.", "TP_EOL", "4-1", "oscilloscope plus DMM", "1V8_MIC", "V", "1.8 V nominal", limit_state="OPEN_B01_FREEZE", evidence="idle, transition and active waveforms"),
        step("PWR-GOOD-01", 240, "Первое питание", "Наблюдать TP_EOL.7 относительно TP_EOL.1. Не подавать сигнал извне.", "Observe TP_EOL.7 relative to TP_EOL.1. Do not drive this contact.", "TP_EOL", "7-1", "logic analyzer or oscilloscope", "PWR_GOOD_sequence", "V and ms", "inactive until rails are valid, then stable active state per PCB-PWR contract", limit_state="OPEN_B01_FREEZE", evidence="synchronized rail and PWR_GOOD waveform", safety="Sense only."),
        step("PWR-FAULT-01", 250, "Первое питание", "Наблюдать TP_EOL.8 относительно TP_EOL.1 при нормальном запуске и разрешенной имитации отказа.", "Observe TP_EOL.8 relative to TP_EOL.1 during normal startup and an approved fault injection.", "TP_EOL", "8-1", "logic analyzer or oscilloscope", "FAULT_sequence", "V and ms", "inactive in normal operation and active for the approved known fault", limit_state="OPEN_B01_FREEZE", evidence="normal and fault waveforms", safety="Sense only. Use a safe fault simulator."),
        step("REV-STRAP-01", 300, "Идентификация платы", "Считать TP_EOL.10 и TP_EOL.11 относительно TP_EOL.1 и сопоставить REV0/REV1 с traveller.", "Read TP_EOL.10 and TP_EOL.11 relative to TP_EOL.1 and match REV0/REV1 to the traveller.", "TP_EOL", "10-1 and 11-1", "logic analyzer or DMM", "revision_strap", "logic", "Exact strap code from released PCB revision", expected_discrete="MATCH_TRAVELLER", evidence="readback log", safety="Sense only."),
        step("UART-IDLE-01", 310, "TEST UART", "Измерить idle уровень выхода DUT_TX на TP_EOL.5 относительно TP_EOL.1 до подключения приемника оснастки.", "Measure DUT_TX idle level at TP_EOL.5 relative to TP_EOL.1 before connecting the fixture receiver.", "TP_EOL", "5-1", "oscilloscope", "uart_idle_level", "V", "3.3 V logic domain", limit_state="OPEN_B01_FREEZE", evidence="idle waveform"),
        step("UART-LINK-01", 320, "TEST UART", "После valid VTREF подключить прием оснастки к TP_EOL.5 и 3.3 V tolerant выход оснастки к TP_EOL.6. Выполнить help, identity и self-test.", "After valid VTREF, connect the fixture receiver to TP_EOL.5 and a 3.3 V tolerant fixture output to TP_EOL.6. Run help, identity and self-test.", "TP_EOL", "5,6,1", "isolated 3.3 V UART", "uart_exchange", "result", "No framing error; exact identity; required self-tests return PASS", expected_discrete="PASS", evidence="complete UART log", safety="Fixture TX remains high impedance until TP_EOL.2 is valid."),
        step("I2C-INA-01", 330, "I2C2", "Через TP_EOL.12 и TP_EOL.13 выполнить guarded open-drain scan и чтение INA226 по адресу 0x40.", "Use TP_EOL.12 and TP_EOL.13 for a guarded open-drain scan and INA226 readback at address 0x40.", "TP_EOL", "12,13,1", "isolated open-drain I2C adapter", "ina226_readback", "result", "INA226 0x40 responds and readings agree with reference instrument within the approved calibration limit", limit_state="OPEN_B01_FREEZE", evidence="I2C trace and comparison CSV", safety="Do not add pull-ups unless separately enabled and documented."),
        step("BOOT0-SAFE-01", 340, "STM32 recovery", "Подтвердить high-Z TP_EOL.9 при свободном NRST. Для recovery сначала прижать NRST на TP_MCU_SWD.4, затем задать BOOT0 через TP_EOL.9, отпустить NRST и после старта вернуть BOOT0 в high-Z.", "Confirm TP_EOL.9 is high impedance while NRST is released. For recovery assert NRST at TP_MCU_SWD.4, drive BOOT0 through TP_EOL.9, release NRST and return BOOT0 to high impedance after startup.", "TP_EOL and TP_MCU_SWD", "9 and 4", "current-limited 3.3 V control", "boot0_recovery", "result", "System memory enumerates and normal boot recovers after BOOT0 release", expected_discrete="PASS", evidence="control waveform and recovery log", safety="Never drive BOOT0 unless NRST is asserted first."),
        step("STM-VTREF-01", 400, "STM32 SWD", "Измерить TP_MCU_SWD.1 относительно TP_MCU_SWD.5. ST-LINK не должен питать DUT.", "Measure TP_MCU_SWD.1 relative to TP_MCU_SWD.5. ST-LINK must not power the DUT.", "TP_MCU_SWD", "1-5", "DMM and ST-LINK VTREF sense", "stm32_vtref", "V", "3.3 V logic domain", limit_state="OPEN_B01_FREEZE", evidence="VTREF value and probe serial", safety="Sense only."),
        step("STM-SWD-01", 410, "STM32 SWD", "Подключить 5 GND, 1 VTREF, 4 NRST, 2 SWDIO, 3 SWCLK. Считать device ID и option bytes, затем program, verify и cold boot.", "Connect 5 GND, 1 VTREF, 4 NRST, 2 SWDIO and 3 SWCLK. Read device ID and option bytes, then program, verify and cold boot.", "TP_MCU_SWD", "1-5", "ST-LINK", "stm32_program_verify", "result", "STM32U585VIT6Q, exact bench option-byte profile, exact image SHA-256 and verify PASS", expected_discrete="PASS", evidence="programmer log, option bytes before and after"),
        step("NRF-VTREF-01", 420, "nRF52840 SWD", "Измерить TP_BLE_SWD.1 относительно TP_BLE_SWD.4. Отладчик не должен питать DUT.", "Measure TP_BLE_SWD.1 relative to TP_BLE_SWD.4. The debugger must not power the DUT.", "TP_BLE_SWD", "1-4", "DMM and nRF probe VTREF sense", "nrf_vtref", "V", "3.3 V logic domain", limit_state="OPEN_B01_FREEZE", evidence="VTREF value and probe serial", safety="Sense only."),
        step("NRF-SWD-01", 430, "nRF52840 SWD", "Подключить 4 GND, 1 VTREF, 2 NRF_SWDIO, 3 NRF_SWCLK. Выполнить erase, program merged.hex, verify, reset и MCUboot signed image check.", "Connect 4 GND, 1 VTREF, 2 NRF_SWDIO and 3 NRF_SWCLK. Erase, program merged.hex, verify, reset and check the MCUboot signed image.", "TP_BLE_SWD", "1-4", "nRF probe", "nrf_program_verify", "result", "Exact nRF target and signed/merged image hashes; verify and BLE startup PASS", expected_discrete="PASS", evidence="programmer and MCUboot logs"),
        step("CELL-VREF-01", 500, "BG95 debug", "После штатного включения BG95 измерить VREF_1V8 на TP_CELL_DBG.1 относительно TP_CELL_DBG.5.", "After normal BG95 power-up, measure VREF_1V8 at TP_CELL_DBG.1 relative to TP_CELL_DBG.5.", "TP_CELL_DBG", "1-5", "DMM and oscilloscope", "bg95_vref", "V", "1.8 V modem I/O domain", limit_state="OPEN_B01_FREEZE", evidence="power sequence waveform", safety="Sense only. All debug outputs remain high impedance until VREF is valid."),
        step("CELL-DBG-01", 510, "BG95 debug", "После valid VREF подключить 1.8 V tolerant RX оснастки к TP_CELL_DBG.2 и 1.8 V output оснастки к TP_CELL_DBG.3. Выполнить AT и прочитать версию.", "After valid VREF, connect the fixture 1.8 V tolerant RX to TP_CELL_DBG.2 and the 1.8 V fixture output to TP_CELL_DBG.3. Run AT and read the version.", "TP_CELL_DBG", "2,3,5", "isolated 1.8 V UART", "bg95_debug_uart", "result", "AT returns OK and the approved BG95 identity/version is recorded", expected_discrete="PASS", evidence="redacted AT log"),
        step("CELL-BOOT-01", 520, "BG95 recovery", "В обычном режиме проверить LOW на TP_CELL_DBG.4. Для recovery подать current-limited 1.8 V HIGH только по утвержденной последовательности power-on, затем вернуть high-Z.", "Verify LOW at TP_CELL_DBG.4 in normal operation. For recovery apply a current-limited 1.8 V HIGH only during the approved power-on sequence, then return high impedance.", "TP_CELL_DBG", "4-5", "current-limited 1.8 V driver and oscilloscope", "usb_boot_sequence", "result", "Normal LOW and recovery enumeration PASS", expected_discrete="PASS", evidence="USB_BOOT, VREF and power waveform", safety="Never apply 3.3 V. Normal fixture state is high impedance."),
        step("CELL-USB-01", 530, "BG95 recovery", "Подключить TP_CELL_USB.4 к modem ground, затем differential D+ к .2, D- к .3 и только после этого current-limited HOST_VBUS к .1. Проверить recovery USB enumeration.", "Connect TP_CELL_USB.4 to modem ground, then differential D+ to .2, D- to .3 and only then current-limited HOST_VBUS to .1. Verify recovery USB enumeration.", "TP_CELL_USB", "4,2,3,1", "isolated USB 2.0 recovery port", "bg95_usb_enumeration", "result", "BG95 recovery interface enumerates and remains isolated from J11", expected_discrete="PASS", evidence="USB descriptor log and current trace", safety="TP_CELL_USB.1 is the only allowed fixture source in the pogo groups. Never join it to J11 VBUS."),
        step("CELL-ISO-01", 540, "BG95 recovery", "При снятом питании проверить отсутствие непрерывности между TP_CELL_USB D+/D-/VBUS и J11 USB_DP/USB_DM/USB_VBUS_CONN.", "With power removed verify no continuity between TP_CELL_USB D+/D-/VBUS and J11 USB_DP/USB_DM/USB_VBUS_CONN.", "TP_CELL_USB and J11", "1-3 and J11", "DMM, low test voltage", "usb_domain_isolation", "result", "NO_CONTINUITY", expected_discrete="NO_CONTINUITY", evidence="isolation record", safety="Power removed."),
        step("MIC-PWR-01", 600, "PCB-MIC 3+1", "На J_MIC1-J_MIC4 измерить pin 1 1V8_MIC относительно pin 2 GND в AAD idle и active PDM.", "At J_MIC1-J_MIC4 measure pin 1 1V8_MIC relative to pin 2 GND in AAD idle and active PDM.", "J_MIC1-J_MIC4", "1-2", "oscilloscope plus DMM", "mic_supply", "V", "1.8 V nominal on all four harnesses", limit_state="OPEN_B01_FREEZE", evidence="four-channel rail CSV"),
        step("MIC-CLK-01", 610, "PCB-MIC 3+1", "На pin 3 каждого J_MIC измерить общий PDM_CLK относительно pin 2, включая запуск и останов для AAD.", "At pin 3 of every J_MIC measure common PDM_CLK relative to pin 2, including AAD start and stop.", "J_MIC1-J_MIC4", "3-2", "4-channel oscilloscope", "pdm_clock", "Hz and V", "Clock exceeds 50 kHz during THSEL/PDM operation; final frequency and edges use approved target limit", lower_limit=50000, limit_state="PARTIAL_APPROVED_MIN_ONLY", evidence="clock waveform"),
        step("MIC-DATA-01", 620, "PCB-MIC 3+1", "Проверить PDM_DATA1-4 на pin 4 J_MIC1-4, отсутствие dropout и соответствие физическому MIC1-MIC4.", "Verify PDM_DATA1-4 at pin 4 of J_MIC1-4, no dropouts and correct physical MIC1-MIC4 mapping.", "J_MIC1-J_MIC4", "4-2", "logic analyzer and acoustic fixture", "mic_channel_mapping", "result", "Four distinct channels, correct 3+1 mapping, zero dropout in the approved capture", limit_state="OPEN_B01_FREEZE", evidence="WAV, mapping CSV and scope trace"),
        step("MIC-WAKE-01", 630, "PCB-MIC 3+1", "На pin 5 J_MIC1-4 измерить MIC_WAKE1-4 и проверить агрегированное пробуждение PA8 при калиброванном событии.", "At pin 5 of J_MIC1-4 measure MIC_WAKE1-4 and verify aggregate PA8 wake on a calibrated event.", "J_MIC1-J_MIC4", "5-2", "oscilloscope and acoustic fixture", "aad_wake", "ms and count", "Every valid event wakes the station; false wake and latency meet approved acoustic limits", limit_state="OPEN_B01_FREEZE", evidence="wake waveforms and event log"),
        step("MIC-CFG-01", 640, "PCB-MIC 3+1", "На pin 6 J_MIC1-4 проверить общий AAD_CFG/THSEL, stop symbol и возврат линии в штатное состояние.", "At pin 6 of J_MIC1-4 verify common AAD_CFG/THSEL, the stop symbol and return to the normal state.", "J_MIC1-J_MIC4", "6-2", "oscilloscope", "aad_cfg_timing", "us and V", "T5838 protocol timing and common-bus behavior pass", limit_state="OPEN_B01_FREEZE", evidence="decoded THSEL waveform"),
        step("STO-01", 700, "Память", "Через self-test проверить QSPI JEDEC/SFDP, microSD detect, CID, write/read SHA-256 и восстановление после прерванной записи.", "Use self-test to verify QSPI JEDEC/SFDP, microSD detect, CID, write/read SHA-256 and interrupted-write recovery.", instrument="station UART and controlled power cut", metric="storage_test", unit="result", engineering_target="W25Q512JV EF 40 20, 64 MiB; approved industrial microSD", expected_discrete="PASS", evidence="UART log and file hashes"),
        step("RF-LOAD-01", 800, "RF", "До передачи установить 50 ohm loads или утвержденные антенны на J8 LTE, J9 GNSS и J10 LoRa. Сверить U.FL и кабели.", "Before transmission install 50 ohm loads or approved antennas at J8 LTE, J9 GNSS and J10 LoRa. Verify U.FL connectors and cables.", "J8/J9/J10", "center and shield", "VNA or approved RF fixture", "rf_fixture_identity", "result", "Correct port, cable, load and region", expected_discrete="PASS", evidence="setup photo and fixture calibration", safety="No LTE or LoRa transmission into an open connector."),
        step("GNSS-PPS-01", 810, "GNSS", "Подключить GNSS к J9, получить fix и измерить PPS/time quality и holdover.", "Connect GNSS at J9, obtain a fix and measure PPS/time quality and holdover.", "J9 plus station diagnostics", "RF center/shield", "GNSS simulator or approved antenna, oscilloscope", "pps_accuracy_holdover", "us and s", "Limits approved after B01 characterization", limit_state="OPEN_B01_FREEZE", evidence="GNSS log and PPS waveform"),
        step("LORA-01", 820, "LoRa", "На J10 в conducted или экранированной оснастке проверить RU868 profile, SPI, packet integrity, frequency and power. Вне стенда TX запрещен.", "At J10 in a conducted or shielded fixture verify the RU868 profile, SPI, packet integrity, frequency and power. TX is prohibited outside the fixture.", "J10", "RF center/shield", "spectrum analyzer and LoRa peer", "lora_rf", "Hz and dBm", "Approved RU868 limits", limit_state="OPEN_B01_FREEZE", evidence="spectrum and packet log", safety="Use conducted or shielded RF setup only."),
        step("CELL-NET-01", 830, "LTE и сервер", "На J8 с утвержденной антенной или нагрузкой выполнить attach, TLS, MQTT, heartbeat, event, receipt, reconnect и SIM failover в tenant bench.", "At J8 with an approved antenna or load run attach, TLS, MQTT, heartbeat, event, receipt, reconnect and SIM failover in the bench tenant.", "J8 and station UART", "RF center/shield", "cellular test setup and dioneya.ru bench", "cellular_end_to_end", "result", "Exact B01 identity; CA and hostname verified; event stored once; no effect on production tenant", expected_discrete="PASS", evidence="redacted modem, station and server logs"),
        step("AB-ROLLBACK-01", 900, "Прошивка", "Проверить signed A/B update, interruption at 10, 30, 70 and 99 percent, trial, confirmation, watchdog rollback and BOOT0/SWD recovery.", "Verify signed A/B update, interruption at 10, 30, 70 and 99 percent, trial, confirmation, watchdog rollback and BOOT0/SWD recovery.", instrument="power interrupter, UART, SWD", metric="ab_rollback", unit="result", engineering_target="All fault injections recover without unsigned boot", expected_discrete="PASS", evidence="power trace and boot records"),
        step("EOL-SELFTEST-01", 910, "Полный EOL", "Запустить полный self-test 1-13, сохранить CBOR/декодированный результат и failed mask.", "Run complete self-test IDs 1-13 and save the CBOR/decoded result and failed mask.", instrument="TEST_UART or authenticated BLE diagnostics", metric="selftest_registry", unit="result", engineering_target="All required registered tests PASS; failed mask 0", expected_discrete="PASS", evidence="raw CBOR, decoded JSON and station log"),
        step("EOL-REGRESSION-01", 920, "Полный EOL", "Выполнить все обязательные EOL, полный регрессионный прогон, проверить evidence и хэши, затем получить две независимые подписи.", "Complete all mandatory EOL tests, full regression, evidence and hash verification, then obtain two independent approvals.", instrument="released EOL system", metric="overall_qualification", unit="result", engineering_target="No OPEN, NOT_RUN, FAIL or HOLD mandatory row", expected_discrete="PASS", evidence="signed register and evidence manifest"),
    ]
    ids = [item["test_id"] for item in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate EOL test ID")
    return rows


def build_program(contacts: list[dict[str, object]], steps: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema": 1,
        "program_id": "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A",
        "revision": "A",
        "date": "2026-10-09",
        "status": "READY_FOR_FIXTURE_BUILD_AND_B01_EXECUTION_RESULTS_NOT_RUN",
        "unit": {"serial": "DIO-EVT-B01", "station_id": 901, "tenant": "bench"},
        "release_id": "EVT_PRE_20_BENCH_RELEASE_2026100601",
        "fixture": {
            "id": "MFG-004",
            "contact_count": len(contacts),
            "board_datum": "PCB top-view coordinate system, origin at board lower-left, X right, Y up",
            "bottom_fixture_transform": "X_fixture = 110.00 - X_board; Y_fixture = Y_board",
            "mounting_holes": [
                {"id": "H1", "x_mm": 8.0, "y_mm": 5.0, "diameter_mm": 3.2},
                {"id": "H2", "x_mm": 105.0, "y_mm": 5.0, "diameter_mm": 3.2},
                {"id": "H3", "x_mm": 105.0, "y_mm": 70.0, "diameter_mm": 3.2},
                {"id": "H4", "x_mm": 5.0, "y_mm": 70.0, "diameter_mm": 3.2},
            ],
        },
        "contacts": contacts,
        "allowed_statuses": ["NOT_RUN", "MEASURED", "PASS", "FAIL", "HOLD"],
        "decision_policy": {
            "initial": "NOT_RUN",
            "pass_requires": [
                "every mandatory row PASS",
                "every mandatory numeric limit approved",
                "instrument and calibration identity recorded",
                "evidence path and SHA-256 recorded",
                "operator and independent reviewer recorded",
                "fixture MSA PASS",
                "full regression PASS",
            ],
            "undefined_limit_result": "HOLD",
            "firmware_lock_authorization": "DENIED_UNTIL_SEPARATE_PRODUCTION_RELEASE",
        },
        "steps": steps,
        "msa": [
            {"id": "MSA-REP-01", "action": "10 repeated full fixture runs on the same B01 or golden unit without reseating", "acceptance": "repeatability limits approved and met", "status": "NOT_RUN"},
            {"id": "MSA-REPRO-01", "action": "3 operators, 3 reseats each, same unit", "acceptance": "operator and reseat effects within approved limits", "status": "NOT_RUN"},
            {"id": "MSA-MIC-01", "action": "known-fault sample with two microphone channels swapped", "acceptance": "mapping test fails and identifies channels", "status": "NOT_RUN"},
            {"id": "MSA-RF-01", "action": "known-fault sample with absent RF load", "acceptance": "interlock blocks transmission or test fails before TX", "status": "NOT_RUN"},
            {"id": "MSA-REGION-01", "action": "known-fault wrong LoRa region profile", "acceptance": "profile test fails closed", "status": "NOT_RUN"},
            {"id": "MSA-STO-01", "action": "known-fault damaged or fault-injected storage", "acceptance": "storage test fails and data is not reported delivered", "status": "NOT_RUN"},
            {"id": "MSA-TLS-01", "action": "known-fault invalid TLS chain or hostname", "acceptance": "connection rejected", "status": "NOT_RUN"},
            {"id": "MSA-ID-01", "action": "known-fault serial or station-ID mismatch", "acceptance": "identity gate fails before provisioning", "status": "NOT_RUN"},
        ],
    }


def build_register_rows(steps: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for item in steps:
        result.append(
            {
                **item,
                "attempt": 1,
                "actual_value": "",
                "actual_text": "",
                "approved_lower_limit": item["lower_limit"],
                "approved_upper_limit": item["upper_limit"],
                "approved_discrete": item["expected_discrete"],
                "instrument_id": "",
                "calibration_due": "",
                "evidence_path": "",
                "evidence_sha256": "",
                "operator": "",
                "reviewer": "",
                "timestamp_utc": "",
                "status": "NOT_RUN",
                "ncr_or_deviation": "",
                "notes": "",
            }
        )
    return result


def main() -> None:
    MFG.mkdir(parents=True, exist_ok=True)
    contacts = build_contact_map()
    steps = build_steps()
    contact_fields = list(contacts[0])
    write_csv(CONTACT_OUT, contact_fields, contacts)
    PROGRAM_OUT.write_text(json.dumps(build_program(contacts, steps), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    register = build_register_rows(steps)
    write_csv(REGISTER_OUT, list(register[0]), register)
    print(f"wrote {CONTACT_OUT} ({len(contacts)} contacts)")
    print(f"wrote {PROGRAM_OUT} ({len(steps)} steps)")
    print(f"wrote {REGISTER_OUT} ({len(register)} rows)")


if __name__ == "__main__":
    main()

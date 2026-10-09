#!/usr/bin/env python3
"""Create the self-contained DIO-EVT-B01 and MFG-004 EOL package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "EVT_PRE_20_DIO_EVT_B01_И_EOL_ОСНАСТКА_20261009_REV_A.zip"
ZIP_TIME = (2026, 10, 9, 12, 0, 0)


FILES = {
    "01_Программа_B01/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_A.docx": ROOT / "docs/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_A.docx",
    "01_Программа_B01/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_A.md": ROOT / "docs/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_A.md",
    "01_Программа_B01/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_PROTOCOL_REV_A.docx": ROOT / "docs/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_PROTOCOL_REV_A.docx",
    "01_Программа_B01/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_PROTOCOL_REV_A.md": ROOT / "docs/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_PROTOCOL_REV_A.md",
    "02_EOL_оснастка_MFG_004/MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.pdf": ROOT / "manufacturing/MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.pdf",
    "02_EOL_оснастка_MFG_004/MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.dxf": ROOT / "manufacturing/MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.dxf",
    "02_EOL_оснастка_MFG_004/MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv": ROOT / "manufacturing/MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv",
    "02_EOL_оснастка_MFG_004/MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json": ROOT / "manufacturing/MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json",
    "02_EOL_оснастка_MFG_004/EOL_TEST_SPEC.md": ROOT / "manufacturing/EOL_TEST_SPEC.md",
    "02_EOL_оснастка_MFG_004/EOL_SOFTWARE_LIMITS_REV_A.json": ROOT / "manufacturing/EOL_SOFTWARE_LIMITS_REV_A.json",
    "03_Распиновка_и_подключение/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md": ROOT / "hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md",
    "03_Распиновка_и_подключение/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv": ROOT / "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv",
    "03_Распиновка_и_подключение/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv": ROOT / "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv",
    "03_Распиновка_и_подключение/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv": ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv",
    "03_Распиновка_и_подключение/HARNESS_LOGICAL_PINOUT_REV_A.csv": ROOT / "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv",
    "03_Распиновка_и_подключение/CONNECTOR_FREEZE_REV_A.csv": ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv",
    "04_Прошивка_и_восстановление/EVT_PRE_20_BENCH_RELEASE_2026100601.zip": ROOT / "outputs/EVT_PRE_20_BENCH_RELEASE_2026100601.zip",
    "04_Прошивка_и_восстановление/bench_release_contract.json": ROOT / "firmware/targets/evt_pre_20/release/bench_release_contract.json",
    "04_Прошивка_и_восстановление/option_bytes_bench_rev_a.json": ROOT / "firmware/targets/evt_pre_20/release/option_bytes_bench_rev_a.json",
    "04_Прошивка_и_восстановление/firmware_lock_interlock_rev_a.json": ROOT / "firmware/targets/evt_pre_20/release/firmware_lock_interlock_rev_a.json",
    "04_Прошивка_и_восстановление/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.docx": ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.docx",
    "04_Прошивка_и_восстановление/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.md": ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.md",
    "05_Формы_результатов/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx": ROOT / "manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx",
    "05_Формы_результатов/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv": ROOT / "manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv",
    "05_Формы_результатов/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.xlsx": ROOT / "manufacturing/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.xlsx",
    "05_Формы_результатов/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.json": ROOT / "manufacturing/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.json",
    "05_Формы_результатов/EOL_RESULT_REGISTER.csv": ROOT / "manufacturing/EOL_RESULT_REGISTER.csv",
    "05_Формы_результатов/UNIT_PASSPORT_TEMPLATE.csv": ROOT / "manufacturing/UNIT_PASSPORT_TEMPLATE.csv",
    "05_Формы_результатов/INCOMING_INSPECTION_PLAN.csv": ROOT / "manufacturing/INCOMING_INSPECTION_PLAN.csv",
    "06_Методики_EVT/EVT_MASTER_PLAN.md": ROOT / "tests/EVT_MASTER_PLAN.md",
    "06_Методики_EVT/EVT_MATRIX.csv": ROOT / "tests/EVT_MATRIX.csv",
    "06_Методики_EVT/EVT_AUD_SI_REV_A.md": ROOT / "tests/EVT_AUD_SI_REV_A.md",
    "07_Проверяющие_утилиты/build_evt_pre_20_b01_eol_sources.py": ROOT / "tools/build_evt_pre_20_b01_eol_sources.py",
    "07_Проверяющие_утилиты/build_evt_pre_20_b01_physical_eol_doc.py": ROOT / "tools/build_evt_pre_20_b01_physical_eol_doc.py",
    "07_Проверяющие_утилиты/build_evt_pre_20_b01_eol_measurement_xlsx.mjs": ROOT / "tools/build_evt_pre_20_b01_eol_measurement_xlsx.mjs",
    "07_Проверяющие_утилиты/build_mfg004_eol_fixture_drawing.py": ROOT / "tools/build_mfg004_eol_fixture_drawing.py",
    "07_Проверяющие_утилиты/validate_evt_pre_20_b01_eol_package.py": ROOT / "tools/validate_evt_pre_20_b01_eol_package.py",
    "07_Проверяющие_утилиты/validate_evt_pre_20_b01_hardware_qualification.py": ROOT / "tools/validate_evt_pre_20_b01_hardware_qualification.py",
    "07_Проверяющие_утилиты/package_evt_pre_20_b01_eol_fixture.py": ROOT / "tools/package_evt_pre_20_b01_eol_fixture.py",
}


README = """DIO-EVT-B01 и EOL оснастка MFG-004 Rev A
Дата: 09.10.2026

Состав:
1. Операционная программа физической квалификации DIO-EVT-B01.
2. PDF и DXF контактной плиты MFG-004, карта 31 pogo контакта и machine-readable program.
3. Точная распиновка, координаты, жгуты и правила подключения.
4. Подписанный стендовый release EVT_PRE_20_BENCH_RELEASE_2026100601.
5. XLSX и CSV реестры измерений, B01 qualification form и формы evidence.
6. EVT master plan, matrix и acoustic SI method.
7. Проверяющие и воспроизводящие утилиты.

Порядок:
1. Начать с 01_Программа_B01.
2. Изготовить и принять оснастку по 02_EOL_оснастка_MFG_004.
3. Сверить каждый контакт по 03_Распиновка_и_подключение.
4. Проверить SHA-256 стендового release до прошивки.
5. Заполнять основной реестр XLSX в 05_Формы_результатов.
6. Сохранять raw evidence и SHA-256 каждой записи.

Текущее состояние: физические испытания и MSA NOT_RUN. Прошивка не блокируется. OPEN_B01_FREEZE дает HOLD, а не PASS.

English summary
This archive is the controlled physical qualification and EOL fixture package for DIO-EVT-B01. It includes the MFG-004 drill template, the exact 31-contact map, the signed bench software release, the measurement register and verification tools. Physical results and fixture MSA are NOT RUN. Undefined mandatory limits produce HOLD. Firmware locking remains denied until a separate production release is approved.
"""


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def main() -> None:
    missing = [str(path) for path in FILES.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing package files:\n" + "\n".join(missing))
    payloads = {name: path.read_bytes() for name, path in FILES.items()}
    payloads["00_Опись/README_RU_EN.txt"] = README.encode("utf-8")
    manifest = {
        "schema": 1,
        "package_id": "EVT_PRE_20_DIO_EVT_B01_EOL_FIXTURE_20261009_REV_A",
        "status": "READY_FOR_FIXTURE_BUILD_AND_B01_EXECUTION_RESULTS_NOT_RUN",
        "physical_results": "NOT_RUN",
        "fixture_msa": "NOT_RUN",
        "firmware_lock": "DENIED",
        "files": [
            {"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(payloads.items())
        ],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    payloads["00_Опись/MANIFEST.json"] = manifest_bytes
    checksums = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(payloads.items())
    ).encode("utf-8")
    payloads["00_Опись/SHA256SUMS.txt"] = checksums
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w") as archive:
        for name, data in sorted(payloads.items()):
            archive.writestr(zip_info(name), data)
    print(f"wrote {OUTPUT}")
    print(f"files {len(payloads)}")
    print(f"sha256 {hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()

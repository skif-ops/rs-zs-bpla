#!/usr/bin/env python3
"""Validate the software-complete EVT-PRE-20 Rev D instruction set."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import zipfile

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
MANUAL_MD = ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.md"
MANUAL_DOCX = ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx"
EOL_MD = ROOT / "docs/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B.md"
EOL_DOCX = ROOT / "docs/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B.docx"
PROGRAM = ROOT / "manufacturing/MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_B.json"
REGISTER_CSV = ROOT / "manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B.csv"
REGISTER_XLSX = ROOT / "manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B.xlsx"
ARCHIVE = ROOT / "outputs/EVT_PRE_20_DIO_EVT_B01_И_EOL_ОСНАСТКА_20261112_REV_B.zip"
TARGET_STATUS = ROOT / "firmware/targets/evt_pre_20/target_status.yaml"
LORA_PROFILE = ROOT / "config/lora/RU868.yaml"
PACKAGE_BUILDERS = (
    ROOT / "tools/build_evt_pre20_rev_e_package.py",
    ROOT / "tools/package_evt_pre_20_b01_eol_fixture.py",
)
FORBIDDEN_DASHES = ("\u2013", "\u2014", "\u2011", "\u2212")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: Path) -> str:
    require(path.is_file(), f"missing file: {path}")
    return path.read_text(encoding="utf-8-sig")


def audit_docx(path: Path, revision: str) -> None:
    require(path.is_file(), f"missing DOCX: {path}")
    document = Document(path)
    text_parts: list[str] = []
    for index, paragraph in enumerate(document.paragraphs, 1):
        if not paragraph.text:
            continue
        text_parts.append(paragraph.text)
        require(paragraph.paragraph_format.line_spacing == 1.0, f"DOCX line spacing {path.name}:{index}")
        for run in paragraph.runs:
            if not run.text:
                continue
            require(run.font.name == "Times New Roman", f"DOCX font {path.name}:{index}")
            require(run.font.size is not None and round(run.font.size.pt, 1) == 14.0,
                    f"DOCX font size {path.name}:{index}")
    for table_index, table in enumerate(document.tables, 1):
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    text_parts.append(paragraph.text)
                    require(paragraph.paragraph_format.line_spacing == 1.0,
                            f"DOCX table spacing {path.name}:{table_index}")
                    for run in paragraph.runs:
                        if not run.text:
                            continue
                        require(run.font.name == "Times New Roman",
                                f"DOCX table font {path.name}:{table_index}")
                        require(run.font.size is not None and round(run.font.size.pt, 1) == 12.0,
                                f"DOCX table font size {path.name}:{table_index}")
    combined = "\n".join(text_parts)
    require(revision in combined, f"DOCX revision missing: {path.name}")
    require(not any(char in combined for char in FORBIDDEN_DASHES),
            f"forbidden dash in {path.name}")


def audit_program() -> None:
    program = json.loads(read(PROGRAM))
    require(program["program_id"] == "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_B",
            "unexpected EOL program ID")
    require(program["revision"] == "B", "unexpected EOL revision")
    steps = {item["test_id"]: item for item in program["steps"]}
    require(len(steps) == 43, "unexpected EOL step count")
    debug = steps["CELL-DBG-01"]
    require("DEBUG UART is not the MAIN UART" in debug["safety_note"],
            "BG95 DEBUG UART distinction missing")
    require("Run AT" not in json.dumps(debug, ensure_ascii=False),
            "AT command remains on TP_CELL_DBG")
    provision = steps["CELL-MAIN-PROV-01"]
    require(provision["limit_state"] == "SOFTWARE_INTEGRATION_PENDING",
            "BG95 target binding is not held pending")
    require(all(name in provision["action_ru"] for name in ("dioneya-root", "station.crt", "station.key")),
            "BG95 TLS file set incomplete")
    lora = steps["LORA-01"]
    require("tx_enabled false" in lora["safety_note"], "LoRa field TX interlock missing")

    with REGISTER_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(len(rows) == len(steps), "CSV and JSON step counts differ")
    require({row["test_id"] for row in rows} == set(steps), "CSV and JSON test IDs differ")
    require(REGISTER_XLSX.is_file() and REGISTER_XLSX.stat().st_size > 10000,
            "Rev B XLSX register missing or empty")


def audit_archive() -> None:
    require(ARCHIVE.is_file(), f"missing Rev B archive: {ARCHIVE}")
    with zipfile.ZipFile(ARCHIVE) as archive:
        names = set(archive.namelist())
        required = {
            "01_Программа_B01/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B.docx",
            "02_EOL_оснастка_MFG_004/MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_B.json",
            "04_Прошивка_и_восстановление/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx",
            "05_Формы_результатов/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B.xlsx",
            "00_Опись/MANIFEST.json",
            "00_Опись/SHA256SUMS.txt",
        }
        require(required <= names, "Rev B archive is missing required files")
        manifest = json.loads(archive.read("00_Опись/MANIFEST.json"))
        require(manifest["package_id"] == "EVT_PRE_20_DIO_EVT_B01_EOL_FIXTURE_20261112_REV_B",
                "unexpected archive package ID")
        for item in manifest["files"]:
            payload = archive.read(item["path"])
            require(len(payload) == item["size"], f"archive size mismatch: {item['path']}")
            require(hashlib.sha256(payload).hexdigest() == item["sha256"],
                    f"archive hash mismatch: {item['path']}")
        checksum_lines = archive.read("00_Опись/SHA256SUMS.txt").decode("utf-8").splitlines()
        for line in checksum_lines:
            digest, name = line.split("  ", 1)
            require(hashlib.sha256(archive.read(name)).hexdigest() == digest,
                    f"SHA256SUMS mismatch: {name}")


def main() -> None:
    manual = read(MANUAL_MD)
    eol = read(EOL_MD)
    for text, label in ((manual, "manual"), (eol, "EOL document")):
        require(not any(char in text for char in FORBIDDEN_DASHES), f"forbidden dash in {label}")
    for token in (
        "Матрица применения приборов и инструментов",
        "TP_CELL_DBG` подключен к DEBUG UART",
        "SOFTWARE INTEGRATION PENDING",
        "Частотный план RU868 утвержден",
        "полевой `tx_enabled` остается false",
    ):
        require(token in manual, f"manual token missing: {token}")
    for token in (
        "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_B.json",
        "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B.xlsx",
        "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B.csv",
    ):
        require(token in eol, f"Rev B EOL reference missing: {token}")
    audit_docx(MANUAL_DOCX, "Rev D")
    audit_docx(EOL_DOCX, "Rev B")
    audit_program()
    audit_archive()

    target = read(TARGET_STATUS)
    require("status: BENCH_RELEASE_BUILT_HARDWARE_VALIDATION_PENDING" in target,
            "target hardware-pending status changed")
    require("firmware_lock: FORBIDDEN_HARDWARE_VALIDATION_PENDING" in target,
            "firmware lock interlock weakened")
    require("tls_material_provisioning: PORTABLE_QFUPL_QFLST_QSSLCFG_STATE_MACHINE_HOST_TEST_PASS_TARGET_SERVICE_BINDING_SECURE_FILE_SOURCE_AND_SIGNED_RELEASE_PENDING" in target,
            "BG95 target-binding status missing")
    require("frequency_plan_decision: ACCEPTED_FOR_EVT_PRE_20" in target,
            "accepted RU868 decision missing from target status")
    require(
        "tx_enabled: false" in target
        or "tx_enabled: SIGNED_FIELD_PROFILE_ONLY_DEFAULT_OFF" in target,
        "target LoRa field TX unexpectedly enabled",
    )

    lora = read(LORA_PROFILE)
    require("decision: ACCEPTED_FOR_EVT_PRE_20" in lora, "RU868 decision missing")
    require("tx_enabled: false" in lora, "RU868 field TX unexpectedly enabled")
    require("max_eirp_dbm: null" in lora and "duty_cycle: null" in lora,
            "unverified RU868 numeric limits were introduced")

    builder_text = "\n".join(read(path) for path in PACKAGE_BUILDERS)
    for token in (
        "EVT_PRE_20_DIO_EVT_B01_И_EOL_ОСНАСТКА_20261112_REV_B.zip",
        "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D",
        "EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B",
        "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_B",
        "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B",
    ):
        require(token in builder_text, f"package builder reference missing: {token}")
    print("EVT-PRE-20 firmware documentation and EOL Rev D/Rev B gate: PASS")
    print("Software-complete status: PASS with BG95 signed target binding explicitly pending")
    print("Hardware qualification, RF numeric limits and firmware locking remain pending")


if __name__ == "__main__":
    main()

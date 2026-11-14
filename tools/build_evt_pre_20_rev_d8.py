from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
D7 = ROOT / "releases" / "EVT_PRE_20_REV_D7" / "Архивы"
OUT = ROOT / "releases" / "EVT_PRE_20_REV_D8"
ARCHIVES = OUT / "Архивы"
DOCS_OUT = OUT / "Документы_REV_D8"
SOURCE_COMMIT = "5be7569149c5bb5e03fbbdd69bfe7ac7f6486c14"
RELEASE_ID = "EVT_PRE_20_REV_D8"
DATE = "2026-10-16"
PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def safe_reset(path: Path) -> None:
    resolved = path.resolve()
    releases = (ROOT / "releases").resolve()
    if resolved.parent != releases or resolved.name != "EVT_PRE_20_REV_D8":
        raise RuntimeError(f"unsafe release reset target: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def inherited_entries(source: Path, old_root: str, new_root: str, exclude_suffixes: tuple[str, ...]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(source) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in inherited archive {source}: {bad}")
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not name.startswith(old_root + "/"):
                raise RuntimeError(f"unexpected root in {source}: {name}")
            if any(name.endswith(suffix) for suffix in exclude_suffixes):
                continue
            result[new_root + name[len(old_root):]] = archive.read(info)
    return result


def add_file(entries: dict[str, bytes], archive_name: str, source: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    entries[archive_name] = source.read_bytes()


def add_tree(entries: dict[str, bytes], archive_prefix: str, source: Path) -> None:
    for path in sorted(p for p in source.rglob("*") if p.is_file()):
        relative = path.relative_to(source).as_posix()
        entries[f"{archive_prefix.rstrip('/')}/{relative}"] = path.read_bytes()


def add_manifest(entries: dict[str, bytes], root: str) -> None:
    name = f"{root}/MANIFEST_SHA256_REV_D8.txt"
    entries.pop(name, None)
    lines = [f"{sha256_bytes(data)}  {path}" for path, data in sorted(entries.items())]
    entries[name] = ("\r\n".join(lines) + "\r\n").encode("utf-8")


def remove_private_key_test_fixtures(entries: dict[str, bytes]) -> list[str]:
    removed: list[str] = []
    for name, data in list(entries.items()):
        if any(marker in data for marker in PRIVATE_KEY_MARKERS):
            if "/tests/" not in name.lower():
                raise RuntimeError(f"private key marker outside a test fixture: {name}")
            entries.pop(name)
            removed.append(name)
    return removed


def write_zip(path: Path, entries: dict[str, bytes]) -> None:
    directories: set[str] = set()
    for name in entries:
        parent = PurePosixPath(name).parent
        while str(parent) not in (".", ""):
            directories.add(str(parent) + "/")
            parent = parent.parent
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        for directory in sorted(directories, key=lambda value: (value.count("/"), value)):
            info = zipfile.ZipInfo(directory, date_time=(2026, 10, 16, 12, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (0o40755 << 16) | 0x10
            archive.writestr(info, b"")
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 16, 12, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def release_readme(scope: str) -> bytes:
    return f"""EVT-PRE-20 REV_D8 — {scope}
Дата / Date: {DATE}
Привязка исходников / Source binding: {SOURCE_COMMIT}

RU
Комплект наследует проверенный REV_D7 и добавляет подписанный release candidate 2026101601,
актуальные инструкции по сборке, прошивке, установке, B01/EOL формы и явную фиксацию
PCB-MAIN 8L, PCB-PWR 4L, PCB-MIC 2L. KiCad не включён в основной и Altium архивы;
исходники KiCad сохранены в Git и истории. Закрытые ключи, keystore и пароли отсутствуют.

Программа EVT состоит из двух групп по 20 станций и одной стендовой станции, всего 41.
Зарезервированы DIO-EVT-001...040 и DIO-EVT-B01. Закупка представлена двумя вариантами:
21 станция (один EVT-20 плюс стендовая) и 41 станция (два EVT-20 плюс стендовая).
Число 21 в форме EOL также встречается как количество открытых критериев и не означает
общий объём программы.

Статус: комплект документов и программных артефактов готов для закупки, EVT-сборки,
заказа прототипов и измерений. Окончательные числовые EOL-пределы, DFM/first article,
полная аппаратная квалификация и производственная блокировка остаются открыты до
измерений собранной DIO-EVT-B01 и последующих станций. Неопределённый обязательный
предел или отсутствующее evidence дают HOLD, а не PASS.

EN
This package inherits the verified REV_D7 handoff and adds signed release candidate
2026101601, current assembly/firmware/installation instructions, B01/EOL forms, and
the fixed stackups PCB-MAIN 8L, PCB-PWR 4L and PCB-MIC 2L. KiCad sources are retained
in Git/history and are excluded from the main and Altium factory archives. No private
key, keystore or password is included.

The EVT program has two groups of 20 stations plus one bench station, 41 total, with
DIO-EVT-001...040 and DIO-EVT-B01 reserved. Procurement is provided as two options:
21 stations (one EVT-20 lot plus the bench) and 41 stations (two EVT-20 lots plus the
bench). The value 21 in the EOL form is also the open-criteria count and is not the
program station quantity.

The document and software handoff is ready for procurement, EVT assembly, prototype
ordering and measurement. Final numeric EOL limits, vendor DFM/first article, full
hardware qualification and production firmware locking remain open until measurements
on assembled DIO-EVT-B01/stations are completed. An undefined mandatory limit or
missing evidence produces HOLD.
""".encode("utf-8")


safe_reset(OUT)
ARCHIVES.mkdir(parents=True)
DOCS_OUT.mkdir(parents=True)

candidate = ROOT / "releases" / "evt-pre-20" / "2026-10-16-release-candidate-2026101601"
docs = ROOT / "docs"
mfg = ROOT / "manufacturing"
tools = ROOT / "tools"

# Altium factory archive. Hardware content is inherited byte-for-byte from REV_D7;
# the wrapper records the new package revision and current release status.
altium = inherited_entries(
    D7 / "EVT_PRE_20_REV_D7_ALTIUM.zip",
    "EVT_D7_ALTIUM",
    "EVT_D8_ALTIUM",
    ("MANIFEST_SHA256_REV_D7.txt",),
)
altium["EVT_D8_ALTIUM/README_FIRST_RU_EN.txt"] = release_readme("Altium PCB/PCBA factory package")
altium_meta = {
    "release_id": RELEASE_ID,
    "scope": "ALTIUM_PCB_PCBA_FACTORY_HANDOFF",
    "date": DATE,
    "source_commit": SOURCE_COMMIT,
    "inherited_hardware_release": "EVT_PRE_20_REV_D7",
    "stackup_layers": {"PCB-MAIN": 8, "PCB-PWR": 4, "PCB-MIC": 2},
    "native_format": "Altium Designer",
    "kicad_in_archive": False,
    "status": "EVT_FACTORY_HANDOFF_VENDOR_DFM_AND_FIRST_ARTICLE_REQUIRED",
    "equivalence_claim": "No unchecked cross-tool equivalence is asserted; use the included reviewed Altium/CAM artifacts and close vendor DFM/first article gates.",
}
altium["EVT_D8_ALTIUM/00_Задание_для_фабрики/release_metadata_rev_d8.json"] = (
    json.dumps(altium_meta, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
add_manifest(altium, "EVT_D8_ALTIUM")
altium_zip = ARCHIVES / "EVT_PRE_20_REV_D8_ALTIUM.zip"
write_zip(altium_zip, altium)

# Full production/assembly handoff.
full = inherited_entries(
    D7 / "EVT_PRE_20_REV_D7_FULL.zip",
    "EVT_D7",
    "EVT_D8",
    (
        "MANIFEST_SHA256_REV_D7.txt",
        "EVT_PRE_20_ПЛАТЫ_ЗАКАЗ_И_МОНТАЖ_ALTIUM_20261016_REV_D7.zip",
        "BOM_EVT_PRE_20_REV_D7.csv",
        "BOM_EVT_PRE_20_REV_D7.xlsx",
        "ЗАКУПОЧНАЯ_BOM_EVT_PRE_20_REV_D7.csv",
    ),
)
full["EVT_D8/README_FIRST_RU_EN.txt"] = release_readme("full procurement and production handoff")
for source_name, archive_name in (
    ("EVT_PRE_20_BOM_REV_A.csv", "BOM_EVT_PRE_20_REV_D8.csv"),
    ("EVT_PRE_20_BOM_REV_A.xlsx", "BOM_EVT_PRE_20_REV_D8.xlsx"),
    ("EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv", "ЗАКУПОЧНАЯ_BOM_EVT_PRE_20_REV_D8.csv"),
):
    add_file(full, f"EVT_D8/02_Закупка_и_BOM/{archive_name}", ROOT / "hardware" / source_name)
for name in (
    "EVT_PRE_20_BOM_REV_A.csv",
    "EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
    "EVT_PRE_20_BOM_PRICE_ESTIMATE_REV_A.csv",
    "EVT_PROGRAM_PROCUREMENT_VARIANTS_REV_A.csv",
    "EVT_PROGRAM_1X20_PLUS_1_PROCUREMENT_REV_A.csv",
    "EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv",
):
    add_file(full, f"EVT_D8/02_Закупка_и_BOM/Исходные_таблицы/{name}", ROOT / "hardware" / name)
for extension in ("docx", "pdf"):
    name = f"EVT_PRE_20_PROCUREMENT_VARIANTS_21_41_NOTICE_REV_D8.{extension}"
    add_file(full, f"EVT_D8/02_Закупка_и_BOM/{name}", docs / name)
for name in (
    "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_A",
    "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_A",
):
    add_file(full, f"EVT_D8/06_Сборка_станций/00_Руководство/{name}.docx", docs / f"{name}.docx")
    add_file(full, f"EVT_D8/06_Сборка_станций/00_Руководство/{name}.pdf", docs / f"{name}.pdf")
add_file(full, "EVT_D8/07_Контроль/00_Программа/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx", docs / "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx")
add_file(full, "EVT_D8/07_Контроль/00_Программа/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.pdf", docs / "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.pdf")
for name in (
    "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.xlsx",
    "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx",
):
    add_file(full, f"EVT_D8/07_Контроль/01_Формы/{name}", mfg / name)
for name in (
    "EOL_RESULT_REGISTER.csv",
    "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv",
    "MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv",
    "LOT_SERIAL_REGISTER.csv",
    "LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv",
):
    add_file(full, f"EVT_D8/07_Контроль/02_Машиночитаемые_CSV/{name}", mfg / name)
for name in (
    "EOL_SOFTWARE_LIMITS_REV_A.json",
    "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.json",
    "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json",
    "MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.dxf",
    "MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.pdf",
):
    add_file(full, f"EVT_D8/07_Контроль/03_EOL_Оснастка/{name}", mfg / name)
add_tree(full, "EVT_D8/08_ПО/Релиз_2026101601", candidate)
full["EVT_D8/09_Архивы_для_подрядчиков/EVT_PRE_20_ПЛАТЫ_ЗАКАЗ_И_МОНТАЖ_ALTIUM_20261016_REV_D8.zip"] = altium_zip.read_bytes()
full_meta = {
    "release_id": RELEASE_ID,
    "scope": "FULL_EVT_PRE_20_PROCUREMENT_PRODUCTION_ASSEMBLY_HANDOFF",
    "date": DATE,
    "source_commit": SOURCE_COMMIT,
    "inherited_release": "EVT_PRE_20_REV_D7",
    "software_release_candidate": "EVT_PRE_20_RELEASE_CANDIDATE_2026101601",
    "stackup_layers": {"PCB-MAIN": 8, "PCB-PWR": 4, "PCB-MIC": 2},
    "evt_program": {
        "production_groups": [20, 20],
        "bench_stations": 1,
        "total_stations": 41,
        "serial_identities": "DIO-EVT-001..040 plus DIO-EVT-B01",
        "serial_identity_count": 41,
    },
    "procurement_variants": {
        "21": "one EVT-20 lot plus DIO-EVT-B01; one EVT-20 spare pool",
        "41": "two EVT-20 lots plus DIO-EVT-B01; two EVT-20 spare pools",
        "selection": "CUSTOMER_TO_SELECT_EXACTLY_ONE",
    },
    "kicad_in_archive": False,
    "private_signing_material_in_archive": False,
    "hardware_result": "NOT_RUN",
    "numeric_eol_limits_approved": False,
    "open_eol_criteria_count": 21,
    "open_eol_criteria_is_not_station_quantity": True,
    "firmware_lock": "FORBIDDEN_HARDWARE_VALIDATION_PENDING",
}
full["EVT_D8/00_Паспорт_комплекта/release_metadata_rev_d8.json"] = (
    json.dumps(full_meta, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
full_removed_key_fixtures = remove_private_key_test_fixtures(full)
full["EVT_D8/00_Паспорт_комплекта/excluded_test_fixtures_rev_d8.json"] = (
    json.dumps({"reason": "private-key text markers are forbidden in handoff archives", "removed": full_removed_key_fixtures}, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
add_manifest(full, "EVT_D8")
full_zip = ARCHIVES / "EVT_PRE_20_REV_D8_FULL.zip"
write_zip(full_zip, full)

# Test methods, report forms and Muhoed training package.
tests = inherited_entries(
    D7 / "EVT_PRE_20_REV_D7_TESTS.zip",
    "EVT_D7_TESTS",
    "EVT_D8_TESTS",
    ("MANIFEST_SHA256_REV_D7.txt",),
)
tests["EVT_D8_TESTS/README_FIRST_RU_EN.txt"] = release_readme("test methods, reports and Muhoed training")
for name in (
    "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D",
    "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_A",
    "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_A",
    "EVT_PRE_20_PROCUREMENT_VARIANTS_21_41_NOTICE_REV_D8",
):
    add_file(tests, f"EVT_D8_TESTS/00_Программа_и_методики/{name}.docx", docs / f"{name}.docx")
    add_file(tests, f"EVT_D8_TESTS/00_Программа_и_методики/{name}.pdf", docs / f"{name}.pdf")
for name in (
    "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.xlsx",
    "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx",
):
    add_file(tests, f"EVT_D8_TESTS/01_Отчетные_таблицы/{name}", mfg / name)
for name in (
    "EOL_RESULT_REGISTER.csv",
    "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv",
    "MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv",
    "LOT_SERIAL_REGISTER.csv",
    "LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv",
):
    add_file(tests, f"EVT_D8_TESTS/01_Отчетные_таблицы/Машиночитаемые_CSV/{name}", mfg / name)
for name in (
    "EOL_SOFTWARE_LIMITS_REV_A.json",
    "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.json",
    "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json",
    "MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.dxf",
    "MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.pdf",
):
    add_file(tests, f"EVT_D8_TESTS/03_EOL_B01/{name}", mfg / name)
for name in (
    "validate_evt_pre_20.py",
    "validate_evt_pre_20_b01_eol_package.py",
    "validate_evt_pre_20_b01_hardware_qualification.py",
    "validate_firmware_lock_interlock.py",
):
    add_file(tests, f"EVT_D8_TESTS/03_EOL_B01/Валидаторы/{name}", tools / name)
for name in ("README.md", "release_candidate_contract.json"):
    add_file(tests, f"EVT_D8_TESTS/04_ПО_кандидат/{name}", candidate / name)
for sub in ("stm32", "nrf52840", "android"):
    for name in ("BUILD_EVIDENCE.txt", "SHA256SUMS.txt"):
        add_file(tests, f"EVT_D8_TESTS/04_ПО_кандидат/{sub}/{name}", candidate / sub / name)
tests_meta = {
    "release_id": RELEASE_ID,
    "scope": "TEST_METHODS_REPORTS_AND_MUHOED_TRAINING",
    "date": DATE,
    "source_commit": SOURCE_COMMIT,
    "physical_results": "NOT_RUN",
    "evt_program_total_stations": 41,
    "evt_program_serial_identity_count": 41,
    "procurement_variants": [21, 41],
    "open_numeric_criteria_count": 21,
    "open_numeric_criteria_is_not_station_quantity": True,
    "undefined_mandatory_limit_policy": "HOLD",
    "firmware_lock": "FORBIDDEN_HARDWARE_VALIDATION_PENDING",
}
tests["EVT_D8_TESTS/release_metadata_rev_d8.json"] = (
    json.dumps(tests_meta, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
tests_removed_key_fixtures = remove_private_key_test_fixtures(tests)
tests["EVT_D8_TESTS/excluded_test_fixtures_rev_d8.json"] = (
    json.dumps({"reason": "private-key text markers are forbidden in handoff archives", "removed": tests_removed_key_fixtures}, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
add_manifest(tests, "EVT_D8_TESTS")
tests_zip = ARCHIVES / "EVT_PRE_20_REV_D8_TESTS.zip"
write_zip(tests_zip, tests)

# Human-facing current documents alongside the archives.
for name in (
    "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx",
    "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.pdf",
    "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_A.docx",
    "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_A.pdf",
    "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_A.docx",
    "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_A.pdf",
    "EVT_PRE_20_PROCUREMENT_VARIANTS_21_41_NOTICE_REV_D8.docx",
    "EVT_PRE_20_PROCUREMENT_VARIANTS_21_41_NOTICE_REV_D8.pdf",
):
    shutil.copy2(docs / name, DOCS_OUT / name)
for name in (
    "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.xlsx",
    "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx",
    "EVT_PRE_20_BOM_REV_A.xlsx",
):
    source = mfg / name if name.startswith(("EVT_PRE_20_B01", "MFG_004")) else ROOT / "hardware" / name
    shutil.copy2(source, DOCS_OUT / name)

# Compatibility, content and extraction audit.
forbidden_kicad = (".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_sym", ".kicad_mod")
sensitive_suffixes = (".jks", ".p12", ".pfx", ".key")
audit = {"release_id": RELEASE_ID, "date": DATE, "archives": {}, "overall": "PASS"}
extract_root = ROOT.parent / "d8_archive_extract_check"
if extract_root.exists():
    resolved = extract_root.resolve()
    allowed = ROOT.parent.resolve()
    if resolved.parent != allowed or resolved.name != "d8_archive_extract_check":
        raise RuntimeError(f"unsafe extract cleanup target: {resolved}")
    shutil.rmtree(resolved)
extract_root.mkdir()
for label, archive_path, expected_root, prohibit_kicad in (
    ("FULL", full_zip, "EVT_D8", True),
    ("ALTIUM", altium_zip, "EVT_D8_ALTIUM", True),
    ("TESTS", tests_zip, "EVT_D8_TESTS", False),
):
    with zipfile.ZipFile(archive_path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in {archive_path}: {bad}")
        names = archive.namelist()
        roots = sorted({name.split("/")[0] for name in names if name})
        if roots != [expected_root]:
            raise RuntimeError(f"unexpected roots in {archive_path}: {roots}")
        file_names = [name for name in names if not name.endswith("/")]
        if label == "FULL":
            required_suffixes = (
                "/02_Закупка_и_BOM/BOM_EVT_PRE_20_REV_D8.xlsx",
                "/02_Закупка_и_BOM/Исходные_таблицы/EVT_PROGRAM_PROCUREMENT_VARIANTS_REV_A.csv",
                "/02_Закупка_и_BOM/Исходные_таблицы/EVT_PROGRAM_1X20_PLUS_1_PROCUREMENT_REV_A.csv",
                "/02_Закупка_и_BOM/Исходные_таблицы/EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv",
                "/07_Контроль/02_Машиночитаемые_CSV/LOT_SERIAL_REGISTER.csv",
                "/07_Контроль/02_Машиночитаемые_CSV/LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv",
            )
            missing = [suffix for suffix in required_suffixes if not any(name.endswith(suffix) for name in file_names)]
            if missing:
                raise RuntimeError(f"required 21/41 procurement or serial files missing from FULL: {missing}")
        if prohibit_kicad and any(name.lower().endswith(forbidden_kicad) for name in file_names):
            raise RuntimeError(f"KiCad file leaked into {label}")
        if any(name.lower().endswith(sensitive_suffixes) for name in file_names):
            raise RuntimeError(f"sensitive key container leaked into {label}")
        for name in file_names:
            data = archive.read(name)
            if any(marker in data for marker in PRIVATE_KEY_MARKERS):
                raise RuntimeError(f"private key marker leaked into {label}: {name}")
        destination = extract_root / label.lower()
        archive.extractall(destination)
        extracted = sum(1 for path in destination.rglob("*") if path.is_file())
        if extracted != len(file_names):
            raise RuntimeError(f"extraction count mismatch for {label}")
        audit["archives"][label] = {
            "filename": archive_path.name,
            "bytes": archive_path.stat().st_size,
            "sha256": sha256_file(archive_path),
            "file_count": len(file_names),
            "directory_entries": sum(name.endswith("/") for name in names),
            "root": expected_root,
            "compression": "ZIP_DEFLATED",
            "crc_test": "PASS",
            "full_extraction": "PASS",
            "max_member_path_characters": max(map(len, names)),
            "kicad_absent": not any(name.lower().endswith(forbidden_kicad) for name in file_names),
            "private_key_markers_absent": True,
        }
shutil.rmtree(extract_root)

audit_path = ARCHIVES / "EVT_PRE_20_REV_D8_COMPAT_AUDIT.json"
audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
checksum_lines = [
    f"{sha256_file(path)}  {path.name}"
    for path in (full_zip, altium_zip, tests_zip, audit_path)
]
(ARCHIVES / "EVT_PRE_20_REV_D8_SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="ascii")

outer_readme = f"""# EVT-PRE-20 REV_D8

Полный документальный и программный комплект для закупки, изготовления, монтажа,
сборки, прошивки, установки и EVT-проверок. Аппаратная часть наследуется от REV_D7;
новая ревизия добавляет signed release candidate 2026101601, текущие инструкции и
актуальные fail-closed формы B01/EOL.

- PCB-MAIN: 8 слоёв; PCB-PWR: 4; PCB-MIC: 2.
- Основной и фабричный архивы содержат платы в Altium/CAM и не содержат KiCad.
- KiCad сохранён в Git и истории проекта.
- Архивы имеют короткие ASCII-корни, directory entries, Deflate, CRC и полную проверку распаковки.
- Закрытые ключи, keystore и пароли не включены.
- Программа EVT: две группы по 20 и одна стендовая, 41 серийный номер.
- Закупка: два варианта, 21 (первая группа плюс стендовая) и 41 (полная программа).
- Значение 21 в строке OPEN criteria формы EOL является количеством открытых критериев, а не станций.
- Окончательные числовые EOL-пределы и firmware lock остаются открыты до измерений собранной B01/станций.

Исходный коммит программной части: `{SOURCE_COMMIT}`.
"""
(OUT / "README.md").write_text(outer_readme, encoding="utf-8")

print(json.dumps(audit, ensure_ascii=False, indent=2))

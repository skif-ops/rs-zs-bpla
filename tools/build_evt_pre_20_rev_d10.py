from __future__ import annotations

import hashlib
import csv
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "releases" / "EVT_PRE_20_REV_D9" / "Архивы"
OUT = ROOT / "releases" / "EVT_PRE_20_REV_D10"
ARCHIVES = OUT / "Архивы"
DOCS_OUT = OUT / "Документы_REV_D10"
SOURCE_COMMIT = "c8bf53f4c39b994b3c792aa00dee3c65edd024e1"
RELEASE_ID = "EVT_PRE_20_REV_D10"
DATE = "2026-10-16"
PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
)
FORBIDDEN_KICAD = (".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_sym", ".kicad_mod")
SENSITIVE_SUFFIXES = (".jks", ".p12", ".pfx", ".key")

DOC_STEMS = (
    "EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B",
    "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_B",
    "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_B",
    "EVT_PRE_20_INSTRUCTION_REGISTER_REV_B",
)

CSV_NAMES = (
    "MANUFACTURING_PARAMETER_APPROVAL_REGISTER_REV_B.csv",
    "ASSEMBLY_ROUTE_REV_B.csv",
    "ASSEMBLY_ROUTE.csv",
    "HARNESS_OPERATION_CARDS_REV_B.csv",
    "STATION_ASSEMBLY_CHECKLIST_REV_B.csv",
    "FIRST_POWER_CHECKLIST_REV_B.csv",
    "INSTALLATION_COMMISSIONING_CHECKLIST_REV_B.csv",
    "EVT_PRE_20_41_STATION_TRAVELLER_REGISTER_REV_B.csv",
)

WORKBOOK_NAME = "EVT_PRE_20_OPERATION_CARDS_AND_CHECKLISTS_REV_B.xlsx"


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
    if resolved.parent != releases or resolved.name != "EVT_PRE_20_REV_D10":
        raise RuntimeError(f"unsafe release reset target: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)


def inherited_entries(
    source: Path,
    old_root: str,
    new_root: str,
    excluded_basenames: set[str],
) -> dict[str, bytes]:
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
            if PurePosixPath(name).name in excluded_basenames:
                continue
            result[new_root + name[len(old_root):]] = archive.read(info)
    return result


def add_file(entries: dict[str, bytes], archive_name: str, source: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    entries[archive_name] = source.read_bytes()


def add_manifest(entries: dict[str, bytes], root: str) -> None:
    name = f"{root}/MANIFEST_SHA256_REV_D10.txt"
    entries.pop(name, None)
    lines = [f"{sha256_bytes(data)}  {path}" for path, data in sorted(entries.items())]
    entries[name] = ("\r\n".join(lines) + "\r\n").encode("utf-8")


def write_zip(path: Path, entries: dict[str, bytes]) -> None:
    directories: set[str] = set()
    for name in entries:
        parent = PurePosixPath(name).parent
        while str(parent) not in (".", ""):
            directories.add(str(parent) + "/")
            parent = parent.parent
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        for directory in sorted(directories, key=lambda value: (value.count("/"), value)):
            info = zipfile.ZipInfo(directory, date_time=(2026, 10, 16, 18, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (0o40755 << 16) | 0x10
            archive.writestr(info, b"")
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 16, 18, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def remove_private_key_test_fixtures(entries: dict[str, bytes]) -> list[str]:
    removed: list[str] = []
    for name, data in list(entries.items()):
        if any(marker in data for marker in PRIVATE_KEY_MARKERS):
            if "/tests/" not in name.lower():
                raise RuntimeError(f"private key marker outside a test fixture: {name}")
            entries.pop(name)
            removed.append(name)
    return removed


def release_readme(scope: str) -> bytes:
    return f"""EVT-PRE-20 REV_D10 — {scope}
Дата / Date: {DATE}
Привязка исходников / Source binding: {SOURCE_COMMIT}

RU
REV_D10 наследует проверенные материалы REV_D9 и закрывает недоработки инструкций,
чек-листов и операционных карт. Добавлены подробные двуязычные процедуры изготовления
жгутов, сборки и настройки станции, первого включения, EOL и монтажа на объекте.
Рабочая книга и CSV содержат полный реестр 41 станции: DIO-EVT-001...040 и DIO-EVT-B01.

Неизвестные параметры не выдуманы: усилия обжима и pull-test, моменты затяжки,
параметры герметизации и фабричные допуски внесены в реестр утверждения параметров.
До заполнения обязательных полей и приложения evidence итоговый статус остаётся HOLD.

Платы наследуются без изменения от REV_D9: PCB-MAIN 8L, PCB-PWR 4L, PCB-MIC 2L.
KiCad отсутствует в основном и Altium-архивах, но сохранён в Git и истории проекта.
Проверки DFM/first article и фактические аппаратные измерения выполняются после заказа
и сборки; итог аппаратных испытаний на дату выпуска: NOT_RUN.

EN
REV_D10 inherits the verified REV_D9 material and closes gaps in instructions,
checklists and operation cards. It adds detailed bilingual procedures for harness
manufacturing, station assembly and setup, first power, EOL and site installation.
The workbook and CSV files cover all 41 identities: DIO-EVT-001...040 and DIO-EVT-B01.

Unknown parameters are controlled rather than invented. Crimp and pull-test forces,
torques, sealing parameters and vendor tolerances are listed in the approval register.
Mandatory empty fields or missing evidence keep the result at HOLD.

PCB data is inherited unchanged from REV_D9: PCB-MAIN 8L, PCB-PWR 4L and PCB-MIC 2L.
KiCad is excluded from the full and Altium archives and remains preserved in Git/history.
Vendor DFM/first article and physical hardware measurements follow ordering and assembly;
the hardware test result at release is NOT_RUN.
""".encode("utf-8")


def payload_hashes(path: Path, root: str) -> dict[str, str]:
    ignored = {
        "README_FIRST_RU_EN.txt",
        "MANIFEST_SHA256_REV_D9.txt",
        "MANIFEST_SHA256_REV_D10.txt",
        "release_metadata_rev_d9.json",
        "release_metadata_rev_d10.json",
    }
    result: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relative = info.filename[len(root) + 1 :]
            if PurePosixPath(relative).name in ignored:
                continue
            result[relative] = sha256_bytes(archive.read(info))
    return result


def validate_manifest(archive: zipfile.ZipFile, root: str) -> int:
    manifest_name = f"{root}/MANIFEST_SHA256_REV_D10.txt"
    lines = archive.read(manifest_name).decode("utf-8").splitlines()
    expected: dict[str, str] = {}
    for line in lines:
        digest, name = line.split("  ", 1)
        expected[name] = digest
    actual_names = [name for name in archive.namelist() if not name.endswith("/") and name != manifest_name]
    if set(expected) != set(actual_names):
        raise RuntimeError(f"manifest member set mismatch in {root}")
    for name in actual_names:
        if expected[name] != sha256_bytes(archive.read(name)):
            raise RuntimeError(f"manifest hash mismatch: {name}")
    return len(actual_names)


def csv_identity_set(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError(f"empty CSV: {path}")
    candidates = ("Serial", "serial_id", "station_serial", "Серийный номер", "Serial ID")
    key = next((candidate for candidate in candidates if candidate in rows[0]), None)
    if key is None:
        raise RuntimeError(f"serial identity column not found in {path.name}: {list(rows[0])}")
    return {row[key].strip() for row in rows if row[key].strip()}


safe_reset(OUT)
ARCHIVES.mkdir(parents=True)
DOCS_OUT.mkdir(parents=True)

docs = ROOT / "docs"
mfg = ROOT / "manufacturing"

base_common_exclusions = {
    "MANIFEST_SHA256_REV_D9.txt",
    "release_metadata_rev_d9.json",
    "excluded_test_fixtures_rev_d9.json",
    "README_FIRST_RU_EN.txt",
}

# Altium factory package: every board payload member is inherited byte-for-byte.
altium = inherited_entries(
    BASE / "EVT_PRE_20_REV_D9_ALTIUM.zip",
    "EVT_D9_ALTIUM",
    "EVT_D10_ALTIUM",
    base_common_exclusions,
)
altium["EVT_D10_ALTIUM/README_FIRST_RU_EN.txt"] = release_readme("Altium PCB/PCBA factory package")
altium_meta = {
    "release_id": RELEASE_ID,
    "scope": "ALTIUM_PCB_PCBA_FACTORY_HANDOFF",
    "date": DATE,
    "source_commit": SOURCE_COMMIT,
    "inherited_hardware_release": "EVT_PRE_20_REV_D9",
    "hardware_payload_change": False,
    "stackup_layers": {"PCB-MAIN": 8, "PCB-PWR": 4, "PCB-MIC": 2},
    "native_format": "Altium Designer",
    "kicad_in_archive": False,
    "status": "EVT_FACTORY_HANDOFF_VENDOR_DFM_AND_FIRST_ARTICLE_REQUIRED",
    "equivalence_claim": "No unchecked cross-tool equivalence is asserted.",
}
altium["EVT_D10_ALTIUM/00_Задание_для_фабрики/release_metadata_rev_d10.json"] = (
    json.dumps(altium_meta, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
add_manifest(altium, "EVT_D10_ALTIUM")
altium_zip = ARCHIVES / "EVT_PRE_20_REV_D10_ALTIUM.zip"
write_zip(altium_zip, altium)

# Full procurement, production, assembly, test and installation handoff.
full_exclusions = set(base_common_exclusions)
full_exclusions.update(
    {
        "EVT_PRE_20_ПЛАТЫ_ЗАКАЗ_И_МОНТАЖ_ALTIUM_20261016_REV_D9.zip",
        "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_A.docx",
        "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_A.pdf",
        "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_A.docx",
        "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_A.pdf",
        "EVT_PRE_20_INSTRUCTION_REGISTER_REV_A.docx",
        "EVT_PRE_20_INSTRUCTION_REGISTER_REV_A.pdf",
        "ASSEMBLY_ROUTE.csv",
    }
)
full = inherited_entries(
    BASE / "EVT_PRE_20_REV_D9_FULL.zip",
    "EVT_D9",
    "EVT_D10",
    full_exclusions,
)
full["EVT_D10/README_FIRST_RU_EN.txt"] = release_readme("full procurement and production handoff")

for ext in ("docx", "pdf"):
    add_file(
        full,
        f"EVT_D10/00_Паспорт_комплекта/EVT_PRE_20_INSTRUCTION_REGISTER_REV_B.{ext}",
        docs / f"EVT_PRE_20_INSTRUCTION_REGISTER_REV_B.{ext}",
    )
    add_file(
        full,
        f"EVT_D10/04_Жгуты_и_кабели/00_Руководство/EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B.{ext}",
        docs / f"EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B.{ext}",
    )
    for stem in (
        "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_B",
        "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_B",
    ):
        add_file(full, f"EVT_D10/06_Сборка_станций/00_Руководство/{stem}.{ext}", docs / f"{stem}.{ext}")

add_file(
    full,
    f"EVT_D10/06_Сборка_станций/01_Операционные_карты/{WORKBOOK_NAME}",
    mfg / WORKBOOK_NAME,
)
for name in CSV_NAMES:
    add_file(full, f"EVT_D10/06_Сборка_станций/02_Машиночитаемые_CSV/{name}", mfg / name)
add_file(full, f"EVT_D10/07_Контроль/01_Формы/{WORKBOOK_NAME}", mfg / WORKBOOK_NAME)
for name in CSV_NAMES:
    add_file(full, f"EVT_D10/07_Контроль/02_Машиночитаемые_CSV/{name}", mfg / name)

nested_altium_name = "EVT_PRE_20_ПЛАТЫ_ЗАКАЗ_И_МОНТАЖ_ALTIUM_20261016_REV_D10.zip"
full[f"EVT_D10/09_Архивы_для_подрядчиков/{nested_altium_name}"] = altium_zip.read_bytes()
full_meta = {
    "release_id": RELEASE_ID,
    "scope": "FULL_EVT_PRE_20_PROCUREMENT_PRODUCTION_ASSEMBLY_HANDOFF",
    "date": DATE,
    "source_commit": SOURCE_COMMIT,
    "inherited_release": "EVT_PRE_20_REV_D9",
    "hardware_payload_change": False,
    "stackup_layers": {"PCB-MAIN": 8, "PCB-PWR": 4, "PCB-MIC": 2},
    "evt_program": {
        "production_groups": [20, 20],
        "bench_stations": 1,
        "total_stations": 41,
        "serial_identities": "DIO-EVT-001..040 plus DIO-EVT-B01",
        "serial_identity_count": 41,
    },
    "procurement_variants": [21, 41],
    "kicad_in_archive": False,
    "private_signing_material_in_archive": False,
    "hardware_result": "NOT_RUN",
    "vendor_dfm_and_first_article": "OPEN",
    "controlled_manufacturing_parameters": {"total": 24, "approved": 0, "open": 24},
    "undefined_mandatory_parameter_policy": "HOLD",
    "firmware_lock": "FORBIDDEN_HARDWARE_VALIDATION_PENDING",
    "instruction_set": {
        "register": "EVT_PRE_20_INSTRUCTION_REGISTER_REV_B",
        "harness_manufacturing": "REV_B_RELEASED_PARAMETERS_OPEN",
        "assembly_setup": "REV_B_RELEASED_PARAMETERS_OPEN",
        "installation_commissioning": "REV_B_RELEASED_PARAMETERS_OPEN",
        "operation_cards_and_checklists": "REV_B_RELEASED_41_IDENTITIES",
    },
}
full["EVT_D10/00_Паспорт_комплекта/release_metadata_rev_d10.json"] = (
    json.dumps(full_meta, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
removed_full = remove_private_key_test_fixtures(full)
full["EVT_D10/00_Паспорт_комплекта/excluded_test_fixtures_rev_d10.json"] = (
    json.dumps({"reason": "private-key markers are forbidden", "removed": removed_full}, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
add_manifest(full, "EVT_D10")
full_zip = ARCHIVES / "EVT_PRE_20_REV_D10_FULL.zip"
write_zip(full_zip, full)

# Methods, report forms and Muhoed training package.
tests_exclusions = set(base_common_exclusions)
tests_exclusions.update(
    {
        "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_A.docx",
        "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_A.pdf",
        "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_A.docx",
        "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_A.pdf",
        "EVT_PRE_20_INSTRUCTION_REGISTER_REV_A.docx",
        "EVT_PRE_20_INSTRUCTION_REGISTER_REV_A.pdf",
        "ASSEMBLY_ROUTE.csv",
    }
)
tests = inherited_entries(
    BASE / "EVT_PRE_20_REV_D9_TESTS.zip",
    "EVT_D9_TESTS",
    "EVT_D10_TESTS",
    tests_exclusions,
)
tests["EVT_D10_TESTS/README_FIRST_RU_EN.txt"] = release_readme("test methods, reports and Muhoed training")
for stem in DOC_STEMS:
    for ext in ("docx", "pdf"):
        add_file(tests, f"EVT_D10_TESTS/00_Программа_и_методики/{stem}.{ext}", docs / f"{stem}.{ext}")
add_file(tests, f"EVT_D10_TESTS/01_Отчетные_таблицы/{WORKBOOK_NAME}", mfg / WORKBOOK_NAME)
for name in CSV_NAMES:
    add_file(tests, f"EVT_D10_TESTS/01_Отчетные_таблицы/Машиночитаемые_CSV/{name}", mfg / name)
tests_meta = {
    "release_id": RELEASE_ID,
    "scope": "TEST_METHODS_REPORTS_AND_MUHOED_TRAINING",
    "date": DATE,
    "source_commit": SOURCE_COMMIT,
    "physical_results": "NOT_RUN",
    "evt_program_total_stations": 41,
    "evt_program_serial_identity_count": 41,
    "procurement_variants": [21, 41],
    "controlled_manufacturing_parameters": {"total": 24, "approved": 0, "open": 24},
    "undefined_mandatory_parameter_policy": "HOLD",
    "firmware_lock": "FORBIDDEN_HARDWARE_VALIDATION_PENDING",
    "instruction_register": "EVT_PRE_20_INSTRUCTION_REGISTER_REV_B",
}
tests["EVT_D10_TESTS/release_metadata_rev_d10.json"] = (
    json.dumps(tests_meta, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
removed_tests = remove_private_key_test_fixtures(tests)
tests["EVT_D10_TESTS/excluded_test_fixtures_rev_d10.json"] = (
    json.dumps({"reason": "private-key markers are forbidden", "removed": removed_tests}, ensure_ascii=False, indent=2) + "\n"
).encode("utf-8")
add_manifest(tests, "EVT_D10_TESTS")
tests_zip = ARCHIVES / "EVT_PRE_20_REV_D10_TESTS.zip"
write_zip(tests_zip, tests)

# Human-facing current documents alongside the archives.
for stem in DOC_STEMS:
    for ext in ("docx", "pdf"):
        shutil.copy2(docs / f"{stem}.{ext}", DOCS_OUT / f"{stem}.{ext}")
shutil.copy2(mfg / WORKBOOK_NAME, DOCS_OUT / WORKBOOK_NAME)
for name in CSV_NAMES:
    shutil.copy2(mfg / name, DOCS_OUT / name)

# Content, CRC, extraction and manifest audit.
audit: dict[str, object] = {
    "release_id": RELEASE_ID,
    "date": DATE,
    "hardware_payload_inherited_from_rev_d9": True,
    "hardware_payload_hash_match": None,
    "archives": {},
    "overall": "PASS",
}
extract_root = OUT / "_extract_check"
extract_root.mkdir()
for label, archive_path, expected_root, prohibit_kicad in (
    ("FULL", full_zip, "EVT_D10", True),
    ("ALTIUM", altium_zip, "EVT_D10_ALTIUM", True),
    ("TESTS", tests_zip, "EVT_D10_TESTS", False),
):
    with zipfile.ZipFile(archive_path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in {archive_path}: {bad}")
        names = archive.namelist()
        roots = sorted({name.split("/")[0] for name in names if name})
        if roots != [expected_root]:
            raise RuntimeError(f"unexpected roots in {archive_path}: {roots}")
        files = [name for name in names if not name.endswith("/")]
        if prohibit_kicad and any(name.lower().endswith(FORBIDDEN_KICAD) for name in files):
            raise RuntimeError(f"KiCad file leaked into {label}")
        if any(name.lower().endswith(SENSITIVE_SUFFIXES) for name in files):
            raise RuntimeError(f"sensitive key container leaked into {label}")
        for name in files:
            data = archive.read(name)
            if any(marker in data for marker in PRIVATE_KEY_MARKERS):
                raise RuntimeError(f"private key marker leaked into {label}: {name}")
        manifest_members = validate_manifest(archive, expected_root)
        required = []
        if label == "FULL":
            required = [
                "/00_Паспорт_комплекта/EVT_PRE_20_INSTRUCTION_REGISTER_REV_B.pdf",
                "/04_Жгуты_и_кабели/00_Руководство/EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B.pdf",
                "/06_Сборка_станций/00_Руководство/EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_B.pdf",
                "/06_Сборка_станций/00_Руководство/EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_B.pdf",
                f"/06_Сборка_станций/01_Операционные_карты/{WORKBOOK_NAME}",
                "/06_Сборка_станций/02_Машиночитаемые_CSV/EVT_PRE_20_41_STATION_TRAVELLER_REGISTER_REV_B.csv",
                f"/09_Архивы_для_подрядчиков/{nested_altium_name}",
            ]
        missing = [suffix for suffix in required if not any(name.endswith(suffix) for name in files)]
        if missing:
            raise RuntimeError(f"required files missing from {label}: {missing}")
        destination = extract_root / label.lower()
        archive.extractall(destination)
        extracted = sum(1 for path in destination.rglob("*") if path.is_file())
        if extracted != len(files):
            raise RuntimeError(f"extraction count mismatch for {label}")
        audit["archives"][label] = {
            "filename": archive_path.name,
            "bytes": archive_path.stat().st_size,
            "sha256": sha256_file(archive_path),
            "file_count": len(files),
            "root": expected_root,
            "crc_test": "PASS",
            "full_extraction": "PASS",
            "max_member_path_characters": max(map(len, names)),
            "kicad_absent": not any(name.lower().endswith(FORBIDDEN_KICAD) for name in files),
            "private_key_markers_absent": True,
            "manifest_hashes_verified": manifest_members,
        }
shutil.rmtree(extract_root)

d9_payload = payload_hashes(BASE / "EVT_PRE_20_REV_D9_ALTIUM.zip", "EVT_D9_ALTIUM")
d10_payload = payload_hashes(altium_zip, "EVT_D10_ALTIUM")
hardware_match = d9_payload == d10_payload
audit["hardware_payload_hash_match"] = hardware_match
audit["hardware_payload_file_count"] = len(d10_payload)
if not hardware_match:
    audit["overall"] = "FAIL"
    raise RuntimeError("REV_D10 Altium hardware payload does not match REV_D9")

with zipfile.ZipFile(full_zip) as archive:
    nested = archive.read(f"EVT_D10/09_Архивы_для_подрядчиков/{nested_altium_name}")
if sha256_bytes(nested) != sha256_file(altium_zip):
    raise RuntimeError("nested Altium archive differs from standalone archive")
audit["nested_altium_matches_standalone"] = True

with zipfile.ZipFile(mfg / WORKBOOK_NAME) as workbook:
    if workbook.testzip() is not None:
        raise RuntimeError("operation workbook CRC failure")
audit["operation_workbook_crc"] = "PASS"
expected_identities = {f"DIO-EVT-{number:03d}" for number in range(1, 41)} | {"DIO-EVT-B01"}
identity_files = (
    "STATION_ASSEMBLY_CHECKLIST_REV_B.csv",
    "FIRST_POWER_CHECKLIST_REV_B.csv",
    "INSTALLATION_COMMISSIONING_CHECKLIST_REV_B.csv",
    "EVT_PRE_20_41_STATION_TRAVELLER_REGISTER_REV_B.csv",
)
for name in identity_files:
    if csv_identity_set(mfg / name) != expected_identities:
        raise RuntimeError(f"41-station identity set mismatch in {name}")
with (mfg / "MANUFACTURING_PARAMETER_APPROVAL_REGISTER_REV_B.csv").open(
    "r", encoding="utf-8-sig", newline=""
) as stream:
    parameter_rows = list(csv.DictReader(stream))
approved_parameters = sum(
    1 for row in parameter_rows if row.get("Status", "").strip().upper() == "APPROVED"
)
audit["serial_identity_count"] = len(expected_identities)
audit["serial_identity_files_verified"] = list(identity_files)
audit["controlled_parameter_count"] = len(parameter_rows)
audit["controlled_parameter_approved_count"] = approved_parameters
audit["controlled_parameter_open_count"] = len(parameter_rows) - approved_parameters

audit_path = ARCHIVES / "EVT_PRE_20_REV_D10_COMPAT_AUDIT.json"
audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
checksum_paths = (full_zip, altium_zip, tests_zip, audit_path)
(ARCHIVES / "EVT_PRE_20_REV_D10_SHA256SUMS.txt").write_text(
    "\n".join(f"{sha256_file(path)}  {path.name}" for path in checksum_paths) + "\n",
    encoding="ascii",
)

outer_readme = f"""# EVT-PRE-20 REV_D10

Полный производственный комплект с обновлёнными инструкциями, чек-листами и
операционными картами. Платы наследуются без изменения от REV_D9.

- PCB-MAIN: 8 слоёв; PCB-PWR: 4; PCB-MIC: 2.
- Программа EVT: две группы по 20 и стендовая DIO-EVT-B01, всего 41 станция.
- Закупочные варианты: 21 и 41 станция.
- Новый комплект форм содержит 41 серийную позицию и 24 контролируемых параметра.
- Неутверждённый обязательный параметр или отсутствующее evidence дают HOLD.
- KiCad сохранён в Git/истории и исключён из FULL/ALTIUM архивов.
- Физические аппаратные измерения и DFM/first article: NOT_RUN/OPEN.
- Проверены CRC, полная распаковка, единый корень, отсутствие KiCad и закрытых ключей.
- Вложенный Altium-архив идентичен отдельному Altium-архиву.
- Аппаратная часть Altium побайтно совпадает с REV_D9.

Исходная привязка: `{SOURCE_COMMIT}`.
"""
(OUT / "README.md").write_text(outer_readme, encoding="utf-8")

print(json.dumps(audit, ensure_ascii=False, indent=2))

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "releases" / "EVT_PRE_20_REV_D10" / "Архивы"
OUT = ROOT / "releases" / "EVT_PRE_20_REV_D11"
ARCHIVES = OUT / "Архивы"
DOCS_SOURCE = OUT / "_documents"
DOCS_OUT = OUT / "Документы_REV_D11"
RELEASE_ID = "EVT_PRE_20_REV_D11"
DATE = "2026-11-14"
APK = Path(
    r"C:\Users\skifn\.codex\.chatgpt-projects\g-p-6a9a94a158908191920dd91e212ea701\outputs\wt_muhoed_prod_release\android\app\build\outputs\apk\release\app-release.apk"
)
EOL_ARCHIVE = Path(
    r"C:\Users\skifn\.codex\.chatgpt-projects\g-p-6a9a94a158908191920dd91e212ea701\outputs\wt_muhoed_prod_release\outputs\EVT_PRE_20_DIO_EVT_B01_И_EOL_ОСНАСТКА_20261112_REV_B.zip"
)

FORBIDDEN_KICAD = (".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_sym", ".kicad_mod")
SENSITIVE_SUFFIXES = (".jks", ".p12", ".pfx", ".key")
SKIP_DIRS = {
    ".git",
    ".gradle",
    ".idea",
    ".venv",
    "__pycache__",
    "build",
    "build-host",
    "node_modules",
    "outputs",
}

DOCUMENT_DESTINATIONS = {
    "00_Опись_и_статус_комплекта_Rev_E": "00_Паспорт_комплекта",
    "01_Техническое_задание_EVT_PRE_20_Rev_E": "01_Проект_ТЗ",
    "02_Развертывание_Мухоеда_Windows11_Ubuntu2404": "08_ПО/00_Регламенты",
    "03_Руководство_администратора_Мухоед": "08_ПО/00_Регламенты",
    "04_Руководство_пользователя_Мухоед": "08_ПО/00_Регламенты",
    "05_Выпуск_сертификатов_и_регистрация_станций": "08_ПО/00_Регламенты",
    "06_Инструкция_монтажника_обновление_станции": "08_ПО/00_Регламенты",
    "07_Методика_дополнительного_дообучения_Мухоед": "07_Контроль/00_Программа",
    "08_Проверка_сервера_dioneya_ru": "08_ПО/00_Регламенты",
    "09_Пошаговая_инструкция_сборщика_EVT_PRE_20": "06_Сборка_станций/00_Руководство",
    "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_B": "06_Сборка_станций/00_Руководство",
    "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_PROTOCOL_REV_A": "07_Контроль/00_Программа",
    "EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B": "07_Контроль/00_Программа",
    "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D": "07_Контроль/00_Программа",
    "EVT_PRE_20_FIRMWARE_LOCK_INTERLOCK_REV_A": "07_Контроль/00_Программа",
    "EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B": "04_Жгуты_и_кабели/00_Руководство",
    "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_B": "06_Сборка_станций/00_Руководство",
    "EVT_PRE_20_INSTRUCTION_REGISTER_REV_B": "00_Паспорт_комплекта",
    "EVT_PRE_20_LONG_RANGE_ACOUSTIC_HEAD_TRADE_STUDY_REV_C": "01_Проект_ТЗ",
    "EVT_PRE_20_PKI_CERTIFICATE_LIFECYCLE_INSTRUCTION_REV_A": "08_ПО/00_Регламенты",
    "EVT_PRE_20_PROCUREMENT_VARIANTS_21_41_NOTICE_REV_D8": "02_Закупка_и_BOM",
    "EVT_PRE_20_SERVER_DEPLOYMENT_BACKUP_OPERATIONS_INSTRUCTION_REV_A": "08_ПО/00_Регламенты",
    "EVT_PRE_20_TIME_SYNCHRONIZATION_TRUST_INSTRUCTION_REV_A": "08_ПО/00_Регламенты",
}


def source_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def contains_private_key(data: bytes) -> bool:
    for marker in (
        b"-----BEGIN PRIVATE KEY-----",
        b"-----BEGIN RSA PRIVATE KEY-----",
        b"-----BEGIN EC PRIVATE KEY-----",
    ):
        start = data.find(marker)
        if start >= 0 and b"-----END" in data[start:] and len(data[start:]) > 128:
            return True
    return False


def reset_outputs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (ARCHIVES, DOCS_OUT):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)


def inherited_entries(source: Path, old_root: str, new_root: str, exclude) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(source) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in inherited archive {source}: {bad}")
        for info in archive.infolist():
            if info.is_dir():
                continue
            if not info.filename.startswith(old_root + "/"):
                raise RuntimeError(f"unexpected root in {source}: {info.filename}")
            relative = info.filename[len(old_root) + 1 :]
            if exclude(relative):
                continue
            result[f"{new_root}/{relative}"] = archive.read(info)
    return result


def add_file(entries: dict[str, bytes], name: str, source: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() in SENSITIVE_SUFFIXES:
        raise RuntimeError(f"sensitive file forbidden: {source}")
    data = source.read_bytes()
    if contains_private_key(data):
        raise RuntimeError(f"private key material forbidden: {source}")
    entries[name.replace("\\", "/")] = data


def add_tree(entries: dict[str, bytes], archive_root: str, source: Path) -> None:
    if not source.is_dir():
        return
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() in SENSITIVE_SUFFIXES:
            continue
        if path.name == ".env":
            continue
        data = path.read_bytes()
        if contains_private_key(data):
            if "tests" in {part.lower() for part in relative.parts}:
                continue
            raise RuntimeError(f"private key material forbidden: {path}")
        entries[f"{archive_root}/{relative.as_posix()}"] = data


def add_documents(entries: dict[str, bytes], root: str, include_all: bool = True) -> None:
    for stem, destination in DOCUMENT_DESTINATIONS.items():
        if not include_all and stem not in {
            "07_Методика_дополнительного_дообучения_Мухоед",
            "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_PROTOCOL_REV_A",
            "EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B",
            "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D",
            "EVT_PRE_20_FIRMWARE_LOCK_INTERLOCK_REV_A",
            "EVT_PRE_20_TIME_SYNCHRONIZATION_TRUST_INSTRUCTION_REV_A",
        }:
            continue
        for extension in ("docx", "pdf"):
            add_file(entries, f"{root}/{destination}/{stem}.{extension}", DOCS_SOURCE / f"{stem}.{extension}")


def add_manifest(entries: dict[str, bytes], root: str) -> None:
    name = f"{root}/MANIFEST_SHA256_REV_D11.txt"
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
            info = zipfile.ZipInfo(directory, date_time=(2026, 11, 14, 18, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (0o40755 << 16) | 0x10
            archive.writestr(info, b"")
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 14, 18, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def base_exclusion(relative: str) -> bool:
    name = PurePosixPath(relative).name
    lower = relative.lower()
    return (
        name.startswith("MANIFEST_SHA256_")
        or name.startswith("release_metadata_")
        or name.startswith("excluded_test_fixtures_")
        or name == "README_FIRST_RU_EN.txt"
        or "_rev_d7" in lower
    )


def altium_exclusion(relative: str) -> bool:
    name = PurePosixPath(relative).name
    return (
        name.startswith("MANIFEST_SHA256_")
        or name.startswith("release_metadata_")
        or name.startswith("excluded_test_fixtures_")
        or name == "README_FIRST_RU_EN.txt"
    )


def full_exclusion(relative: str) -> bool:
    lower = relative.lower()
    name = PurePosixPath(relative).name
    if base_exclusion(relative):
        return True
    if lower.endswith(".docx"):
        return True
    if any(name == f"{stem}.pdf" for stem in DOCUMENT_DESTINATIONS):
        return True
    if lower.startswith("02_закупка_и_bom/bom_evt_pre_20_"):
        return True
    if lower.startswith("08_по/релиз_2026101601/"):
        return True
    if lower.startswith("08_по/прошивка_станции/") or lower.startswith("08_по/сервер_мухоед/"):
        return True
    if lower.startswith("08_по/протоколы/") or lower.startswith("08_по/pki_инструменты/"):
        return True
    if lower.startswith("09_архивы_для_подрядчиков/"):
        return True
    if name in {
        "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx",
        "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv",
    }:
        return True
    return False


def tests_exclusion(relative: str) -> bool:
    lower = relative.lower()
    name = PurePosixPath(relative).name
    if base_exclusion(relative):
        return True
    if lower.endswith(".docx"):
        return True
    if any(name == f"{stem}.pdf" for stem in DOCUMENT_DESTINATIONS):
        return True
    if name in {
        "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx",
        "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv",
    }:
        return True
    return False


def readme(scope: str, commit: str) -> bytes:
    return f"""EVT-PRE-20 REV_D11, {scope}
Дата / Date: {DATE}
Привязка исходников / Source binding: {commit}

RU
REV_D11 является исправленным полным комплектом после оформления закупки. Заказные
параметры не изменены: PCB-MAIN 8L, PCB-PWR 4L, PCB-MIC 2L. Фабричный Altium/CAM
пакет унаследован побайтно от REV_D10. BOM, реестры и документация приведены к
фактически заказанной конфигурации. Старые конкурирующие документы REV_D7 исключены.

Все включенные DOCX прошли проверку шаблона: Times New Roman 14 пт, в таблицах
12 пт, одинарный интервал, выравнивание по ширине, отступ первой строки 1,25 см
вне таблиц и отсутствие такого отступа в таблицах. Длинное и среднее тире не применены.

Стендовый программный выпуск 2026111201 остается в статусе аппаратной проверки.
Подписанный APK включен и соответствует release contract. Подписанные бинарные образы
STM32U585 и nRF52840 с хешами выпуска отсутствуют в контролируемом рабочем каталоге,
поэтому старые образы 2026101601 исключены, а прошивка станции до восстановления либо
повторной подписанной сборки запрещена. Блокировка прошивки также запрещена.

EN
REV_D11 is the corrected complete package issued after procurement. Ordered hardware
parameters are unchanged. The Altium/CAM factory payload is inherited byte-for-byte
from REV_D10. BOM and records match the ordered eight-layer PCB-MAIN baseline.
Conflicting REV_D7 documents are excluded. All included DOCX files passed the approved
format audit. The signed Android APK matches the release contract. The controlled
workspace does not contain the signed STM32U585 and nRF52840 binaries for release
2026111201, so obsolete 2026101601 images are excluded and station flashing is blocked
until the signed artifacts are restored or reproducibly rebuilt and signed.
""".encode("utf-8")


def software_readme(commit: str) -> bytes:
    return readme("software, firmware sources, server and installer application", commit)


def add_current_manufacturing(entries: dict[str, bytes], root: str) -> None:
    manufacturing = ROOT / "manufacturing"
    for path in sorted(manufacturing.iterdir()):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".xlsx", ".dxf", ".pdf"}:
            add_file(entries, f"{root}/{path.name}", path)


def validate_manifest(archive: zipfile.ZipFile, root: str) -> int:
    manifest = f"{root}/MANIFEST_SHA256_REV_D11.txt"
    expected: dict[str, str] = {}
    for line in archive.read(manifest).decode("utf-8").splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest
    actual = [name for name in archive.namelist() if not name.endswith("/") and name != manifest]
    if set(expected) != set(actual):
        raise RuntimeError(f"manifest member set mismatch in {root}")
    for name in actual:
        if expected[name] != sha256_bytes(archive.read(name)):
            raise RuntimeError(f"manifest hash mismatch: {name}")
    return len(actual)


def payload_hashes(path: Path, root: str) -> dict[str, str]:
    result: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            relative = info.filename[len(root) + 1 :]
            name = PurePosixPath(relative).name
            if name == "README_FIRST_RU_EN.txt" or name.startswith("MANIFEST_SHA256_") or name.startswith("release_metadata_"):
                continue
            result[relative] = sha256_bytes(archive.read(info))
    return result


def audit_archive(path: Path, root: str, prohibit_kicad: bool) -> dict[str, object]:
    destination = OUT / "_extract_check" / root
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in {path}: {bad}")
        names = archive.namelist()
        roots = sorted({name.split("/")[0] for name in names if name})
        if roots != [root]:
            raise RuntimeError(f"unexpected archive roots: {roots}")
        files = [name for name in names if not name.endswith("/")]
        if prohibit_kicad and any(name.lower().endswith(FORBIDDEN_KICAD) for name in files):
            raise RuntimeError(f"KiCad file leaked into {path.name}")
        if any(name.lower().endswith(SENSITIVE_SUFFIXES) for name in files):
            raise RuntimeError(f"sensitive key container leaked into {path.name}")
        for name in files:
            if contains_private_key(archive.read(name)):
                raise RuntimeError(f"private key leaked into {path.name}: {name}")
        manifest_count = validate_manifest(archive, root)
        archive.extractall(destination)
        extracted = sum(1 for item in destination.rglob("*") if item.is_file())
        if extracted != len(files):
            raise RuntimeError(f"full extraction count mismatch in {path.name}")
    return {
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "file_count": len(files),
        "root": root,
        "crc": "PASS",
        "manifest_hashes_verified": manifest_count,
        "full_extraction": "PASS",
        "kicad_absent": not any(name.lower().endswith(FORBIDDEN_KICAD) for name in files),
        "private_keys_absent": True,
    }


def main() -> None:
    if not DOCS_SOURCE.is_dir():
        raise FileNotFoundError(DOCS_SOURCE)
    commit = source_commit()
    reset_outputs()

    doc_audit = json.loads((DOCS_SOURCE / "КОНТРОЛЬ_ФОРМАТА_DOCX.json").read_text(encoding="utf-8"))
    if doc_audit.get("overall") != "PASS" or len(doc_audit.get("documents", [])) != len(DOCUMENT_DESTINATIONS):
        raise RuntimeError("DOCX format audit is not PASS for the complete current document set")

    altium = inherited_entries(
        BASE / "EVT_PRE_20_REV_D10_ALTIUM.zip",
        "EVT_D10_ALTIUM",
        "EVT_D11_ALTIUM",
        altium_exclusion,
    )
    altium["EVT_D11_ALTIUM/README_FIRST_RU_EN.txt"] = readme("Altium PCB/PCBA factory package", commit)
    altium_meta = {
        "release_id": RELEASE_ID,
        "date": DATE,
        "source_commit": commit,
        "scope": "ALTIUM_PCB_PCBA_FACTORY_HANDOFF",
        "ordered_baseline": {"PCB-MAIN": "8L JLC08161H Rev B", "PCB-PWR": "4L", "PCB-MIC": "2L"},
        "hardware_payload_change_from_rev_d10": False,
        "vendor_dfm_comments": "CONTROLLED_ENGINEERING_DISPOSITION_REQUIRED",
    }
    altium["EVT_D11_ALTIUM/00_Задание_для_фабрики/release_metadata_rev_d11.json"] = (
        json.dumps(altium_meta, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    add_manifest(altium, "EVT_D11_ALTIUM")
    altium_zip = ARCHIVES / "EVT_PRE_20_REV_D11_ALTIUM.zip"
    write_zip(altium_zip, altium)

    software: dict[str, bytes] = {
        "EVT_D11_SOFTWARE/README_FIRST_RU_EN.txt": software_readme(commit),
    }
    add_tree(software, "EVT_D11_SOFTWARE/01_Исходники_прошивки", ROOT / "firmware")
    add_tree(software, "EVT_D11_SOFTWARE/02_Приложение_монтажника/Исходники", ROOT / "android")
    add_tree(software, "EVT_D11_SOFTWARE/03_Сервер_Мухоед", ROOT / "server")
    add_tree(software, "EVT_D11_SOFTWARE/04_Развертывание", ROOT / "deploy")
    add_tree(software, "EVT_D11_SOFTWARE/05_Протоколы", ROOT / "protocols")
    add_tree(software, "EVT_D11_SOFTWARE/06_PKI", ROOT / "server" / "pki")
    for tool_name in (
        "validate_mqtt_command_transport.py",
        "validate_evt_pre_20_bench_release.py",
        "package_evt_pre_20_bench_release_2026111201.py",
        "validate_firmware_lock_interlock_rev_a.py",
    ):
        tool = ROOT / "tools" / tool_name
        if tool.is_file():
            add_file(software, f"EVT_D11_SOFTWARE/07_Контроль/{tool_name}", tool)
    if not APK.is_file() or sha256_file(APK) != "B60661F98369B4731310FAF57B78471F38315A5C4E3F7803C6C9E9AB891A3E30":
        raise RuntimeError("release APK is missing or does not match the approved contract")
    add_file(
        software,
        "EVT_D11_SOFTWARE/08_Релиз_2026111201/android/Dioneya_Commissioning_0.1.1_bench_20261112.apk",
        APK,
    )
    release_note = {
        "release_id": "EVT_PRE_20_BENCH_RELEASE_2026111201",
        "apk": {"included": True, "sha256": sha256_file(APK)},
        "stm32_signed_binary": {"included": False, "expected_sha256": "98DD4076980EE80D3CD5D2AD6CF7CD84375203602BFE1DA52CDFF366087E1715"},
        "nrf52840_signed_binary": {"included": False, "expected_sha256": "E2A10E2F8B68C4221F99509C7DD78728767301E7F867AE66C870601FBF6402B6"},
        "reason": "signed firmware artifacts are absent from the controlled workspace; obsolete 2026101601 images are intentionally excluded",
        "flashing_permission": "DENIED_UNTIL_SIGNED_ARTIFACTS_RESTORED_AND_VALIDATED",
        "firmware_lock": "FORBIDDEN_HARDWARE_VALIDATION_PENDING",
    }
    software["EVT_D11_SOFTWARE/08_Релиз_2026111201/ARTIFACT_STATUS.json"] = (
        json.dumps(release_note, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    add_manifest(software, "EVT_D11_SOFTWARE")
    software_zip = ARCHIVES / "EVT_PRE_20_REV_D11_SOFTWARE.zip"
    write_zip(software_zip, software)

    tests = inherited_entries(
        BASE / "EVT_PRE_20_REV_D10_TESTS.zip",
        "EVT_D10_TESTS",
        "EVT_D11_TESTS",
        tests_exclusion,
    )
    tests["EVT_D11_TESTS/README_FIRST_RU_EN.txt"] = readme("test methods, EOL records and Muhoed training", commit)
    add_documents(tests, "EVT_D11_TESTS/00_Программа_и_методики", include_all=False)
    add_current_manufacturing(tests, "EVT_D11_TESTS/01_Отчетные_материалы")
    if EOL_ARCHIVE.is_file():
        add_file(tests, f"EVT_D11_TESTS/02_EOL_Оснастка/{EOL_ARCHIVE.name}", EOL_ARCHIVE)
    tests_meta = {
        "release_id": RELEASE_ID,
        "date": DATE,
        "source_commit": commit,
        "physical_results": "NOT_RUN",
        "hardware_validation": "PENDING",
        "firmware_lock": "FORBIDDEN_HARDWARE_VALIDATION_PENDING",
        "undefined_limit_or_missing_evidence": "HOLD",
    }
    tests["EVT_D11_TESTS/release_metadata_rev_d11.json"] = (
        json.dumps(tests_meta, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    add_manifest(tests, "EVT_D11_TESTS")
    tests_zip = ARCHIVES / "EVT_PRE_20_REV_D11_TESTS.zip"
    write_zip(tests_zip, tests)

    full = inherited_entries(
        BASE / "EVT_PRE_20_REV_D10_FULL.zip",
        "EVT_D10",
        "EVT_D11",
        full_exclusion,
    )
    full["EVT_D11/README_FIRST_RU_EN.txt"] = readme("full procurement, production, software and test handoff", commit)
    add_documents(full, "EVT_D11", include_all=True)
    add_file(full, "EVT_D11/00_Паспорт_комплекта/КОНТРОЛЬ_ФОРМАТА_DOCX.json", DOCS_SOURCE / "КОНТРОЛЬ_ФОРМАТА_DOCX.json")
    for name in (
        "EVT_PRE_20_BOM_REV_A.xlsx",
        "EVT_PRE_20_BOM_REV_A.csv",
        "EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
        "EVT_PROGRAM_1X20_PLUS_1_PROCUREMENT_REV_A.csv",
        "EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv",
        "CHINA_PROCUREMENT_RFQ.csv",
    ):
        add_file(full, f"EVT_D11/02_Закупка_и_BOM/{name}", ROOT / "hardware" / name)
    for review in (
        "EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.md",
        "EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.md",
    ):
        add_file(full, f"EVT_D11/02_Закупка_и_BOM/Основания/{review}", ROOT / "hardware" / "reviews" / review)
    add_current_manufacturing(full, "EVT_D11/07_Контроль/01_Формы")
    add_tree(full, "EVT_D11/08_ПО/01_Исходники_прошивки", ROOT / "firmware")
    add_tree(full, "EVT_D11/08_ПО/02_Приложение_монтажника/Исходники", ROOT / "android")
    add_tree(full, "EVT_D11/08_ПО/03_Сервер_Мухоед", ROOT / "server")
    add_tree(full, "EVT_D11/08_ПО/04_Развертывание", ROOT / "deploy")
    add_tree(full, "EVT_D11/08_ПО/05_Протоколы", ROOT / "protocols")
    add_file(
        full,
        "EVT_D11/08_ПО/06_Релиз_2026111201/android/Dioneya_Commissioning_0.1.1_bench_20261112.apk",
        APK,
    )
    full["EVT_D11/08_ПО/06_Релиз_2026111201/ARTIFACT_STATUS.json"] = (
        json.dumps(release_note, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    full["EVT_D11/09_Архивы_для_подрядчиков/EVT_PRE_20_REV_D11_ALTIUM.zip"] = altium_zip.read_bytes()
    full["EVT_D11/09_Архивы_для_подрядчиков/EVT_PRE_20_REV_D11_SOFTWARE.zip"] = software_zip.read_bytes()
    full["EVT_D11/09_Архивы_для_подрядчиков/EVT_PRE_20_REV_D11_TESTS.zip"] = tests_zip.read_bytes()
    if EOL_ARCHIVE.is_file():
        add_file(full, f"EVT_D11/09_Архивы_для_подрядчиков/{EOL_ARCHIVE.name}", EOL_ARCHIVE)
    full_meta = {
        "release_id": RELEASE_ID,
        "date": DATE,
        "source_commit": commit,
        "scope": "FULL_EVT_PRE_20_PROCUREMENT_PRODUCTION_SOFTWARE_TEST_HANDOFF",
        "procurement_state": "ORDER_PLACED",
        "ordered_baseline": {"PCB-MAIN": "8L JLC08161H Rev B", "PCB-PWR": "4L", "PCB-MIC": "2L"},
        "hardware_payload_change_from_rev_d10": False,
        "docx_format_audit": "PASS",
        "docx_current_files": len(DOCUMENT_DESTINATIONS),
        "obsolete_rev_d7_documents_included": False,
        "software_release": release_note,
        "hardware_test_result": "NOT_RUN",
        "firmware_lock": "FORBIDDEN_HARDWARE_VALIDATION_PENDING",
    }
    full["EVT_D11/00_Паспорт_комплекта/release_metadata_rev_d11.json"] = (
        json.dumps(full_meta, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    add_manifest(full, "EVT_D11")
    full_zip = ARCHIVES / "EVT_PRE_20_REV_D11_FULL.zip"
    write_zip(full_zip, full)

    for path in sorted(DOCS_SOURCE.iterdir()):
        if path.is_file() and path.suffix.lower() in {".docx", ".pdf", ".json"}:
            shutil.copy2(path, DOCS_OUT / path.name)
    shutil.copy2(ROOT / "hardware" / "EVT_PRE_20_BOM_REV_A.xlsx", DOCS_OUT / "EVT_PRE_20_BOM_REV_A.xlsx")

    extraction = OUT / "_extract_check"
    if extraction.exists():
        shutil.rmtree(extraction)
    extraction.mkdir()
    audit = {
        "release_id": RELEASE_ID,
        "date": DATE,
        "source_commit": commit,
        "overall": "PASS",
        "archives": {},
        "docx_format_audit": "PASS",
        "docx_files": len(DOCUMENT_DESTINATIONS),
        "ordered_pcb_main_layers": 8,
        "procurement_state": "ORDER_PLACED",
        "software_artifact_status": release_note,
    }
    for label, path, root, prohibit_kicad in (
        ("FULL", full_zip, "EVT_D11", True),
        ("ALTIUM", altium_zip, "EVT_D11_ALTIUM", True),
        ("TESTS", tests_zip, "EVT_D11_TESTS", False),
        ("SOFTWARE", software_zip, "EVT_D11_SOFTWARE", False),
    ):
        audit["archives"][label] = audit_archive(path, root, prohibit_kicad)

    d10_payload = payload_hashes(BASE / "EVT_PRE_20_REV_D10_ALTIUM.zip", "EVT_D10_ALTIUM")
    d11_payload = payload_hashes(altium_zip, "EVT_D11_ALTIUM")
    if d10_payload != d11_payload:
        raise RuntimeError("REV_D11 Altium payload differs from REV_D10")
    audit["altium_payload_byte_identical_to_rev_d10"] = True
    audit["altium_payload_file_count"] = len(d11_payload)

    with zipfile.ZipFile(full_zip) as archive:
        full_files = [name for name in archive.namelist() if not name.endswith("/")]
        included_docx = [name for name in full_files if name.lower().endswith(".docx")]
        if len(included_docx) != len(DOCUMENT_DESTINATIONS):
            raise RuntimeError(f"unexpected DOCX count in full package: {len(included_docx)}")
        if any("REV_D7" in name.upper() for name in full_files):
            raise RuntimeError("obsolete REV_D7 file leaked into full package")
        nested = {
            "ALTIUM": archive.read("EVT_D11/09_Архивы_для_подрядчиков/EVT_PRE_20_REV_D11_ALTIUM.zip"),
            "SOFTWARE": archive.read("EVT_D11/09_Архивы_для_подрядчиков/EVT_PRE_20_REV_D11_SOFTWARE.zip"),
            "TESTS": archive.read("EVT_D11/09_Архивы_для_подрядчиков/EVT_PRE_20_REV_D11_TESTS.zip"),
        }
    for label, path in (("ALTIUM", altium_zip), ("SOFTWARE", software_zip), ("TESTS", tests_zip)):
        if sha256_bytes(nested[label]) != sha256_file(path):
            raise RuntimeError(f"nested {label} archive differs from standalone archive")
    audit["nested_archives_match_standalone"] = True
    shutil.rmtree(extraction)

    audit_path = ARCHIVES / "EVT_PRE_20_REV_D11_COMPAT_AUDIT.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksum_paths = (full_zip, altium_zip, tests_zip, software_zip, audit_path)
    (ARCHIVES / "EVT_PRE_20_REV_D11_SHA256SUMS.txt").write_text(
        "\n".join(f"{sha256_file(path)}  {path.name}" for path in checksum_paths) + "\n",
        encoding="ascii",
    )
    (OUT / "README.md").write_text(
        f"""# EVT-PRE-20 REV_D11

Исправленный полный комплект после оформления закупки.

- Заказная конфигурация сохранена: PCB-MAIN 8L, PCB-PWR 4L, PCB-MIC 2L.
- Фабричный Altium/CAM пакет побайтно совпадает с REV_D10.
- BOM и закупочные реестры приведены к фактически заказанной конфигурации.
- Включено {len(DOCUMENT_DESTINATIONS)} действующих DOCX; проверка утвержденного шаблона PASS.
- Старые конкурирующие документы REV_D7 исключены.
- APK 2026111201 включен и соответствует release contract.
- Подписанные STM32U585 и nRF52840 бинарные файлы 2026111201 отсутствуют в контролируемом каталоге. Прошивка до их восстановления запрещена.
- Аппаратные испытания: NOT_RUN. Блокировка прошивки: FORBIDDEN.
- Контроль CRC, полной распаковки, манифестов, закрытых ключей и вложенных архивов: PASS.

Исходная привязка: `{commit}`.
""",
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

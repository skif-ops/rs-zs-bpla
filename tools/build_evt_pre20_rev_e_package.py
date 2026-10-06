from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs"
DOCS = OUTPUT / "EVT_PRE_20_REV_E_DOCUMENTS"
D5_RELEASE = ROOT.parent / "repo_pcbmain" / "releases" / "evt-pre-20" / "2026-10-02-rev-d5"
D5_FULL = D5_RELEASE / "EVT_PRE_20_ПОЛНЫЙ_ПАКЕТ_20261002_REV_D5.zip"
D5_TESTS = D5_RELEASE / "EVT_PRE_20_ПРОГРАММА_И_МУХОЕД_20261002_REV_D5.zip"
FIRMWARE = OUTPUT / "EVT_PRE_20_BENCH_RELEASE_2026100601.zip"
PKI_APP = OUTPUT / "PKI_WINDOWS_APP"
DEPLOY_PUBLIC = Path(r"F:\Проекты\muhoed-deploy\pki\bundle")

MAIN_ZIP = OUTPUT / "EVT_PRE_20_ПОЛНЫЙ_КОМПЛЕКТ_20261006_REV_E.zip"
TEST_ZIP = OUTPUT / "EVT_PRE_20_ПРОГРАММА_МЕТОДИКИ_ОТЧЕТЫ_И_ДООБУЧЕНИЕ_20261006_REV_E.zip"

FORBIDDEN_NAMES = (
    "root.key",
    "issuing.key",
    "command-signing.key",
    "release-key",
    "release_key",
    "android-keystore",
    ".jks",
    ".keystore",
    "id_rsa",
    "muhoed_deploy",
    "root-passphrase",
    "passphrase.txt",
    ".env",
)
PRIVATE_MARKERS = (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN ENCRYPTED PRIVATE KEY-----", b"-----BEGIN EC PRIVATE KEY-----")


class Package:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def add_bytes(self, name: str, data: bytes) -> None:
        normalized = str(PurePosixPath(name))
        lower = normalized.lower()
        if any(token in lower for token in FORBIDDEN_NAMES):
            raise ValueError(f"forbidden filename: {normalized}")
        if any(marker in data for marker in PRIVATE_MARKERS):
            raise ValueError(f"private key marker: {normalized}")
        if normalized in self.files:
            raise ValueError(f"duplicate: {normalized}")
        self.files[normalized] = data

    def add_file(self, name: str, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        self.add_bytes(name, path.read_bytes())

    def add_zip(self, prefix: str, path: Path, skip_prefixes: tuple[str, ...] = ()) -> None:
        with zipfile.ZipFile(path) as source:
            if source.testzip() is not None:
                raise ValueError(f"bad zip: {path}")
            for info in source.infolist():
                if info.is_dir():
                    continue
                if any(info.filename.startswith(skipped) for skipped in skip_prefixes):
                    continue
                self.add_bytes(f"{prefix}/{info.filename}", source.read(info))

    def write(self, path: Path, status: dict) -> None:
        self.add_bytes("00_Опись_и_контроль/СТАТУС_ПАКЕТА.json", json.dumps(status, ensure_ascii=False, indent=2).encode("utf-8"))
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(self.files.items())}
        manifest = {
            "package": path.name,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "files": [{"path": n, "bytes": len(self.files[n]), "sha256": h} for n, h in hashes.items()],
            "status": status,
        }
        self.add_bytes("00_Опись_и_контроль/МАНИФЕСТ_SHA256.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        sums = "".join(f"{digest}  {name}\n" for name, digest in hashes.items()).encode("utf-8")
        self.add_bytes("00_Опись_и_контроль/SHA256SUMS.txt", sums)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
            for name, data in sorted(self.files.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 10, 6, 12, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                target.writestr(info, data, compresslevel=9)


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def build_server_archive() -> tuple[Path, str]:
    commit = git_commit()
    target = OUTPUT / f"MUHOED_SERVER_SOURCE_{commit[:8]}_20261006.tar.gz"
    subprocess.run(
        ["git", "archive", "--format=tar.gz", "--prefix=muhoed/", "-o", str(target), commit, "server", "tools/generate_command_signing_key.py"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(target, "r:gz") as archive:
        names = archive.getnames()
        if not any(name.endswith("server/deploy/compose.ubuntu.yml") for name in names):
            raise ValueError("server archive has no Ubuntu compose")
        if not any(name.endswith("server/deploy/compose.windows.tls.yml") for name in names):
            raise ValueError("server archive has no Windows TLS compose")
    return target, commit


def extract_d5_technical_project() -> bytes:
    wanted = "Основной_пакет/06_Технический_проект/Технический_проект_EVT_PRE_20.docx"
    with zipfile.ZipFile(D5_FULL) as archive:
        return archive.read(wanted)


def add_pki_sources(package: Package) -> None:
    for path in sorted((ROOT / "server" / "pki").glob("*")):
        if path.is_file() and path.suffix.lower() in {".py", ".ps1", ".spec", ".md"}:
            package.add_file(f"04_Сертификаты_и_реестры/Исходники_PKI/{path.name}", path)
    for rel in ("server/requirements-pki.txt", "tools/generate_evt_station_csr.py", "tools/verify_evt_station_certificate.py"):
        path = ROOT / rel
        package.add_file(f"04_Сертификаты_и_реестры/Исходники_PKI/{path.name}", path)


def build_main(server_archive: Path, commit: str) -> None:
    package = Package()
    package.add_file("00_Опись_и_контроль/Опись_и_статус_комплекта_Rev_E.docx", DOCS / "00_Опись_и_статус_комплекта_Rev_E.docx")
    package.add_file("00_Опись_и_контроль/Проверка_сервера_dioneya_ru.docx", DOCS / "08_Проверка_сервера_dioneya_ru.docx")
    package.add_file("00_Опись_и_контроль/КОНТРОЛЬ_ФОРМАТА_DOCX.json", DOCS / "КОНТРОЛЬ_ФОРМАТА_DOCX.json")
    package.add_bytes("01_Технический_проект_и_ТЗ/Технический_проект_EVT_PRE_20.docx", extract_d5_technical_project())
    package.add_file("01_Технический_проект_и_ТЗ/Техническое_задание_EVT_PRE_20_Rev_E.docx", DOCS / "01_Техническое_задание_EVT_PRE_20_Rev_E.docx")
    package.add_zip(
        "02_Закупка_производство_сборка/Аппаратный_комплект_Rev_D5",
        D5_FULL,
        skip_prefixes=("Основной_пакет/07_Отдельные_архивы/",),
    )
    package.add_zip("03_ПО_станции_и_приложение", FIRMWARE)
    package.add_file("04_Сертификаты_и_реестры/Выпуск_сертификатов_и_регистрация_станций.docx", DOCS / "05_Выпуск_сертификатов_и_регистрация_станций.docx")
    for name in ("muhoed-pki.exe", "dioneya-root-offline.exe", "SHA256SUMS.txt"):
        package.add_file(f"04_Сертификаты_и_реестры/Приложение_Windows/{name}", PKI_APP / name)
    for name in ("LOT_SERIAL_REGISTER.csv", "LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv"):
        package.add_file(f"04_Сертификаты_и_реестры/Реестры/{name}", ROOT / "manufacturing" / name)
    add_pki_sources(package)
    for name in ("bundle.json", "ca-chain.pem", "command-signing.pub", "server-fingerprint.txt"):
        package.add_file(f"04_Сертификаты_и_реестры/Публичный_профиль_dioneya_ru/{name}", DEPLOY_PUBLIC / name)
    package.add_file(f"05_Мухоед_сервер/{server_archive.name}", server_archive)
    package.add_file("05_Мухоед_сервер/Развертывание_Мухоеда_Windows11_Ubuntu2404.docx", DOCS / "02_Развертывание_Мухоеда_Windows11_Ubuntu2404.docx")
    package.add_file("06_Инструкции_ролей/Руководство_администратора_Мухоед.docx", DOCS / "03_Руководство_администратора_Мухоед.docx")
    package.add_file("06_Инструкции_ролей/Руководство_пользователя_Мухоед.docx", DOCS / "04_Руководство_пользователя_Мухоед.docx")
    package.add_file("06_Инструкции_ролей/Инструкция_монтажника_обновление_станции.docx", DOCS / "06_Инструкция_монтажника_обновление_станции.docx")
    separate_hardware = (
        "EVT_PRE_20_ЖГУТЫ_И_КАБЕЛИ_20261002_REV_D5.zip",
        "EVT_PRE_20_ПЛАТЫ_ЗАКАЗ_И_МОНТАЖ_20261002_REV_D5.zip",
        "EVT_PRE_20_СБОРКА_И_КОРПУСА_20261002_REV_D5.zip",
    )
    for name in separate_hardware:
        package.add_file(f"07_Отдельные_архивы/{name}", D5_RELEASE / name)
    package.add_file(f"07_Отдельные_архивы/{FIRMWARE.name}", FIRMWARE)
    package.add_file(f"07_Отдельные_архивы/{server_archive.name}", server_archive)
    status = {
        "release": "EVT-PRE-20 Rev E",
        "date": "2026-10-06",
        "hardware_baseline": "Rev D5 2026-10-02",
        "firmware_release": "2026100601",
        "server_source_commit": commit,
        "production_quantity": 40,
        "bench_quantity": 1,
        "procurement_bom_quantity": 41,
        "contains_private_keys": False,
        "hardware_only_pending": ["option bytes and secure boot on target", "A/B rollback on target", "EOL electrical limits", "factory DFM", "mechanical and acoustic validation"],
    }
    package.write(MAIN_ZIP, status)


def build_tests(commit: str) -> None:
    package = Package()
    package.add_file("00_Опись_и_контроль/Опись_и_статус_комплекта_Rev_E.docx", DOCS / "00_Опись_и_статус_комплекта_Rev_E.docx")
    package.add_zip("01_Программа_методики_и_формы_Rev_D5", D5_TESTS)
    package.add_file("02_Методика_дополнительного_дообучения/Методика_дополнительного_дообучения_Мухоед.docx", DOCS / "07_Методика_дополнительного_дообучения_Мухоед.docx")
    package.add_file("03_Прошивка_и_EOL/Инструкция_по_прошивке_настройке_и_испытаниям_Rev_C.docx", ROOT / "docs" / "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.docx")
    for candidate in (
        OUTPUT / "ctest_final.txt",
        OUTPUT / "server_regression_summary_20261006.txt",
        OUTPUT / "server_regression_20261006.txt",
        OUTPUT / "server_webhook_regression_20261006.txt",
        OUTPUT / "pki_regression_20261006.txt",
    ):
        if candidate.exists():
            package.add_file(f"04_Отчетные_материалы/{candidate.name}", candidate)
    for name in ("LOT_SERIAL_REGISTER.csv", "LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv", "INCOMING_INSPECTION_PLAN.csv"):
        package.add_file(f"05_Машинные_реестры/{name}", ROOT / "manufacturing" / name)
    status = {
        "release": "EVT-PRE-20 Rev E tests and reports",
        "date": "2026-10-06",
        "server_source_commit": commit,
        "contains_private_keys": False,
        "scope": "EVT program, methods, report forms, retraining and available software evidence",
    }
    package.write(TEST_ZIP, status)


def validate(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"CRC failure: {bad}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate names")
        for name in names:
            lower = name.lower()
            if any(token in lower for token in FORBIDDEN_NAMES):
                raise ValueError(f"forbidden file in result: {name}")
            data = archive.read(name)
            if any(marker in data for marker in PRIVATE_MARKERS):
                raise ValueError(f"private key in result: {name}")
        xlsx = [name for name in names if name.lower().endswith(".xlsx")]
        for name in xlsx:
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as book:
                if "[Content_Types].xml" not in book.namelist():
                    raise ValueError(f"invalid xlsx: {name}")
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "entries": len(names), "xlsx": len(xlsx)}


def main() -> None:
    required = [DOCS, D5_FULL, D5_TESTS, FIRMWARE, PKI_APP / "muhoed-pki.exe", DEPLOY_PUBLIC / "bundle.json"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(missing)
    server_archive, commit = build_server_archive()
    build_main(server_archive, commit)
    build_tests(commit)
    report = [validate(MAIN_ZIP), validate(TEST_ZIP), validate(FIRMWARE)]
    report_path = OUTPUT / "EVT_PRE_20_REV_E_ARCHIVE_CONTROL.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

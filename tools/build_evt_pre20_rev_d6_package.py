from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT.parent / "EVT_PRE_20_ПРОИЗВОДСТВЕННЫЙ_КОМПЛЕКТ_20261002_REV_D5"
RELEASE = ROOT / "releases" / "evt-pre-20" / "2026-10-13-rev-d6"
EXPORT_DIR = ROOT.parent
ZIP_TIME = (2026, 10, 13, 12, 0, 0)

FOLDERS = (
    "Основной_пакет",
    "Заказ_плат_и_монтаж",
    "Заказ_жгутов_и_кабелей",
    "Сборка_и_корпуса",
    "Программа_EVT_и_Мухоед",
    "Ревью_PCB_MIC_отдельно",
)

ARCHIVES = {
    "full": "EVT_PRE_20_ПОЛНЫЙ_ПАКЕТ_20261013_REV_D6.zip",
    "boards": "EVT_PRE_20_ПЛАТЫ_ЗАКАЗ_И_МОНТАЖ_20261013_REV_D6.zip",
    "programme": "EVT_PRE_20_ПРОГРАММА_И_МУХОЕД_20261013_REV_D6.zip",
    "harness": "EVT_PRE_20_ЖГУТЫ_И_КАБЕЛИ_20261013_REV_D6.zip",
    "assembly": "EVT_PRE_20_СБОРКА_И_КОРПУСА_20261013_REV_D6.zip",
    "review": "EVT_PRE_20_PCB_MIC_REVIEW_B_20261013_REV_D6.zip",
}

PRIVATE_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_recreate(target: Path) -> None:
    target = target.resolve()
    expected_parent = (ROOT / "releases" / "evt-pre-20").resolve()
    if target.parent != expected_parent or target.name != "2026-10-13-rev-d6":
        raise ValueError(f"refusing to replace unexpected directory: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)


def copy_source(source: Path) -> None:
    missing = [name for name in FOLDERS if not (source / name).is_dir()]
    if missing:
        raise FileNotFoundError(f"missing source folders: {missing}")
    safe_recreate(RELEASE)
    for name in FOLDERS:
        shutil.copytree(source / name, RELEASE / name)


def mapping_target(relative: Path) -> Path:
    first = relative.parts[0]
    if first == "gerber":
        return Path("01_Изготовление_платы") / "Gerber" / Path(*relative.parts[1:])
    if first == "drill":
        return Path("01_Изготовление_платы") / "Сверловка_Excellon" / Path(*relative.parts[1:])
    if first == "Исходники_KiCad":
        return Path("03_Исходники_и_контроль") / "Проект_KiCad" / Path(*relative.parts[1:])

    fabrication = {
        "PCB-PWR_copper_layers.pdf",
        "PCB-PWR.d356",
    }
    assembly = {
        "PCB-PWR_assembly_RU_EN.pdf",
        "PCB-PWR_BOM_PCBA.csv",
        "PCB-PWR_DNP_И_ОСОБЫЕ_ПОЗИЦИИ.csv",
        "PCB-PWR_pos.csv",
        "PCB-PWR_schematic_RU_EN.pdf",
    }
    control = {
        "ПРОИСХОЖДЕНИЕ_И_КОНТРОЛЬ_ПОСТАВКИ.json",
        "MANIFEST.json",
        "PCB-PWR_bottom.png",
        "PCB-PWR_top.png",
        "PCB-PWR_drc.json",
        "PCB-PWR_drc.rpt",
        "PCB-PWR_erc.json",
        "PCB-PWR_layout_schematic_audit.log",
        "PCB-PWR_parity_disposition.csv",
        "PCB-PWR_parity_disposition.docx",
        "PCB-PWR_parity_drc.json",
    }
    if len(relative.parts) != 1:
        raise ValueError(f"unknown PCB-PWR source path: {relative}")
    if first in fabrication:
        return Path("01_Изготовление_платы") / first
    if first in assembly:
        return Path("02_Монтаж_платы") / first
    if first in control:
        return Path("03_Исходники_и_контроль") / first
    raise ValueError(f"unclassified PCB-PWR file: {relative}")


def standardize_board_roots() -> dict:
    boards = RELEASE / "Заказ_плат_и_монтаж"
    common = boards / "00_Условия_передачи"
    pwr = boards / "01_PCB_PWR_заводская_проверка_и_заказ"
    main = boards / "03_PCB_MAIN_заказ_с_DFM"

    source_files = sorted(path for path in pwr.rglob("*") if path.is_file())
    source_hashes = {path.relative_to(pwr).as_posix(): sha256(path) for path in source_files}
    moves: list[dict[str, str]] = []
    for path in source_files:
        relative = path.relative_to(pwr)
        target_relative = mapping_target(relative)
        target = pwr / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        moves.append(
            {
                "source": relative.as_posix(),
                "target": target_relative.as_posix(),
                "sha256": source_hashes[relative.as_posix()],
            }
        )

    for directory in sorted((path for path in pwr.rglob("*") if path.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()

    common_copies = {
        "00_Задание_PCB-PWR_на_изготовление_и_монтаж.docx": "Задание_на_изготовление_и_монтаж_плат.docx",
        "ИЗВЕЩЕНИЕ_ПО_ЕДИНОЙ_ПАРТИИ_RU_EN.pdf": "ИЗВЕЩЕНИЕ_ПО_ЕДИНОЙ_ПАРТИИ_RU_EN.pdf",
        "ПОРЯДОК_ЕДИНОЙ_ПАРТИИ_CONTROL.json": "ПОРЯДОК_ЕДИНОЙ_ПАРТИИ_CONTROL.json",
    }
    for target_name, source_name in common_copies.items():
        shutil.copy2(common / source_name, pwr / target_name)

    main_copies = {
        "00_Задание_PCB-MAIN_на_изготовление_и_монтаж.docx": "Задание_на_изготовление_и_монтаж_плат.docx",
        "ИЗВЕЩЕНИЕ_ПО_ЕДИНОЙ_ПАРТИИ_RU_EN.pdf": "ИЗВЕЩЕНИЕ_ПО_ЕДИНОЙ_ПАРТИИ_RU_EN.pdf",
        "ПОРЯДОК_ЕДИНОЙ_ПАРТИИ_CONTROL.json": "ПОРЯДОК_ЕДИНОЙ_ПАРТИИ_CONTROL.json",
    }
    for target_name, source_name in main_copies.items():
        if not (main / target_name).exists():
            shutil.copy2(common / source_name, main / target_name)

    for item in moves:
        target = pwr / PurePosixPath(item["target"])
        if sha256(target) != item["sha256"]:
            raise ValueError(f"PCB-PWR byte drift: {item['target']}")

    status = {
        "schema": "dioneya-pcb-order-structure-v1",
        "release": "EVT-PRE-20 Rev D6",
        "date": "2026-10-13",
        "technical_baseline": "Rev D5 2026-10-02; manufacturing bytes unchanged",
        "board": "PCB-PWR",
        "result": "PASS",
        "structure": [
            "01_Изготовление_платы",
            "02_Монтаж_платы",
            "03_Исходники_и_контроль",
        ],
        "preserved_files": len(moves),
        "mapping": moves,
    }
    (pwr / "STATUS.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def update_status_files() -> None:
    main_status_path = RELEASE / "Основной_пакет" / "СТАТУС_ПАКЕТА.json"
    main_status = json.loads(main_status_path.read_text(encoding="utf-8"))
    main_status["date"] = "2026-10-13"
    main_status["release_packaging_revision"] = "REV_D6_NORMALIZED_PCB_ORDER_STRUCTURE"
    main_status["technical_baseline"] = "REV_D5_2026-10-02_UNCHANGED"
    main_status["pcb_pwr_folder_structure"] = "01_FABRICATION_02_ASSEMBLY_03_SOURCES_AND_CONTROL"
    main_status["pcb_mic_review_b_archive"] = ARCHIVES["review"]
    main_status_path.write_text(json.dumps(main_status, ensure_ascii=False, indent=2), encoding="utf-8")

    programme_status_path = RELEASE / "Программа_EVT_и_Мухоед" / "СТАТУС_ПАКЕТА.json"
    programme_status = json.loads(programme_status_path.read_text(encoding="utf-8"))
    programme_status["package_revision"] = "REV_D6"
    programme_status["package_date"] = "2026-10-13"
    programme_status["technical_baseline"] = "REV_D5_2026-10-02_UNCHANGED"
    programme_status_path.write_text(json.dumps(programme_status, ensure_ascii=False, indent=2), encoding="utf-8")


def zip_tree(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source.parent).as_posix()):
            if not path.is_file():
                continue
            name = path.relative_to(source.parent).as_posix()
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)


def validate_office(name: str, data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        if package.testzip() is not None or "[Content_Types].xml" not in package.namelist():
            raise ValueError(f"invalid Office file: {name}")
        if name.lower().endswith(".docx") and "word/document.xml" not in package.namelist():
            raise ValueError(f"invalid DOCX: {name}")
        if name.lower().endswith(".xlsx") and "xl/workbook.xml" not in package.namelist():
            raise ValueError(f"invalid XLSX: {name}")


def validate_archive(path: Path) -> dict:
    extensions: Counter[str] = Counter()
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"CRC failure in {path.name}: {bad}")
        files = [item for item in archive.infolist() if not item.is_dir()]
        names = [item.filename for item in files]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate paths in {path.name}")
        for item in files:
            data = archive.read(item)
            if not data:
                raise ValueError(f"empty file in {path.name}: {item.filename}")
            if any(marker in data for marker in PRIVATE_MARKERS):
                raise ValueError(f"private key in {path.name}: {item.filename}")
            suffix = Path(item.filename).suffix.lower()
            extensions[suffix or "<none>"] += 1
            if suffix in {".docx", ".xlsx"}:
                validate_office(item.filename, data)
            elif suffix == ".pdf" and not data.startswith(b"%PDF-"):
                raise ValueError(f"invalid PDF header: {item.filename}")
            elif suffix == ".csv":
                text = None
                for encoding in ("utf-8-sig", "utf-8", "cp1251"):
                    try:
                        text = data.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        pass
                if text is None or not next(csv.reader(io.StringIO(text)), None):
                    raise ValueError(f"invalid CSV: {item.filename}")
    return {
        "name": path.name,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "entries": len(files),
        "extensions": dict(sorted(extensions.items())),
    }


def verify_board_structure() -> dict:
    boards = RELEASE / "Заказ_плат_и_монтаж"
    board_names = (
        "01_PCB_PWR_заводская_проверка_и_заказ",
        "02_PCB_MIC_управляемый_заказ_и_монтаж",
        "03_PCB_MAIN_заказ_с_DFM",
    )
    report: dict[str, dict] = {}
    for name in board_names:
        board = boards / name
        required = [
            board / "01_Изготовление_платы",
            board / "02_Монтаж_платы",
            board / "03_Исходники_и_контроль",
        ]
        if not all(path.is_dir() for path in required):
            raise ValueError(f"non-uniform board structure: {name}")
        report[name] = {
            "result": "PASS",
            "files": sum(1 for path in board.rglob("*") if path.is_file()),
            "fabrication_files": sum(1 for path in required[0].rglob("*") if path.is_file()),
            "assembly_files": sum(1 for path in required[1].rglob("*") if path.is_file()),
            "source_control_files": sum(1 for path in required[2].rglob("*") if path.is_file()),
        }

    pwr = boards / board_names[0]
    required_pwr = (
        pwr / "01_Изготовление_платы" / "Gerber" / "PCB-PWR-job.gbrjob",
        pwr / "01_Изготовление_платы" / "Gerber" / "PCB-PWR-Edge_Cuts.gm1",
        pwr / "01_Изготовление_платы" / "Сверловка_Excellon" / "PCB-PWR.drl",
        pwr / "02_Монтаж_платы" / "PCB-PWR_BOM_PCBA.csv",
        pwr / "02_Монтаж_платы" / "PCB-PWR_pos.csv",
        pwr / "02_Монтаж_платы" / "PCB-PWR_assembly_RU_EN.pdf",
        pwr / "02_Монтаж_платы" / "PCB-PWR_schematic_RU_EN.pdf",
        pwr / "03_Исходники_и_контроль" / "Проект_KiCad" / "PCB-PWR.kicad_pcb",
        pwr / "03_Исходники_и_контроль" / "Проект_KiCad" / "PCB-PWR.kicad_sch",
        pwr / "03_Исходники_и_контроль" / "PCB-PWR_drc.json",
        pwr / "03_Исходники_и_контроль" / "PCB-PWR_erc.json",
    )
    missing = [path.relative_to(pwr).as_posix() for path in required_pwr if not path.is_file()]
    if missing:
        raise ValueError(f"PCB-PWR required files missing: {missing}")
    return report


def build_archives() -> list[dict]:
    jobs = (
        ("boards", "Заказ_плат_и_монтаж"),
        ("programme", "Программа_EVT_и_Мухоед"),
        ("harness", "Заказ_жгутов_и_кабелей"),
        ("assembly", "Сборка_и_корпуса"),
        ("review", "Ревью_PCB_MIC_отдельно"),
    )
    results: list[dict] = []
    for key, folder in jobs:
        target = RELEASE / ARCHIVES[key]
        zip_tree(RELEASE / folder, target)
        results.append(validate_archive(target))

    embedded = RELEASE / "Основной_пакет" / "07_Отдельные_архивы"
    for old in embedded.glob("*.zip"):
        old.unlink()
    for key in ("boards", "programme", "harness", "assembly"):
        shutil.copy2(RELEASE / ARCHIVES[key], embedded / ARCHIVES[key])

    report = {
        "schema": "dioneya-evt-pre-20-package-verification-v1",
        "revision": "REV_D6_NORMALIZED_PCB_ORDER_STRUCTURE",
        "date": "2026-10-13",
        "result": "PASS",
        "technical_baseline": "Rev D5 2026-10-02; PCB manufacturing bytes unchanged",
        "board_structure": verify_board_structure(),
        "checked": [
            "uniform PCB order folders",
            "PCB-PWR source byte preservation",
            "required Gerber, Excellon, BOM, placement, assembly, schematic and KiCad files",
            "ZIP CRC and duplicate paths",
            "DOCX and XLSX container integrity",
            "PDF signatures and CSV readability",
            "absence of private-key PEM markers",
        ],
        "standalone_archives": results,
    }
    report_path = RELEASE / "Основной_пакет" / "00_Опись_и_статус" / "ОТЧЕТ_ПРОВЕРКИ_КОМПЛЕКТА_REV_D6.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    full = RELEASE / ARCHIVES["full"]
    zip_tree(RELEASE / "Основной_пакет", full)
    results.insert(0, validate_archive(full))
    return results


def write_control(results: list[dict]) -> Path:
    control = {
        "schema": "dioneya-evt-pre-20-archive-control-v7",
        "revision": "REV_D6_NORMALIZED_PCB_ORDER_STRUCTURE",
        "date": "2026-10-13",
        "result": "PASS",
        "technical_baseline": "REV_D5_2026-10-02_UNCHANGED",
        "pcb_pwr_structure": "NORMALIZED_01_FABRICATION_02_ASSEMBLY_03_SOURCES_AND_CONTROL",
        "pcb_mic_order": "ALREADY_PLACED_NO_CHANGE_NO_CANCELLATION",
        "review_b_archive_separate_from_full_production_zip": True,
        "archives": results,
    }
    path = RELEASE / "КОНТРОЛЬ_АРХИВОВ.json"
    path.write_text(json.dumps(control, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def verify_nested_board_archive() -> None:
    full = RELEASE / ARCHIVES["full"]
    nested_name = f"Основной_пакет/07_Отдельные_архивы/{ARCHIVES['boards']}"
    with zipfile.ZipFile(full) as archive:
        nested = archive.read(nested_name)
    with zipfile.ZipFile(io.BytesIO(nested)) as boards:
        if boards.testzip() is not None:
            raise ValueError("nested board archive CRC failure")
        required = (
            "Заказ_плат_и_монтаж/01_PCB_PWR_заводская_проверка_и_заказ/01_Изготовление_платы/Gerber/PCB-PWR-job.gbrjob",
            "Заказ_плат_и_монтаж/01_PCB_PWR_заводская_проверка_и_заказ/02_Монтаж_платы/PCB-PWR_BOM_PCBA.csv",
            "Заказ_плат_и_монтаж/01_PCB_PWR_заводская_проверка_и_заказ/03_Исходники_и_контроль/Проект_KiCad/PCB-PWR.kicad_pcb",
        )
        missing = [name for name in required if name not in boards.namelist()]
        if missing:
            raise ValueError(f"nested board archive is incomplete: {missing}")


def export_downloads() -> list[Path]:
    exported: list[Path] = []
    for key in ("full", "boards"):
        source = RELEASE / ARCHIVES[key]
        target = EXPORT_DIR / source.name
        shutil.copy2(source, target)
        exported.append(target)
    shutil.copy2(RELEASE / "КОНТРОЛЬ_АРХИВОВ.json", EXPORT_DIR / "EVT_PRE_20_REV_D6_КОНТРОЛЬ_АРХИВОВ.json")
    return exported


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the normalized EVT-PRE-20 Rev D6 production package")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    source = args.source.resolve()
    copy_source(source)
    pwr_status = standardize_board_roots()
    update_status_files()
    board_report = verify_board_structure()
    results = build_archives()
    control = write_control(results)
    verify_nested_board_archive()
    exported = export_downloads()
    summary = {
        "result": "PASS",
        "release": str(RELEASE),
        "control": str(control),
        "pcb_pwr_preserved_files": pwr_status["preserved_files"],
        "board_structure": board_report,
        "archives": results,
        "exported": [str(path) for path in exported],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

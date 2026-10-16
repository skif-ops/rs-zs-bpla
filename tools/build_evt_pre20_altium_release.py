#!/usr/bin/env python3
"""Build split EVT-PRE-20 Altium production and KiCad reference archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path


KICAD_SUFFIXES = {
    ".kicad_pcb",
    ".kicad_sch",
    ".kicad_pro",
    ".kicad_sym",
    ".kicad_mod",
}
KICAD_FILENAMES = {"fp-lib-table", "sym-lib-table"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def safe_remove(path: Path, allowed_parent: Path) -> None:
    resolved = path.resolve()
    parent = allowed_parent.resolve()
    if resolved == parent or parent not in resolved.parents:
        raise RuntimeError(f"Refusing to remove path outside output root: {resolved}")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def copy_tree_filtered(src: Path, dst: Path, reject=None) -> None:
    if not src.is_dir():
        raise FileNotFoundError(src)
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if reject and reject(rel, path):
            continue
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def is_kicad_source(path: Path) -> bool:
    return path.suffix.lower() in KICAD_SUFFIXES or path.name.lower() in KICAD_FILENAMES


def main_support_reject(rel: Path, _path: Path) -> bool:
    blocked_parts = {"Gerber", "Сверловка_Excellon", "Проект_KiCad"}
    if any(part in blocked_parts for part in rel.parts):
        return True
    if is_kicad_source(rel):
        return True
    if rel.name == "PCB-MAIN_netlist.ipc":
        return True
    return False


def system_reject(rel: Path, _path: Path) -> bool:
    return is_kicad_source(rel)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def file_inventory(root: Path, excluded_names: set[str] | None = None) -> list[dict]:
    excluded_names = excluded_names or set()
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name not in excluded_names):
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    return rows


def copper_gerbers(board_root: Path, board: str) -> list[Path]:
    gerber = board_root / "ALTIUM_MASTER" / f"Project Outputs for {board}" / "GerberX2"
    return sorted(gerber.glob(f"{board}_Copper_Signal_*.gbr"))


def validate_altium_payload(root: Path) -> dict:
    board_expectations = {
        "PCB-MAIN": {"layers": 8, "schdocs": 10},
        "PCB-PWR": {"layers": 4, "schdocs": 5},
        "PCB-MIC": {"layers": 2, "schdocs": 1},
    }
    boards = {}
    failures: list[str] = []
    for board, expected in board_expectations.items():
        board_root = root / "01_BOARDS" / board
        master = board_root / "ALTIUM_MASTER"
        required = [
            master / f"{board}.PrjPcb",
            master / f"{board}.PcbDoc",
            master / f"EVT-PRE-20_{board}.OutJob",
            master / f"Project Outputs for {board}" / "Pick Place" / f"Pick Place for {board}.txt",
            master / f"Project Outputs for {board}" / "ExportSTEP" / f"{board}.step",
        ]
        missing = [path.relative_to(root).as_posix() for path in required if not path.is_file()]
        copper = copper_gerbers(board_root, board)
        schdocs = sorted(master.glob("*.SchDoc"))
        schlibs = sorted(master.glob("*.SchLib"))
        pcblibs = sorted(master.glob("*.PcbLib"))
        drc_reports = sorted((master / f"Project Outputs for {board}").rglob("*.html"))
        passed = (
            not missing
            and len(copper) == expected["layers"]
            and len(schdocs) == expected["schdocs"]
            and bool(schlibs)
            and bool(pcblibs)
            and bool(drc_reports)
        )
        if not passed:
            failures.append(board)
        boards[board] = {
            "pass": passed,
            "expected_copper_layers": expected["layers"],
            "copper_gerber_count": len(copper),
            "copper_gerbers": [path.name for path in copper],
            "expected_schdoc_count": expected["schdocs"],
            "schdoc_count": len(schdocs),
            "schlib_count": len(schlibs),
            "pcblib_count": len(pcblibs),
            "drc_report_count": len(drc_reports),
            "missing": missing,
        }
    forbidden = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and is_kicad_source(path)
    )
    if forbidden:
        failures.append("KiCad source leakage")
    return {
        "schema": "dioneya-evt-pre-20-altium-payload-verification-v1",
        "status": "PASS" if not failures else "FAIL",
        "boards": boards,
        "kicad_source_file_count": len(forbidden),
        "kicad_source_files": forbidden,
        "failures": failures,
    }


def create_zip(root: Path, archive: Path) -> dict:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            arcname = (Path(root.name) / path.relative_to(root)).as_posix()
            zf.write(path, arcname)
    with zipfile.ZipFile(archive, "r") as zf:
        bad = zf.testzip()
        names = zf.namelist()
        confined = all(
            not Path(name).is_absolute()
            and ".." not in Path(name).parts
            and Path(name).parts
            and Path(name).parts[0] == root.name
            for name in names
        )
        expected = {
            (Path(root.name) / path.relative_to(root)).as_posix(): sha256(path)
            for path in root.rglob("*") if path.is_file()
        }
        zip_hashes_ok = True
        for name, expected_hash in expected.items():
            data_hash = hashlib.sha256(zf.read(name)).hexdigest().upper()
            if data_hash != expected_hash:
                zip_hashes_ok = False
                break
    return {
        "archive": str(archive),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": sha256(archive),
        "zip_member_count": len(names),
        "zip_crc_verified": bad is None,
        "zip_payload_hashes_verified": zip_hashes_ok,
        "path_confinement_verified": confined,
    }


def build(args: argparse.Namespace) -> dict:
    source = args.source.resolve()
    output_root = args.output_root.resolve()
    record_dir = args.record_dir.resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    output_root.mkdir(parents=True, exist_ok=True)
    record_dir.mkdir(parents=True, exist_ok=True)

    compact_date = args.date.replace("-", "")
    altium_name = f"EVT_PRE_20_ПРОИЗВОДСТВЕННЫЙ_КОМПЛЕКТ_{compact_date}"
    kicad_name = f"EVT_PRE_20_KICAD_ИСХОДНИКИ_АРХИВ_{compact_date}"
    altium_root = output_root / altium_name
    kicad_root = output_root / kicad_name
    altium_zip = output_root / f"{altium_name}.zip"
    kicad_zip = output_root / f"{kicad_name}.zip"
    for path in (altium_root, kicad_root, altium_zip, kicad_zip):
        if path.exists():
            safe_remove(path, output_root)

    # Altium production master.
    copy_tree_filtered(source / "PCB-MAIN" / "Altium-8L-Rev-B", altium_root / "01_BOARDS" / "PCB-MAIN" / "ALTIUM_MASTER")
    copy_tree_filtered(source / "PCB-PWR" / "Altium", altium_root / "01_BOARDS" / "PCB-PWR" / "ALTIUM_MASTER")
    copy_tree_filtered(source / "PCB-MIC" / "Altium", altium_root / "01_BOARDS" / "PCB-MIC" / "ALTIUM_MASTER")
    copy_tree_filtered(
        source / "PCB-MAIN" / "Current-Manufacturing-8L-Rev-B",
        altium_root / "01_BOARDS" / "PCB-MAIN" / "FACTORY_SUPPORT",
        reject=main_support_reject,
    )
    for board in ("PCB-PWR", "PCB-MIC"):
        current = source / board / "Current-Manufacturing"
        support = altium_root / "01_BOARDS" / board / "FACTORY_SUPPORT"
        for name in (
            "FAB_NOTES.md",
            "STATUS.json",
            f"{board}_bom.csv",
            f"{board}_jlc_bom.csv",
            f"{board}_schematic.pdf",
            "drc.json",
            "erc.json",
        ):
            copy_file(current / name, support / name)
    copy_tree_filtered(source / "System", altium_root / "02_SYSTEM", reject=system_reject)

    altium_readme = f"""# EVT-PRE-20 — ALTIUM PRODUCTION RELEASE

## Назначение

Это основной производственный пакет для изготовления плат, монтажа, изготовления жгутов и корпусов EVT-PRE-20.
Производственный master всех трёх плат — Altium Designer 26.10.1.

- PCB-MAIN: Rev.B, 8 медных слоёв, JLC08161H-3313, 1.6 mm, ENIG.
- PCB-PWR: 4 медных слоя.
- PCB-MIC: 2 медных слоя.

Для каждой платы каталог `ALTIUM_MASTER` содержит PrjPcb, SchDoc, PcbDoc, библиотеки, OutJob, Gerber X2,
NC Drill, Pick&Place, STEP и отчёты DRC. Каталог `FACTORY_SUPPORT` содержит контролируемые BOM,
задания, примечания и документы сборки.

KiCad-исходников в этом архиве нет. Упоминания KiCad в отчётах относятся только к истории независимой
проверки конверсии и не являются входными файлами производства.

Перед запуском заказчик должен подтвердить параметры заказа, заполнение и медное закрытие 76 POFV
на PCB-MAIN, результаты DFM и финальные production files фабрики. Серийный выпуск требует результатов
проверки первого физического комплекта.

Source payload commit: `{args.source_commit}`.
"""
    write_text(altium_root / "00_READ_ME_FIRST_RU_EN.md", altium_readme)
    write_json(altium_root / "00_RELEASE_STATUS.json", {
        "schema": "dioneya-evt-pre-20-altium-production-release-v1",
        "date": args.date,
        "source_payload_commit": args.source_commit,
        "release_status": "EVT_BUILD_RELEASED_CUSTOMER_CHECKOUT_REQUIRED",
        "manufacturing_master": "Altium Designer 26.10.1",
        "kicad_sources_included": False,
        "pcb_main": {"revision": "Rev.B", "copper_layers": 8, "stack_id": "JLC08161H-3313", "thickness_mm": 1.6},
        "pcb_pwr": {"copper_layers": 4},
        "pcb_mic": {"copper_layers": 2},
        "customer_checkout_required": True,
        "first_article_hold_required": True,
        "serial_release": False,
    })
    verification = validate_altium_payload(altium_root)
    write_json(altium_root / "00_PAYLOAD_VERIFICATION.json", verification)
    if verification["status"] != "PASS":
        raise RuntimeError(f"Altium payload validation failed: {verification['failures']}")
    altium_manifest_rows = file_inventory(altium_root, {"SHA256SUMS.json"})
    write_json(altium_root / "SHA256SUMS.json", {
        "schema": "dioneya-sha256-manifest-v1",
        "root": altium_name,
        "file_count": len(altium_manifest_rows),
        "files": altium_manifest_rows,
    })

    # Separate KiCad source/history archive.
    copy_tree_filtered(source / "PCB-MAIN" / "Authoritative-KiCad-8L-Rev-B", kicad_root / "PCB-MAIN" / "ACTIVE_8L_REV_B")
    copy_tree_filtered(source / "PCB-MAIN" / "History", kicad_root / "PCB-MAIN" / "HISTORY")
    copy_tree_filtered(source / "PCB-MAIN" / "KiCad-8L-Rev-B-Candidate-Record", kicad_root / "PCB-MAIN" / "CANDIDATE_RECORD")
    copy_tree_filtered(source / "PCB-PWR" / "KiCad", kicad_root / "PCB-PWR" / "SOURCE")
    copy_tree_filtered(source / "PCB-MIC" / "KiCad", kicad_root / "PCB-MIC" / "SOURCE")
    kicad_readme = f"""# EVT-PRE-20 — KICAD SOURCE ARCHIVE

Этот архив хранит исходные файлы KiCad и историю проекта.

**НЕ ИСПОЛЬЗОВАТЬ КАК ПРОИЗВОДСТВЕННЫЙ MASTER.**

Для заказа плат и монтажа используйте только архив `{altium_name}.zip`, где производственным
master является Altium Designer. Этот архив нужен для истории, воспроизводимости и независимой проверки.

Source payload commit: `{args.source_commit}`.
"""
    write_text(kicad_root / "00_NOT_FOR_FACTORY_README.md", kicad_readme)
    write_json(kicad_root / "00_ARCHIVE_STATUS.json", {
        "schema": "dioneya-evt-pre-20-kicad-source-archive-v1",
        "date": args.date,
        "source_payload_commit": args.source_commit,
        "purpose": "history, reproducibility and independent conversion verification",
        "manufacturing_master": False,
        "send_to_factory_for_production": False,
        "paired_altium_archive": f"{altium_name}.zip",
    })
    kicad_manifest_rows = file_inventory(kicad_root, {"SHA256SUMS.json"})
    write_json(kicad_root / "SHA256SUMS.json", {
        "schema": "dioneya-sha256-manifest-v1",
        "root": kicad_name,
        "file_count": len(kicad_manifest_rows),
        "files": kicad_manifest_rows,
    })

    altium_archive = create_zip(altium_root, altium_zip)
    kicad_archive = create_zip(kicad_root, kicad_zip)
    result = {
        "schema": "dioneya-evt-pre-20-split-archive-record-v1",
        "date": args.date,
        "source_payload_commit": args.source_commit,
        "primary_altium_production_archive": {
            **altium_archive,
            "directory": str(altium_root),
            "payload_file_count": sum(1 for p in altium_root.rglob("*") if p.is_file()),
            "validation": verification,
        },
        "separate_kicad_source_archive": {
            **kicad_archive,
            "directory": str(kicad_root),
            "payload_file_count": sum(1 for p in kicad_root.rglob("*") if p.is_file()),
            "manufacturing_master": False,
        },
    }
    write_json(record_dir / "ARCHIVES.json", result)
    write_json(record_dir / "STATUS.json", {
        "schema": "dioneya-evt-pre-20-altium-release-record-v1",
        "date": args.date,
        "release_status": "EVT_BUILD_RELEASED_CUSTOMER_CHECKOUT_REQUIRED",
        "primary_archive": altium_zip.name,
        "primary_sha256": altium_archive["archive_sha256"],
        "kicad_reference_archive": kicad_zip.name,
        "kicad_reference_sha256": kicad_archive["archive_sha256"],
        "pcb_main_layers": 8,
        "pcb_pwr_layers": 4,
        "pcb_mic_layers": 2,
        "altium_payload_validation": verification["status"],
        "customer_checkout_required": True,
        "first_article_hold_required": True,
        "serial_release": False,
    })
    write_text(record_dir / "README.md", altium_readme + "\nKiCad сохранён отдельным архивом: `" + kicad_zip.name + "`.\n")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--record-dir", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--source-commit", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        print(json.dumps(build(parse_args()), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

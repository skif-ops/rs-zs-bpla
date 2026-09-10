#!/usr/bin/env python3
"""Build reproducible current-state EVT-PRE-20 engineering and test-method ZIPs.

These archives are engineering snapshots. They become final release archives only when the
strict second-pass release audit passes.
"""

from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "evt-pre-20-current"

MAIN_ROOTS = [
    ".github/workflows",
    "android",
    "config",
    "docs",
    "firmware",
    "hardware",
    "manufacturing",
    "mechanics",
    "protocols",
    "server",
    "tests",
    "tools",
]

TEST_FILES = [
    "tests/EVT_MASTER_PLAN.md",
    "tests/EVT_MATRIX.csv",
    "tests/DEVIATION_LOG.csv",
    "manufacturing/EOL_TEST_SPEC.md",
    "manufacturing/EOL_RESULT_REGISTER.csv",
    "manufacturing/INCOMING_INSPECTION_PLAN.csv",
    "manufacturing/UNIT_PASSPORT_TEMPLATE.csv",
    "docs/REQUIREMENTS_TRACEABILITY.csv",
    "docs/RISK_REGISTER.csv",
    "hardware/PCB_DOUBLE_REVIEW_GATE.md",
]

EXCLUDE_PARTS = {
    ".git",
    ".gradle",
    ".idea",
    "__pycache__",
    ".pytest_cache",
    "build",
    ".venv",
    "venv",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_PARTS for part in rel.parts):
        return False
    if path.suffix in EXCLUDE_SUFFIXES:
        return False
    if OUT in path.parents:
        return False
    return path.is_file()


def iter_main_files() -> list[Path]:
    files: set[Path] = set()
    for root_name in MAIN_ROOTS:
        root = ROOT / root_name
        if root.is_file() and included(root):
            files.add(root)
        elif root.is_dir():
            files.update(path for path in root.rglob("*") if included(path))
    return sorted(files, key=lambda p: str(p.relative_to(ROOT)).lower())


def fixed_zip_write(archive: zipfile.ZipFile, path: Path) -> None:
    rel = str(path.relative_to(ROOT)).replace(os.sep, "/")
    info = zipfile.ZipInfo(rel)
    info.date_time = (2026, 9, 8, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, path.read_bytes())


def write_zip(output: Path, files: list[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for path in files:
            fixed_zip_write(archive, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    main_zip = OUT / "Dioneya_EVT_PRE_20_ENGINEERING_CURRENT.zip"
    tests_zip = OUT / "Dioneya_EVT_PRE_20_PMI_REPORTS_CURRENT.zip"

    main_files = iter_main_files()
    test_files = [ROOT / name for name in TEST_FILES if (ROOT / name).is_file()]

    write_zip(main_zip, main_files)
    write_zip(tests_zip, test_files)

    sums = OUT / "SHA256SUMS.txt"
    sums.write_text(
        f"{sha256(main_zip)}  {main_zip.name}\n{sha256(tests_zip)}  {tests_zip.name}\n",
        encoding="ascii",
    )

    print(main_zip.relative_to(ROOT))
    print(tests_zip.relative_to(ROOT))
    print(sums.relative_to(ROOT))


if __name__ == "__main__":
    main()

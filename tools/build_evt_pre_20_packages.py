#!/usr/bin/env python3
"""Build reproducible EVT-PRE-20 engineering, test and response-request ZIPs.

These archives are engineering snapshots or controlled request inputs. They
become final release archives only when the strict second-pass release audit
passes.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "evt-pre-20-current"
EXTERNAL_CONTRACT = (
    ROOT / "manufacturing/EVT_PRE_20_EXTERNAL_RESPONSE_BUNDLE_REV_A.json"
)

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


def fixed_zip_write_bytes(
    archive: zipfile.ZipFile, rel: str, payload: bytes
) -> None:
    info = zipfile.ZipInfo(rel)
    info.date_time = (2026, 9, 8, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, payload)


def fixed_zip_write(archive: zipfile.ZipFile, path: Path) -> None:
    rel = str(path.relative_to(ROOT)).replace(os.sep, "/")
    fixed_zip_write_bytes(archive, rel, path.read_bytes())


def write_zip(output: Path, files: list[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for path in files:
            fixed_zip_write(archive, path)


def external_request_files() -> list[Path]:
    contract = json.loads(EXTERNAL_CONTRACT.read_text(encoding="utf-8"))
    names = list(contract["common_files"])
    for group in contract["groups"]:
        names.extend(group["files"])
    paths = {ROOT / name for name in names}
    missing = sorted(
        str(path.relative_to(ROOT)) for path in paths if not path.is_file()
    )
    if missing:
        raise FileNotFoundError(
            "external-response bundle sources missing: " + ", ".join(missing)
        )
    excluded = tuple(contract["excluded_prefixes"])
    violations = sorted(
        str(path.relative_to(ROOT)).replace(os.sep, "/")
        for path in paths
        if str(path.relative_to(ROOT)).replace(os.sep, "/").startswith(excluded)
    )
    if violations:
        raise RuntimeError(
            "external-response bundle contains excluded paths: "
            + ", ".join(violations)
        )
    return sorted(paths, key=lambda path: str(path.relative_to(ROOT)).lower())


def write_external_request_zip(output: Path, files: list[Path]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_lines = []
    for path in files:
        rel = str(path.relative_to(ROOT)).replace(os.sep, "/")
        manifest_lines.append(f"{sha256(path)}  {rel}\n")
    with zipfile.ZipFile(output, "w") as archive:
        fixed_zip_write_bytes(
            archive,
            "BUNDLE_MANIFEST.sha256",
            "".join(manifest_lines).encode("ascii"),
        )
        for path in files:
            fixed_zip_write(archive, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    main_zip = OUT / "Dioneya_EVT_PRE_20_ENGINEERING_CURRENT.zip"
    tests_zip = OUT / "Dioneya_EVT_PRE_20_PMI_REPORTS_CURRENT.zip"
    external_zip = (
        OUT / "Dioneya_EVT_PRE_20_EXTERNAL_RESPONSE_REQUESTS_CURRENT.zip"
    )

    main_files = iter_main_files()
    test_files = [ROOT / name for name in TEST_FILES if (ROOT / name).is_file()]
    external_files = external_request_files()

    write_zip(main_zip, main_files)
    write_zip(tests_zip, test_files)
    write_external_request_zip(external_zip, external_files)

    sums = OUT / "SHA256SUMS.txt"
    sums.write_text(
        f"{sha256(main_zip)}  {main_zip.name}\n"
        f"{sha256(tests_zip)}  {tests_zip.name}\n"
        f"{sha256(external_zip)}  {external_zip.name}\n",
        encoding="ascii",
    )

    print(main_zip.relative_to(ROOT))
    print(tests_zip.relative_to(ROOT))
    print(external_zip.relative_to(ROOT))
    print(sums.relative_to(ROOT))


if __name__ == "__main__":
    main()

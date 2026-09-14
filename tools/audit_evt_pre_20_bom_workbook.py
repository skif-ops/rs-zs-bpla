#!/usr/bin/env python3
"""Verify the controlled BOM workbook against its CSV source authorities.

The audit uses only Python's standard library and reads XLSX Open Packaging XML
directly. It compares every value in the Engineering BOM, Procurement and RFQ
worksheets and verifies that each native Excel table covers the complete source range.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.xlsx"
DEFAULT_OUTPUT = ROOT / "artifacts/evt_pre_20_bom_workbook_audit.json"
SOURCES = {
    "Engineering BOM": ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv",
    "Procurement": ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
    "RFQ": ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv",
}
EXPECTED_TABLE_REFS = {
    "Engineering BOM": "A1:AC294",
    "Procurement": "A1:Y123",
    "RFQ": "A1:S23",
}
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_matrix(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [list(row) for row in csv.reader(stream)]


def column_index(reference: str) -> int:
    match = re.fullmatch(r"([A-Z]+)[0-9]+", reference)
    require(match is not None, f"invalid XLSX cell reference {reference!r}")
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - ord("A") + 1
    return value - 1


def package_path(target: str, base: str = "xl") -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return str(PurePosixPath(base) / target)


class XlsxReader:
    def __init__(self, path: Path) -> None:
        self.archive = zipfile.ZipFile(path)
        self.shared_strings = self._shared_strings()
        self.sheets = self._sheet_paths()

    def close(self) -> None:
        self.archive.close()

    def _xml(self, path: str) -> ET.Element:
        try:
            return ET.fromstring(self.archive.read(path))
        except KeyError as exc:
            raise RuntimeError(f"XLSX package part missing: {path}") from exc

    def _shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self.archive.namelist():
            return []
        root = self._xml("xl/sharedStrings.xml")
        return [
            "".join(node.text or "" for node in item.findall(f".//{{{MAIN_NS}}}t"))
            for item in root.findall(f"{{{MAIN_NS}}}si")
        ]

    def _sheet_paths(self) -> dict[str, str]:
        workbook = self._xml("xl/workbook.xml")
        rels = self._xml("xl/_rels/workbook.xml.rels")
        targets = {
            rel.attrib["Id"]: package_path(rel.attrib["Target"])
            for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship")
            if rel.attrib.get("Type", "").endswith("/worksheet")
        }
        result: dict[str, str] = {}
        for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
            name = sheet.attrib["name"]
            rel_id = sheet.attrib[f"{{{DOC_REL_NS}}}id"]
            require(rel_id in targets, f"worksheet relationship missing for {name}")
            result[name] = targets[rel_id]
        return result

    def _cell_value(self, cell: ET.Element) -> str:
        cell_type = cell.attrib.get("t", "n")
        if cell_type == "inlineStr":
            return "".join(node.text or "" for node in cell.findall(f".//{{{MAIN_NS}}}t"))
        value = cell.find(f"{{{MAIN_NS}}}v")
        text = value.text if value is not None and value.text is not None else ""
        if cell_type == "s":
            require(text.isdigit(), f"invalid shared-string index {text!r}")
            index = int(text)
            require(index < len(self.shared_strings), f"shared-string index out of range: {index}")
            return self.shared_strings[index]
        if cell_type == "b":
            return "TRUE" if text == "1" else "FALSE"
        return text

    def matrix(self, sheet_name: str, width: int, height: int) -> list[list[str]]:
        require(sheet_name in self.sheets, f"workbook worksheet missing: {sheet_name}")
        root = self._xml(self.sheets[sheet_name])
        result = [["" for _ in range(width)] for _ in range(height)]
        for row in root.findall(f".//{{{MAIN_NS}}}row"):
            row_index = int(row.attrib["r"]) - 1
            require(row_index < height, f"{sheet_name}: unexpected populated row {row_index + 1}")
            for cell in row.findall(f"{{{MAIN_NS}}}c"):
                index = column_index(cell.attrib["r"])
                require(index < width, f"{sheet_name}: unexpected populated cell {cell.attrib['r']}")
                result[row_index][index] = self._cell_value(cell)
        return result

    def table_ref(self, sheet_name: str) -> str:
        sheet_path = PurePosixPath(self.sheets[sheet_name])
        rel_path = str(sheet_path.parent / "_rels" / f"{sheet_path.name}.rels")
        rels = self._xml(rel_path)
        targets = [
            rel.attrib["Target"]
            for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship")
            if rel.attrib.get("Type", "").endswith("/table")
        ]
        require(len(targets) == 1, f"{sheet_name}: expected exactly one native Excel table")
        table_path = package_path(targets[0], str(sheet_path.parent))
        return self._xml(table_path).attrib["ref"]


def compare_matrix(sheet_name: str, expected: list[list[str]], actual: list[list[str]]) -> None:
    require(len(actual) == len(expected), f"{sheet_name}: row count mismatch")
    mismatches: list[str] = []
    for row_index, (expected_row, actual_row) in enumerate(zip(expected, actual), start=1):
        require(len(actual_row) == len(expected_row), f"{sheet_name}: column count mismatch")
        for column, (expected_value, actual_value) in enumerate(zip(expected_row, actual_row), start=1):
            if actual_value != expected_value:
                mismatches.append(
                    f"R{row_index}C{column}: workbook={actual_value!r} csv={expected_value!r}"
                )
                if len(mismatches) == 10:
                    break
        if len(mismatches) == 10:
            break
    require(not mismatches, f"{sheet_name}: workbook/CSV mismatch: {' | '.join(mismatches)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    workbook_path = args.workbook.resolve()
    require(workbook_path.is_file() and workbook_path.stat().st_size > 0,
            f"controlled workbook missing: {workbook_path}")

    source_matrices = {name: csv_matrix(path) for name, path in SOURCES.items()}
    reader = XlsxReader(workbook_path)
    try:
        for name, expected in source_matrices.items():
            width = len(expected[0])
            require(all(len(row) == width for row in expected), f"{name}: ragged CSV source")
            actual = reader.matrix(name, width, len(expected))
            compare_matrix(name, expected, actual)
            require(reader.table_ref(name) == EXPECTED_TABLE_REFS[name],
                    f"{name}: native table range does not cover {EXPECTED_TABLE_REFS[name]}")

        summary = reader.matrix("Summary", 6, 25)
        require(summary[4] == [
            "Lot stations", "PCB-MAIN PCBA", "PCB-PWR PCBA", "PCB-MIC PCBA",
            "T5838 microphones", "Vacuum-cast housings",
        ], "Summary: controlled lot header mismatch")
        require(summary[5:8] == [
            ["4", "4", "4", "16", "16", "4"],
            ["10", "10", "10", "40", "40", "10"],
            ["20", "20", "20", "80", "80", "20"],
        ], "Summary: 4/10/20 station quantities mismatch")
        require(summary[14][1] == "PASS", "Summary: QG-1 status is not PASS")
        require(summary[15][1] == "BLOCKED", "Summary: QG-2 must remain BLOCKED")
        require("U8" not in summary[22][1], "Summary: U8 incorrectly remains an open selection")
        require(re.fullmatch(r"[0-9a-f]{12}", summary[11][1]) is not None,
                "Summary: source commit is not a 12-hex identifier")
    finally:
        reader.close()

    try:
        workbook_display = str(workbook_path.relative_to(ROOT))
    except ValueError:
        workbook_display = str(workbook_path)

    result = {
        "status": "PASS",
        "workbook": workbook_display,
        "workbook_sha256": sha256(workbook_path),
        "worksheets": {
            name: {
                "source": str(SOURCES[name].relative_to(ROOT)),
                "source_sha256": sha256(SOURCES[name]),
                "rows": len(matrix),
                "columns": len(matrix[0]),
                "table_ref": EXPECTED_TABLE_REFS[name],
            }
            for name, matrix in source_matrices.items()
        },
        "lot_sizes": [4, 10, 20],
        "qg1": "PASS",
        "qg2": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("EVT-PRE-20 BOM workbook-to-CSV audit PASS")
    print("Engineering BOM 293 rows; Procurement 122 rows; RFQ 22 rows; lots 4/10/20")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

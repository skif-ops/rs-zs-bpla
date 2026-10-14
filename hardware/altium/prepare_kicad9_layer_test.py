"""Prepare isolated KiCad 9 layer-number test inputs for Altium's KiCad importer.

Only the numeric IDs in PCB-PWR/PCB-MIC layer tables are changed. The resulting
copies are diagnostic inputs; they are not approved design or fabrication data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


LEGACY_LAYER_IDS = {
    "F.Cu": 0,
    "In1.Cu": 1,
    "In2.Cu": 2,
    "In3.Cu": 3,
    "In4.Cu": 4,
    "B.Cu": 31,
    "B.Adhes": 32,
    "F.Adhes": 33,
    "B.Paste": 34,
    "F.Paste": 35,
    "B.SilkS": 36,
    "F.SilkS": 37,
    "B.Mask": 38,
    "F.Mask": 39,
    "Dwgs.User": 40,
    "Cmts.User": 41,
    "Eco1.User": 42,
    "Eco2.User": 43,
    "Edge.Cuts": 44,
    "Margin": 45,
    "B.CrtYd": 46,
    "F.CrtYd": 47,
    "B.Fab": 48,
    "F.Fab": 49,
    **{f"User.{i}": 49 + i for i in range(1, 10)},
}
LAYER_TABLE = re.compile(r"(?ms)^\t\(layers\s*\n(?P<body>.*?)^\t\)")
LAYER_ROW = re.compile(r'\((\d+) "([^"]+)"')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_board(source: str) -> tuple[str, list[dict]]:
    match = LAYER_TABLE.search(source)
    if not match:
        raise ValueError("KiCad 9 layer table not found")
    old_body = match.group("body")
    changes = []

    def remap(row: re.Match[str]) -> str:
        old_id, name = row.groups()
        if name not in LEGACY_LAYER_IDS:
            raise ValueError(f"Unrecognized layer: {name}")
        new_id = LEGACY_LAYER_IDS[name]
        changes.append({"layer": name, "from": int(old_id), "to": new_id})
        return f'({new_id} "{name}"'

    new_body = LAYER_ROW.sub(remap, old_body)
    if not changes or len({c["to"] for c in changes}) != len(changes):
        raise ValueError("Missing or duplicate normalized layer IDs")
    result = source[: match.start("body")] + new_body + source[match.end("body") :]
    if result.replace(new_body, old_body, 1) != source:
        raise ValueError("Transformation changed content outside layer table")
    return result, changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New directory on F for complete native KiCad tree")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    destination = args.destination.resolve()
    if destination.drive.upper() != "F:":
        raise ValueError("Diagnostic copies must be written on F:")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing directory: {destination}")
    native = root / "hardware/kicad/native"
    shutil.copytree(native, destination)
    report = {"source": str(native), "destination": str(destination), "boards": {}}
    for board in ("PCB-PWR", "PCB-MIC"):
        original = native / board / f"{board}.kicad_pcb"
        copied = destination / board / f"{board}.kicad_pcb"
        changed, rows = normalized_board(original.read_text(encoding="utf-8"))
        copied.write_text(changed, encoding="utf-8")
        report["boards"][board] = {
            "original_sha256": digest(original),
            "diagnostic_copy_sha256": digest(copied),
            "layer_id_changes": [row for row in rows if row["from"] != row["to"]],
        }
    (destination / "ALTIUM_LAYER_TEST_MANIFEST.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()

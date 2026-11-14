"""Compare KiCad Edge.Cuts with the primary Altium Board6 outline.

Run with KiCad's bundled Python and olefile. This checks line and arc geometry,
including arc centers and radii. It does not check fabrication drawings, holes,
mechanical layers, keepouts, or filled copper.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

import olefile
import pcbnew


TRANSFORMS = {
    "PCB-MAIN": (3.685, 75.025),
    "PCB-PWR": (0.0, 60.0),
    "PCB-MIC": (0.0, 22.0),
}


def point(x: float, y: float) -> tuple[float, float]:
    return round(x, 3), round(y, 3)


def source_edges(path: Path, board_name: str) -> Counter:
    dx, y_sum = TRANSFORMS[board_name]
    board = pcbnew.LoadBoard(str(path))
    edges = Counter()
    for shape in board.GetDrawings():
        if shape.GetLayerName() != "Edge.Cuts":
            continue
        start = shape.GetStart()
        end = shape.GetEnd()
        endpoints = tuple(sorted((
            point(start.x / 1e6 + dx, y_sum - start.y / 1e6),
            point(end.x / 1e6 + dx, y_sum - end.y / 1e6),
        )))
        if shape.GetShape() == pcbnew.SHAPE_T_ARC:
            center = shape.GetCenter()
            key = ("arc", endpoints, point(center.x / 1e6 + dx, y_sum - center.y / 1e6), round(shape.GetRadius() / 1e6, 3))
        else:
            key = ("line", endpoints)
        edges[key] += 1
    return edges


def imported_edges(path: Path, count: int) -> Counter:
    with olefile.OleFileIO(str(path)) as doc:
        data = doc.openstream(["Board6", "Data"]).read().decode("latin1")
    start = data.find("|KIND0=")
    if start < 0:
        raise ValueError("Board6 has no primary outline vertices")
    end = data.find("|SHELVED=", start)
    if end < 0:
        raise ValueError("Board6 outline record has no terminator")
    fields = dict(re.findall(r"\b([A-Z]+\d+)\s*=\s*([^|]+)", data[start:end]))

    def mm(field: str) -> float:
        return float(fields[field].removesuffix("mil")) * 0.0254

    vertices = [point(mm(f"VX{i}"), mm(f"VY{i}")) for i in range(count + 1)]
    if vertices[-1] != vertices[0]:
        raise ValueError("Primary board outline does not close at source edge count")
    edges = Counter()
    for i in range(count):
        endpoints = tuple(sorted((vertices[i], vertices[i + 1])))
        kind = int(fields[f"KIND{i}"])
        if kind == 1:
            key = ("arc", endpoints, point(mm(f"CX{i}"), mm(f"CY{i}")), round(mm(f"R{i}"), 3))
        elif kind == 0:
            key = ("line", endpoints)
        else:
            raise ValueError(f"Unsupported Altium outline segment type {kind}")
        edges[key] += 1
    return edges


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--board", choices=TRANSFORMS, required=True)
    parser.add_argument("--pcb-file", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = source_edges(args.root / "hardware/kicad/native" / args.board / f"{args.board}.kicad_pcb", args.board)
    imported = imported_edges(args.pcb_file, sum(source.values()))
    result = {
        "source_edge_count": sum(source.values()),
        "imported_edge_count": sum(imported.values()),
        "matching_line_and_arc_geometry": sum((source & imported).values()),
        "source_missing": sum((source - imported).values()),
        "imported_extra": sum((imported - source).values()),
        "coordinate_resolution_mm": 0.001,
        "missing_examples": [str(item) for item in list(source - imported)[:5]],
        "extra_examples": [str(item) for item in list(imported - source)[:5]],
        "scope_limitations": ["mechanical layers, holes, keepouts, and filled copper not checked"],
    }
    payload = json.dumps({args.board: result}, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()

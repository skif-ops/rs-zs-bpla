#!/usr/bin/env python3
"""Independent mechanical/release-metadata audit for EVT-PRE-20 PCB-MIC Rev.A.

Mechanical geometry and board thickness are read directly from native KiCad PCB data.
Surface finish is checked from the versioned fabrication_metadata.json because KiCad 9
SWIG exposes GetStackupDescriptor() as an opaque object on supported Linux builds.
The Gerber-job copy of that metadata is independently checked later by kicad_native_gate.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pcbnew

EXPECTED_W = 24.0
EXPECTED_H = 22.0
EXPECTED_THICKNESS = 1.0
EXPECTED_MATERIAL = "FR-4"
EXPECTED_FINISH = "ENIG"
EXPECTED_REV = "A"
EXPECTED_MOUNTS = {
    "H1": (4.0, 16.65),
    "H2": (20.0, 16.65),
}
EXPECTED_MOUNT_DRILL = 2.2
EXPECTED_ACOUSTIC = (12.0, 16.65, 0.8)


def to_mm(value: int) -> float:
    return float(pcbnew.ToMM(value))


def pos_mm(item) -> tuple[float, float]:
    p = item.GetPosition()
    return to_mm(p.x), to_mm(p.y)


def close(actual: float, expected: float, tol: float, label: str) -> None:
    if abs(actual - expected) > tol:
        raise RuntimeError(f"{label}: {actual:.6f} mm != {expected:.6f} mm +/- {tol:.6f}")


def edge_extents(board) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for item in board.GetDrawings():
        if item.GetLayer() != pcbnew.Edge_Cuts:
            continue
        if not hasattr(item, "GetStart") or not hasattr(item, "GetEnd"):
            continue
        for point in (item.GetStart(), item.GetEnd()):
            xs.append(to_mm(point.x))
            ys.append(to_mm(point.y))
    if not xs:
        raise RuntimeError("PCB-MIC Edge.Cuts geometry is missing")
    return min(xs), min(ys), max(xs), max(ys)


def one_npth(fp, reference: str):
    npths = [p for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    if len(npths) != 1:
        raise RuntimeError(f"{reference}: expected one NPTH pad, found {len(npths)}")
    return npths[0]


def load_fabrication_metadata(board_path: Path) -> dict:
    path = board_path.parent / "fabrication_metadata.json"
    if not path.is_file():
        raise RuntimeError(f"controlled fabrication metadata missing: {path}")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if metadata.get("board") != "PCB-MIC":
        raise RuntimeError(f"fabrication metadata board mismatch: {metadata.get('board')!r}")
    if metadata.get("revision") != EXPECTED_REV:
        raise RuntimeError(f"fabrication metadata revision: {metadata.get('revision')!r} != {EXPECTED_REV!r}")
    if metadata.get("surface_finish") != EXPECTED_FINISH:
        raise RuntimeError(
            f"fabrication metadata finish: {metadata.get('surface_finish')!r} != {EXPECTED_FINISH!r}"
        )
    if metadata.get("material") != EXPECTED_MATERIAL:
        raise RuntimeError(
            f"fabrication metadata material: {metadata.get('material')!r} != {EXPECTED_MATERIAL!r}"
        )
    close(float(metadata.get("board_thickness_mm", -1.0)), EXPECTED_THICKNESS, 0.001, "metadata board thickness")
    if int(metadata.get("copper_layers", -1)) != 2:
        raise RuntimeError(f"fabrication metadata copper layers: {metadata.get('copper_layers')!r} != 2")
    if metadata.get("status") != "NOT_FOR_MANUFACTURE":
        raise RuntimeError(f"unexpected PCB-MIC release state: {metadata.get('status')!r}")
    return metadata


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    args = ap.parse_args()

    board = pcbnew.LoadBoard(str(args.board))
    if board is None:
        raise RuntimeError(f"cannot load board {args.board}")
    metadata = load_fabrication_metadata(args.board)

    x0, y0, x1, y1 = edge_extents(board)
    close(x0, 0.0, 0.01, "outline X min")
    close(y0, 0.0, 0.01, "outline Y min")
    close(x1 - x0, EXPECTED_W, 0.01, "outline width")
    close(y1 - y0, EXPECTED_H, 0.01, "outline height")

    settings = board.GetDesignSettings()
    thickness = to_mm(settings.GetBoardThickness())
    close(thickness, EXPECTED_THICKNESS, 0.01, "native board thickness")

    title = board.GetTitleBlock()
    if str(title.GetRevision()) != EXPECTED_REV:
        raise RuntimeError(f"title block revision: {title.GetRevision()!r} != {EXPECTED_REV!r}")
    if "PCB-MIC" not in str(title.GetTitle()):
        raise RuntimeError(f"title block does not identify PCB-MIC: {title.GetTitle()!r}")

    refs = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for ref, expected_xy in EXPECTED_MOUNTS.items():
        if ref not in refs:
            raise RuntimeError(f"missing mounting hole {ref}")
        fp = refs[ref]
        if not fp.IsBoardOnly():
            raise RuntimeError(f"{ref}: mechanical footprint is not board-only")
        if not fp.IsExcludedFromBOM():
            raise RuntimeError(f"{ref}: mechanical footprint is not excluded from BOM")
        if not fp.IsExcludedFromPosFiles():
            raise RuntimeError(f"{ref}: mechanical footprint is not excluded from position files")
        hole = one_npth(fp, ref)
        x, y = pos_mm(hole)
        close(x, expected_xy[0], 0.01, f"{ref} X")
        close(y, expected_xy[1], 0.01, f"{ref} Y")
        drill = hole.GetDrillSize()
        close(to_mm(drill.x), EXPECTED_MOUNT_DRILL, 0.01, f"{ref} drill X")
        close(to_mm(drill.y), EXPECTED_MOUNT_DRILL, 0.01, f"{ref} drill Y")

    if "MK1" not in refs:
        raise RuntimeError("MK1 missing")
    acoustic_holes = [p for p in refs["MK1"].Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    if len(acoustic_holes) != 1:
        raise RuntimeError(f"MK1 acoustic NPTH: expected one, got {len(acoustic_holes)}")
    acoustic = acoustic_holes[0]
    ax, ay = pos_mm(acoustic)
    drill = acoustic.GetDrillSize()
    close(ax, EXPECTED_ACOUSTIC[0], 0.01, "acoustic port X")
    close(ay, EXPECTED_ACOUSTIC[1], 0.01, "acoustic port Y")
    close(to_mm(drill.x), EXPECTED_ACOUSTIC[2], 0.01, "acoustic port drill")

    stale = []
    for drawing in board.GetDrawings():
        if hasattr(drawing, "GetText") and "DIM-004 OPEN" in drawing.GetText():
            stale.append(drawing.GetText())
    if stale:
        raise RuntimeError(f"stale DIM-004 OPEN fabrication note remains: {stale}")

    print("PCB-MIC Rev.A mechanical/release metadata audit PASS")
    print(
        f"outline {EXPECTED_W:.1f} x {EXPECTED_H:.1f} mm; native thickness {thickness:.1f} mm; "
        f"controlled finish {metadata['surface_finish']}; revision {metadata['revision']}"
    )
    print("H1/H2: NPTH 2.2 mm and excluded from BOM/PnP")
    print("acoustic port: NPTH 0.8 mm at (12.0,16.65)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

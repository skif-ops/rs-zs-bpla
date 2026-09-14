#!/usr/bin/env python3
"""Archiveable, independent PCB-MIC Review-A geometry audit.

The existing pcbnew checks prove that KiCad itself interprets the native board as
expected.  This second control uses kiutils and direct source inspection so it can
emit a stable JSON record containing the reviewed source hashes, commit binding,
and the exact T5838/Molex copper, mask, paste and drill geometry.

A PASS from this script is geometry evidence only.  It does not replace KiCad 9
ERC/DRC, Review-A signature, Review B, DFM, or physical acoustic verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

from kiutils.board import Board
from kiutils.footprint import Footprint


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pcb"
DEFAULT_OUTPUT = ROOT / "artifacts/kicad-native/PCB-MIC/review_a_geometry_audit.json"
T5838_LIBRARY = ROOT / "hardware/kicad/native/PCB-MIC/libs/Dioneya.pretty/T5838_RevA.kicad_mod"
MOLEX_LIBRARY = ROOT / "hardware/kicad/native/PCB-MIC/libs/Dioneya.pretty/Molex_5040500691.kicad_mod"
FABRICATION_METADATA = ROOT / "hardware/kicad/native/PCB-MIC/fabrication_metadata.json"
AUDIT_TOOL = Path(__file__).resolve()
NATIVE_WORKFLOW = ROOT / ".github/workflows/pcb-native.yml"

T5838_SIGNAL_PADS = {
    "1": ((-0.630, -1.420), (0.522, 0.725), -0.050, "PDM_DATA_MIC"),
    "2": ((-0.630, -0.600), (0.522, 0.725), -0.050, "GND"),
    "4": ((-1.070, 1.420), (0.300, 0.300), -0.015, "MIC_WAKE"),
    "5": ((1.070, 1.420), (0.300, 0.300), -0.015, "AAD_CFG"),
    "6": ((0.630, -0.600), (0.522, 0.725), -0.050, "PDM_CLK"),
    "7": ((0.630, -1.420), (0.522, 0.725), -0.050, "1V8_MIC"),
}
MOLEX_SIGNAL_X = {
    "1": -3.750,
    "2": -2.250,
    "3": -0.750,
    "4": 0.750,
    "5": 2.250,
    "6": 3.750,
}
MOLEX_NETS = {
    "1": "1V8_MIC",
    "2": "GND",
    "3": "PDM_CLK",
    "4": "PDM_DATA",
    "5": "MIC_WAKE",
    "6": "AAD_CFG",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def close(actual: float, expected: float, tolerance: float, label: str) -> None:
    if abs(actual - expected) > tolerance:
        raise RuntimeError(
            f"{label}: {actual:.6f} mm != {expected:.6f} mm +/- {tolerance:.6f}"
        )


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"controlled source missing: {path}")
    return {"path": rel(path), "sha256": sha256(path), "bytes": path.stat().st_size}


def net_name(pad: Any) -> str | None:
    return None if pad.net is None else str(pad.net.name)


def position(pad: Any) -> tuple[float, float]:
    return float(pad.position.X), float(pad.position.Y)


def size(pad: Any) -> tuple[float, float]:
    return float(pad.size.X), float(pad.size.Y)


def angle(pad: Any) -> float:
    return float(pad.position.angle or 0.0) % 360.0


def angle_error_180(actual: float, expected: float) -> float:
    return abs(((actual - expected + 90.0) % 180.0) - 90.0)


def grouped_pads(footprint: Any) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for pad in footprint.pads:
        result.setdefault(str(pad.number), []).append(pad)
    return result


def audit_t5838(footprint: Any, *, require_nets: bool) -> dict[str, Any]:
    require(footprint.entryName == "T5838_RevA", "MK1 footprint entry-name drift")
    require(footprint.properties.get("Value") == "T5838", "MK1 footprint value drift")
    require(len(footprint.pads) == 39, f"MK1 pad count: {len(footprint.pads)} != 39")
    pads = grouped_pads(footprint)
    signal_report: dict[str, Any] = {}

    for number, (expected_xy, expected_wh, paste_margin, expected_net) in T5838_SIGNAL_PADS.items():
        candidates = pads.get(number, [])
        require(len(candidates) == 1, f"MK1 pad {number}: expected one, got {len(candidates)}")
        pad = candidates[0]
        x, y = position(pad)
        w, h = size(pad)
        close(x, expected_xy[0], 0.002, f"MK1 pad {number} local X")
        close(y, expected_xy[1], 0.002, f"MK1 pad {number} local Y")
        close(w, expected_wh[0], 0.002, f"MK1 pad {number} copper width")
        close(h, expected_wh[1], 0.002, f"MK1 pad {number} copper height")
        require(pad.type == "smd" and pad.shape == "rect", f"MK1 pad {number}: type/shape drift")
        require(set(pad.layers) == {"F.Cu", "F.Mask", "F.Paste"}, f"MK1 pad {number}: layer drift")
        require(pad.drill is None, f"MK1 pad {number}: unexpected drill")
        close(float(pad.solderPasteMargin), paste_margin, 0.0005, f"MK1 pad {number} paste margin")
        require(pad.solderMaskMargin in (None, 0), f"MK1 pad {number}: nonzero mask margin")
        if require_nets:
            require(net_name(pad) == expected_net, f"MK1 pad {number}: net drift")
        else:
            require(net_name(pad) is None, f"MK1 library pad {number}: unexpected net")
        signal_report[number] = {
            "local_xy_mm": [x, y],
            "copper_and_mask_mm": [w, h],
            "paste_margin_mm": float(pad.solderPasteMargin),
            "paste_aperture_mm": [
                round(w + 2.0 * paste_margin, 6),
                round(h + 2.0 * paste_margin, 6),
            ],
            "layers": list(pad.layers),
            "net": net_name(pad),
        }

    ring = pads.get("3", [])
    require(len(ring) == 32, f"MK1 GND annulus segment count: {len(ring)} != 32")
    center_x, center_y = 0.0, 0.650
    center_radii: list[float] = []
    radial_widths: list[float] = []
    for index, pad in enumerate(ring):
        x, y = position(pad)
        w, h = size(pad)
        radius = math.hypot(x - center_x, y - center_y)
        center_radii.append(radius)
        radial_widths.append(h)
        close(radius, 0.6625, 0.003, f"MK1 ring segment {index} center radius")
        close(w, 0.145691, 0.003, f"MK1 ring segment {index} tangential width")
        close(h, 0.300000, 0.003, f"MK1 ring segment {index} radial height")
        require(pad.type == "smd" and pad.shape == "rect", f"MK1 ring segment {index}: type/shape drift")
        require(set(pad.layers) == {"F.Cu", "F.Mask"}, f"MK1 ring segment {index}: layer drift")
        require(pad.solderPasteMargin in (None, 0), f"MK1 ring segment {index}: paste margin drift")
        require(pad.solderMaskMargin in (None, 0), f"MK1 ring segment {index}: mask margin drift")
        if require_nets:
            require(net_name(pad) == "GND", f"MK1 ring segment {index}: net drift")
        else:
            require(net_name(pad) is None, f"MK1 library ring segment {index}: unexpected net")
        radial_angle = math.degrees(math.atan2(y - center_y, x - center_x)) % 360.0
        expected_orientation = (radial_angle + 90.0) % 360.0
        require(
            angle_error_180(angle(pad), expected_orientation) <= 0.05,
            f"MK1 ring segment {index}: tangential orientation drift",
        )

    mean_radius = sum(center_radii) / len(center_radii)
    mean_radial_width = sum(radial_widths) / len(radial_widths)
    copper_od = 2.0 * (mean_radius + mean_radial_width / 2.0)
    copper_id = 2.0 * (mean_radius - mean_radial_width / 2.0)
    close(copper_od, 1.625, 0.006, "MK1 GND copper/mask OD")
    close(copper_id, 1.025, 0.006, "MK1 GND copper/mask ID")

    holes = [pad for pad in footprint.pads if pad.type == "np_thru_hole"]
    require(len(holes) == 1, f"MK1 acoustic NPTH count: {len(holes)} != 1")
    hole = holes[0]
    hx, hy = position(hole)
    hw, hh = size(hole)
    close(hx, center_x, 0.002, "MK1 acoustic NPTH local X")
    close(hy, center_y, 0.002, "MK1 acoustic NPTH local Y")
    close(hw, 0.800, 0.002, "MK1 acoustic NPTH size X")
    close(hh, 0.800, 0.002, "MK1 acoustic NPTH size Y")
    require(hole.drill is not None, "MK1 acoustic NPTH drill missing")
    close(float(hole.drill.diameter), 0.800, 0.002, "MK1 acoustic NPTH drill")
    require(set(hole.layers) == {"*.Cu", "*.Mask"}, "MK1 acoustic NPTH layer drift")
    require("F.Paste" not in hole.layers, "MK1 acoustic NPTH leaked into paste")

    return {
        "status": "PASS",
        "pad_count": len(footprint.pads),
        "signal_pads": signal_report,
        "ground_annulus": {
            "segments": len(ring),
            "copper_and_mask_od_mm": round(copper_od, 6),
            "copper_and_mask_id_mm": round(copper_id, 6),
            "center_radius_mm": round(mean_radius, 6),
            "segment_tangential_width_mm": float(ring[0].size.X),
            "segment_radial_height_mm": round(mean_radial_width, 6),
            "paste_excluded_from_segments": True,
        },
        "acoustic_port": {
            "type": hole.type,
            "local_xy_mm": [hx, hy],
            "size_mm": [hw, hh],
            "drill_mm": float(hole.drill.diameter),
            "layers": list(hole.layers),
        },
    }


def audit_molex(footprint: Any, *, require_nets: bool) -> dict[str, Any]:
    require(footprint.entryName == "Molex_5040500691", "J1 footprint entry-name drift")
    require(footprint.properties.get("Value") == "5040500691", "J1 value drift")
    require(len(footprint.pads) == 8, f"J1 pad count: {len(footprint.pads)} != 8")
    pads = grouped_pads(footprint)
    signal_report: dict[str, Any] = {}
    xs: list[float] = []
    ys: list[float] = []

    for number, expected_x in MOLEX_SIGNAL_X.items():
        candidates = pads.get(number, [])
        require(len(candidates) == 1, f"J1 circuit {number}: expected one pad")
        pad = candidates[0]
        x, y = position(pad)
        w, h = size(pad)
        close(x, expected_x, 0.005, f"J1 pad {number} local X")
        close(y, -2.590, 0.005, f"J1 pad {number} local Y")
        close(w, 0.600, 0.005, f"J1 pad {number} copper/mask/paste width")
        close(h, 1.000, 0.005, f"J1 pad {number} copper/mask/paste height")
        require(pad.type == "smd" and pad.shape == "rect", f"J1 pad {number}: type/shape drift")
        require(set(pad.layers) == {"F.Cu", "F.Mask", "F.Paste"}, f"J1 pad {number}: layer drift")
        require(pad.drill is None, f"J1 pad {number}: unexpected drill")
        require(pad.solderMaskMargin in (None, 0), f"J1 pad {number}: mask margin drift")
        require(pad.solderPasteMargin in (None, 0), f"J1 pad {number}: paste margin drift")
        if require_nets:
            require(net_name(pad) == MOLEX_NETS[number], f"J1 pad {number}: net drift")
        else:
            require(net_name(pad) is None, f"J1 library pad {number}: unexpected net")
        xs.append(x)
        ys.append(y)
        signal_report[number] = {
            "local_xy_mm": [x, y],
            "copper_mask_paste_mm": [w, h],
            "layers": list(pad.layers),
            "net": net_name(pad),
        }

    ordered_x = sorted(xs)
    for index, (left, right) in enumerate(zip(ordered_x, ordered_x[1:]), start=1):
        close(right - left, 1.500, 0.005, f"J1 pitch pair {index}")
    close(ordered_x[-1] - ordered_x[0], 7.500, 0.005, "J1 B span")
    require(max(ys) - min(ys) <= 0.005, "J1 signal row is not collinear")

    nails = pads.get("", [])
    require(len(nails) == 2, f"J1 nail count: {len(nails)} != 2")
    nail_xy: list[list[float]] = []
    nail_ys: list[float] = []
    for index, pad in enumerate(sorted(nails, key=lambda item: position(item)[0]), start=1):
        x, y = position(pad)
        w, h = size(pad)
        close(abs(x), 6.350, 0.005, f"J1 nail {index} absolute X")
        close(y, 2.590, 0.005, f"J1 nail {index} local Y")
        close(w, 1.250, 0.005, f"J1 nail {index} copper/mask/paste width")
        close(h, 1.800, 0.005, f"J1 nail {index} copper/mask/paste height")
        require(pad.type == "smd" and pad.shape == "rect", f"J1 nail {index}: type/shape drift")
        require(set(pad.layers) == {"F.Cu", "F.Mask", "F.Paste"}, f"J1 nail {index}: layer drift")
        require(pad.drill is None, f"J1 nail {index}: unexpected drill")
        require(net_name(pad) is None, f"J1 nail {index}: unexpected net")
        nail_xy.append([x, y])
        nail_ys.append(y)

    require(max(nail_ys) - min(nail_ys) <= 0.005, "J1 nail row is not collinear")
    row_gap = abs(sum(nail_ys) / 2.0 - sum(ys) / 6.0) - 0.500 - 0.900
    close(row_gap, 3.790, 0.020, "J1 recommended-pattern copper row gap")

    return {
        "status": "PASS",
        "pad_count": len(footprint.pads),
        "signal_pads": signal_report,
        "signal_pitch_mm": 1.500,
        "signal_span_b_mm": ordered_x[-1] - ordered_x[0],
        "mechanical_nails": {
            "count": len(nails),
            "local_xy_mm": nail_xy,
            "copper_mask_paste_mm": [1.250, 1.800],
            "signal_to_nail_copper_row_gap_mm": round(row_gap, 6),
        },
        "drilled_features": 0,
    }


def source_blocks(text: str, head: str) -> list[str]:
    """Return balanced S-expression blocks beginning with ``(head``."""
    blocks: list[str] = []
    cursor = 0
    needle = f"({head}"
    while True:
        start = text.find(needle, cursor)
        if start < 0:
            break
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[start:index + 1])
                    cursor = index + 1
                    break
        else:
            raise RuntimeError(f"unbalanced KiCad S-expression at {head} offset {start}")
    return blocks


def tuple_field(block: str, field: str) -> tuple[float, float]:
    match = re.search(
        rf"\({re.escape(field)}\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", block
    )
    require(match is not None, f"{field} missing from KiCad source block")
    return float(match.group(1)), float(match.group(2))


def audit_t5838_paste_ring(board_path: Path) -> dict[str, Any]:
    candidates = []
    for block in source_blocks(board_path.read_text(encoding="utf-8"), "gr_circle"):
        if re.search(r'\(layer\s+"F\.Paste"\)', block):
            candidates.append(block)
    require(len(candidates) == 1, f"T5838 board-level F.Paste ring count: {len(candidates)} != 1")
    block = candidates[0]
    center = tuple_field(block, "center")
    end = tuple_field(block, "end")
    width_match = re.search(r"\(stroke\s+\(width\s+([-+0-9.eE]+)\)", block, re.S)
    require(width_match is not None, "T5838 paste-ring stroke width missing")
    width = float(width_match.group(1))
    require(re.search(r"\(fill\s+no\)", block) is not None, "T5838 paste ring must be unfilled")
    close(center[0], 12.000, 0.002, "T5838 paste-ring center X")
    close(center[1], 16.650, 0.002, "T5838 paste-ring center Y")
    radius = math.hypot(end[0] - center[0], end[1] - center[1])
    close(radius, 0.6875, 0.002, "T5838 paste-ring center radius")
    close(width, 0.2500, 0.002, "T5838 paste-ring stroke width")
    outer_diameter = 2.0 * (radius + width / 2.0)
    inner_diameter = 2.0 * (radius - width / 2.0)
    close(outer_diameter, 1.625, 0.004, "T5838 paste-ring OD")
    close(inner_diameter, 1.125, 0.004, "T5838 paste-ring ID")
    return {
        "status": "PASS_CONTROLLED_BOARD_LEVEL_GRAPHIC",
        "layer": "F.Paste",
        "center_xy_mm": list(center),
        "center_radius_mm": radius,
        "stroke_width_mm": width,
        "outer_diameter_mm": outer_diameter,
        "inner_diameter_mm": inner_diameter,
        "source_form": "gr_circle",
    }


def audit_mechanical(board: Board) -> dict[str, Any]:
    close(float(board.general.thickness), 1.000, 0.001, "PCB-MIC thickness")
    require(board.titleBlock.revision == "A", "PCB-MIC title-block revision drift")
    require("PCB-MIC" in str(board.titleBlock.title), "PCB-MIC title-block identity missing")
    edges = [item for item in board.graphicItems if item.layer == "Edge.Cuts"]
    require(len(edges) == 4, f"PCB-MIC Edge.Cuts segment count: {len(edges)} != 4")
    points = []
    for edge in edges:
        require(hasattr(edge, "start") and hasattr(edge, "end"), "PCB-MIC non-line Edge.Cuts item")
        points.extend([(float(edge.start.X), float(edge.start.Y)), (float(edge.end.X), float(edge.end.Y))])
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    close(min(xs), 0.000, 0.010, "PCB-MIC outline X min")
    close(min(ys), 0.000, 0.010, "PCB-MIC outline Y min")
    close(max(xs) - min(xs), 24.000, 0.010, "PCB-MIC outline width")
    close(max(ys) - min(ys), 22.000, 0.010, "PCB-MIC outline height")

    refs = {str(fp.properties.get("Reference")): fp for fp in board.footprints}
    holes: dict[str, Any] = {}
    for reference, expected_xy in {"H1": (4.0, 16.65), "H2": (20.0, 16.65)}.items():
        require(reference in refs, f"PCB-MIC mounting hole {reference} missing")
        footprint = refs[reference]
        require(footprint.attributes.boardOnly, f"{reference}: board-only flag missing")
        require(footprint.attributes.excludeFromBom, f"{reference}: BOM exclusion missing")
        require(footprint.attributes.excludeFromPosFiles, f"{reference}: PnP exclusion missing")
        require(len(footprint.pads) == 1, f"{reference}: expected one pad")
        pad = footprint.pads[0]
        require(pad.type == "np_thru_hole", f"{reference}: not NPTH")
        close(float(footprint.position.X), expected_xy[0], 0.010, f"{reference} X")
        close(float(footprint.position.Y), expected_xy[1], 0.010, f"{reference} Y")
        close(float(pad.drill.diameter), 2.200, 0.010, f"{reference} drill")
        require(set(pad.layers) == {"*.Cu", "*.Mask"}, f"{reference}: layer drift")
        holes[reference] = {"xy_mm": list(expected_xy), "drill_mm": float(pad.drill.diameter)}

    metadata = json.loads(FABRICATION_METADATA.read_text(encoding="utf-8"))
    expected_metadata = {
        "board": "PCB-MIC",
        "revision": "A",
        "material": "FR-4",
        "surface_finish": "ENIG",
        "board_thickness_mm": 1.0,
        "copper_layers": 2,
        "status": "NOT_FOR_MANUFACTURE",
        "authority": "hardware/kicad/REV_A_CAPTURE_ADDENDUM_003_PCB_MIC_MECH.md",
    }
    for key, expected in expected_metadata.items():
        require(metadata.get(key) == expected, f"fabrication metadata {key}: {metadata.get(key)!r} != {expected!r}")

    return {
        "status": "PASS",
        "outline_mm": [24.0, 22.0],
        "thickness_mm": float(board.general.thickness),
        "mounting_holes": holes,
        "fabrication_metadata": expected_metadata,
    }


def source_matches_commit(commit_sha: str, paths: list[Path]) -> bool:
    for path in paths:
        actual = subprocess.check_output(
            ["git", "hash-object", str(path)], cwd=ROOT, text=True
        ).strip()
        committed = subprocess.run(
            ["git", "rev-parse", f"{commit_sha}:{rel(path)}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if committed.returncode != 0 or committed.stdout.strip() != actual:
            return False
    return True


def resolve_commit(explicit: str | None) -> str:
    if explicit:
        require(re.fullmatch(r"[0-9a-fA-F]{40}", explicit) is not None, "--commit-sha must be a full 40-hex SHA")
        return explicit.lower()
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--commit-sha")
    parser.add_argument("--phase", default="LOCAL_OR_UNSPECIFIED")
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args()

    board_path = args.board.resolve()
    controlled_paths = [board_path, T5838_LIBRARY, MOLEX_LIBRARY, FABRICATION_METADATA]
    control_definition_paths = [AUDIT_TOOL, NATIVE_WORKFLOW]
    commit_sha = resolve_commit(args.commit_sha)
    source_commit_match = source_matches_commit(commit_sha, controlled_paths)
    control_commit_match = source_matches_commit(commit_sha, control_definition_paths)
    if args.require_clean_source:
        require(source_commit_match, f"PCB-MIC geometry sources do not match commit {commit_sha}")
        require(control_commit_match, f"PCB-MIC geometry audit control does not match commit {commit_sha}")

    board = Board().from_file(str(board_path))
    refs = {str(fp.properties.get("Reference")): fp for fp in board.footprints}
    require(len(refs) == len(board.footprints), "PCB-MIC contains duplicate/missing footprint references")
    require("MK1" in refs and "J1" in refs, f"PCB-MIC required footprints missing: {sorted(refs)}")

    t5838_library = Footprint().from_file(str(T5838_LIBRARY))
    molex_library = Footprint().from_file(str(MOLEX_LIBRARY))
    board_t5838 = audit_t5838(refs["MK1"], require_nets=True)
    library_t5838 = audit_t5838(t5838_library, require_nets=False)
    board_molex = audit_molex(refs["J1"], require_nets=True)
    library_molex = audit_molex(molex_library, require_nets=False)
    paste_ring = audit_t5838_paste_ring(board_path)
    mechanical = audit_mechanical(board)

    report = {
        "status": "PASS_GEOMETRY_EVIDENCE_REVIEW_A_SIGNATURE_STILL_REQUIRED",
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MIC",
        "phase": args.phase,
        "commit_binding": {
            "commit_sha": commit_sha,
            "controlled_sources_match_commit": source_commit_match,
            "audit_control_matches_commit": control_commit_match,
            "require_clean_source": bool(args.require_clean_source),
        },
        "source_files": [file_record(path) for path in controlled_paths],
        "audit_control_files": [file_record(path) for path in control_definition_paths],
        "checks": {
            "native_board_t5838": board_t5838,
            "project_library_t5838": library_t5838,
            "native_board_molex_5040500691": board_molex,
            "project_library_molex_5040500691": library_molex,
            "t5838_stencil_ring": paste_ring,
            "mechanical_and_fabrication_metadata": mechanical,
        },
        "remaining_review_a_evidence": [
            "commit-matched KiCad 9 ERC report with zero unexplained violations",
            "reviewer/date/commit signature and evidence links in PCB_MIC_CAPTURE_STATUS_REV_A.json",
        ],
        "release_effect": "NONE_NOT_FOR_MANUFACTURE",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-MIC Review-A copper/mask/paste/drill geometry audit PASS")
    print(
        f"commit={commit_sha} controlled_sources_match_commit={source_commit_match} "
        f"audit_control_matches_commit={control_commit_match} phase={args.phase}"
    )
    print(f"evidence={args.output}")
    print("Review A remains OPEN pending commit-matched KiCad 9 ERC and signed traceability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

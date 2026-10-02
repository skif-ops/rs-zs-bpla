#!/usr/bin/env python3
"""Apply PCB-MIC Review-B ECO-007 to the authoritative KiCad sources.

The edit is deliberately narrow and idempotent:
* orient the 32 T5838 pad-3 copper segments radially in KiCad coordinates;
* implement the four-gap TDK Figure 33 paste ring (OD 1.525 / ID 1.025 mm);
* disable plotted drill guide marks;
* record the nominal 2-layer 1.0 mm FR-4 / ENIG stack and board revision B.
"""
from __future__ import annotations

import math
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pcb"
LIB = ROOT / "hardware/kicad/native/PCB-MIC/libs/Dioneya.pretty/T5838_RevA.kicad_mod"


def sexpr_blocks(text: str, head: str) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    token = f"({head}"
    cursor = 0
    while True:
        start = text.find(token, cursor)
        if start < 0:
            return result
        depth = 0
        quoted = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if quoted:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    quoted = False
                continue
            if ch == '"':
                quoted = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    result.append((start, i + 1, text[start : i + 1]))
                    cursor = i + 1
                    break
        else:
            raise RuntimeError(f"unbalanced {head} expression")


def patch_ring_orientations(text: str) -> str:
    blocks = sexpr_blocks(text, 'pad "3"')
    if len(blocks) != 32:
        raise RuntimeError(f"expected 32 T5838 pad-3 segments, found {len(blocks)}")
    patched = text
    for start, end, block in reversed(blocks):
        match = re.search(r"\(at\s+([-+0-9.]+)\s+([-+0-9.]+)(?:\s+([-+0-9.]+))?\)", block)
        if match is None:
            raise RuntimeError("ring segment position missing")
        x = float(match.group(1))
        y = float(match.group(2))
        # KiCad file Y increases down.  The pad angle convention therefore needs
        # the physical angle atan2(-(y-cy), x-cx), not atan2(y-cy, x-cx).
        phi = math.degrees(math.atan2(-(y - 0.649999), x))
        target = (90.0 + phi) % 360.0
        target_text = f"{target:.6f}".rstrip("0").rstrip(".")
        replacement = f"(at {match.group(1)} {match.group(2)}"
        if abs(target) > 1e-9:
            replacement += f" {target_text}"
        replacement += ")"
        new_block = block[: match.start()] + replacement + block[match.end() :]
        patched = patched[:start] + new_block + patched[end:]
    return patched


def paste_arcs() -> str:
    cx, cy = 12.0, 16.649999
    radius = (1.525 + 1.025) / 4.0
    width = (1.525 - 1.025) / 2.0
    half_gap = math.degrees(math.asin(0.05 / radius))
    rows: list[str] = []
    for quadrant in range(4):
        a0 = quadrant * 90.0 + half_gap
        a1 = (quadrant + 1) * 90.0 - half_gap
        am = (a0 + a1) / 2.0

        def point(angle: float) -> tuple[float, float]:
            rad = math.radians(angle)
            return cx + radius * math.cos(rad), cy + radius * math.sin(rad)

        start = point(a0)
        mid = point(am)
        end = point(a1)
        uid = uuid.uuid5(uuid.NAMESPACE_URL, f"dioneya-pcb-mic-eco-007-paste-arc-{quadrant}")
        rows.append(
            "\t(gr_arc\n"
            f"\t\t(start {start[0]:.6f} {start[1]:.6f})\n"
            f"\t\t(mid {mid[0]:.6f} {mid[1]:.6f})\n"
            f"\t\t(end {end[0]:.6f} {end[1]:.6f})\n"
            "\t\t(stroke\n"
            f"\t\t\t(width {width:.6f})\n"
            "\t\t\t(type default)\n"
            "\t\t)\n"
            "\t\t(layer \"F.Paste\")\n"
            f"\t\t(uuid \"{uid}\")\n"
            "\t)"
        )
    return "\n".join(rows)


def patch_board(text: str) -> str:
    footprints = [
        block for block in sexpr_blocks(text, "footprint")
        if '(property "Reference" "MK1"' in block[2]
    ]
    if len(footprints) != 1:
        raise RuntimeError(f"expected one MK1 footprint, found {len(footprints)}")
    start, end, block = footprints[0]
    text = text[:start] + patch_ring_orientations(block) + text[end:]
    text, count = re.subn(r"\(drillshape\s+1\)", "(drillshape 0)", text)
    if count != 1:
        raise RuntimeError(f"drillshape replacement count {count}")
    text = text.replace('(rev "A")', '(rev "B")', 1)
    text = text.replace('(date "2026-09-09")', '(date "2026-09-30")', 1)
    text = text.replace(
        '(comment 1 "NOT FOR MANUFACTURE until Review A/B and DFM close")',
        '(comment 1 "CONTROLLED FIRST ARTICLE - REVIEW B - DFM REQUIRED")',
        1,
    )
    setup = "\t(setup\n"
    stack = (
        "\t(setup\n"
        "\t\t(stackup\n"
        "\t\t\t(layer \"F.SilkS\" (type \"Top Silk Screen\") (color \"White\"))\n"
        "\t\t\t(layer \"F.Paste\" (type \"Top Solder Paste\"))\n"
        "\t\t\t(layer \"F.Mask\" (type \"Top Solder Mask\") (color \"Green\") (thickness 0.01))\n"
        "\t\t\t(layer \"F.Cu\" (type \"copper\") (thickness 0.035))\n"
        "\t\t\t(layer \"dielectric 1\" (type \"core\") (thickness 0.91) (material \"FR4\"))\n"
        "\t\t\t(layer \"B.Cu\" (type \"copper\") (thickness 0.035))\n"
        "\t\t\t(layer \"B.Mask\" (type \"Bottom Solder Mask\") (color \"Green\") (thickness 0.01))\n"
        "\t\t\t(layer \"B.Paste\" (type \"Bottom Solder Paste\"))\n"
        "\t\t\t(layer \"B.SilkS\" (type \"Bottom Silk Screen\") (color \"White\"))\n"
        "\t\t\t(copper_finish \"ENIG\")\n"
        "\t\t\t(dielectric_constraints no)\n"
        "\t\t)\n"
    )
    if "\t\t(stackup\n" not in text:
        if setup not in text:
            raise RuntimeError("setup block not found")
        text = text.replace(setup, stack, 1)
    circles = [b for b in sexpr_blocks(text, "gr_circle") if '(layer "F.Paste")' in b[2]]
    if len(circles) != 1:
        raise RuntimeError(f"expected one board F.Paste circle, found {len(circles)}")
    start, end, _ = circles[0]
    text = text[:start] + paste_arcs() + text[end:]
    return text


def main() -> int:
    board_original = BOARD.read_text(encoding="utf-8")
    lib_original = LIB.read_text(encoding="utf-8")
    board_new = patch_board(board_original)
    lib_new = patch_ring_orientations(lib_original)
    BOARD.write_text(board_new, encoding="utf-8", newline="\n")
    LIB.write_text(lib_new, encoding="utf-8", newline="\n")
    print(BOARD)
    print(LIB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

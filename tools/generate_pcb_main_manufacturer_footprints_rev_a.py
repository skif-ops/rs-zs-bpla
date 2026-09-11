#!/usr/bin/env python3
"""Generate the PCB-MAIN Rev.A manufacturer-specific land patterns.

The dimensions below are transcribed from the cited manufacturer drawings.  The
files are deliberately generated from compact coordinate contracts so review and
CI can detect any silent footprint drift.
"""
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty"


def header(name: str, description: str, tags: str, attr: str = "smd") -> list[str]:
    return [
        f'(footprint "{name}" (version 20221018) (generator pcbnew)',
        '  (layer "F.Cu")',
        f'  (descr "{description}")',
        f'  (tags "{tags}")',
        f'  (attr {attr})',
        '  (fp_text reference "REF**" (at 0 -14) (layer "F.SilkS")',
        '    (effects (font (size 0.8 0.8) (thickness 0.12))))',
        f'  (fp_text value "{name}" (at 0 14) (layer "F.Fab") hide',
        '    (effects (font (size 0.8 0.8) (thickness 0.12))))',
    ]


def rect(lines: list[str], x1: float, y1: float, x2: float, y2: float,
         layer: str, width: float) -> None:
    lines.append(
        f'  (fp_rect (start {x1:g} {y1:g}) (end {x2:g} {y2:g}) '
        f'(stroke (width {width:g}) (type default)) (fill none) (layer "{layer}"))'
    )


def smd(lines: list[str], number: str, x: float, y: float, sx: float, sy: float,
        shape: str = "rect") -> None:
    extra = " (roundrect_rratio 0.2)" if shape == "roundrect" else ""
    lines.append(
        f'  (pad "{number}" smd {shape} (at {x:g} {y:g}) (size {sx:g} {sy:g}) '
        f'(layers "F.Cu" "F.Paste" "F.Mask"){extra})'
    )


def ufl() -> str:
    name = "Hirose_U.FL-R-SMT-1"
    lines = header(
        name,
        "Hirose U.FL-R-SMT-1 vertical receptacle; U.FL catalog 2026-08-01 recommended PCB and metal-mask patterns",
        "Hirose U.FL-R-SMT-1 coaxial vertical",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -2.7) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 2.7) (layer "F.Fab") hide'
    # The footprint origin and orientation retain the KiCad-library convention.
    # Copper/mask dimensions match the recommended PCB mounting pattern.
    rect(lines, -1.825, -2.25, 2.275, 2.25, "F.CrtYd", 0.05)
    rect(lines, -1.075, -1.55, 2.025, 1.55, "F.Fab", 0.10)
    for number, x, y, sx, sy in [
        ("1", -1.05, 0.0, 1.05, 1.00),
        ("SHIELD", 0.475, -1.475, 2.20, 1.05),
        ("SHIELD", 0.475, 1.475, 2.20, 1.05),
    ]:
        lines.append(
            f'  (pad "{number}" smd rect (at {x:g} {y:g}) (size {sx:g} {sy:g}) '
            '(layers "F.Cu" "F.Mask"))'
        )
    # Hirose specifies smaller metal-mask apertures than the copper.  Separate
    # paste-only pads prevent the KiCad-library copper-sized paste from leaking
    # back into a regenerated board.
    for x, y, sx, sy in [
        (-1.05, 0.0, 0.85, 0.80),
        (0.475, -1.475, 2.00, 0.90),
        (0.475, 1.475, 2.00, 0.90),
    ]:
        lines.append(
            f'  (pad "" smd rect (at {x:g} {y:g}) (size {sx:g} {sy:g}) '
            '(layers "F.Paste"))'
        )
    lines.append(")")
    return "\n".join(lines) + "\n"


def bg95() -> str:
    name = "Quectel_BG95-M3_LGA-102"
    lines = header(
        name,
        "Quectel BG95-M3 LGA-102; recommended footprint in BG95 Series Hardware Design V1.8 Figure 46",
        "Quectel BG95-M3 LGA-102 23.6x19.9",
    )
    # Quectel explicitly calls for at least 3 mm to adjacent components.
    rect(lines, -12.95, -14.80, 12.95, 14.80, "F.CrtYd", 0.05)
    rect(lines, -9.95, -11.80, 9.95, 11.80, "F.Fab", 0.10)
    rect(lines, -10.10, -11.95, 10.10, 11.95, "F.SilkS", 0.12)

    left_y = [-9.7 + 1.1 * index for index in range(10)] + [1.9 + 1.1 * index for index in range(8)]
    for number, y in enumerate(left_y, 1):
        smd(lines, str(number), -9.15, y, 1.10, 0.70, "rect" if number == 1 else "roundrect")
    top_x = [-7.45 + 1.1 * index for index in range(6)] + [0.55 + 1.1 * index for index in range(7)]
    for number, x in enumerate(top_x, 19):
        smd(lines, str(number), x, 11.00, 0.70, 1.10, "roundrect")
    right_y = [9.6 - 1.1 * index for index in range(8)] + [0.2 - 1.1 * index for index in range(10)]
    for number, y in enumerate(right_y, 32):
        smd(lines, str(number), 9.15, y, 1.10, 0.70, "roundrect")
    bottom_x = [7.15 - 1.1 * index for index in range(7)] + [-1.95 - 1.1 * index for index in range(6)]
    for number, x in enumerate(bottom_x, 50):
        smd(lines, str(number), x, -11.00, 0.70, 1.10, "roundrect")

    inner = {
        63: (-5.95, -4.25), 64: (-5.95, -2.55), 65: (-5.95, -0.85),
        66: (-5.95, 0.85), 67: (-5.95, 2.55), 68: (-5.95, 4.25),
        69: (-2.55, 7.65), 70: (-0.85, 7.65), 71: (0.85, 7.65), 72: (2.55, 7.65),
        73: (5.95, 4.25), 74: (5.95, 2.55), 75: (5.95, 0.85),
        76: (5.95, -0.85), 77: (5.95, -2.55), 78: (5.95, -4.25),
        79: (2.55, -7.65), 80: (0.85, -7.65), 81: (-0.85, -7.65), 82: (-2.55, -7.65),
        83: (-4.25, -4.25), 84: (-4.25, -2.55), 85: (-4.25, -0.85),
        86: (-4.25, 0.85), 87: (-4.25, 2.55), 88: (-4.25, 4.25),
        89: (-2.55, 5.95), 90: (-0.85, 5.95), 91: (0.85, 5.95), 92: (2.55, 5.95),
        93: (4.25, 4.25), 94: (4.25, 2.55), 95: (4.25, 0.85),
        96: (4.25, -0.85), 97: (4.25, -2.55), 98: (4.25, -4.25),
        99: (2.55, -5.95), 100: (0.85, -5.95), 101: (-0.85, -5.95), 102: (-2.55, -5.95),
    }
    for number, (x, y) in inner.items():
        smd(lines, str(number), x, y, 1.00, 1.00, "roundrect")
    lines.append(")")
    return "\n".join(lines) + "\n"


def microsd() -> str:
    name = "GCT_MEM2052-00-195-00-A"
    lines = header(
        name,
        "GCT MEM2052-00-195-00-A microSD push-push connector; official drawing MEM2052 Rev A3, 2022-11-23",
        "GCT MEM2052 microSD push-push card detect",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -9) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 9) (layer "F.Fab") hide'
    rect(lines, -7.525, -8.365, 7.525, 13.425, "F.CrtYd", 0.05)
    rect(lines, -7.00, -7.625, 7.00, 7.625, "F.Fab", 0.10)
    contacts = {
        "1": (1.905, 3.635), "2": (0.805, 3.235), "3": (-0.295, 3.635),
        "4": (-1.395, 3.835), "5": (-2.495, 3.635), "6": (-3.595, 3.835),
        "7": (-4.695, 3.635), "8": (-5.795, 3.635),
    }
    for number, (x, y) in contacts.items():
        smd(lines, number, x, y, 0.80, 1.50, "rect" if number == "1" else "roundrect")
    smd(lines, "CD", -3.585, -7.595, 1.00, 1.04)
    for x, y, sx, sy in [(-6.575, 5.925, 1.40, 1.90), (-5.035, -7.225, 1.20, 1.40),
                         (0.715, -7.225, 1.30, 1.40), (6.575, 6.925, 1.40, 1.90)]:
        smd(lines, "SHIELD", x, y, sx, sy)
    lines.append(")")
    return "\n".join(lines) + "\n"


def picolock() -> str:
    name = "Molex_504050-0291_PicoLock-2"
    lines = header(
        name,
        "Molex 504050-0291 Pico-Lock 1.50 mm two-circuit right-angle SMT; customer drawing 5040500000-SD PSD 001 Rev B",
        "Molex 504050-0291 Pico-Lock 1.5mm",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -4.5) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 4.5) (layer "F.Fab") hide'
    rect(lines, -4.48, -3.30, 4.48, 3.82, "F.CrtYd", 0.05)
    rect(lines, -3.485, -2.895, 3.485, 3.425, "F.Fab", 0.10)
    smd(lines, "1", -0.75, -2.795, 0.60, 1.00, "rect")
    smd(lines, "2", 0.75, -2.795, 0.60, 1.00, "roundrect")
    smd(lines, "", -3.355, 2.395, 1.25, 1.80)
    smd(lines, "", 3.355, 2.395, 1.25, 1.80)
    lines.append(")")
    return "\n".join(lines) + "\n"


def microfit() -> str:
    name = "Molex_43045-1202_MicroFit-12_RA"
    lines = header(
        name,
        "Molex 43045-1202 Micro-Fit 3.0 2x6 right-angle through-hole; customer drawing SD-43045-001 PSD 001 Rev H1",
        "Molex 43045-1202 Micro-Fit 3.0 12 circuit right angle",
        "through_hole",
    )
    lines[5] = '  (fp_text reference "REF**" (at 7.5 -10.1) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 7.5 5.7) (layer "F.Fab") hide'
    rect(lines, -4.08, -9.42, 19.08, 4.25, "F.CrtYd", 0.05)
    rect(lines, -3.575, -8.92, 18.575, 0.99, "F.Fab", 0.10)
    for number in range(1, 13):
        x = 3.0 * ((number - 1) % 6)
        y = 0.0 if number <= 6 else 3.0
        shape = "roundrect" if number == 1 else "circle"
        extra = " (roundrect_rratio 0.2)" if number == 1 else ""
        lines.append(
            f'  (pad "{number}" thru_hole {shape} (at {x:g} {y:g}) (size 1.5 1.5) '
            f'(drill 1.02) (layers "*.Cu" "*.Mask"){extra})'
        )
    for x in (2.15, 12.85):
        lines.append(
            f'  (pad "" np_thru_hole circle (at {x:g} -4.32) (size 3 3) '
            '(drill 3) (layers "*.Cu" "*.Mask"))'
        )
    lines.append(")")
    return "\n".join(lines) + "\n"


GENERATORS = {
    "Hirose_U.FL-R-SMT-1.kicad_mod": ufl,
    "Quectel_BG95-M3_LGA-102.kicad_mod": bg95,
    "GCT_MEM2052-00-195-00-A.kicad_mod": microsd,
    "Molex_504050-0291_PicoLock-2.kicad_mod": picolock,
    "Molex_43045-1202_MicroFit-12_RA.kicad_mod": microfit,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatches: list[str] = []
    for filename, generate in GENERATORS.items():
        path = OUT / filename
        expected = generate()
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                mismatches.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(expected, encoding="utf-8")
    if mismatches:
        raise SystemExit("stale manufacturer footprint(s): " + ", ".join(mismatches))
    print(f"PCB-MAIN manufacturer footprints: {'PASS' if args.check else 'GENERATED'} ({len(GENERATORS)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

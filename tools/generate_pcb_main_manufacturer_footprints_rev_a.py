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


def polygon(lines: list[str], points: list[tuple[float, float]],
            layer: str, width: float, fill: str = "none") -> None:
    coordinates = " ".join(f"(xy {x:g} {y:g})" for x, y in points)
    lines.append(
        f'  (fp_poly (pts {coordinates}) (stroke (width {width:g}) '
        f'(type default)) (fill {fill}) (layer "{layer}"))'
    )


def smd(lines: list[str], number: str, x: float, y: float, sx: float, sy: float,
        shape: str = "rect", mask_margin: float | None = None,
        paste_ratio: float | None = None,
        roundrect_ratio: float = 0.2) -> None:
    extra = f" (roundrect_rratio {roundrect_ratio:g})" if shape == "roundrect" else ""
    if mask_margin is not None:
        extra += f" (solder_mask_margin {mask_margin:g})"
    if paste_ratio is not None:
        extra += f" (solder_paste_margin_ratio {paste_ratio:g})"
    lines.append(
        f'  (pad "{number}" smd {shape} (at {x:g} {y:g}) (size {sx:g} {sy:g}) '
        f'(layers "F.Cu" "F.Paste" "F.Mask"){extra})'
    )


def keepout(lines: list[str], layers: str,
            points: list[tuple[float, float]]) -> None:
    layer_token = f'(layer "{layers}")' if layers == "F.Cu" else f'(layers "{layers}")'
    lines.extend([
        f'  (zone (net 0) (net_name "") {layer_token} (hatch full 0.508)',
        '    (connect_pads (clearance 0))',
        '    (min_thickness 0.254) (filled_areas_thickness no)',
        '    (keepout (tracks not_allowed) (vias not_allowed) (pads not_allowed) '
        '(copperpour not_allowed) (footprints not_allowed))',
        '    (fill (thermal_gap 0.508) (thermal_bridge_width 0.508))',
        '    (polygon',
        '      (pts',
    ])
    for x, y in points:
        lines.append(f'        (xy {x:g} {y:g})')
    lines.extend(['      )', '    )', '  )'])


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


def stm32u585_lqfp100() -> str:
    name = "ST_STM32U585_LQFP100_1L"
    lines = header(
        name,
        "ST STM32U585 LQFP100 package 1L; DS13086 Rev 10 Figure 96 footprint example",
        "ST STM32U585 LQFP100 14x14mm 0.5mm package 1L",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -9.2) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 9.2) (layer "F.Fab") hide'
    # Figure 96 gives a 16.7 mm outer land span, a 14.3 mm inner span,
    # 1.2 x 0.3 mm lands and 0.5 mm pitch.  The resulting land centers are
    # therefore 7.75 mm from the package origin.  The 12.3 mm row span is
    # independently reproduced by 25 lands across 24 pitches.
    rect(lines, -8.60, -8.60, 8.60, 8.60, "F.CrtYd", 0.05)
    polygon(lines, [(-7.0, -6.5), (-6.5, -7.0), (7.0, -7.0),
                    (7.0, 7.0), (-7.0, 7.0)], "F.Fab", 0.10)
    polygon(lines, [(-7.7375, -6.41), (-8.0775, -6.88),
                    (-7.3975, -6.88)], "F.SilkS", 0.12, "solid")
    for number in range(1, 26):
        smd(lines, str(number), -7.75, -6.0 + (number - 1) * 0.5, 1.2, 0.3)
    for number in range(26, 51):
        smd(lines, str(number), -6.0 + (number - 26) * 0.5, 7.75, 0.3, 1.2)
    for number in range(51, 76):
        smd(lines, str(number), 7.75, 6.0 - (number - 51) * 0.5, 1.2, 0.3)
    for number in range(76, 101):
        smd(lines, str(number), 6.0 - (number - 76) * 0.5, -7.75, 0.3, 1.2)
    lines.append(")")
    return "\n".join(lines) + "\n"


def ti_pw0014a() -> str:
    name = "TI_PW0014A_TSSOP14"
    lines = header(
        name,
        "TI PW0014A 14-pin TSSOP; 4220202/B 12/2023 example board layout",
        "Texas Instruments PW0014A TSSOP-14 0.65mm",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -3.35) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 3.35) (layer "F.Fab") hide'
    rect(lines, -3.90, -2.75, 3.90, 2.75, "F.CrtYd", 0.05)
    polygon(lines, [(-2.2, -2.0), (-1.7, -2.5), (2.2, -2.5),
                    (2.2, 2.5), (-2.2, 2.5)], "F.Fab", 0.10)
    polygon(lines, [(-2.84, -2.10), (-3.16, -2.55),
                    (-2.52, -2.55)], "F.SilkS", 0.12, "solid")
    # TI 4220202/B defines 1.50 x 0.45 mm lands, R0.05 corners,
    # 0.65 mm pitch and 5.80 mm row-center separation.  The example stencil
    # uses the same apertures; the preferred NSMD opening is +0.05 mm/side.
    for number in range(1, 8):
        smd(lines, str(number), -2.90, round(-1.95 + (number - 1) * 0.65, 6),
            1.50, 0.45, "roundrect", mask_margin=0.05,
            roundrect_ratio=1 / 9)
    for number in range(8, 15):
        y = round(1.95 - (number - 8) * 0.65, 6)
        smd(lines, str(number), 2.90, 0.0 if y == 0 else y,
            1.50, 0.45, "roundrect", mask_margin=0.05,
            roundrect_ratio=1 / 9)
    lines.append(")")
    return "\n".join(lines) + "\n"


def ti_pw0024a() -> str:
    name = "TI_PW0024A_TSSOP24"
    lines = header(
        name,
        "TI PW0024A 24-pin TSSOP; 4220208/A 02/2017 example board layout",
        "Texas Instruments PW0024A TSSOP-24 0.65mm",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -4.75) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 4.75) (layer "F.Fab") hide'
    rect(lines, -3.90, -4.15, 3.90, 4.15, "F.CrtYd", 0.05)
    polygon(lines, [(-2.2, -3.4), (-1.7, -3.9), (2.2, -3.9),
                    (2.2, 3.9), (-2.2, 3.9)], "F.Fab", 0.10)
    polygon(lines, [(-2.84, -3.73), (-3.16, -4.08),
                    (-2.52, -4.08)], "F.SilkS", 0.12, "solid")
    # TI 4220208/A defines the same 1.50 x 0.45 mm, R0.05 land and
    # 5.80 mm row spacing as PW0014A, with 24 pins on 0.65 mm pitch.
    for number in range(1, 13):
        smd(lines, str(number), -2.90, round(-3.575 + (number - 1) * 0.65, 6),
            1.50, 0.45, "roundrect", mask_margin=0.05,
            roundrect_ratio=1 / 9)
    for number in range(13, 25):
        smd(lines, str(number), 2.90, round(3.575 - (number - 13) * 0.65, 6),
            1.50, 0.45, "roundrect", mask_margin=0.05,
            roundrect_ratio=1 / 9)
    lines.append(")")
    return "\n".join(lines) + "\n"


def ti_drl0006a() -> str:
    name = "TI_DRL0006A_SOT6"
    lines = header(
        name,
        "TI DRL0006A 6-pin SOT-5X3; 4223266/F 11/2024 example board layout",
        "Texas Instruments DRL0006A SOT-5X3-6 0.5mm",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -1.55) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 1.55) (layer "F.Fab") hide'
    rect(lines, -1.33, -1.05, 1.33, 1.05, "F.CrtYd", 0.05)
    polygon(lines, [(-0.8, -0.55), (-0.55, -0.8), (0.8, -0.8),
                    (0.8, 0.8), (-0.8, 0.8)], "F.Fab", 0.10)
    polygon(lines, [(-1.00, -0.67), (-1.20, -0.92),
                    (-0.80, -0.92)], "F.SilkS", 0.12, "solid")
    # TI 4223266/F defines 0.67 x 0.30 mm lands, R0.05 corners,
    # 0.50 mm pitch and 1.48 mm row-center separation.  The example stencil
    # uses equal apertures and the preferred NSMD opening is +0.05 mm/side.
    expected = {
        "1": (-0.74, -0.50), "2": (-0.74, 0.00), "3": (-0.74, 0.50),
        "4": (0.74, 0.50), "5": (0.74, 0.00), "6": (0.74, -0.50),
    }
    for number, (x, y) in expected.items():
        smd(lines, number, x, y, 0.67, 0.30, "roundrect",
            mask_margin=0.05, roundrect_ratio=1 / 3)
    lines.append(")")
    return "\n".join(lines) + "\n"


def ti_dbv0005a() -> str:
    name = "TI_DBV0005A_SOT23-5"
    lines = header(
        name,
        "TI DBV0005A 5-pin SOT-23; 4214839/K 08/2024 example board layout",
        "Texas Instruments DBV0005A SOT-23-5 0.95mm",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -2.20) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 2.20) (layer "F.Fab") hide'
    rect(lines, -2.10, -1.78, 2.10, 1.78, "F.CrtYd", 0.05)
    polygon(lines, [(-0.8, -1.05), (-0.4, -1.45), (0.8, -1.45),
                    (0.8, 1.45), (-0.8, 1.45)], "F.Fab", 0.10)
    polygon(lines, [(-1.48, -1.08), (-1.68, -1.28),
                    (-1.28, -1.28)], "F.SilkS", 0.12, "solid")
    # TI 4214839/K defines 1.10 x 0.60 mm R0.05 lands and stencil
    # apertures, 0.95 mm lead pitch and 2.60 mm row-center separation.
    # The preferred NSMD detail permits up to 0.07 mm mask clearance
    # around the exposed metal; this controlled pattern uses that value.
    expected = {
        "1": (-1.30, -0.95), "2": (-1.30, 0.00), "3": (-1.30, 0.95),
        "4": (1.30, 0.95), "5": (1.30, -0.95),
    }
    for number, (x, y) in expected.items():
        smd(lines, number, x, y, 1.10, 0.60, "roundrect",
            mask_margin=0.07, roundrect_ratio=1 / 6)
    lines.append(")")
    return "\n".join(lines) + "\n"


def ti_dya0002a() -> str:
    name = "TI_DYA0002A_SOD523"
    lines = header(
        name,
        "TI DYA0002A 2-pin SOD-523; 4224978/B 09/2021 example board layout",
        "Texas Instruments DYA0002A SOD-523 2-pin",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -1.20) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 1.20) (layer "F.Fab") hide'
    rect(lines, -1.18, -0.65, 1.18, 0.65, "F.CrtYd", 0.05)
    polygon(lines, [(-0.8, -0.4), (0.8, -0.4), (0.8, 0.4),
                    (-0.8, 0.4)], "F.Fab", 0.10)
    polygon(lines, [(-1.00, -0.46), (-1.18, -0.64),
                    (-0.82, -0.64)], "F.SilkS", 0.12, "solid")
    # TI 4224978/B defines two 0.67 x 0.40 mm R0.05 lands with 1.48 mm
    # center spacing.  The example stencil uses equal apertures and the
    # preferred NSMD opening is +0.05 mm/side.
    smd(lines, "1", -0.74, 0.0, 0.67, 0.40, "roundrect",
        mask_margin=0.05, roundrect_ratio=0.25)
    smd(lines, "2", 0.74, 0.0, 0.67, 0.40, "roundrect",
        mask_margin=0.05, roundrect_ratio=0.25)
    lines.append(")")
    return "\n".join(lines) + "\n"


def nexperia_pesd5v0s1ul_sod882() -> str:
    name = "Nexperia_PESD5V0S1UL_SOD882"
    lines = header(
        name,
        "Nexperia PESD5V0S1UL SOD882; data sheet v5 2025-12-01 Figure 11 reflow footprint",
        "Nexperia PESD5V0S1UL DFN1006-2 SOD882",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -1.10) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 1.10) (layer "F.Fab") hide'
    rect(lines, -0.65, -0.45, 0.65, 0.45, "F.CrtYd", 0.05)
    polygon(lines, [(-0.5, -0.3), (0.5, -0.3), (0.5, 0.3),
                    (-0.5, 0.3)], "F.Fab", 0.10)
    polygon(lines, [(-0.58, -0.32), (-0.72, -0.46),
                    (-0.44, -0.46)], "F.SilkS", 0.12, "solid")
    # Nexperia Figure 11 defines 0.40 x 0.70 mm R0.05 copper lands,
    # 0.50 x 0.80 mm solder-resist openings and 0.30 x 0.60 mm R0.05
    # paste apertures at 0.70 mm center spacing.
    for number, x in (("1", -0.35), ("2", 0.35)):
        lines.append(
            f'  (pad "{number}" smd roundrect (at {x:g} 0) (size 0.4 0.7) '
            '(layers "F.Cu" "F.Mask") (roundrect_rratio 0.25) '
            '(solder_mask_margin 0.05))'
        )
        lines.append(
            f'  (pad "" smd roundrect (at {x:g} 0) (size 0.3 0.6) '
            '(layers "F.Paste") (roundrect_rratio 0.333333))'
        )
    lines.append(")")
    return "\n".join(lines) + "\n"


def nexperia_mmbt3904_sot23() -> str:
    name = "Nexperia_MMBT3904_SOT23"
    lines = header(
        name,
        "Nexperia MMBT3904 SOT23; data sheet v5 2026-04-08 Figure 8 reflow footprint",
        "Nexperia MMBT3904 SOT23 TO-236AB",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -2.20) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 2.20) (layer "F.Fab") hide'
    # Figure 8's 3.3 x 3.0 mm occupied area is rotated with the land pattern
    # into the project's established SOT23 orientation.
    rect(lines, -1.50, -1.65, 1.50, 1.65, "F.CrtYd", 0.05)
    polygon(lines, [(-0.65, -1.10), (-0.35, -1.45), (0.65, -1.45),
                    (0.65, 1.45), (-0.65, 1.45)], "F.Fab", 0.10)
    polygon(lines, [(-1.15, -1.43), (-1.35, -1.63),
                    (-0.95, -1.63)], "F.SilkS", 0.12, "solid")
    # Nexperia Figure 8 defines 0.60 x 0.70 mm rectangular copper lands,
    # 0.50 x 0.60 mm stencil apertures, and 0.75 x 0.85 mm solder-resist
    # openings at 1.90 mm lead pitch and 2.00 mm row spacing.  Rotating the
    # pattern 90 degrees counter-clockwise preserves KiCad's existing SOT23
    # pin orientation: pin 1 base, pin 2 emitter, pin 3 collector.
    expected = {
        "1": (-1.00, -0.95),
        "2": (-1.00, 0.95),
        "3": (1.00, 0.00),
    }
    for number, (x, y) in expected.items():
        lines.append(
            f'  (pad "{number}" smd rect (at {x:g} {y:g}) (size 0.7 0.6) '
            '(layers "F.Cu" "F.Mask") (solder_mask_margin 0.075))'
        )
        lines.append(
            f'  (pad "" smd rect (at {x:g} {y:g}) (size 0.6 0.5) '
            '(layers "F.Paste"))'
        )
    lines.append(")")
    return "\n".join(lines) + "\n"


def st_esdalc6v1_5p6_sot666() -> str:
    name = "ST_ESDALC6V1-5P6_SOT666"
    lines = header(
        name,
        "ST ESDALC6V1-5P6 SOT666; data sheet Rev 3 Figure 14 footprint",
        "ST ESDALC6V1-5P6 SOT666 0.5mm",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -1.45) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 1.45) (layer "F.Fab") hide'
    rect(lines, -1.55, -1.10, 1.55, 1.10, "F.CrtYd", 0.05)
    polygon(lines, [(-0.65, -0.53), (-0.33, -0.85), (0.65, -0.85),
                    (0.65, 0.85), (-0.65, 0.85)], "F.Fab", 0.10)
    polygon(lines, [(-1.28, -0.57), (-1.48, -0.77),
                    (-1.08, -0.77)], "F.SilkS", 0.12, "solid")
    # ST Rev 3 Figure 14 defines six rectangular 0.30 x 0.99 mm lands,
    # 0.50 mm lead pitch, a 0.62 mm inner gap and a 2.60 mm outer span.
    # Rotating the pattern 90 degrees preserves the board's established
    # SOT666 pin orientation; the resulting row centers are 1.61 mm apart.
    expected = {
        "1": (-0.805, -0.50), "2": (-0.805, 0.00),
        "3": (-0.805, 0.50), "4": (0.805, 0.50),
        "5": (0.805, 0.00), "6": (0.805, -0.50),
    }
    for number, (x, y) in expected.items():
        smd(lines, number, x, y, 0.99, 0.30)
    lines.append(")")
    return "\n".join(lines) + "\n"


def ti_dqa0010a() -> str:
    name = "TI_DQA0010A_USON10"
    lines = header(
        name,
        "TI DQA0010A 10-pin USON; 4220328/A 12/2015 example board layout",
        "Texas Instruments DQA0010A USON-10 2.5x1.0mm 0.5mm",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -1.85) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 1.85) (layer "F.Fab") hide'
    rect(lines, -0.95, -1.50, 0.95, 1.50, "F.CrtYd", 0.05)
    polygon(lines, [(-0.5, -1.0), (-0.25, -1.25), (0.5, -1.25),
                    (0.5, 1.25), (-0.5, 1.25)], "F.Fab", 0.10)
    polygon(lines, [(-0.68, -1.10), (-0.88, -1.35),
                    (-0.48, -1.35)], "F.SilkS", 0.12, "solid")
    # TI 4220328/A defines 0.565 mm land length and 0.835 mm between row
    # centers.  Signal lands are 0.20 mm wide; the two GND lands (3 and 8)
    # are 0.40 mm wide.  The preferred NSMD opening is +0.07 mm/side.
    # The 0.1 mm stencil keeps signal apertures equal to copper while reducing
    # GND apertures to 0.36 mm width (90% area under the package).
    expected = {
        "1": (-0.4175, -1.00), "2": (-0.4175, -0.50),
        "4": (-0.4175, 0.50), "5": (-0.4175, 1.00),
        "6": (0.4175, 1.00), "7": (0.4175, 0.50),
        "9": (0.4175, -0.50), "10": (0.4175, -1.00),
    }
    for number, (x, y) in expected.items():
        smd(lines, number, x, y, 0.565, 0.20, "roundrect",
            mask_margin=0.07, roundrect_ratio=0.5)
    for number, x in (("3", -0.4175), ("8", 0.4175)):
        lines.append(
            f'  (pad "{number}" smd roundrect (at {x:g} 0) (size 0.565 0.4) '
            '(layers "F.Cu" "F.Mask") (roundrect_rratio 0.25) '
            '(solder_mask_margin 0.07))'
        )
        lines.append(
            f'  (pad "" smd roundrect (at {x:g} 0) (size 0.565 0.36) '
            '(layers "F.Paste") (roundrect_rratio 0.277778))'
        )
    lines.append(")")
    return "\n".join(lines) + "\n"


def lis2dw12() -> str:
    name = "ST_LIS2DW12_LGA-12L"
    lines = header(
        name,
        "ST LIS2DW12 LGA-12L; DS11811 Rev 9 package geometry and TN0018 Rev 8 PCB/stencil rules",
        "ST LIS2DW12 LGA-12L 2x2mm 0.5mm",
    )
    lines[5] = '  (fp_text reference "REF**" (at 0 -1.6) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 1.6) (layer "F.Fab") hide'
    rect(lines, -1.25, -1.25, 1.25, 1.25, "F.CrtYd", 0.05)
    rect(lines, -1.00, -1.00, 1.00, 1.00, "F.Fab", 0.10)

    # DS11811 defines 0.275 x 0.250 mm package pads on 0.5 mm pitch.
    # TN0018 adds 0.1 mm to both PCB-land dimensions because the package-pad
    # spacing is greater than 0.2 mm.  A 0.05 mm mask margin gives the required
    # land + 0.1 mm opening; -10% per stencil dimension gives 81% land area,
    # inside ST's 70-90% recommendation.
    pads = {
        "1": (-0.7625, -0.75, 0.375, 0.350),
        "2": (-0.7625, -0.25, 0.375, 0.350),
        "3": (-0.7625, 0.25, 0.375, 0.350),
        "4": (-0.7625, 0.75, 0.375, 0.350),
        "5": (-0.25, 0.7625, 0.350, 0.375),
        "6": (0.25, 0.7625, 0.350, 0.375),
        "7": (0.7625, 0.75, 0.375, 0.350),
        "8": (0.7625, 0.25, 0.375, 0.350),
        "9": (0.7625, -0.25, 0.375, 0.350),
        "10": (0.7625, -0.75, 0.375, 0.350),
        "11": (0.25, -0.7625, 0.350, 0.375),
        "12": (-0.25, -0.7625, 0.350, 0.375),
    }
    for number, (x, y, sx, sy) in pads.items():
        smd(lines, number, x, y, sx, sy, mask_margin=0.05, paste_ratio=-0.10)
    lines.append(")")
    return "\n".join(lines) + "\n"


def raytac_mdbt50q_p1mv2() -> str:
    name = "Raytac_MDBT50Q-P1MV2"
    lines = header(
        name,
        "Raytac MDBT50Q-P1MV2; Footprint Design Guide 230606 solder-pad and RF-layout control",
        "Raytac MDBT50Q-P1MV2 nRF52840 PCB antenna",
    )
    lines[5] = '  (fp_text reference "REF**" (at -6 0 270) (layer "F.SilkS")'
    lines[7] = f'  (fp_text value "{name}" (at 0 8.95) (layer "F.Fab") hide'
    rect(lines, -5.75, -8.25, 5.75, 8.25, "F.CrtYd", 0.05)
    rect(lines, -5.25, -7.75, 5.25, 7.75, "F.Fab", 0.10)

    # Manufacturer Eagle library 230606, normalized to KiCad's mirrored-Y
    # local convention.  Rotated package-edge lands are represented by swapped
    # X/Y sizes so the pure-kiutils materializer need not retain local angles.
    pads: dict[int, tuple[float, float, float, float]] = {
        1: (-4.65, -3.75, .6, .4), 2: (-4.65, -2.65, .6, .4),
        3: (-4.65, -1.85, .6, .4), 4: (-4.65, -.25, .6, .4),
        5: (-3.75, .15, .6, .4), 6: (-4.65, .55, .6, .4),
        7: (-3.75, .95, .6, .4), 8: (-4.65, 1.35, .6, .4),
        9: (-3.75, 1.75, .6, .4), 10: (-4.65, 2.15, .6, .4),
        11: (-3.75, 2.55, .6, .4), 12: (-4.65, 2.95, .6, .4),
        13: (-3.75, 3.35, .6, .4), 14: (-4.65, 3.75, .6, .4),
        34: (4.65, 6.15, .6, .4), 35: (4.65, 5.35, .6, .4),
        36: (3.75, 4.95, .6, .4), 37: (4.65, 4.55, .6, .4),
        38: (3.75, 4.15, .6, .4), 39: (4.65, 3.75, .6, .4),
        40: (3.75, 3.35, .6, .4), 41: (4.65, 2.95, .6, .4),
        42: (3.75, 2.55, .6, .4), 43: (3.75, 1.75, .6, .4),
        44: (4.65, 1.35, .6, .4), 45: (3.75, .95, .6, .4),
        46: (4.65, .55, .6, .4), 47: (3.75, .15, .6, .4),
        48: (4.65, -.25, .6, .4), 49: (3.75, -.65, .6, .4),
        50: (3.75, -1.45, .6, .4), 51: (4.65, -1.85, .6, .4),
        52: (3.75, -2.25, .6, .4), 53: (4.65, -2.65, .6, .4),
        54: (3.75, -3.05, .6, .4), 55: (4.65, -3.75, .6, .4),
    }
    for number, x in zip((15, 16, 17, 18, 20, 22, 24, 26, 28, 30, 31, 32, 33),
                         (-4.8, -4.0, -3.2, -2.4, -1.6, -.8, 0, .8, 1.6, 2.4, 3.2, 4.0, 4.8)):
        pads[number] = (x, 7.15, .4, .6)
    for number, x in zip((19, 21, 23, 25, 27, 29), (-2.0, -1.2, -.4, .4, 1.2, 2.0)):
        pads[number] = (x, 6.25, .4, .6)
    for number, x in zip(range(56, 62), (-2.0, -1.2, -.4, .4, 1.2, 2.0)):
        pads[number] = (x, .55, .4, .6)
    if set(pads) != set(range(1, 62)):
        raise RuntimeError("Raytac coordinate contract must define exactly 61 pads")
    for number in range(1, 62):
        smd(lines, str(number), *pads[number])

    # The 1.6 x 1.2 mm top-layer feed keepout and the minimum 10.5 x 3.8 mm
    # all-copper antenna keepout are taken from the Raytac RF layout.  U11's
    # locked -90 degree placement maps the latter to board x=106.20..110.00,
    # y=30.00..40.50 mm.
    keepout(lines, "F.Cu", [(-2.3, -3.95), (-.7, -3.95), (-.7, -2.75), (-2.3, -2.75)])
    keepout(lines, "*.Cu", [(-5.25, -7.75), (5.25, -7.75), (5.25, -3.95), (-5.25, -3.95)])
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
    "ST_STM32U585_LQFP100_1L.kicad_mod": stm32u585_lqfp100,
    "TI_PW0014A_TSSOP14.kicad_mod": ti_pw0014a,
    "TI_PW0024A_TSSOP24.kicad_mod": ti_pw0024a,
    "TI_DRL0006A_SOT6.kicad_mod": ti_drl0006a,
    "TI_DBV0005A_SOT23-5.kicad_mod": ti_dbv0005a,
    "TI_DYA0002A_SOD523.kicad_mod": ti_dya0002a,
    "Nexperia_PESD5V0S1UL_SOD882.kicad_mod": nexperia_pesd5v0s1ul_sod882,
    "Nexperia_MMBT3904_SOT23.kicad_mod": nexperia_mmbt3904_sot23,
    "ST_ESDALC6V1-5P6_SOT666.kicad_mod": st_esdalc6v1_5p6_sot666,
    "TI_DQA0010A_USON10.kicad_mod": ti_dqa0010a,
    "ST_LIS2DW12_LGA-12L.kicad_mod": lis2dw12,
    "Raytac_MDBT50Q-P1MV2.kicad_mod": raytac_mdbt50q_p1mv2,
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

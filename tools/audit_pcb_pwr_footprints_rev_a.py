#!/usr/bin/env python3
"""Audit manufacturer-controlled PCB-PWR footprints against frozen geometry."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from kiutils.footprint import Footprint

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY = ROOT / "hardware/kicad/native/PCB-PWR/libs/DioneyaPWR.pretty"
DEFAULT_SHARED_LIBRARY = ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty"


def rounded_pad(pad) -> tuple[str, float, float, float, float, tuple[str, ...]]:
    return (
        str(pad.number),
        round(float(pad.position.X), 4), round(float(pad.position.Y), 4),
        round(float(pad.size.X), 4), round(float(pad.size.Y), 4),
        tuple(str(layer) for layer in pad.layers),
    )


def detailed_pad(pad) -> tuple[
    str, str, float, float, float, float, tuple[str, ...], float | None, float | None
]:
    return (
        str(pad.number), str(pad.shape),
        round(float(pad.position.X), 4), round(float(pad.position.Y), 4),
        round(float(pad.size.X), 4), round(float(pad.size.Y), 4),
        tuple(str(layer) for layer in pad.layers),
        None if pad.roundrectRatio is None else round(float(pad.roundrectRatio), 6),
        None if pad.solderMaskMargin is None else round(float(pad.solderMaskMargin), 4),
    )


def audit_simple_ti_package(path: Path, expected_name: str, expected: set[tuple]) -> None:
    if not path.is_file():
        raise RuntimeError(f"controlled TI footprint missing: {path}")
    fp = Footprint.from_file(str(path), encoding="utf-8")
    if str(fp.entryName) != expected_name:
        raise RuntimeError(f"unexpected controlled TI footprint name: {fp.entryName}")
    actual = [detailed_pad(p) for p in fp.pads]
    if set(actual) != expected or len(actual) != len(expected):
        raise RuntimeError(f"{expected_name} manufacturer geometry drift: {actual}")


def audit_ti_support_ics(library: Path, shared_library: Path) -> None:
    dbv6 = {
        ("1", "roundrect", -1.3, -0.95, 1.1, 0.6, ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07),
        ("2", "roundrect", -1.3, 0.00, 1.1, 0.6, ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07),
        ("3", "roundrect", -1.3, 0.95, 1.1, 0.6, ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07),
        ("4", "roundrect", 1.3, 0.95, 1.1, 0.6, ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07),
        ("5", "roundrect", 1.3, 0.00, 1.1, 0.6, ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07),
        ("6", "roundrect", 1.3, -0.95, 1.1, 0.6, ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07),
    }
    audit_simple_ti_package(library / "TI_DBV0006A_SOT23-6.kicad_mod", "TI_DBV0006A_SOT23-6", dbv6)

    dbv5 = dbv6 - {
        ("5", "roundrect", 1.3, 0.00, 1.1, 0.6, ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07),
        ("6", "roundrect", 1.3, -0.95, 1.1, 0.6, ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07),
    }
    dbv5.add(("5", "roundrect", 1.3, -0.95, 1.1, 0.6,
              ("F.Cu", "F.Paste", "F.Mask"), 0.166667, 0.07))
    audit_simple_ti_package(shared_library / "TI_DBV0005A_SOT23-5.kicad_mod",
                            "TI_DBV0005A_SOT23-5", dbv5)

    dgs10 = set()
    for number, y in zip(("1", "2", "3", "4", "5"), (-1.0, -0.5, 0.0, 0.5, 1.0)):
        dgs10.add((number, "roundrect", -2.2, y, 1.45, 0.3,
                   ("F.Cu", "F.Paste", "F.Mask"), 0.333333, 0.05))
    for number, y in zip(("10", "9", "8", "7", "6"), (-1.0, -0.5, 0.0, 0.5, 1.0)):
        dgs10.add((number, "roundrect", 2.2, y, 1.45, 0.3,
                   ("F.Cu", "F.Paste", "F.Mask"), 0.333333, 0.05))
    audit_simple_ti_package(library / "TI_DGS0010A_VSSOP10.kicad_mod",
                            "TI_DGS0010A_VSSOP10", dgs10)


def audit_remaining_power_components(library: Path) -> None:
    j1_path = library / "Molex_43045-0213_MicroFit-2_Vertical.kicad_mod"
    if not j1_path.is_file():
        raise RuntimeError(f"controlled J1 footprint missing: {j1_path}")
    j1 = Footprint.from_file(str(j1_path), encoding="utf-8")
    if str(j1.entryName) != "Molex_43045-0213_MicroFit-2_Vertical":
        raise RuntimeError(f"unexpected J1 footprint name: {j1.entryName}")
    actual_j1 = {
        (
            str(p.number), str(p.type), str(p.shape),
            round(float(p.position.X), 4), round(float(p.position.Y), 4),
            round(float(p.size.X), 4), round(float(p.size.Y), 4),
            round(float(p.drill.diameter), 4), tuple(str(layer) for layer in p.layers),
        )
        for p in j1.pads
    }
    expected_j1 = {
        ("1", "thru_hole", "roundrect", 0.0, 3.0, 1.5, 1.5, 1.02, ("*.Cu", "*.Mask")),
        ("2", "thru_hole", "circle", 0.0, 0.0, 1.5, 1.5, 1.02, ("*.Cu", "*.Mask")),
        ("", "np_thru_hole", "circle", -3.0, 0.0, 0.94, 0.94, 0.94, ("*.Cu", "*.Mask")),
        ("", "np_thru_hole", "circle", 3.0, 0.0, 0.94, 0.94, 0.94, ("*.Cu", "*.Mask")),
    }
    if actual_j1 != expected_j1 or len(j1.pads) != len(expected_j1):
        raise RuntimeError(f"Molex 43045-0213 hole-field drift: {actual_j1}")

    wsk = {
        ("1", "rect", -2.985, -0.635, 2.29, 2.03,
         ("F.Cu", "F.Paste", "F.Mask"), None, None),
        ("2", "rect", 2.985, 0.635, 2.29, 2.03,
         ("F.Cu", "F.Paste", "F.Mask"), None, None),
        ("3", "rect", -3.28, 1.27, 1.70, 0.76,
         ("F.Cu", "F.Paste", "F.Mask"), None, None),
        ("4", "rect", 3.28, -1.27, 1.70, 0.76,
         ("F.Cu", "F.Paste", "F.Mask"), None, None),
    }
    audit_simple_ti_package(library / "Vishay_WSK2512_4T_T1.19mm.kicad_mod",
                            "Vishay_WSK2512_4T_T1.19mm", wsk)

    xal = {
        ("1", "rect", 2.26, 0.0, 1.58, 6.50,
         ("F.Cu", "F.Paste", "F.Mask"), None, None),
        ("2", "rect", -2.26, 0.0, 1.58, 6.50,
         ("F.Cu", "F.Paste", "F.Mask"), None, None),
    }
    audit_simple_ti_package(library / "Coilcraft_XAL7030_472.kicad_mod",
                            "Coilcraft_XAL7030_472", xal)

    testpoint = {
        ("1", "circle", 0.0, 0.0, 1.70, 1.70,
         ("F.Cu", "F.Mask"), None, 0.20),
    }
    audit_simple_ti_package(library / "TestPoint_DFT_1.7mm_NoPaste.kicad_mod",
                            "TestPoint_DFT_1.7mm_NoPaste", testpoint)


def audit_lmr60440(library: Path) -> None:
    path = library / "LMR60440_RAK0009A.kicad_mod"
    if not path.is_file():
        raise RuntimeError(f"controlled LMR60440 footprint missing: {path}")
    fp = Footprint.from_file(str(path), encoding="utf-8")
    if str(fp.entryName) != "LMR60440_RAK0009A":
        raise RuntimeError(f"unexpected LMR60440 footprint name: {fp.entryName}")
    if len(fp.pads) != 20:
        raise RuntimeError(f"LMR60440 pad/aperture count drift: {len(fp.pads)}")

    copper = [detailed_pad(p) for p in fp.pads if "F.Cu" in p.layers]
    expected_copper = {
        ("1", "roundrect", -0.900, -0.9275, 0.600, 0.345, ("F.Cu", "F.Mask"), 0.289855, 0.05),
        ("1", "roundrect", -0.725, -1.1025, 0.250, 0.695, ("F.Cu", "F.Mask"), 0.400000, 0.05),
        ("3", "roundrect", -0.900, 0.9275, 0.600, 0.345, ("F.Cu", "F.Mask"), 0.289855, 0.05),
        ("3", "roundrect", -0.725, 1.1025, 0.250, 0.695, ("F.Cu", "F.Mask"), 0.400000, 0.05),
        ("9", "roundrect", -0.075, -1.125, 0.250, 0.650, ("F.Cu", "F.Paste", "F.Mask"), 0.400000, 0.05),
        ("4", "roundrect", -0.075, 1.125, 0.250, 0.650, ("F.Cu", "F.Paste", "F.Mask"), 0.400000, 0.05),
        ("8", "roundrect", 0.700, -1.175, 0.300, 0.550, ("F.Cu", "F.Paste", "F.Mask"), 0.333333, 0.05),
        ("8", "roundrect", 0.900, -1.000, 0.700, 0.200, ("F.Cu", "F.Paste", "F.Mask"), 0.500000, 0.05),
        ("5", "roundrect", 0.700, 1.175, 0.300, 0.550, ("F.Cu", "F.Paste", "F.Mask"), 0.333333, 0.05),
        ("5", "roundrect", 0.900, 1.000, 0.700, 0.200, ("F.Cu", "F.Paste", "F.Mask"), 0.500000, 0.05),
        ("7", "roundrect", 0.875, -0.525, 0.650, 0.250, ("F.Cu", "F.Paste", "F.Mask"), 0.400000, 0.05),
        ("6", "roundrect", 0.875, 0.525, 0.650, 0.250, ("F.Cu", "F.Paste", "F.Mask"), 0.400000, 0.05),
        ("2", "roundrect", 0.000, 0.000, 2.500, 0.550, ("F.Cu",), 0.363636, None),
    }
    if set(copper) != expected_copper or len(copper) != len(expected_copper):
        raise RuntimeError(f"LMR60440 copper geometry drift: {copper}")
    if Counter(p[0] for p in copper) != Counter(
        {"1": 2, "2": 1, "3": 2, "4": 1, "5": 2, "6": 1, "7": 1, "8": 2, "9": 1}
    ):
        raise RuntimeError("LMR60440 electrical pad-number coverage drift")

    paste = [detailed_pad(p) for p in fp.pads if p.layers == ["F.Paste"]]
    expected_paste = {
        ("", "roundrect", -0.920, -0.9275, 0.560, 0.345, ("F.Paste",), 0.289855, None),
        ("", "roundrect", -0.745, -1.1025, 0.210, 0.695, ("F.Paste",), 0.476190, None),
        ("", "roundrect", -0.920, 0.9275, 0.560, 0.345, ("F.Paste",), 0.289855, None),
        ("", "roundrect", -0.745, 1.1025, 0.210, 0.695, ("F.Paste",), 0.476190, None),
        ("", "roundrect", -0.650, 0.000, 1.100, 0.410, ("F.Paste",), 0.243902, None),
        ("", "roundrect", 0.650, 0.000, 1.100, 0.300, ("F.Paste",), 0.333333, None),
    }
    if set(paste) != expected_paste or len(paste) != len(expected_paste):
        raise RuntimeError(f"LMR60440 explicit stencil geometry drift: {paste}")

    mask = [p for p in fp.pads if p.layers == ["F.Mask"]]
    if len(mask) != 1 or mask[0].shape != "custom" or len(mask[0].customPadPrimitives) != 1:
        raise RuntimeError("LMR60440 pad-2 solder-mask aperture is not one controlled custom polygon")
    primitive = mask[0].customPadPrimitives[0]
    actual_points = [(round(float(p.X), 3), round(float(p.Y), 3)) for p in primitive.coordinates]
    expected_points = [
        (-1.150, -0.225), (-0.059, -0.225), (-0.027, -0.214), (0.037, -0.161),
        (0.069, -0.150), (1.150, -0.150), (1.200, -0.100), (1.200, 0.100),
        (1.150, 0.150), (0.069, 0.150), (0.037, 0.161), (-0.027, 0.214),
        (-0.059, 0.225), (-1.150, 0.225), (-1.200, 0.175), (-1.200, -0.175),
    ]
    if actual_points != expected_points or float(primitive.width) != 0 or primitive.fill != "yes":
        raise RuntimeError(f"LMR60440 pad-2 solder-mask polygon drift: {actual_points}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    ap.add_argument("--shared-library", type=Path, default=DEFAULT_SHARED_LIBRARY)
    args = ap.parse_args()

    path = args.library / "CSD18540Q5B_DNK.kicad_mod"
    if not path.is_file():
        raise RuntimeError(f"controlled CSD18540 footprint missing: {path}")
    fp = Footprint.from_file(str(path), encoding="utf-8")
    if str(fp.entryName) != "CSD18540Q5B_DNK":
        raise RuntimeError(f"unexpected footprint name: {fp.entryName}")

    copper = [rounded_pad(p) for p in fp.pads if str(p.number)]
    paste = [rounded_pad(p) for p in fp.pads if not str(p.number)]
    expected_copper = {
        ("1", 2.770, 1.905, 1.372, 0.710, ("F.Cu", "F.Mask")),
        ("2", 2.770, 0.635, 1.372, 0.710, ("F.Cu", "F.Mask")),
        ("3", 2.770, -0.635, 1.372, 0.710, ("F.Cu", "F.Mask")),
        ("4", 2.770, -1.905, 1.372, 0.710, ("F.Cu", "F.Mask")),
        ("5", -1.236, -1.905, 4.440, 0.710, ("F.Cu", "F.Mask")),
        ("6", -1.236, -0.635, 4.440, 0.710, ("F.Cu", "F.Mask")),
        ("7", -1.236, 0.635, 4.440, 0.710, ("F.Cu", "F.Mask")),
        ("8", -1.236, 1.905, 4.440, 0.710, ("F.Cu", "F.Mask")),
        ("5", -0.941, -1.270, 3.850, 0.560, ("F.Cu", "F.Mask")),
        ("5", -0.941, 0.000, 3.850, 0.560, ("F.Cu", "F.Mask")),
        ("5", -0.941, 1.270, 3.850, 0.560, ("F.Cu", "F.Mask")),
    }
    if set(copper) != expected_copper or len(copper) != len(expected_copper):
        raise RuntimeError(f"CSD18540 copper geometry drift: {copper}")
    if Counter(p[0] for p in copper) != Counter({"1": 1, "2": 1, "3": 1, "4": 1, "5": 4, "6": 1, "7": 1, "8": 1}):
        raise RuntimeError("CSD18540 electrical pad-number coverage drift")

    expected_paste = set()
    for y in (-1.905, -0.635, 0.635, 1.905):
        expected_paste.add(("", -2.910, y, 0.766, 0.508, ("F.Paste",)))
        expected_paste.add(("", 2.758, y, 1.072, 0.562, ("F.Paste",)))
    for y in (-1.569, -0.523, 0.523, 1.569):
        expected_paste.add(("", -1.594, y, 1.294, 0.746, ("F.Paste",)))
        expected_paste.add(("", 0.050, y, 1.294, 0.746, ("F.Paste",)))
    if set(paste) != expected_paste or len(paste) != 16:
        raise RuntimeError(f"CSD18540 stencil geometry drift: {paste}")

    audit_lmr60440(args.library)
    audit_ti_support_ics(args.library, args.shared_library)
    audit_remaining_power_components(args.library)
    print("PCB-PWR manufacturer footprint audit PASS")
    print("Q1 CSD18540Q5B: TI SLPS488B copper + 16-aperture stencil exact")
    print("U3/U4 LMR60440: TI SNAS877 RAK0009A copper/mask/stencil exact")
    print("U1/U2/U5: TI DBV0006A/DGS0010A/DBV0005A lands, mask and stencil exact")
    print("J1/RSH1/L1/L2: Molex/Vishay/Coilcraft manufacturer geometry exact")
    print("TP1-TP10: project DFT target 1.70 mm copper / 2.10 mm mask / no paste exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

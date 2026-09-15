
#!/usr/bin/env python3
"""Generate the controlled PCB-MAIN Rev.A placement-stage native layout.

The output is deliberately an engineering layout candidate, not fabrication data.
It contains the locked six-layer outline, mounting holes, mechanical anchors, all
schematic components and all native nets.  Routing and manufacturer approval of
project-local footprints remain Review-B gates and are never inferred here.

Run with the pcbnew Python module supplied by KiCad 7+; CI validates the resulting
file with KiCad 9.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import uuid
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_pcb_main_native_schematic_rev_a import expected_components  # noqa: E402

OUT = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
MECH = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
PLACEMENT = ROOT / "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv"
KICAD_FP = Path(os.environ.get("DIONEYA_KICAD_FOOTPRINT_DIR", "/usr/share/kicad/footprints"))
PROJECT_FP = ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty"
PASSIVE_COURTYARD_STATUS = "CONTROLLED_PAD_ENVELOPE_PLUS_0.25_MM"
PASSIVE_COURTYARD_SOURCE = "PCB_MAIN_PASSIVE_COURTYARD_RULE_REV_A"

KICAD_DRAWING_VERIFIED = {
    (
        "Connector_Molex.pretty",
        "Molex_Pico-Lock_504050-0691_1x06-1MP_P1.50mm_Horizontal",
    ): "Molex_5040500000-SD_PSD000_RevB_RecommendedPattern",
    (
        "Connector_USB.pretty",
        "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
    ): "GCT_USB4105_RevB4_2023-12-18_RecommendedPCBLayout",
}

STANDARD = {
    "LQFP100_14x14": ("PROJECT", "ST_STM32U585_LQFP100_1L", {}),
    "LGA-12_2x2mm": ("PROJECT", "ST_LIS2DW12_LGA-12L", {}),
    "TSSOP-24_PW": ("PROJECT", "TI_PW0024A_TSSOP24", {}),
    "TSSOP-14_PW": ("PROJECT", "TI_PW0014A_TSSOP14", {}),
    "SOT23": ("PROJECT", "Nexperia_MMBT3904_SOT23", {}),
    "SOT-563_SC-89": ("PROJECT", "Vishay_Si1016X_SC-89", {}),
    "SOD882": ("PROJECT", "Nexperia_PESD5V0S1UL_SOD882", {}),
    "SOIC-16_300mil_F": ("PROJECT", "Winbond_W25Q512JV_PackageF_IPC_Candidate", {}),
    "U.FL_SMT": ("PROJECT", "Hirose_U.FL-R-SMT-1", {}),
    "USB-C_16P_horizontal_top_mount_1.20mm_stake": (
        "Connector_USB.pretty", "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
        {"S1": "SHIELD"},
    ),
    "SOT666_1.6x1.6mm": ("PROJECT", "ST_ESDALC6V1-5P6_SOT666", {}),
    "SOD-523_DYA": ("PROJECT", "TI_DYA0002A_SOD523", {}),
    "SOT-9X3_DRT": ("PROJECT", "TI_DRT0003A_IPC_Candidate", {}),
    "SOT-5X3-6_DRL": ("PROJECT", "TI_DRL0006A_SOT6", {}),
    "7343-31": ("PROJECT", "KEMET_T52X_D_7343-31_DensityB", {}),
    "Pico-Lock_1.5_1x06_Right_Angle": (
        "Connector_Molex.pretty", "Molex_Pico-Lock_504050-0691_1x06-1MP_P1.50mm_Horizontal",
        {"MP": ""},
    ),
    "nRF52840_SMD_10.5x15.5_61P_PCB_antenna": (
        "PROJECT", "Raytac_MDBT50Q-P1MV2", {},
    ),
    "USON-10_DQA": ("PROJECT", "TI_DQA0010A_USON10", {}),
    "SOT-23-5_DBV": ("PROJECT", "TI_DBV0005A_SOT23-5", {}),
    "SOD962-2": ("PROJECT", "PESD5V0C1BSF_SOD962-2", {}),
    "UDFN-6L_2x2mm": ("PROJECT", "STTS22H_UDFN-6L", {}),
    "DFN-6_DCB_2x3mm": ("PROJECT", "LT6000_DCB-7", {}),
    "CSP-4_1.5x0.8mm": ("PROJECT", "SiT1552_JE_CSP-4", {}),
    "LCC-18_9.7x10.1mm": ("PROJECT", "u-blox_MAX-M10S_LCC-18", {}),
    "SMD_20x14_22P_1.27mm": ("PROJECT", "Ebyte_E22-M22S_Castellated-22", {}),
    "1109-5": ("PROJECT", "Abracon_ABSES5AF_1109-5", {}),
    "TE_NanoSIM_H1.37": ("PROJECT", "TE_2336582-1_NanoSIM", {}),
    "LGA-102_23.6x19.9mm": ("PROJECT", "Quectel_BG95-M3_LGA-102", {}),
    "Micro-Fit_3.0_2x06_Right_Angle": ("PROJECT", "Molex_43045-1202_MicroFit-12_RA", {}),
    "Pico-Lock_1.5mm_2P_RA_SMT": ("PROJECT", "Molex_504050-0291_PicoLock-2", {}),
    "microSD_push-push_1.95mm_8P_CD": ("PROJECT", "GCT_MEM2052-00-195-00-A", {}),
    "0402": None,
    "0603": None,
    "0805": None,
    "1206": None,
    "1210": None,
}

BODY = {
    "LGA-102_23.6x19.9mm": (23.6, 19.9),
    "LCC-18_9.7x10.1mm": (9.7, 10.1),
    "SMD_20x14_22P_1.27mm": (20.0, 14.0),
    "nRF52840_SMD_10.5x15.5_61P_PCB_antenna": (15.5, 10.5),
    "TE_NanoSIM_H1.37": (16.0, 14.0),
    "Micro-Fit_3.0_2x06_Right_Angle": (18.0, 10.0),
    "Pico-Lock_1.5_1x06_Right_Angle": (10.0, 5.0),
    "Pico-Lock_1.5mm_2P_RA_SMT": (5.0, 4.0),
    "microSD_push-push_1.95mm_8P_CD": (14.5, 14.0),
    "USB-C_16P_horizontal_top_mount_1.20mm_stake": (9.5, 7.5),
    "7343-31": (7.3, 4.3),
}


def mm(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I_MM(float(x), float(y))


def set_footprint_property(fp: pcbnew.FOOTPRINT, key: str, value: str) -> None:
    """Set a custom footprint field across the KiCad 7-to-9 SWIG API change."""
    if hasattr(fp, "SetField"):
        fp.SetField(key, value)
    else:
        fp.SetProperty(key, value)


def props(symbol: dict) -> tuple[str, str]:
    return str(symbol["mpn"]), str(symbol["package"])


def anchors() -> dict[str, tuple[float, float, float]]:
    result: dict[str, tuple[float, float, float]] = {}
    with MECH.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["Feature_Type"] in {"CONNECTOR_PLACEMENT", "MODULE_PLACEMENT"}:
                result[row["RefDes"]] = (
                    float(row["X_mm"]), float(row["Y_mm"]), float(row["Rotation_deg"])
                )
    return result


def placement_manifest() -> dict[str, tuple[float, float, float]]:
    result: dict[str, tuple[float, float, float]] = {}
    with PLACEMENT.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError("PCB-MAIN placement repack manifest is empty")
    for row in rows:
        ref = row["RefDes"]
        if ref in result:
            raise RuntimeError(f"{ref}: duplicate placement manifest row")
        if (row["Placement_Class"] != "UNLOCKED_LAYOUT_CANDIDATE"
                or row["Status"] != "ENGINEERING_CANDIDATE_NOT_FOR_MANUFACTURE"):
            raise RuntimeError(f"{ref}: invalid placement release boundary")
        result[ref] = (
            float(row["X_mm"]),
            float(row["Y_mm"]),
            float(row["Rotation_deg"]),
        )
    return result


def passive_footprint(board: pcbnew.BOARD, package: str) -> pcbnew.FOOTPRINT:
    dims = {
        "0402": (1.0, 0.5, 0.55), "0603": (1.6, 0.8, 0.9),
        "0805": (2.0, 1.25, 1.05), "1206": (3.2, 1.6, 1.55),
        "1210": (3.2, 2.5, 1.55),
    }
    length, width, pitch = dims[package]
    fp = pcbnew.FOOTPRINT(board)
    for number, x in (("1", -pitch / 2), ("2", pitch / 2)):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(number)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
        pad.SetRoundRectRadiusRatio(0.2)
        pad.SetSize(mm(max(0.55, length / 2), width))
        pad.SetFPRelativePosition(mm(x, 0))
        layers = pcbnew.LSET()
        for layer in (pcbnew.F_Cu, pcbnew.F_Paste, pcbnew.F_Mask):
            layers.AddLayer(layer)
        pad.SetLayerSet(layers)
        fp.Add(pad)
    pad_width = max(0.55, length / 2)
    half_x = pitch / 2 + pad_width / 2 + 0.25
    half_y = width / 2 + 0.25
    courtyard = pcbnew.PCB_SHAPE(fp)
    courtyard.SetShape(pcbnew.SHAPE_T_RECT)
    courtyard.SetStart(mm(-half_x, -half_y))
    courtyard.SetEnd(mm(half_x, half_y))
    courtyard.SetLayer(pcbnew.F_CrtYd)
    courtyard.SetWidth(pcbnew.FromMM(0.05))
    fp.Add(courtyard)
    set_footprint_property(fp, "DIONEA_COURTYARD_STATUS", PASSIVE_COURTYARD_STATUS)
    set_footprint_property(fp, "DIONEA_COURTYARD_SOURCE", PASSIVE_COURTYARD_SOURCE)
    return fp


def generic_footprint(board: pcbnew.BOARD, pin_numbers: list[str], package: str) -> pcbnew.FOOTPRINT:
    """Create a visibly provisional project-local land pattern.

    These footprints permit placement/mechanical iteration only.  Their custom
    property is audited so they cannot silently become production-approved.
    """
    width, height = BODY.get(package, (max(2.0, min(12.0, len(pin_numbers) * 0.35)), 3.0))
    fp = pcbnew.FOOTPRINT(board)
    set_footprint_property(
        fp, "DIONEA_FOOTPRINT_STATUS", "PROVISIONAL_REQUIRES_MANUFACTURER_DRAWING"
    )
    count = len(pin_numbers)
    sides = max(1, (count + 3) // 4)
    coords: list[tuple[float, float]] = []
    for i in range(sides):
        t = (i + 0.5) / sides
        coords.extend([(-width / 2, -height / 2 + t * height),
                       (-width / 2 + t * width, height / 2),
                       (width / 2, height / 2 - t * height),
                       (width / 2 - t * width, -height / 2)])
    for number, (x, y) in zip(pin_numbers, coords):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(number))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT if str(number) == "1" else pcbnew.PAD_SHAPE_ROUNDRECT)
        if str(number) != "1":
            pad.SetRoundRectRadiusRatio(0.2)
        pad.SetSize(mm(0.55, 0.9))
        pad.SetFPRelativePosition(mm(x, y))
        layers = pcbnew.LSET()
        for layer in (pcbnew.F_Cu, pcbnew.F_Paste, pcbnew.F_Mask):
            layers.AddLayer(layer)
        pad.SetLayerSet(layers)
        fp.Add(pad)
    return fp


def fixture_footprint(board: pcbnew.BOARD, ref: str, pins: list[str]) -> tuple[pcbnew.FOOTPRINT, tuple[float, float]]:
    """Build the exact bottom-side pogo group frozen by MAIN-AUTH-011."""
    rows = []
    with MECH.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["Feature_Type"] == "TEST_PAD" and row["RefDes"] == ref:
                rows.append(row)
    rows.sort(key=lambda row: int(row["Contact"]))
    if [row["Contact"] for row in rows] != pins:
        raise RuntimeError(f"{ref}: MAIN-AUTH-011 pogo contact mismatch")
    x0, y0 = float(rows[0]["X_mm"]), float(rows[0]["Y_mm"])
    fp = pcbnew.FOOTPRINT(board)
    fp.SetLayer(pcbnew.B_Cu)
    set_footprint_property(
        fp, "DIONEA_FOOTPRINT_STATUS", "CONTROLLED_MAIN_AUTH_011_POGO_PATTERN"
    )
    set_footprint_property(fp, "DIONEA_FOOTPRINT_SOURCE", str(MECH.relative_to(ROOT)))
    for row in rows:
        pad = pcbnew.PAD(fp)
        pad.SetNumber(row["Contact"])
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(mm(1.70, 1.70))
        relative = mm(float(row["X_mm"]) - x0, float(row["Y_mm"]) - y0)
        pad.SetFPRelativePosition(relative)
        pad.SetLocalSolderMaskMargin(pcbnew.FromMM(0.20))
        layers = pcbnew.LSET()
        for layer in (pcbnew.B_Cu, pcbnew.B_Mask):
            layers.AddLayer(layer)
        pad.SetLayerSet(layers)
        fp.Add(pad)
    return fp, (x0, y0)


def load_footprint(board: pcbnew.BOARD, package: str, pins: list[str]) -> pcbnew.FOOTPRINT:
    if package in {"0402", "0603", "0805", "1206", "1210"}:
        return passive_footprint(board, package)
    entry = STANDARD.get(package)
    if entry:
        # Older entries intentionally remain two-tuples for compatibility.
        directory, name, aliases = (*entry, {}) if len(entry) == 2 else entry
        source_dir = PROJECT_FP if directory == "PROJECT" else KICAD_FP / directory
        fp = pcbnew.FootprintLoad(str(source_dir), name)
        if fp is not None:
            for pad in fp.Pads():
                if pad.GetNumber() in aliases:
                    pad.SetNumber(aliases[pad.GetNumber()])
            # Empty-number pads are mechanical/paste apertures and are not
            # logical pins.  Duplicate shell pads deliberately share a name.
            logical = {p.GetNumber() for p in fp.Pads() if p.GetNumber()}
            if logical == set(pins):
                if directory == "PROJECT":
                    ipc_candidates = {
                        "Winbond_W25Q512JV_PackageF_IPC_Candidate":
                            "PROJECT_IPC_W25Q512JV_F_KICAD_GULLWING_ASSEMBLER_DFM_REQUIRED",
                        "TI_DRT0003A_IPC_Candidate":
                            "PROJECT_IPC_TI_DRT0003A_KICAD_DRT3_ASSEMBLER_DFM_REQUIRED",
                    }
                    set_footprint_property(
                        fp,
                        "DIONEA_FOOTPRINT_STATUS",
                        (
                            "PROJECT_IPC_PATTERN_CONTROLLED_ASSEMBLY_DFM_REQUIRED"
                            if name in ipc_candidates
                            else "MANUFACTURER_DRAWING_PATTERN_CONTROLLED"
                        ),
                    )
                    sources = {
                        "PESD5V0C1BSF_SOD962-2": "Nexperia_PESD5V0C1BSF_v3_Fig14",
                        "Nexperia_PESD5V0S1UL_SOD882": "Nexperia_PESD5V0S1UL_v5_2025-12-01_Fig11_ReflowFootprint",
                        "Nexperia_MMBT3904_SOT23": "Nexperia_MMBT3904_v5_2026-04-08_Fig8_ReflowFootprint",
                        "ST_ESDALC6V1-5P6_SOT666": "ST_ESDALC6V1-5P6_Rev3_Figure14_SOT666_Footprint",
                        "Vishay_Si1016X_SC-89": "Vishay_Si1016X_RevE_AN826_RecommendedMinimumPads",
                        "KEMET_T52X_D_7343-31_DensityB": "KEMET_T2076_T52X-530_2026-08-20_Table2_DensityB",
                        "STTS22H_UDFN-6L": "ST_DS12606_Rev8_Fig10_11",
                        "LT6000_DCB-7": "ADI_LT6000_600012fa_LTC_DWG_05-08-1715",
                        "SiT1552_JE_CSP-4": "SiTime_SiT1552_Rev1.43_POD-35_RevA",
                        "u-blox_MAX-M10S_LCC-18": "u-blox_UBX-20053088_R05_Fig30_Table44",
                        "Ebyte_E22-M22S_Castellated-22": "Ebyte_E22-M_v1.2_2026-02-06_Section3.2",
                        "Abracon_ABSES5AF_1109-5": "Abracon_ABSES5AF-L100KM_2025-09-16_LandPattern",
                        "TE_2336582-1_NanoSIM": "TE_C-2336582_RevA2_RecommendedPCBLayout",
                        "Quectel_BG95-M3_LGA-102": "Quectel_BG95_HW_Design_V1.8_Figure46",
                        "Molex_43045-1202_MicroFit-12_RA": "Molex_SD-43045-001_PSD001_RevH1_PCBLayout",
                        "Molex_504050-0291_PicoLock-2": "Molex_5040500000-SD_PSD001_RevB_RecommendedPattern",
                        "GCT_MEM2052-00-195-00-A": "GCT_MEM2052_RevA3_RecommendedPCBLayout",
                        "Hirose_U.FL-R-SMT-1": "Hirose_U.FL_CAT_2026-08-01_PCB_and_MetalMask",
                        "ST_STM32U585_LQFP100_1L": "ST_DS13086_Rev10_Figure96_LQFP100_1L",
                        "TI_PW0014A_TSSOP14": "TI_PW0014A_4220202B_2023-12_RecommendedLandPattern",
                        "TI_PW0024A_TSSOP24": "TI_PW0024A_4220208A_2017-02_RecommendedLandPattern",
                        "TI_DRL0006A_SOT6": "TI_DRL0006A_4223266F_2024-11_RecommendedLandPattern",
                        "TI_DBV0005A_SOT23-5": "TI_DBV0005A_4214839K_2024-08_RecommendedLandPattern",
                        "TI_DYA0002A_SOD523": "TI_DYA0002A_4224978B_2021-09_RecommendedLandPattern",
                        "TI_DQA0010A_USON10": "TI_DQA0010A_4220328A_2015-12_RecommendedLandPattern",
                        "ST_LIS2DW12_LGA-12L": "ST_DS11811_Rev9_and_TN0018_Rev8_LGA-12L_Pattern",
                        "Raytac_MDBT50Q-P1MV2": "Raytac_MDBT50Q_Footprint_Design_Guide_230606",
                        "Winbond_W25Q512JV_PackageF_IPC_Candidate": ipc_candidates["Winbond_W25Q512JV_PackageF_IPC_Candidate"],
                        "TI_DRT0003A_IPC_Candidate": ipc_candidates["TI_DRT0003A_IPC_Candidate"],
                    }
                    set_footprint_property(fp, "DIONEA_FOOTPRINT_SOURCE", sources[name])
                elif (directory, name) in KICAD_DRAWING_VERIFIED:
                    set_footprint_property(
                        fp, "DIONEA_FOOTPRINT_STATUS", "KICAD_LIBRARY_PATTERN_DRAWING_VERIFIED"
                    )
                    set_footprint_property(
                        fp, "DIONEA_FOOTPRINT_SOURCE", KICAD_DRAWING_VERIFIED[(directory, name)]
                    )
                else:
                    set_footprint_property(
                        fp, "DIONEA_FOOTPRINT_STATUS", "KICAD_LIBRARY_PATTERN_REVIEW_PENDING"
                    )
                    set_footprint_property(
                        fp, "DIONEA_FOOTPRINT_SOURCE", f"KiCad:{directory}/{name}"
                    )
                return fp
    return generic_footprint(board, pins, package)


def add_outline(board: pcbnew.BOARD) -> None:
    # Locked 110 x 75 mm outline with tangent R3 corners.
    for a, b in [((3, 0), (107, 0)), ((110, 3), (110, 72)),
                 ((107, 75), (3, 75)), ((0, 72), (0, 3))]:
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(mm(*a)); shape.SetEnd(mm(*b))
        shape.SetLayer(pcbnew.Edge_Cuts); shape.SetWidth(pcbnew.FromMM(0.1))
        board.Add(shape)
    for start, mid, end in [
        ((3, 0), (0.879, 0.879), (0, 3)), ((110, 3), (109.121, 0.879), (107, 0)),
        ((107, 75), (109.121, 74.121), (110, 72)), ((0, 72), (0.879, 74.121), (3, 75)),
    ]:
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_ARC)
        shape.SetArcGeometry(mm(*start), mm(*mid), mm(*end))
        shape.SetLayer(pcbnew.Edge_Cuts); shape.SetWidth(pcbnew.FromMM(0.1))
        board.Add(shape)


def add_mounting_hole(board: pcbnew.BOARD, ref: str, x: float, y: float) -> None:
    fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue("M3_NPTH")
    pad = pcbnew.PAD(fp); pad.SetNumber(""); pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE); pad.SetSize(mm(3.2, 3.2)); pad.SetDrillSize(mm(3.2, 3.2))
    pad.SetPosition(mm(0, 0)); pad.SetLayerSet(pcbnew.LSET.AllCuMask()); fp.Add(pad)
    fp.SetPosition(mm(x, y)); normalize_text(fp); board.Add(fp)


def normalize_text(fp: pcbnew.FOOTPRINT) -> None:
    """Keep the placement plot readable; values stay available in properties/BOM."""
    fp.Value().SetVisible(False)
    fp.Reference().SetVisible(True)
    fp.Reference().SetTextSize(mm(0.8, 0.8))
    fp.Reference().SetTextThickness(pcbnew.FromMM(0.12))
    fp.Reference().SetPosition(fp.GetPosition() + mm(0, -1.2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=OUT,
        help="write the generated native board to this path",
    )
    args = parser.parse_args()
    output = args.output.resolve()

    components = expected_components()
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
    add_outline(board)
    for ref, x, y in (("H1", 5, 5), ("H2", 105, 5), ("H3", 105, 70), ("H4", 5, 70)):
        add_mounting_hole(board, ref, x, y)

    nets = sorted({p["native"] for c in components.values() for p in c["pins"].values()
                   if p["native"] != "NC"})
    net_items: dict[str, pcbnew.NETINFO_ITEM] = {}
    for name in nets:
        item = pcbnew.NETINFO_ITEM(board, name); board.Add(item); net_items[name] = item

    fixed = anchors()
    placement = placement_manifest()
    expected_movable = {
        ref for ref, component in components.items()
        if component["on_board"]
        and ref not in fixed
        and not str(component["package"]).startswith("POGO_FIXTURE_")
    }
    if set(placement) != expected_movable:
        raise RuntimeError(
            "placement manifest reference mismatch: "
            f"missing={sorted(expected_movable - set(placement))} "
            f"extra={sorted(set(placement) - expected_movable)}"
        )

    for ref in sorted(components):
        component = components[ref]
        if not component["on_board"]:
            continue
        pin_numbers = list(component["pins"])
        mpn, package = props(component)
        fixture_position = None
        if package.startswith("POGO_FIXTURE_"):
            fp, fixture_position = fixture_footprint(board, ref, pin_numbers)
        else:
            fp = load_footprint(board, package, pin_numbers)
        fp.SetReference(ref); fp.SetValue(mpn)
        set_footprint_property(fp, "DIONEA_PACKAGE", package)
        set_footprint_property(fp, "DIONEA_POPULATION", component["population"])
        if component["population"] == "DNP":
            fp.SetExcludedFromPosFiles(True)
        by_number = {pad.GetNumber(): pad for pad in fp.Pads() if pad.GetNumber()}
        if set(by_number) != set(pin_numbers):
            raise RuntimeError(f"{ref}: footprint pin mismatch {sorted(by_number)} != {sorted(pin_numbers)}")
        for number, pin in component["pins"].items():
            if pin["native"] != "NC":
                by_number[number].SetNet(net_items[pin["native"]])
        if fixture_position is not None:
            x, y = fixture_position; angle = 0
        elif ref in fixed:
            x, y, angle = fixed[ref]
        else:
            x, y, angle = placement[ref]
            set_footprint_property(
                fp, "DIONEA_PLACEMENT_SOURCE", "PCB_MAIN_PLACEMENT_REPACK_REV_A"
            )
            set_footprint_property(
                fp, "DIONEA_PLACEMENT_CLASS", "UNLOCKED_LAYOUT_CANDIDATE"
            )
        fp.SetPosition(mm(x, y)); fp.SetOrientationDegrees(angle); normalize_text(fp); board.Add(fp)

    board.BuildListOfNets()
    output.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output), board)
    display = output.relative_to(ROOT) if output.is_relative_to(ROOT) else output
    print(f"PCB-MAIN placement candidate: {display}")
    print(f"components={len(list(board.GetFootprints())) - 4} holes=4 nets={len(nets)} copper_layers=6")
    print("status=LAYOUT_ENGINEERING_CANDIDATE / NOT FOR MANUFACTURE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import cadquery as cq
from cadquery import exporters
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


OUT = Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)

REV = "A"
DATE = "2026-10-16"


def rounded_outer(x: float, y: float, z: float, radius: float) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .box(x, y, z, centered=(True, True, False))
        .edges("|Z")
        .fillet(radius)
    )


def tub(
    x: float,
    y: float,
    z: float,
    wall: float,
    bottom: float,
    radius: float,
    fastener_xy: list[tuple[float, float]],
    fastener_d: float,
    boss_d: float,
) -> cq.Workplane:
    result = rounded_outer(x, y, z, radius)
    inner = (
        cq.Workplane("XY")
        .box(x - 2 * wall, y - 2 * wall, z - bottom + 1, centered=(True, True, False))
        .translate((0, 0, bottom))
    )
    result = result.cut(inner)
    for px, py in fastener_xy:
        boss = cq.Workplane("XY").center(px, py).circle(boss_d / 2).extrude(z)
        hole = cq.Workplane("XY").center(px, py).circle(fastener_d / 2).extrude(z + 2)
        result = result.union(boss).cut(hole)
    return result


def lid(
    x: float,
    y: float,
    plate: float,
    wall: float,
    radius: float,
    fastener_xy: list[tuple[float, float]],
    fastener_d: float,
) -> cq.Workplane:
    result = rounded_outer(x, y, plate, radius)
    lip_outer = cq.Workplane("XY").rect(x - 2 * wall - 0.8, y - 2 * wall - 0.8).extrude(5).translate((0, 0, plate))
    lip_inner = cq.Workplane("XY").rect(x - 4 * wall - 0.8, y - 4 * wall - 0.8).extrude(6).translate((0, 0, plate))
    result = result.union(lip_outer.cut(lip_inner))
    for px, py in fastener_xy:
        hole = cq.Workplane("XY").center(px, py).circle(fastener_d / 2).extrude(plate + 7)
        result = result.cut(hole)
    return result


def add_bosses(
    part: cq.Workplane,
    points: list[tuple[float, float]],
    z0: float,
    height: float,
    boss_d: float,
    hole_d: float,
) -> cq.Workplane:
    for px, py in points:
        boss = cq.Workplane("XY").center(px, py).circle(boss_d / 2).extrude(height).translate((0, 0, z0))
        hole = cq.Workplane("XY").center(px, py).circle(hole_d / 2).extrude(height + 1).translate((0, 0, z0))
        part = part.union(boss).cut(hole)
    return part


def cut_y_hole(part: cq.Workplane, x: float, z: float, diameter: float, length: float) -> cq.Workplane:
    cutter = cq.Workplane("XZ").center(x, z).circle(diameter / 2).extrude(length, both=True)
    return part.cut(cutter)


upper_fasteners = [(-67, -49.5), (67, -49.5), (67, 49.5), (-67, 49.5)]
upper_base = tub(150, 115, 44, 5, 4, 7, upper_fasteners, 3.4, 8)
main_points = [(-50, -32.5), (50, -32.5), (50, 32.5), (-50, 32.5)]
upper_base = add_bosses(upper_base, main_points, 4, 6, 7, 3.2)
for rf_x in (-42, 0, 42):
    upper_base = cut_y_hole(upper_base, rf_x, 26, 6.5, 130)
upper_base = cut_y_hole(upper_base, 57, 17, 16.5, 130)
upper_lid = lid(150, 115, 7, 5, 7, upper_fasteners, 4.2)


power_fasteners = [(-99, -83.5), (99, -83.5), (99, 83.5), (-99, 83.5)]
power_base = tub(215, 184, 196, 5, 6, 8, power_fasteners, 4.5, 10)
power_base = cut_y_hole(power_base, -55, 28, 20.5, 200)
power_base = cut_y_hole(power_base, 0, 28, 20.5, 200)
power_base = cut_y_hole(power_base, 55, 28, 16.5, 200)

power_lid = lid(215, 184, 8, 5, 8, power_fasteners, 4.5)
# PCB-PWR 90 x 60 mm mounting pattern, shifted left.
pwr_points = [(-78, -30), (-1, -30), (-15, 20), (-78, 20)]
power_lid = add_bosses(power_lid, pwr_points, 8, 8, 8, 3.2)
# MPPT mounting provision: 113 x 100 mm envelope, shifted right and represented
# by four slotted clearance holes with conservative 80 x 70 mm pitch.
mppt_points = [(25, -35), (95, -35), (25, 45), (95, 45)]
power_lid = add_bosses(power_lid, mppt_points, 8, 8, 9, 4.5)


mic_fasteners = [(-10, 9), (10, 9)]
mic_base = tub(30, 28, 14, 2.5, 3, 3, mic_fasteners, 2.4, 5)
mic_base = mic_base.cut(cq.Workplane("XY").circle(1.0).extrude(20))
mic_cap = rounded_outer(30, 28, 3, 3)
mic_cap = mic_cap.cut(cq.Workplane("XY").circle(2.0).extrude(5))
for px, py in mic_fasteners:
    mic_cap = mic_cap.cut(cq.Workplane("XY").center(px, py).circle(1.2).extrude(5))


parts = {
    "DIO_HSG_ELECTRONICS_BASE_REV_A": (upper_base, 1, "Upper electronics enclosure base"),
    "DIO_HSG_ELECTRONICS_LID_REV_A": (upper_lid, 1, "Gasketed upper electronics lid"),
    "DIO_HSG_POWER_BASE_REV_A": (power_base, 1, "RB40 battery enclosure base"),
    "DIO_HSG_POWER_LID_REV_A": (power_lid, 1, "Power electronics lid with PCB-PWR/MPPT mounting provisions"),
    "DIO_HSG_MIC_POD_BASE_REV_A": (mic_base, 4, "PCB-MIC pod base"),
    "DIO_HSG_MIC_POD_CAP_REV_A": (mic_cap, 4, "Acoustic membrane retaining cap"),
}


manifest = []
for name, (shape, qty, description) in parts.items():
    stl = OUT / f"{name}.stl"
    exporters.export(shape, str(stl), tolerance=0.05, angularTolerance=0.1)
    box = shape.val().BoundingBox()
    manifest.append({
        "part_number": name,
        "description": description,
        "quantity_per_station": qty,
        "bbox_mm": [round(box.xlen, 3), round(box.ylen, 3), round(box.zlen, 3)],
        "volume_mm3": round(shape.val().Volume(), 2),
        "solid_count": len(shape.val().Solids()),
        "stl": stl.name,
        "stl_sha256": hashlib.sha256(stl.read_bytes()).hexdigest(),
    })


located = []
locations = {
    "DIO_HSG_ELECTRONICS_BASE_REV_A": (0, 0, 0),
    "DIO_HSG_ELECTRONICS_LID_REV_A": (180, 0, 0),
    "DIO_HSG_POWER_BASE_REV_A": (0, 230, 0),
    "DIO_HSG_POWER_LID_REV_A": (250, 230, 0),
    "DIO_HSG_MIC_POD_BASE_REV_A": (0, 450, 0),
    "DIO_HSG_MIC_POD_CAP_REV_A": (50, 450, 0),
}
for name, (shape, _, _) in parts.items():
    x, y, z = locations[name]
    located.append(shape.val().moved(cq.Location(cq.Vector(x, y, z))))
compound = cq.Compound.makeCompound(located)
step_path = OUT / "EVT_HOUSING_MASTER_REV_A.step"
exporters.export(compound, str(step_path))


profile = {
    "schema": "dioneya-fdm-profile-v1",
    "revision": REV,
    "date": DATE,
    "printer": "FlashForge Adventurer 5M Pro",
    "build_volume_mm": [220, 220, 220],
    "material": "UV-stabilized ASA, black or light grey, supplier lot recorded",
    "nozzle_mm": 0.4,
    "layer_height_mm": 0.2,
    "first_layer_mm": 0.24,
    "perimeters": 5,
    "top_layers": 7,
    "bottom_layers": 7,
    "infill_percent": 35,
    "infill_pattern": "gyroid",
    "nozzle_temperature_c": 255,
    "bed_temperature_c": 105,
    "chamber": "closed; stabilize before print",
    "fan_percent": 15,
    "max_volumetric_speed_mm3_s": 8,
    "supports": "organic/tree from build plate only where required; none in gasket grooves or threaded insert bores",
    "brim": "5 mm except DIO_HSG_POWER_BASE_REV_A: no brim because 215 mm envelope; use controlled bed adhesive",
    "seam": "rear face away from gasket and label surfaces",
    "shrink_scale_xy": 1.006,
    "shrink_scale_z": 1.003,
    "post_process": [
        "condition 24 h at 23 +/- 5 C",
        "ream fastener and insert bores only to drawing size",
        "install brass inserts with temperature-controlled tool",
        "do not coat acoustic paths or RF connector seats",
        "inspect gasket faces for gaps and layer separation",
    ],
    "first_article_hold": True,
}
(OUT / "PRINT_PROFILE_EVT_ASA_REV_A.json").write_text(
    json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
)


bom_rows = [
    ["DIO_HSG_ELECTRONICS_BASE_REV_A", "Upper electronics base", 1, "UV-stabilized ASA", "Print from controlled STL; three SMA holes and one M16 gland hole"],
    ["DIO_HSG_ELECTRONICS_LID_REV_A", "Upper electronics lid", 1, "UV-stabilized ASA", "EPDM seal, M4 A4 screws"],
    ["DIO_HSG_POWER_BASE_REV_A", "RB40 battery base", 1, "UV-stabilized ASA", "Internal 205 x 174 x 190 mm; M20/M16 gland openings"],
    ["DIO_HSG_POWER_LID_REV_A", "Power electronics lid", 1, "UV-stabilized ASA", "PCB-PWR and MPPT mounting provisions"],
    ["DIO_HSG_MIC_POD_BASE_REV_A", "Microphone pod base", 4, "UV-stabilized ASA", "Fits PCB-MIC 24 x 22 mm; centered acoustic path"],
    ["DIO_HSG_MIC_POD_CAP_REV_A", "Microphone pod cap", 4, "UV-stabilized ASA", "Retains controlled ePTFE membrane"],
    ["DIO_SEAL_EPDM70_REV_A", "Gasket set", 1, "Closed-cell EPDM 70 Shore A", "15-25 percent compression; cut to lid grooves"],
    ["DIO_INSERT_M3_M4_REV_A", "Heat-set insert set", 1, "Brass, knurled", "M3 PCB/pod and M4 enclosure inserts"],
    ["DIO_FASTENER_A4_REV_A", "Fastener set", 1, "A4 stainless", "M3/M4 with captive washers; torque per drawing"],
    ["DIO_ACOUSTIC_MEMBRANE_PTFE_REV_A", "Acoustic membrane set", 4, "Hydrophobic ePTFE", "Supplier lot controlled; first-article acoustic validation required"],
]
with (OUT / "HOUSING_BOM_EVT_REV_A.csv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["Part_number", "Description", "Qty_per_station", "Material_or_spec", "Manufacturing_notes"])
    writer.writerows(bom_rows)


def fit_text(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, size: float = 8) -> None:
    words = text.split()
    line = ""
    lines = []
    for word in words:
        candidate = f"{line} {word}".strip()
        if stringWidth(candidate, "Helvetica", size) <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    for index, item in enumerate(lines):
        c.drawString(x, y - index * (size + 2), item)


pdf = OUT / "EVT_HOUSING_DRAWING_REV_A.pdf"
c = canvas.Canvas(str(pdf), pagesize=landscape(A3))
pw, ph = landscape(A3)

def title_block(page_title: str, page: int, total: int) -> None:
    c.setStrokeColor(colors.HexColor("#1F2937"))
    c.setLineWidth(0.6)
    c.rect(12 * mm, 12 * mm, pw - 24 * mm, ph - 24 * mm)
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(18 * mm, ph - 23 * mm, page_title)
    c.setFont("Helvetica", 8)
    c.drawRightString(pw - 18 * mm, ph - 21 * mm, f"Dioneya EVT-PRE-20 | Rev.{REV} | {DATE} | Sheet {page}/{total}")
    c.line(12 * mm, ph - 29 * mm, pw - 12 * mm, ph - 29 * mm)
    c.setFont("Helvetica", 7)
    c.drawString(18 * mm, 17 * mm, "UNITS: mm | GENERAL FDM TOLERANCE: +/-0.5 unless stated | FIRST ARTICLE HOLD REQUIRED")
    c.drawRightString(pw - 18 * mm, 17 * mm, "DIO-HSG-3D-EVT-REV-A")


def dim_box(x: float, y: float, w: float, h: float, label: str, dims: str) -> None:
    c.setStrokeColor(colors.HexColor("#4B5563"))
    c.setFillColor(colors.HexColor("#F3F4F6"))
    c.roundRect(x, y, w, h, 5, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x + w / 2, y + h - 14, label)
    c.setFont("Helvetica", 9)
    c.drawCentredString(x + w / 2, y + h / 2 - 3, dims)


title_block("EVT 3D-PRINTED HOUSING - GENERAL ARRANGEMENT", 1, 2)
c.setFont("Helvetica", 9)
fit_text(c, "Controlled build-to-print option for the EVT lot. Upper electronics and power modules are separate sealed volumes. Four PCB-MIC pods are replaceable. The power base accepts the RELiON RB40 envelope; the power lid provides PCB-PWR and Victron MPPT mounting provisions.", 18 * mm, ph - 38 * mm, pw - 36 * mm, 9)

dim_box(22 * mm, 126 * mm, 78 * mm, 58 * mm, "UPPER ELECTRONICS BASE", "150 x 115 x 44")
dim_box(112 * mm, 126 * mm, 78 * mm, 58 * mm, "UPPER LID", "150 x 115 x 12 total")
dim_box(202 * mm, 126 * mm, 78 * mm, 58 * mm, "POWER BASE", "215 x 184 x 196")
dim_box(292 * mm, 126 * mm, 78 * mm, 58 * mm, "POWER LID", "215 x 184 x 13 total")
dim_box(92 * mm, 30 * mm, 78 * mm, 34 * mm, "MIC POD BASE x4", "30 x 28 x 14")
dim_box(230 * mm, 30 * mm, 78 * mm, 34 * mm, "MIC POD CAP x4", "30 x 28 x 3")

c.setFont("Helvetica-Bold", 10)
c.drawString(18 * mm, 112 * mm, "Controlled interfaces")
c.setFont("Helvetica", 8)
interface_lines = [
    "PCB-MAIN: 110 x 75 x 12 PCBA envelope, M3 pattern X5/105 Y5/70 mapped to four internal bosses.",
    "PCB-PWR: 90 x 60 mm, four M3 mounting points, >=20 mm connector service volume retained.",
    "Battery: RB40 197 x 166 x 173 mm inside 205 x 174 x 190 mm cavity; terminal volume continues into lid.",
    "RF: three SMA bulkhead holes, 42 mm pitch; CAB.0243 minimum bend radius 6.8 mm.",
    "Acoustic: centered 2.0 mm free opening, adhesive exclusion radius 1.5 mm, membrane in removable cap.",
]
for idx, line in enumerate(interface_lines):
    c.drawString(22 * mm, (103 - idx * 7) * mm, f"- {line}")
c.showPage()


title_block("EVT 3D-PRINTED HOUSING - MANUFACTURING AND INSPECTION", 2, 2)
c.setFont("Helvetica-Bold", 10)
c.drawString(18 * mm, ph - 40 * mm, "Print controls")
c.setFont("Helvetica", 8)
print_lines = [
    "Printer class: FlashForge Adventurer 5M Pro, build volume 220 x 220 x 220 mm.",
    "Material: UV-stabilized ASA; 0.4 mm nozzle; 0.20 mm layers; 5 perimeters; 35 percent gyroid infill.",
    "Power base maximum print envelope 215 x 184 x 196 mm. No brim; verify actual calibrated build area before start.",
    "Do not place supports or post-process tools on gasket faces, acoustic openings, insert bores or RF seats.",
    "Condition parts 24 h before dimensional inspection and insert installation.",
]
for idx, line in enumerate(print_lines):
    c.drawString(22 * mm, (ph / mm - 49 - idx * 7) * mm, f"- {line}")

c.setFont("Helvetica-Bold", 10)
c.drawString(18 * mm, 190 * mm, "First article inspection - release remaining lot only after PASS")
c.setFont("Helvetica", 8)
inspection = [
    ("DIMENSION", "All outer envelopes +/-0.5; PCB and OTS item fit without force; service clearances retained."),
    ("FASTENERS", "Insert pull and torque sample; M3 <=0.4 N m at PCB; M4 torque set by hardware stack."),
    ("SEAL", "Uniform 15-25 percent gasket compression; visual light-gap check followed by controlled IP test."),
    ("ACOUSTIC", "Four open ports; no adhesive/paste/coating; gain, phase, noise and delay within EVT limits."),
    ("RF", "Bulkhead seating and torque, cable bend/retention, installed VSWR/sensitivity/coexistence."),
    ("POWER", "Battery terminal cover and tool clearances, gland pull, fuse access, temperature and fault checks."),
    ("SERVICE", "USB-C, SIM, microSD and SWD access without PCB or seal damage; cover can be resealed."),
    ("TRACEABILITY", "Part/revision/material lot/printer/profile/operator/date recorded for every printed set."),
]
tx, ty = 22 * mm, 178 * mm
row_h = 15 * mm
col1, col2 = 38 * mm, 335 * mm
c.setStrokeColor(colors.HexColor("#6B7280"))
for idx, (gate, requirement) in enumerate(inspection):
    y = ty - idx * row_h
    c.rect(tx, y - row_h, col1, row_h)
    c.rect(tx + col1, y - row_h, col2, row_h)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(tx + 3 * mm, y - 9 * mm, gate)
    c.setFont("Helvetica", 7)
    fit_text(c, requirement, tx + col1 + 3 * mm, y - 6 * mm, col2 - 6 * mm, 7)

c.setFont("Helvetica-Bold", 9)
c.drawString(18 * mm, 43 * mm, "Release boundary")
c.setFont("Helvetica", 8)
fit_text(c, "These files authorize fabrication of the EVT printed housing set. Physical IP, UV/environmental, structural, thermal, RF and acoustic results are collected on the first articles and block serial transfer. Do not scale STL meshes or change wall, hole, gasket or acoustic geometry without an ECO.", 22 * mm, 36 * mm, pw - 44 * mm, 8)
c.save()


release = {
    "schema": "dioneya-evt-housing-package-v1",
    "configuration": "EVT-PRE-20",
    "technology": "3D_PRINT_FDM",
    "revision": REV,
    "date": DATE,
    "status": "RELEASED_FOR_EVT_FIRST_ARTICLE_BUILD",
    "master_step": step_path.name,
    "drawing_pdf": pdf.name,
    "printer_profile": "PRINT_PROFILE_EVT_ASA_REV_A.json",
    "housing_bom": "HOUSING_BOM_EVT_REV_A.csv",
    "parts": manifest,
    "maximum_part_bbox_mm": [215, 184, 196],
    "printer_build_volume_mm": [220, 220, 220],
    "first_article_hold": True,
    "physical_evt_complete": False,
    "serial_release": False,
}
release["master_step_sha256"] = hashlib.sha256(step_path.read_bytes()).hexdigest()
release["drawing_pdf_sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
(OUT / "EVT_HOUSING_RELEASE_REV_A.json").write_text(
    json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
)


(OUT / "RELEASE_README_REV_A.md").write_text(
    """# EVT-PRE-20 3D-printed housing package Rev.A

Status: `RELEASED_FOR_EVT_FIRST_ARTICLE_BUILD`.

This is the controlled, reproducible housing option that can be manufactured before a specific vacuum-casting supplier is selected. It contains a master STEP assembly, individual STL files, a two-sheet drawing, a housing BOM, a printer profile and a machine-readable release manifest.

The source geometry is generated by `EVT_HOUSING_REV_A.py` with CadQuery 2.6.1. Do not scale STL files. The largest part is 215 x 184 x 196 mm and fits the stated 220 x 220 x 220 mm printer envelope with no brim.

The first printed set is held for dimensional fit, insert pull/torque, sealing, service, RF, thermal/power and four-channel acoustic checks. Those physical results block the remaining housing lot and serial transfer; they do not block fabrication of the first EVT set.

Vacuum casting remains a separate technology track and requires its own supplier DFM and master package if selected by the customer.
""",
    encoding="utf-8",
    newline="\n",
)

print(json.dumps({
    "status": release["status"],
    "part_count": len(parts),
    "stl_count": len(list(OUT.glob("*.stl"))),
    "step_bytes": step_path.stat().st_size,
    "pdf_bytes": pdf.stat().st_size,
    "maximum_part_bbox_mm": release["maximum_part_bbox_mm"],
}, indent=2))

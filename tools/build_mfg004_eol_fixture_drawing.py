#!/usr/bin/env python3
"""Build the MFG-004 bottom fixture drill template as DXF and bilingual PDF."""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "manufacturing/MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json"
DXF = ROOT / "manufacturing/MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.dxf"
PDF = ROOT / "manufacturing/MFG_004_EOL_FIXTURE_DRILL_TEMPLATE_REV_A.pdf"
FONT = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"


def register_fonts() -> None:
    candidates = [
        Path("C:/Windows/Fonts/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    regular = next((path for path in candidates if path.exists()), None)
    bold = next((path for path in bold_candidates if path.exists()), None)
    if regular is None or bold is None:
        raise FileNotFoundError("Cyrillic TrueType font not found")
    pdfmetrics.registerFont(TTFont(FONT, regular))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, bold))


def dxf_pair(code: int, value: object) -> str:
    return f"{code}\n{value}\n"


def add_line(parts: list[str], x1: float, y1: float, x2: float, y2: float, layer: str) -> None:
    parts.extend([dxf_pair(0, "LINE"), dxf_pair(8, layer), dxf_pair(10, f"{x1:.3f}"), dxf_pair(20, f"{y1:.3f}"), dxf_pair(11, f"{x2:.3f}"), dxf_pair(21, f"{y2:.3f}")])


def add_circle(parts: list[str], x: float, y: float, radius: float, layer: str) -> None:
    parts.extend([dxf_pair(0, "CIRCLE"), dxf_pair(8, layer), dxf_pair(10, f"{x:.3f}"), dxf_pair(20, f"{y:.3f}"), dxf_pair(40, f"{radius:.3f}")])


def add_text(parts: list[str], x: float, y: float, text: str, height: float, layer: str) -> None:
    parts.extend([dxf_pair(0, "TEXT"), dxf_pair(8, layer), dxf_pair(10, f"{x:.3f}"), dxf_pair(20, f"{y:.3f}"), dxf_pair(40, f"{height:.3f}"), dxf_pair(1, text)])


def build_dxf(record: dict) -> None:
    parts = [dxf_pair(0, "SECTION"), dxf_pair(2, "HEADER"), dxf_pair(9, "$INSUNITS"), dxf_pair(70, 4), dxf_pair(0, "ENDSEC"), dxf_pair(0, "SECTION"), dxf_pair(2, "ENTITIES")]
    add_line(parts, 0, 0, 110, 0, "BOARD_OUTLINE")
    add_line(parts, 110, 0, 110, 75, "BOARD_OUTLINE")
    add_line(parts, 110, 75, 0, 75, "BOARD_OUTLINE")
    add_line(parts, 0, 75, 0, 0, "BOARD_OUTLINE")
    for hole in record["fixture"]["mounting_holes"]:
        x = 110.0 - float(hole["x_mm"])
        y = float(hole["y_mm"])
        add_circle(parts, x, y, float(hole["diameter_mm"]) / 2.0, "MOUNTING_HOLES_D3_2")
        add_text(parts, x + 2.2, y + 1.2, hole["id"], 1.5, "LABELS")
    short = {"TP_EOL": "E", "TP_MCU_SWD": "MS", "TP_BLE_SWD": "BS", "TP_CELL_USB": "CU", "TP_CELL_DBG": "CD"}
    for item in record["contacts"]:
        x = float(item["Bottom_Fixture_View_X_mm"])
        y = float(item["Bottom_Fixture_View_Y_mm"])
        add_circle(parts, x, y, 0.85, "POGO_D1_7")
        add_text(parts, x - 0.7, y + 1.7, f"{short[item['Fixture_Group']]}{item['Contact']}", 1.1, "LABELS")
    add_text(parts, 2, 72, "MFG-004 BOTTOM FIXTURE VIEW - DO NOT MIRROR AGAIN", 2.2, "NOTES")
    parts.extend([dxf_pair(0, "ENDSEC"), dxf_pair(0, "EOF")])
    DXF.write_text("".join(parts), encoding="ascii")


def draw_wrapped(c: canvas.Canvas, text: str, x: float, y: float, width: float, size: float, leading: float) -> float:
    words = text.split()
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if pdfmetrics.stringWidth(trial, FONT, size) <= width:
            line = trial
        else:
            c.drawString(x, y, line)
            y -= leading
            line = word
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def build_pdf(record: dict) -> None:
    register_fonts()
    page_w, page_h = landscape(A3)
    c = canvas.Canvas(str(PDF), pagesize=(page_w, page_h))
    c.setTitle("MFG-004 EOL fixture drill template Rev A")
    c.setAuthor("Проект Дионея")
    margin = 30
    c.setFont(FONT_BOLD, 16)
    c.drawString(margin, page_h - 32, "MFG-004. Контактная плита EOL оснастки / EOL fixture contact plate")
    c.setFont(FONT, 10)
    c.drawRightString(page_w - margin, page_h - 30, "Rev A   09.10.2026   DIO-EVT-B01")

    plot_x = 42
    plot_y = 170
    scale = 6.2
    board_w = 110 * scale
    board_h = 75 * scale
    c.setLineWidth(1.2)
    c.rect(plot_x, plot_y, board_w, board_h)
    c.setFont(FONT_BOLD, 10)
    c.drawString(plot_x, plot_y + board_h + 12, "Вид со стороны pogo / View from pogo side")
    c.setFont(FONT, 8)
    c.drawString(plot_x, plot_y - 14, "Начало координат Xf=0, Yf=0 / Fixture origin at lower left")
    c.drawString(plot_x, plot_y - 26, "Xf = 110.00 - Xboard; Yf = Yboard. Повторное зеркало запрещено / Do not mirror again")

    group_colors = {
        "TP_EOL": colors.HexColor("#1F77B4"),
        "TP_MCU_SWD": colors.HexColor("#D62728"),
        "TP_BLE_SWD": colors.HexColor("#2CA02C"),
        "TP_CELL_USB": colors.HexColor("#9467BD"),
        "TP_CELL_DBG": colors.HexColor("#FF7F0E"),
    }
    short = {"TP_EOL": "E", "TP_MCU_SWD": "MS", "TP_BLE_SWD": "BS", "TP_CELL_USB": "CU", "TP_CELL_DBG": "CD"}
    for hole in record["fixture"]["mounting_holes"]:
        x = plot_x + (110.0 - float(hole["x_mm"])) * scale
        y = plot_y + float(hole["y_mm"]) * scale
        c.setStrokeColor(colors.black)
        c.setLineWidth(1.0)
        c.circle(x, y, float(hole["diameter_mm"]) * scale / 2.0, stroke=1, fill=0)
        c.setFont(FONT_BOLD, 8)
        c.drawString(x + 8, y + 4, hole["id"])
    for item in record["contacts"]:
        x = plot_x + float(item["Bottom_Fixture_View_X_mm"]) * scale
        y = plot_y + float(item["Bottom_Fixture_View_Y_mm"]) * scale
        c.setStrokeColor(group_colors[item["Fixture_Group"]])
        c.setFillColor(colors.white)
        c.setLineWidth(1.2)
        c.circle(x, y, 0.85 * scale, stroke=1, fill=1)
        c.setFillColor(group_colors[item["Fixture_Group"]])
        c.setFont(FONT_BOLD, 6.5)
        c.drawCentredString(x, y + 8, f"{short[item['Fixture_Group']]}{item['Contact']}")
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    legend_x = plot_x + board_w + 34
    legend_y = plot_y + board_h
    c.setFont(FONT_BOLD, 11)
    c.drawString(legend_x, legend_y, "Группы / Groups")
    legend_y -= 20
    for group in ["TP_EOL", "TP_MCU_SWD", "TP_BLE_SWD", "TP_CELL_USB", "TP_CELL_DBG"]:
        c.setFillColor(group_colors[group])
        c.circle(legend_x + 5, legend_y + 3, 4, stroke=0, fill=1)
        c.setFillColor(colors.black)
        c.setFont(FONT, 8.5)
        count = sum(item["Fixture_Group"] == group for item in record["contacts"])
        c.drawString(legend_x + 16, legend_y, f"{short[group]}  {group}, {count} contacts")
        legend_y -= 16

    c.setFont(FONT_BOLD, 11)
    c.drawString(legend_x, legend_y - 2, "Опорные размеры / Datum")
    legend_y -= 22
    c.setFont(FONT, 8.5)
    for line in [
        "PCB outline: 110.00 x 75.00 mm",
        "Pogo pads: diameter 1.70 mm",
        "Pitch in each group: 2.54 mm",
        "Mounting holes: diameter 3.20 mm NPTH",
        "H1 is asymmetric and is the orientation key",
    ]:
        c.drawString(legend_x, legend_y, line)
        legend_y -= 14

    c.setFont(FONT_BOLD, 11)
    c.drawString(legend_x, legend_y - 2, "Критические правила / Critical rules")
    legend_y -= 22
    c.setFont(FONT, 8.5)
    rules = [
        "GND mates first and disconnects last.",
        "VTREF and rail sense are never sources.",
        "BOOT0 is driven only while NRST is asserted.",
        "BG95 debug uses 1.8 V only.",
        "TP_CELL_USB is isolated from STM32 J11.",
        "CELL_USB_VBUS is current limited.",
        "All outputs stay high-Z until reference is valid.",
    ]
    for line in rules:
        legend_y = draw_wrapped(c, line, legend_x, legend_y, page_w - margin - legend_x, 8.5, 12)

    table_y = 130
    c.setFont(FONT_BOLD, 9)
    c.drawString(margin, table_y, "Контактные ряды / Contact rows")
    table_y -= 15
    c.setFont(FONT, 8)
    rows = [
        "TP_EOL: Y=23.00, Xboard 33.00..63.48, contacts 1..13",
        "TP_MCU_SWD: Y=23.00, Xboard 69.00..79.16, contacts 1..5",
        "TP_BLE_SWD: Y=23.00, Xboard 84.00..91.62, contacts 1..4",
        "TP_CELL_USB: Y=30.00, Xboard 33.00..40.62, contacts 1..4",
        "TP_CELL_DBG: Y=30.00, Xboard 47.00..57.16, contacts 1..5",
    ]
    for index, line in enumerate(rows):
        c.drawString(margin + (index % 3) * 360, table_y - (index // 3) * 14, line)

    c.setFont(FONT, 8)
    c.drawString(margin, 48, "Полная распиновка и оба набора координат находятся в MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv.")
    c.drawString(margin, 36, "The complete pin map and both coordinate systems are in MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv.")
    c.drawRightString(page_w - margin, 36, "Статус / Status: FOR FIXTURE BUILD, PHYSICAL MSA NOT RUN")
    c.showPage()
    c.save()


def main() -> None:
    record = json.loads(PROGRAM.read_text(encoding="utf-8"))
    build_pdf(record)
    build_dxf(record)
    print(f"wrote {DXF}")
    print(f"wrote {PDF}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate a legible PCB-PWR Review B assembly sheet from native F.Fab and PCB poses."""
from __future__ import annotations

import argparse
import io
import math
import subprocess
from pathlib import Path

from kiutils.board import Board
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
OUT = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_E/PCB-PWR_assembly.pdf"
MM = 72 / 25.4
PAGE_W, PAGE_H = landscape(A3)
SCALE = 2.4
BOARD_X, BOARD_Y = 25 * MM, 75 * MM


def to_sheet(x: float, y: float) -> tuple[float, float]:
    return BOARD_X + SCALE * x * MM, BOARD_Y + SCALE * (60 - y) * MM


def pad_global(fp, pad) -> tuple[float, float]:
    angle = math.radians(float(fp.position.angle or 0))
    x, y = float(pad.position.X), float(pad.position.Y)
    return (float(fp.position.X) + x * math.cos(angle) + y * math.sin(angle),
            float(fp.position.Y) - x * math.sin(angle) + y * math.cos(angle))


def overlap(a, b, gap: float = 1.7) -> bool:
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or
                a[3] + gap < b[1] or b[3] + gap < a[1])


def label_layout(fps) -> dict[str, tuple[float, float]]:
    placed = []
    labels = {}
    # Dense component clusters are placed first, then larger footprints.
    for fp in sorted(fps, key=lambda f: (f.properties.get("Reference", "").startswith("TP"),
                                        float(f.position.X), float(f.position.Y))):
        ref = str(fp.properties["Reference"])
        cx, cy = to_sheet(float(fp.position.X), float(fp.position.Y))
        width = stringWidth(ref, "Helvetica-Bold", 7.5)
        choices = [(3, 3), (3, -5), (-3, 3), (-3, -5), (6, 0), (-6, 0)]
        for radius in (10, 14, 20, 27, 35, 45, 58):
            for degrees in range(0, 360, 30):
                theta = math.radians(degrees)
                choices.append((radius * math.cos(theta), radius * math.sin(theta)))
        best = None
        for dx, dy in choices:
            x, y = cx + dx, cy + dy
            rect = (x, y - 1.5, x + width, y + 8)
            if rect[0] < BOARD_X + 4 * MM or rect[2] > BOARD_X + 90 * SCALE * MM - 4 * MM:
                continue
            if rect[1] < BOARD_Y + 3 * MM or rect[3] > BOARD_Y + 60 * SCALE * MM - 3 * MM:
                continue
            if any(overlap(rect, other) for other in placed):
                continue
            best = (x, y, rect)
            break
        if best is None:
            raise RuntimeError(f"No assembly label space for {ref}")
        labels[ref] = (best[0], best[1])
        placed.append(best[2])
    return labels


def make_overlay(fps, labels, board_sha: str) -> bytes:
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    c.setTitle("PCB-PWR assembly / Review B Rev E")
    c.setAuthor("Dioneya engineering")
    c.setStrokeColor(colors.HexColor("#24364B"))
    c.setLineWidth(0.6)
    c.rect(12 * MM, 12 * MM, PAGE_W - 24 * MM, PAGE_H - 24 * MM)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(18 * MM, PAGE_H - 25 * MM, "PCB-PWR / ASSEMBLY DRAWING")
    c.setFont("Helvetica", 9)
    c.drawString(18 * MM, PAGE_H - 32 * MM, "Review B Rev E   |   Board Rev A   |   2026-09-28   |   NOT FOR MANUFACTURE")
    c.drawString(18 * MM, PAGE_H - 38 * MM, "Top view, KiCad F.Fab + Edge.Cuts, 2.4:1. Coordinates from upper-left, +Y down.")
    c.setFont("Helvetica", 7)
    c.drawString(18 * MM, 24 * MM, f"PCB source SHA-256: {board_sha}")
    c.drawString(18 * MM, 19 * MM, "Exact refdes overlay is generated from the same native PCB as the F.Fab plot.")
    c.setStrokeColor(colors.HexColor("#6A7786"))
    c.setLineWidth(0.35)
    for fp in fps:
        ref = str(fp.properties["Reference"])
        x0, y0 = to_sheet(float(fp.position.X), float(fp.position.Y))
        x, y = labels[ref]
        if math.dist((x0, y0), (x, y)) > 15:
            c.line(x0, y0, x - 1, y + 2)
    for fp in fps:
        ref = str(fp.properties["Reference"])
        x, y = labels[ref]
        is_dnp = bool(fp.attributes.excludeFromBom) and not (ref.startswith("H") or ref.startswith("TP"))
        c.setFillColor(colors.HexColor("#A43B36") if is_dnp else colors.HexColor("#0A4380"))
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(x, y, ref)
        if is_dnp:
            w = stringWidth(ref, "Helvetica-Bold", 7.5)
            c.setStrokeColor(colors.HexColor("#A43B36"))
            c.line(x, y + 3, x + w, y + 3)
        # Ring around actual pad 1 for orientation-sensitive components.
        if ref.startswith(("U", "J", "Q", "D")) or ref in {"C13", "F1", "RSH1"}:
            pad1 = next((pad for pad in fp.pads if str(pad.number) == "1"), None)
            if pad1:
                px, py = to_sheet(*pad_global(fp, pad1))
                c.setStrokeColor(colors.HexColor("#CA4E16"))
                c.setLineWidth(0.9)
                c.circle(px, py, 2.3, stroke=1, fill=0)
    c.setFillColor(colors.HexColor("#24364B"))
    c.setStrokeColor(colors.HexColor("#24364B"))
    rx = 260 * MM
    c.line(rx, 52 * MM, rx, 250 * MM)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(rx + 8 * MM, 245 * MM, "ASSEMBLY KEY")
    c.setFont("Helvetica", 8.5)
    notes = [
        "Blue: all board reference designators",
        "Red strike: do not populate (DNP)",
        "Orange ring: actual pad 1 location",
        "J1 mating direction: +Z",
        "J2 mating direction: +X (east edge)",
        "D1 polarity: follow footprint bar / pad 1",
        "C13 polarity: verify pad 1 against BOM",
        "All components and test points: top side",
    ]
    for index, note in enumerate(notes):
        c.drawString(rx + 8 * MM, (236 - 7 * index) * MM, note)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(rx + 8 * MM, 170 * MM, "DNP / DO NOT FIT")
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#A43B36"))
    c.drawString(rx + 8 * MM, 162 * MM, "R5  R9  R13  R14  R15")
    c.setFillColor(colors.HexColor("#24364B"))
    c.setFont("Helvetica", 8.5)
    c.drawString(rx + 8 * MM, 150 * MM, "Material target: 4 x 35 um Cu, ENIG")
    c.drawString(rx + 8 * MM, 143 * MM, "Board: 90 x 60 x 1.6 mm")
    c.drawString(rx + 8 * MM, 136 * MM, "Factory stack ID: pending checkout")
    c.drawString(rx + 8 * MM, 129 * MM, "Mechanical DIM-003 Rev B: review open")
    c.drawString(rx + 8 * MM, 122 * MM, "Connector plug/fixture CAD: unavailable")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(rx + 8 * MM, 80 * MM, "REVIEW STATUS: HOLD")
    c.setFont("Helvetica", 8)
    c.drawString(rx + 8 * MM, 72 * MM, "Assembly drawing for review only.")
    c.drawString(rx + 8 * MM, 66 * MM, "Human Review B signature required.")
    c.showPage()
    c.save()
    return stream.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kicad-cli", default="kicad-cli")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    board = Board.from_file(str(BOARD), encoding="utf-8")
    fps = [fp for fp in board.footprints if fp.properties.get("Reference")]
    assert len(fps) == 66 and len({fp.properties["Reference"] for fp in fps}) == 66
    dnp = {fp.properties["Reference"] for fp in fps if fp.attributes.excludeFromBom}
    assert {"R5", "R9", "R13", "R14", "R15"} <= dnp
    labels = label_layout(fps)
    import hashlib
    digest = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = args.output.with_name("_assembly_fab_raw.pdf")
    subprocess.run([args.kicad_cli, "pcb", "export", "pdf", "--layers", "F.Fab,Edge.Cuts",
                    "--mode-single", "--sketch-pads-on-fab-layers", "--exclude-refdes", "--black-and-white",
                    "-o", str(raw), str(BOARD)], check=True)
    source = PdfReader(str(raw)).pages[0]
    overlay = PdfReader(io.BytesIO(make_overlay(fps, labels, digest))).pages[0]
    writer = PdfWriter()
    page = writer.add_blank_page(width=PAGE_W, height=PAGE_H)
    # The raw KiCad PDF places board (0,0) at the upper-left of an A4 sheet.
    ty = BOARD_Y - SCALE * (float(source.mediabox.height) - 60 * MM)
    page.merge_transformed_page(source, Transformation().scale(SCALE).translate(BOARD_X, ty))
    page.merge_page(overlay)
    with args.output.open("wb") as handle:
        writer.write(handle)
    raw.unlink()
    print(f"Assembly sheet: {len(fps)} refs, 5 DNP, board {digest}, {args.output}")


if __name__ == "__main__":
    main()

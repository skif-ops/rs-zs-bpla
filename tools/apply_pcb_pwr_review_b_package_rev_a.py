#!/usr/bin/env python3
"""Export the PCB-PWR Review B package (evidence for the human reviewer).

Run by .github/workflows/ci-apply.yml (docker available). Uses the pinned KiCad
9.0.9 image on the authoritative board/project/rules; changes no design file.
Output: hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_A/
  PCB-PWR_copper_layers.pdf      F.Cu, In1.Cu, In2.Cu, B.Cu (one page each, outline)
  PCB-PWR_assembly.pdf           F/B fabrication + silkscreen pages
  PCB-PWR_top.png / _bottom.png  3D renders (board only if models are absent)
  PCB-PWR_schematic.pdf          native hierarchical schematic
  PCB-PWR_drc.rpt / _drc.json    KiCad DRC with the authoritative rule file
  gerber/ drill/                 Gerber X2, Excellon + map (review only, not a release)
  PCB-PWR_pos.csv, PCB-PWR.d356  placement and IPC-D-356 netlist
  POWER_COPPER_WIDTH.json        measured power-copper width vs the 35 um screen
  MANIFEST.json                  commands, return codes, output SHA-256
--check verifies MANIFEST.json exists and binds the current board.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
NATIVE = "hardware/kicad/native/PCB-PWR"
BOARD = f"{NATIVE}/PCB-PWR.kicad_pcb"
SCHEMATIC = f"{NATIVE}/PCB-PWR.kicad_sch"
OUT = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_A"
REL = OUT.relative_to(ROOT)
# KiCad runs on a scratch copy of the native directory (outside hardware/), so no tool
# side file (fp-info-cache, backups) can land next to the authoritative sources.
SCRATCH = "build/review_b_src/PCB-PWR"
SRC_BOARD = f"{SCRATCH}/PCB-PWR.kicad_pcb"
SRC_SCHEMATIC = f"{SCRATCH}/PCB-PWR.kicad_sch"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commands() -> list[tuple[str, list[str]]]:
    BOARD, SCHEMATIC = SRC_BOARD, SRC_SCHEMATIC  # noqa: N806 - scratch copy, see SCRATCH
    return [
        ("drc_report", ["kicad-cli", "pcb", "drc", "--format", "report", "--severity-all",
                        "-o", f"{REL}/PCB-PWR_drc.rpt", BOARD]),
        ("drc_json", ["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                      "-o", f"{REL}/PCB-PWR_drc.json", BOARD]),
        ("copper_pdf", ["kicad-cli", "pcb", "export", "pdf", "-o", f"{REL}/copper-pdf",
                        "--layers", "F.Cu,In1.Cu,In2.Cu,B.Cu", "--common-layers", "Edge.Cuts",
                        "--mode-multipage", "--include-border-title", "--drill-shape-opt", "2", BOARD]),
        ("assembly_pdf", ["kicad-cli", "pcb", "export", "pdf", "-o", f"{REL}/assembly-pdf",
                          "--layers", "F.Fab,F.Silkscreen,B.Fab,B.Silkscreen", "--common-layers", "Edge.Cuts",
                          "--mode-multipage", "--sketch-pads-on-fab-layers", "--include-border-title",
                          "--drill-shape-opt", "2", BOARD]),
        ("render_top", ["kicad-cli", "pcb", "render", "-o", f"{REL}/PCB-PWR_top.png", "--side", "top",
                        "--width", "1800", "--height", "1300", "--quality", "basic", BOARD]),
        ("render_bottom", ["kicad-cli", "pcb", "render", "-o", f"{REL}/PCB-PWR_bottom.png", "--side", "bottom",
                           "--width", "1800", "--height", "1300", "--quality", "basic", BOARD]),
        ("schematic_pdf", ["kicad-cli", "sch", "export", "pdf", "-o", f"{REL}/PCB-PWR_schematic.pdf", SCHEMATIC]),
        ("gerbers", ["kicad-cli", "pcb", "export", "gerbers", "-o", f"{REL}/gerber/", BOARD]),
        ("drill", ["kicad-cli", "pcb", "export", "drill", "-o", f"{REL}/drill/", "--format", "excellon",
                   "--generate-map", BOARD]),
        ("pos", ["kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                 "-o", f"{REL}/PCB-PWR_pos.csv", BOARD]),
        ("ipcd356", ["kicad-cli", "pcb", "export", "ipcd356", "-o", f"{REL}/PCB-PWR.d356", BOARD]),
    ]


def docker(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w",
                           KICAD_IMAGE, *argv], capture_output=True, text=True)


def power_copper_width() -> dict:
    """Perpendicular cuts every 0.25 mm along power tracks >= 1 mm through the union of
    same-net tracks, filled zones and pads on the same layer (host side, kiutils)."""
    import collections
    import math

    try:
        from shapely.geometry import LineString, Point, Polygon
        from shapely.ops import unary_union
    except ImportError:
        subprocess.run(["python", "-m", "pip", "install", "--quiet", "shapely"], check=True)
        from shapely.geometry import LineString, Point, Polygon
        from shapely.ops import unary_union
    from kiutils.board import Board

    def place(fp, x: float, y: float) -> tuple[float, float]:
        a = math.radians(fp.position.angle or 0)
        return (fp.position.X + x * math.cos(a) + y * math.sin(a),
                fp.position.Y - x * math.sin(a) + y * math.cos(a))

    board = Board.from_file(str(ROOT / BOARD))
    names = {net.number: net.name for net in board.nets}
    basis = json.loads((ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json")
                       .read_text(encoding="utf-8"))
    screen = {"PWR_INPUT_5A": 2.765521, "PWR_RAIL_4A": 2.032863}
    class_of = {net: cls for cls, nets in basis["netclass_assignments"].items() for net in nets}
    copper, tracks = collections.defaultdict(list), collections.defaultdict(list)
    for zone in board.zones:
        for fill in zone.filledPolygons or []:
            points = [(c.X, c.Y) for c in fill.coordinates]
            if len(points) >= 3:
                copper[(zone.netName, fill.layer)].append(Polygon(points).buffer(0))
    for item in board.traceItems:
        if type(item).__name__ != "Segment":
            continue
        net = names.get(item.net)
        copper[(net, item.layer)].append(
            LineString([(item.start.X, item.start.Y), (item.end.X, item.end.Y)]).buffer(item.width / 2))
        tracks[(net, item.layer)].append(((item.start.X, item.start.Y), (item.end.X, item.end.Y), item.width))
    for footprint in board.footprints:
        for pad in footprint.pads:
            if not pad.net or not [layer for layer in pad.layers if "Cu" in layer]:
                continue
            centre = Point(*place(footprint, pad.position.X, pad.position.Y))
            for layer in (["F.Cu", "B.Cu"] if pad.type == "thru_hole" else ["F.Cu"]):
                copper[(pad.net.name, layer)].append(centre.buffer(min(pad.size.X, pad.size.Y) / 2))
    rows = []
    for (net, layer), segments in sorted(tracks.items()):
        cls = class_of.get(net)
        if cls not in screen:
            continue
        union = unary_union(copper[(net, layer)])
        widths = []
        for a, b, width in segments:
            length = math.dist(a, b)
            if width < 0.9 or length < 0.3:
                continue
            ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            k = 1
            while k * 0.25 < length:
                px, py = a[0] + ux * k * 0.25, a[1] + uy * k * 0.25
                cut = LineString([(px + uy * 4, py - ux * 4), (px - uy * 4, py + ux * 4)]).intersection(union)
                for part in ([cut] if cut.geom_type == "LineString" else list(getattr(cut, "geoms", []))):
                    if part.distance(Point(px, py)) < 1e-6:
                        widths.append((round(part.length, 3), [round(px, 2), round(py, 2)]))
                        break
                k += 1
        if widths:
            ordered = sorted(w for w, _ in widths)
            low = sorted(x for x in widths if x[0] < screen[cls])
            rows.append({"net": net, "layer": layer, "class": cls, "screen_mm": round(screen[cls], 3),
                         "samples": len(widths), "min_mm": ordered[0], "median_mm": ordered[len(ordered) // 2],
                         "below_screen_samples": len(low),
                         "narrowest": [{"width_mm": w, "at_mm": at} for w, at in low[:8]]})
    return {
        "schema": "dioneya-pcb-pwr-power-copper-width-v1",
        "board_sha256": sha256(ROOT / BOARD),
        "method": "perpendicular cuts every 0.25 mm along power tracks >= 1 mm wide through the union of "
                  "same-net tracks, filled zones and pads on the same layer; sense/escape stubs < 1 mm excluded",
        "screen": "35 um outer copper, delta-T 10 C: 5 A 2.77 mm, 4 A 2.03 mm "
                  "(hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json)",
        "rows": rows,
    }


def flatten_pdf(folder: Path, target: Path) -> None:
    pdfs = sorted(folder.glob("*.pdf")) if folder.is_dir() else []
    if len(pdfs) == 1:
        shutil.copyfile(pdfs[0], target)
    shutil.rmtree(folder, ignore_errors=True)


def generate() -> None:
    if OUT.exists():
        keep = {"REVIEW_B_CHECKLIST.md"}
        for item in OUT.iterdir():
            if item.name in keep:
                continue
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    scratch = ROOT / SCRATCH
    shutil.rmtree(scratch.parent, ignore_errors=True)
    shutil.copytree(ROOT / NATIVE, scratch)
    for sub in ("gerber", "drill", "copper-pdf", "assembly-pdf"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    steps = []
    for name, argv in commands():
        result = docker(argv)
        steps.append({"step": name, "command": " ".join(argv), "rc": result.returncode,
                      "stderr_tail": (result.stderr or "")[-1500:]})
    subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                    "chmod", "-R", "a+rwX", str(REL)], capture_output=True)
    subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                    "rm", "-rf", str(scratch.parent.relative_to(ROOT))], capture_output=True)
    flatten_pdf(OUT / "copper-pdf", OUT / "PCB-PWR_copper_layers.pdf")
    flatten_pdf(OUT / "assembly-pdf", OUT / "PCB-PWR_assembly.pdf")
    try:
        width = power_copper_width()
    except Exception as error:  # noqa: BLE001 - recorded, the package still carries the KiCad outputs
        width = {"error": repr(error)}
    (OUT / "POWER_COPPER_WIDTH.json").write_text(json.dumps(width, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    outputs = {str(path.relative_to(OUT)): sha256(path)
               for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "MANIFEST.json"}
    manifest = {
        "schema": "dioneya-pcb-pwr-review-b-package-v1",
        "kicad_image": KICAD_IMAGE,
        "board_sha256": sha256(ROOT / BOARD),
        "rules_sha256": sha256(ROOT / f"{NATIVE}/PCB-PWR.kicad_dru"),
        "project_sha256": sha256(ROOT / f"{NATIVE}/PCB-PWR.kicad_pro"),
        "steps": steps,
        "outputs": outputs,
        "manufacturing_release": False,
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [s["step"] for s in steps if s["rc"] != 0]
    print(f"PCB-PWR Review B package: {len(outputs)} files, failed steps: {failed or 'none'}")


def check() -> None:
    manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["board_sha256"] == sha256(ROOT / BOARD), "Review B package does not bind the current board"
    print(f"PCB-PWR Review B package: PRESENT {len(manifest['outputs'])} files")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

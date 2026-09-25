#!/usr/bin/env python3
"""PCB-PWR ECO-005 candidate: power-return remediation at J2 / NT1-NT3 (Review B R1, finding 6).

Run by .github/workflows/ci-apply.yml (docker available). Starts from the authoritative
autoroute-011 board (SHA-256 pinned), writes a candidate only; the authoritative board is
not changed. Output: hardware/kicad/candidates/PCB-PWR-ECO-005/
  PCB-PWR_ECO_005_CANDIDATE_REV_A.kicad_pcb  refilled candidate
  ECO_005_SPEC.json                          exact geometry delta applied by the KiCad stage
  drc.json                                   KiCad 9.0.9 DRC with the authoritative project + rules
  SUMMARY.json                               DRC counts, return cross-sections, via groups
Delta (nets, netlist and net-tie count unchanged; no new domain join):
  - NT2 rotated 180 deg: its GND_DIGITAL pad faces J2.4, its GND_PWR pad faces the GND_PWR pour
    (NT1/NT3 keep their orientation: C17/C19 and C7/C8 GND_PWR pads bound them);
  - removed: the GND_MODEM 0.25 mm router track and single via, the GND_DIGITAL 0.4 mm track,
    the 0.3 mm GND_PWR stubs and via on NT2;
  - GND_MODEM: existing B.Cu return band from J2.2 and F.Cu zone at NT1 (solid pad
    connection), joined by 3 same-net vias 0.6/0.3 (the 3V8 J2->TP4 test-point branch, no load
    current, is narrowed 1.0 -> 0.3 mm next to J2 to free the via window);
  - GND_DIGITAL: F.Cu zone with solid pad connection from J2.4 straight to the rotated NT2;
  - GND_MIC (0.3 A class): second via 0.6/0.3 beside the existing one;
  - GND_PWR: 5 plane vias on the GND_PWR side of NT1/NT2/NT3.
--check verifies the candidate matches SUMMARY.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
NATIVE = ROOT / "hardware/kicad/native/PCB-PWR"
BOARD = NATIVE / "PCB-PWR.kicad_pcb"
BASE_SHA256 = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"  # autoroute 011
OUT = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-005"
STEM = "PCB-PWR_ECO_005_CANDIDATE_REV_A"
WORK = ROOT / "build/eco005"

REGION = (72.0, 37.0, 83.0, 57.5)          # tie / J2 return region
DOMAINS = ("GND_MODEM", "GND_DIGITAL")      # router tracks of these nets in REGION are replaced by zones
# Via positions: exhaustive 0.05 mm search of the free windows (0.2 mm to every other-net
# item on F.Cu and B.Cu, 0.8 mm pitch); see hardware/reviews/PCB_PWR_ECO_005_REV_A.md.
GND_MODEM_VIAS = [(73.85, 42.15), (74.4, 42.75), (74.15, 43.55)]        # B.Cu band -> F.Cu at NT1
GND_PWR_VIAS = [(76.65, 39.15),                                          # NT1 GND_PWR side
                (74.35, 48.15), (73.75, 48.75), (74.75, 48.85),          # NT2 GND_PWR side (rotated)
                (76.95, 51.15)]                                          # NT3 GND_PWR side
OLD_GND_MODEM_VIA = (74.35, 42.55)
NT2_PWR_STUBS = [((76.1, 48.52), (76.6, 48.52)), ((76.6, 48.52), (76.6, 51.5)), ((76.6, 51.5), (76.1, 52.0))]
NT2_PWR_VIA = (76.6, 48.52)
# J2 -> TP4 test-point branch of 3V8_MODEM on B.Cu (no load current): 1.0 -> 0.3 mm next to J2
TP4_BRANCH = [((81.08, 40.0), (79.6065, 41.4735)), ((79.6065, 41.4735), (70.8572, 41.4735))]
GND_MIC_SECOND_VIA = [
    ("via", "", "GND_MIC", 0.6, [(73.85, 52.95)]),
    ("track", "F.Cu", "GND_MIC", 0.5, [(73.85, 52.95), (74.5474, 52.5526)]),
    ("track", "B.Cu", "GND_MIC", 0.5, [(73.85, 52.95), (74.55, 53.18)]),
]
GND_DIGITAL_ZONE = [(75.8, 46.4), (82.6, 46.4), (82.6, 50.4), (75.8, 50.4)]
# cross-section probes: (label, layer, net, polyline) - cuts every 0.25 mm perpendicular to the line
PROBES = [
    ("GND_MODEM J2.2->vias", "B.Cu", "GND_MODEM", [(80.2, 43.0), (74.6, 43.0)]),
    ("GND_MODEM vias->NT1", "F.Cu", "GND_MODEM", [(74.0, 42.3), (74.0, 40.4)]),
    ("GND_DIGITAL J2.4->NT2", "F.Cu", "GND_DIGITAL", [(80.2, 48.3), (76.6, 48.3)]),
    ("GND_PWR NT1 east", "F.Cu", "GND_PWR", [(76.4, 40.12), (77.2, 40.12)]),
    ("GND_PWR NT2 west", "F.Cu", "GND_PWR", [(74.8, 48.52), (73.6, 48.52)]),
    ("GND_PWR NT3 east", "F.Cu", "GND_PWR", [(76.4, 52.0), (77.2, 51.4)]),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w",
                           KICAD_IMAGE, *argv], capture_output=True, text=True)


def shapely():
    try:
        import shapely.geometry  # noqa: F401
    except ImportError:
        subprocess.run(["python", "-m", "pip", "install", "--quiet", "shapely"], check=True)
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    return LineString, Point, Polygon, unary_union


def inside(x: float, y: float) -> bool:
    return REGION[0] <= x <= REGION[2] and REGION[1] <= y <= REGION[3]


def zone_polygon(board, net: str, layer: str, point) -> list:
    from shapely.geometry import Point, Polygon

    for zone in board.zones:
        if zone.netName == net and zone.layers == [layer]:
            for poly in zone.polygons:
                pts = [(c.X, c.Y) for c in poly.coordinates]
                if Polygon(pts).buffer(0).contains(Point(*point)):
                    return pts
    raise AssertionError(f"zone {net}/{layer} at {point} not found")


def build_spec() -> dict:
    """Exact removal list from the authoritative board plus the explicit additions."""
    from kiutils.board import Board

    shapely()
    board = Board.from_file(str(BOARD))
    names = {net.number: net.name for net in board.nets}
    spec = {"rotate": [{"ref": "NT2", "angle_deg": 180}],
            "remove_tracks": [], "remove_vias": [],
            # the GND_MODEM zones already connect pads solidly (connect_pads yes) and stay as they are
            "remove_zones": [{"net": "GND_DIGITAL", "layer": "F.Cu", "contains": [78.0, 47.0]}],
            "add_zones": [{"net": "GND_DIGITAL", "layer": "F.Cu", "priority": 14, "clearance_mm": 0.3,
                           "polygon": GND_DIGITAL_ZONE}],
            "add_items": []}
    for item in board.traceItems:
        net = names.get(item.net)
        if type(item).__name__ == "Via":
            continue
        ends = [(item.start.X, item.start.Y), (item.end.X, item.end.Y)]
        if net in DOMAINS and all(inside(*p) for p in ends):
            spec["remove_tracks"].append({"net": net, "layer": item.layer, "start": list(ends[0]),
                                          "end": list(ends[1])})
    for a, b in NT2_PWR_STUBS:
        spec["remove_tracks"].append({"net": "GND_PWR", "layer": "F.Cu", "start": list(a), "end": list(b)})
    for a, b in TP4_BRANCH:
        spec["remove_tracks"].append({"net": "3V8_MODEM", "layer": "B.Cu", "start": list(a), "end": list(b)})
    spec["remove_vias"] = [{"net": "GND_MODEM", "pos": list(OLD_GND_MODEM_VIA)},
                           {"net": "GND_PWR", "pos": list(NT2_PWR_VIA)}]
    spec["add_items"] = (
        [("via", "", "GND_MODEM", 0.6, [v]) for v in GND_MODEM_VIAS]
        + [("via", "", "GND_PWR", 0.6, [v]) for v in GND_PWR_VIAS]
        + [("track", "B.Cu", "3V8_MODEM", 0.3, [a, b]) for a, b in TP4_BRANCH]
        + GND_MIC_SECOND_VIA)
    return spec


def remove_text(text: str, spec: dict) -> tuple[str, dict]:
    """Remove the exact (segment|via|zone) blocks of the spec from the board text; every other
    byte is kept. Each requested removal must match exactly one block."""
    import re

    _, Point, Polygon, _ = shapely()
    nets = {int(m.group(1)): m.group(2) for m in re.finditer(r'^\t\(net (\d+) "([^"]*)"\)$', text, re.M)}
    lines = text.split("\n")
    blocks = []  # (kind, first_line, last_line)
    i = 0
    while i < len(lines):
        m = re.fullmatch(r"\t\((segment|via|zone)", lines[i])
        if m:
            j = i + 1
            while lines[j] != "\t)":
                j += 1
            blocks.append((m.group(1), i, j))
            i = j + 1
        else:
            i += 1

    def field(body: str, name: str):
        m = re.search(r"\(" + name + r" ([^()]*)\)", body)
        return m.group(1) if m else None

    def num_pair(value: str):
        a, b = value.split()[:2]
        return float(a), float(b)

    doomed, counts = set(), {"segment": 0, "via": 0, "zone": 0}
    for kind, a, b in blocks:
        body = "\n".join(lines[a:b + 1])
        net = nets.get(int(field(body, "net").split()[0]))
        if kind == "segment":
            start, end = num_pair(field(body, "start")), num_pair(field(body, "end"))
            layer = field(body, "layer").strip('"')
            hits = [r for r in spec["remove_tracks"] if r["net"] == net and r["layer"] == layer and (
                (math.dist(start, r["start"]) < 0.01 and math.dist(end, r["end"]) < 0.01)
                or (math.dist(start, r["end"]) < 0.01 and math.dist(end, r["start"]) < 0.01))]
        elif kind == "via":
            at = num_pair(field(body, "at"))
            hits = [r for r in spec["remove_vias"] if r["net"] == net and math.dist(at, r["pos"]) < 0.01]
        else:
            layer = (field(body, "layer") or "").strip('"')
            outline = body[body.index("(polygon"):] if "(polygon" in body else ""
            outline = outline[:outline.index("(filled_polygon")] if "(filled_polygon" in outline else outline
            pts = [(float(x), float(y)) for x, y in re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", outline)]
            hits = [r for r in spec["remove_zones"] if r["net"] == net and r["layer"] == layer and len(pts) >= 3
                    and Polygon(pts).buffer(0).contains(Point(*r["contains"]))]
        if hits:
            assert len(hits) == 1
            doomed.add((a, b))
            counts[kind] += 1
    expected = {"segment": len(spec["remove_tracks"]), "via": len(spec["remove_vias"]),
                "zone": len(spec["remove_zones"])}
    assert counts == expected, f"text removal matched {counts}, expected {expected}"
    keep = [line for index, line in enumerate(lines) if not any(a <= index <= b for a, b in doomed)]
    return "\n".join(keep), counts


def check_additions(spec: dict) -> list[str]:
    """Local clearance screen of the explicit new vias/tracks against all remaining copper."""
    from kiutils.board import Board

    LineString, Point, Polygon, unary_union = shapely()
    board = Board.from_file(str(BOARD))
    names = {net.number: net.name for net in board.nets}
    removed_t = {(tuple(r["start"]), tuple(r["end"])) for r in spec["remove_tracks"]}
    removed_v = {tuple(r["pos"]) for r in spec["remove_vias"]}
    shapes = []  # (net, layer, geometry)
    for item in board.traceItems:
        net = names.get(item.net)
        if type(item).__name__ == "Via":
            if (item.position.X, item.position.Y) in removed_v:
                continue
            for layer in ("F.Cu", "B.Cu"):
                shapes.append((net, layer, Point(item.position.X, item.position.Y).buffer(item.size / 2)))
        else:
            if ((item.start.X, item.start.Y), (item.end.X, item.end.Y)) in removed_t:
                continue
            shapes.append((net, item.layer, LineString([(item.start.X, item.start.Y),
                                                        (item.end.X, item.end.Y)]).buffer(item.width / 2)))
    rotated = {"NT2"}
    for fp in board.footprints:
        ref = next((p.value for p in (fp.properties if not isinstance(fp.properties, dict) else [])
                    if getattr(p, "key", None) == "Reference"), None) or \
            (fp.properties.get("Reference") if isinstance(fp.properties, dict) else None)
        angle = math.radians((fp.position.angle or 0) + (180 if ref in rotated else 0))
        for pad in fp.pads:
            if not [l for l in pad.layers if "Cu" in l] or pad.type == "np_thru_hole":
                continue
            x = fp.position.X + pad.position.X * math.cos(angle) + pad.position.Y * math.sin(angle)
            y = fp.position.Y - pad.position.X * math.sin(angle) + pad.position.Y * math.cos(angle)
            net = pad.net.name if pad.net else None
            r = min(pad.size.X, pad.size.Y) / 2
            for layer in (("F.Cu", "B.Cu") if pad.type == "thru_hole" else (pad.layers[0],)):
                shapes.append((net, layer, Point(x, y).buffer(r)))
    problems = []
    for kind, layer, net, width, points in spec["add_items"]:
        if kind == "via":
            geoms = [(lay, Point(*points[0]).buffer(width / 2)) for lay in ("F.Cu", "B.Cu")]
        else:
            geoms = [(layer, LineString(points).buffer(width / 2))]
        for lay, geom in geoms:
            for other_net, other_layer, other in shapes:
                if other_layer != lay or other_net == net:
                    continue
                gap = geom.distance(other)
                if gap < 0.2 - 1e-6:
                    problems.append(f"{kind} {net} {points[0]} on {lay}: {gap:.3f} mm to {other_net}")
    return problems


def cross_sections(geometry: dict) -> list[dict]:
    LineString, Point, Polygon, unary_union = shapely()
    rows = []
    for label, layer, net, line in PROBES:
        parts = []
        for fill in geometry["fills"]:
            if fill["net"] == net and fill["layer"] == layer and len(fill["points"]) >= 3:
                parts.append(Polygon(fill["points"], [h for h in fill["holes"] if len(h) >= 3]).buffer(0))
        for track in geometry["tracks"]:
            if track["net"] == net and track["layer"] == layer:
                parts.append(LineString([track["start"], track["end"]]).buffer(track["width"] / 2))
        for pad in geometry["pads"]:
            if pad["net"] == net and layer in pad["layers"]:
                parts.append(Polygon(pad["poly"]).buffer(0))
        copper = unary_union(parts) if parts else None
        (x0, y0), (x1, y1) = line
        length = math.dist((x0, y0), (x1, y1))
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        widths = []
        k = 0
        while k * 0.25 <= length:
            px, py = x0 + ux * k * 0.25, y0 + uy * k * 0.25
            width = 0.0
            if copper is not None:
                cut = LineString([(px + uy * 5, py - ux * 5), (px - uy * 5, py + ux * 5)]).intersection(copper)
                for piece in ([cut] if cut.geom_type == "LineString" else list(getattr(cut, "geoms", []))):
                    if piece.distance(Point(px, py)) < 1e-6:
                        width = piece.length
                        break
            widths.append((round(width, 3), [round(px, 2), round(py, 2)]))
            k += 1
        low = min(widths)
        rows.append({"probe": label, "layer": layer, "net": net, "min_width_mm": low[0], "at_mm": low[1],
                     "samples": len(widths)})
    return rows


def generate() -> None:
    assert sha256(BOARD) == BASE_SHA256, "authoritative PCB-PWR is not the autoroute 011 board"
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    spec = build_spec()
    problems = check_additions(spec)
    (OUT / "ECO_005_SPEC.json").write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
    summary = {"schema": "dioneya-pcb-pwr-eco-005-candidate-v1", "base_board_sha256": BASE_SHA256,
               "kicad_image": KICAD_IMAGE, "local_clearance_screen": problems or "PASS",
               "manufacturing_release": False}
    if not problems:
        base = WORK / f"{STEM}.kicad_pcb"
        text, counts = remove_text(BOARD.read_text(encoding="utf-8"), spec)
        base.write_text(text, encoding="utf-8")
        summary["text_removal"] = counts
        shutil.copyfile(NATIVE / "PCB-PWR.kicad_pro", WORK / f"{STEM}.kicad_pro")
        shutil.copyfile(NATIVE / "PCB-PWR.kicad_dru", WORK / f"{STEM}.kicad_dru")
        stage_spec = {k: v for k, v in spec.items() if not k.startswith("remove_")}
        (WORK / "spec.json").write_text(json.dumps(stage_spec), encoding="utf-8")
        rel = WORK.relative_to(ROOT)
        stage = docker("/usr/bin/python3", "tools/pcb_pwr_eco_005_stage_rev_a.py", "apply", f"{rel}/{STEM}.kicad_pcb",
                       f"{rel}/spec.json", f"{rel}/{STEM}.kicad_pcb")
        summary["stage"] = {"rc": stage.returncode, "stdout": stage.stdout[-800:], "stderr": stage.stderr[-1500:]}
        if stage.returncode == 0:
            drc = docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                         "-o", f"{rel}/drc.json", f"{rel}/{STEM}.kicad_pcb")
            dump = docker("/usr/bin/python3", "tools/pcb_pwr_eco_005_stage_rev_a.py", "dump", f"{rel}/{STEM}.kicad_pcb",
                          f"{rel}/geometry.json")
            summary["drc_rc"], summary["dump_rc"] = drc.returncode, dump.returncode
            docker("chmod", "-R", "a+rwX", str(rel))
            if not (WORK / "drc.json").exists():
                summary["drc_stderr"] = drc.stderr[-1500:]
                (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
                raise SystemExit("KiCad DRC produced no report")
            report = json.loads((WORK / "drc.json").read_text(encoding="utf-8"))
            errors = [v for v in report["violations"] if v["severity"] == "error"]
            counts: dict = {}
            for v in report["violations"]:
                key = f"{v['severity']}:{v['type']}"
                counts[key] = counts.get(key, 0) + 1
            summary["drc"] = {"error_total": len(errors), "unconnected_total": len(report["unconnected_items"]),
                              "by_type": counts,
                              "errors": [[v["type"]] + [i["description"] for i in v["items"]] for v in errors][:60],
                              "unconnected": [[i["description"] for i in u["items"]]
                                              for u in report["unconnected_items"]][:40]}
            summary["return_cross_sections"] = cross_sections(json.loads((WORK / "geometry.json").read_text()))
            shutil.copyfile(WORK / f"{STEM}.kicad_pcb", OUT / f"{STEM}.kicad_pcb")
            shutil.copyfile(WORK / "drc.json", OUT / "drc.json")
            summary["candidate_sha256"] = sha256(OUT / f"{STEM}.kicad_pcb")
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    docker("rm", "-rf", str(WORK.relative_to(ROOT)))
    print(json.dumps({k: summary.get(k) for k in ("local_clearance_screen", "drc", "candidate_sha256")},
                     ensure_ascii=False)[:1500])


def check() -> None:
    summary = json.loads((OUT / "SUMMARY.json").read_text(encoding="utf-8"))
    candidate = OUT / f"{STEM}.kicad_pcb"
    if candidate.exists():
        assert summary.get("candidate_sha256") == sha256(candidate), "candidate differs from SUMMARY.json"
    print("PCB-PWR ECO-005 candidate: SUMMARY present")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

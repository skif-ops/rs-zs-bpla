#!/usr/bin/env python3
"""Generate the PCB-PWR autoroute candidate 011 (run by .github/workflows/ci-apply.yml).

Pipeline (the authoritative board is NOT modified):
1. copy native PCB-PWR board and project to a work directory; the project gets
   the net classes of the accepted 35 um routing basis
   (hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json);
2. KiCad 9.0.9 (pinned image) locks all accepted copper, adds the GND_PWR plane
   on In1.Cu and exports Specctra DSN;
3. Freerouting 2.4.1 (pinned SHA-256, headless) routes the open nets;
4. KiCad imports the session, refills zones, runs DRC;
5. candidate board, project, DRC report and SUMMARY.json are written to
   hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/ for review.

--check verifies that the committed summary matches the committed candidate.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = "PCB-PWR"
NATIVE_DIR = ROOT / "hardware/kicad/native/PCB-PWR"
BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"
OUT_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011"
WORK = ROOT / "build/autoroute/PCB-PWR"
STEM = "PCB-PWR_AUTOROUTE_011_CANDIDATE_REV_A"
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
FREEROUTING_URL = "https://github.com/freerouting/freerouting/releases/download/v2.4.1/freerouting-2.4.1-linux-x64.zip"
FREEROUTING_SHA256 = "3ad5a956ab474b12f331d24195feadac90e8344b8e013c6a4ab26e203ce51519"
# Layer authority PCB-PWR: F.Cu POWER_SIGNAL, In1.Cu REFERENCE, In2.Cu POWER_RETURN,
# B.Cu POWER_SIGNAL -> both inner layers are GND_PWR planes, routing on outer layers
# only (an inner 1 oz conductor would need ~2x the outer width for the same rise).
PLANES = [{"net": "GND_PWR", "layer": "In1.Cu", "inset_mm": 0.5},
          {"net": "GND_PWR", "layer": "In2.Cu", "inset_mm": 0.5}]
HOLE_KEEPOUTS = {"refs": ["H1", "H2", "H3", "H4"], "radius_mm": 4.0}
PASSES = 150
# Locked pre-routes, all checked against every copper item of the authoritative
# board and against each other (>= 0.2 mm, SW nodes 0.4 mm, NPTH 0.3 mm, mounting
# hole keepouts, 0.5 mm edge); power items keep >= 0.3 mm (basis):
# - input protection: VBAT_FUSED on F.Cu from F1 through the D1/U1 corridor
#   (1.9 mm, the 1206 fuse is the narrower element) and under Q1 (3.0 mm) to the
#   source pins, with the D1 cathode; VBAT_PROTECTED from the Q1 drain through
#   7 vias, 3.0 mm on B.Cu, 7 vias at RSH1/C10 (no via-in-pad; the provisional
#   12-via value of the basis is covered by the EVT +70 C / 5 A test);
# - 3V8_MODEM from the accepted 3V8 copper to J2 pin 1 along the east corridor
#   (3.0 mm); 3V3_DIGITAL from C17/C19 to J2 pin 3 on B.Cu (1.2 mm between the
#   J2 pins and the locating peg: connector pitch limit, documented);
# - fan-outs of the LMR60440 pin rows 5..8 (U3/U4) and of U2 with vias, FB/MODE
#   on B.Cu to R1/R5/R10/R9, EN_MODEM corridor, NT2 net-tie exits, DNP I2C
#   pull-ups R13/R14 and test points TP9/TP10 (SDA on B.Cu north of SCL, clear
#   of the H3 keepout, into J2 pin 12 between pins 11/12), 3V3 links C7->R13/R14 and
#   R15/U2->C5; GND_PWR of U1 pin 2 and U2 pins 1/2 to vias under the package
#   bodies, NT3 GND_PWR pad to the NT2 ground via, R2 (FB divider) and R11 ground vias.
PREROUTE = [
    ('track', 'F.Cu', '3V3_DIGITAL', 0.2, [(46.2, 24.0), (47.7, 24.0)]),
    ('via', None, '3V3_DIGITAL', 0.6, [(47.7, 24.0)]),
    ('track', 'F.Cu', 'VBAT_SYS', 0.2, [(46.2, 23.0), (47.3, 23.0)]),
    ('via', None, 'VBAT_SYS', 0.6, [(47.3, 23.0)]),
    ('track', 'F.Cu', 'GND_PWR', 0.2, [(46.2, 23.5), (44.9, 23.5)]),
    ('via', None, 'GND_PWR', 0.6, [(44.9, 23.5)]),
    ('track', 'F.Cu', 'GND_DIGITAL', 0.4, [(75.1, 48.52), (75.1, 47.8), (79.5, 47.8), (81.08, 49.0)]),
    ('track', 'F.Cu', 'EN_MODEM', 0.2, [(53.875, 14.075), (53.175, 14.075), (53.175, 12.2)]),
    ('via', None, 'EN_MODEM', 0.6, [(53.175, 12.2)]),
    ('track', 'F.Cu', 'I2C2_SCL', 0.25, [(75.11, 56.5), (76.2, 56.5), (76.9, 55.8), (76.9, 52.9), (78.08, 52.0)]),
    ('track', 'F.Cu', 'I2C2_SDA', 0.25, [(75.11, 58.0), (76.6, 58.0), (78.08, 56.5), (78.08, 55.0)]),
    ('track', 'F.Cu', 'GND_PWR', 0.3, [(76.1, 48.52), (76.6, 48.52)]),
    ('via', None, 'GND_PWR', 0.6, [(76.6, 48.52)]),
    ('track', 'F.Cu', 'PG_3V8', 0.2, [(56.0, 12.9), (56.0, 12.4), (56.6, 11.8)]),
    ('via', None, 'PG_3V8', 0.6, [(56.6, 11.8)]),
    ('track', 'F.Cu', 'FB_3V8', 0.2, [(55.585, 13.125), (55.585, 11.2)]),
    ('via', None, 'FB_3V8', 0.6, [(55.585, 11.2)]),
    ('track', 'F.Cu', 'MODE_3V8', 0.2, [(54.415, 13.125), (54.415, 10.7)]),
    ('via', None, 'MODE_3V8', 0.6, [(54.415, 10.7)]),
    ('track', 'F.Cu', 'RT_3V8', 0.2, [(54.0, 12.9), (54.0, 12.3), (53.6, 11.5)]),
    ('via', None, 'RT_3V8', 0.6, [(53.6, 11.5)]),
    ('track', 'F.Cu', 'PWR_GOOD', 0.2, [(56.0, 40.9), (56.0, 40.4), (56.6, 39.8)]),
    ('via', None, 'PWR_GOOD', 0.6, [(56.6, 39.8)]),
    ('track', 'F.Cu', '3V3_DIGITAL', 0.2, [(55.585, 41.125), (55.585, 39.2)]),
    ('via', None, '3V3_DIGITAL', 0.6, [(55.585, 39.2)]),
    ('track', 'F.Cu', 'MODE_3V3', 0.2, [(54.415, 41.125), (54.415, 38.7)]),
    ('via', None, 'MODE_3V3', 0.6, [(54.415, 38.7)]),
    ('track', 'F.Cu', 'RT_3V3', 0.2, [(54.0, 40.9), (54.0, 40.3), (53.6, 39.5)]),
    ('via', None, 'RT_3V3', 0.6, [(53.6, 39.5)]),
    ('track', 'B.Cu', 'FB_3V8', 0.2, [(55.585, 11.2), (56.51, 19.9)]),
    ('via', None, 'FB_3V8', 0.6, [(56.51, 19.9)]),
    ('track', 'F.Cu', 'FB_3V8', 0.2, [(56.51, 19.9), (56.51, 19.0)]),
    ('track', 'B.Cu', 'MODE_3V8', 0.2, [(54.415, 10.7), (54.2, 12.5), (54.2, 16.0), (54.99, 21.9)]),
    ('via', None, 'MODE_3V8', 0.6, [(54.99, 21.9)]),
    ('track', 'F.Cu', 'MODE_3V8', 0.2, [(54.99, 21.9), (54.99, 21.0)]),
    ('track', 'B.Cu', '3V3_DIGITAL', 0.2, [(55.585, 39.2), (57.49, 47.9)]),
    ('via', None, '3V3_DIGITAL', 0.6, [(57.49, 47.9)]),
    ('track', 'F.Cu', '3V3_DIGITAL', 0.2, [(57.49, 47.9), (57.49, 47.0)]),
    ('track', 'B.Cu', 'MODE_3V3', 0.2, [(54.415, 38.7), (54.2, 40.5), (54.2, 44.0), (54.49, 49.9)]),
    ('via', None, 'MODE_3V3', 0.6, [(54.49, 49.9)]),
    ('track', 'F.Cu', 'MODE_3V3', 0.2, [(54.49, 49.9), (54.49, 49.0)]),
    ('track', 'F.Cu', '3V3_DIGITAL', 0.25, [(47.7, 24.0), (48.2, 23.5), (48.2, 22.2)]),
    ('track', 'B.Cu', '3V3_DIGITAL', 0.25, [(47.7, 24.0), (61.51, 24.0), (61.51, 21.4)]),
    ('via', None, '3V3_DIGITAL', 0.6, [(61.51, 21.4)]),
    ('track', 'F.Cu', '3V3_DIGITAL', 0.25, [(61.51, 21.4), (61.51, 20.5)]),
    ('track', 'B.Cu', 'VBAT_SYS', 0.25, [(47.3, 23.0), (44.0, 28.5)]),
    ('via', None, 'VBAT_SYS', 0.6, [(44.0, 28.5)]),
    ('via', None, 'I2C2_SCL', 0.6, [(45.32, 54.6)]),
    ('track', 'F.Cu', 'I2C2_SCL', 0.25, [(45.32, 56.0), (45.32, 54.6)]),
    ('track', 'B.Cu', 'I2C2_SCL', 0.25, [(45.32, 54.6), (62.0, 50.5), (73.5, 50.5), (76.9, 53.9)]),
    ('via', None, 'I2C2_SCL', 0.6, [(76.9, 53.9)]),
    ('track', 'F.Cu', '3V3_DIGITAL', 0.25, [(73.625, 50.3), (73.2, 50.8), (73.2, 56.5), (74.09, 56.5), (74.09, 58.0)]),
    ('track', 'B.Cu', '3V3_DIGITAL', 0.25, [(61.51, 24.0), (64.5, 27.0), (64.5, 35.0)]),
    ('via', None, '3V3_DIGITAL', 0.6, [(64.5, 35.0)]),
    ('track', 'F.Cu', '3V3_DIGITAL', 0.25, [(64.5, 35.0), (66.4, 36.9), (67.3, 36.9)]),
    ('track', 'F.Cu', 'FAULT', 0.2, [(41.8, 23.0), (42.7, 23.0), (43.2, 22.2)]),
    ('via', None, 'FAULT', 0.6, [(43.2, 22.2)]),
    ('track', 'F.Cu', 'I2C2_SDA', 0.2, [(41.8, 23.5), (43.9, 23.5)]),
    ('via', None, 'I2C2_SDA', 0.6, [(43.9, 23.5)]),
    ('track', 'F.Cu', 'I2C2_SCL', 0.2, [(41.8, 24.0), (42.7, 24.0), (43.2, 24.8)]),
    ('via', None, 'I2C2_SCL', 0.6, [(43.2, 24.8)]),
    ('track', 'F.Cu', 'VBAT_FUSED', 1.9, [(14.4, 29.0), (16.9, 29.0), (16.9, 35.5)]),
    ('track', 'F.Cu', 'VBAT_FUSED', 3.0, [(14.5, 35.5), (29.77, 35.5)]),
    ('track', 'F.Cu', 'VBAT_FUSED', 1.2, [(29.77, 35.5), (29.77, 29.365)]),
    ('track', 'F.Cu', 'VBAT_FUSED', 2.4, [(30.4, 32.9), (30.4, 34.5)]),
    ('track', 'F.Cu', 'VBAT_PROTECTED', 1.0, [(22.9, 31.4), (22.9, 32.6), (27.9, 32.6)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(22.9, 31.4)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(22.9, 32.4)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(23.9, 33.3)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(24.9, 33.3)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(25.9, 33.3)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(26.9, 33.3)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(27.9, 33.3)]),
    ('track', 'B.Cu', 'VBAT_PROTECTED', 3.0, [(22.9, 31.4), (22.9, 33.3), (31.35, 33.3), (31.35, 27.0), (33.9, 28.3)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(31.35, 27.0)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(31.35, 28.0)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(31.35, 29.0)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(31.35, 30.0)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(31.35, 31.0)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(33.0, 28.3)]),
    ('via', None, 'VBAT_PROTECTED', 0.6, [(33.9, 28.3)]),
    ('track', 'F.Cu', 'VBAT_PROTECTED', 1.0, [(31.35, 27.0), (31.35, 31.0)]),
    ('track', 'F.Cu', 'VBAT_PROTECTED', 1.6, [(31.85, 30.4), (32.6, 30.4)]),
    ('track', 'F.Cu', 'VBAT_PROTECTED', 1.0, [(31.35, 27.0), (32.525, 26.0)]),
    ('track', 'F.Cu', 'VBAT_PROTECTED', 1.2, [(32.525, 26.0), (33.515, 30.365)]),
    ('track', 'F.Cu', 'VBAT_PROTECTED', 0.8, [(33.0, 28.3), (33.9, 28.3)]),
    ('track', 'F.Cu', '3V8_MODEM', 3.0, [(72.525, 20.2), (79.5, 20.2), (83.5, 24.2), (83.5, 37.0), (81.08, 39.42)]),
    ('track', 'F.Cu', '3V3_DIGITAL', 1.0, [(72.525, 38.0), (72.525, 42.25)]),
    ('via', None, '3V3_DIGITAL', 0.6, [(72.0, 40.1)]),
    ('via', None, '3V3_DIGITAL', 0.6, [(73.0, 40.1)]),
    ('track', 'B.Cu', '3V3_DIGITAL', 1.2, [(72.0, 40.1), (76.5, 38.0), (82.95, 38.0), (82.95, 44.5), (81.08, 46.0)]),
    ('track', 'F.Cu', 'GND_PWR', 0.3, [(18.7, 30.0), (20.0, 30.0)]),
    ('via', None, 'GND_PWR', 0.6, [(20.0, 30.0)]),
    ('track', 'F.Cu', 'GND_PWR', 0.3, [(42.3, 22.0), (42.8, 21.5), (44.4, 21.5)]),
    ('via', None, 'GND_PWR', 0.6, [(44.4, 21.5)]),
    ('track', 'F.Cu', 'GND_PWR', 0.3, [(76.6, 48.52), (76.6, 51.5), (76.1, 52.0)]),
    ('track', 'F.Cu', 'GND_PWR', 0.3, [(59.01, 19.0), (59.01, 19.9)]),
    ('via', None, 'GND_PWR', 0.6, [(59.01, 19.9)]),
    ('track', 'F.Cu', 'I2C2_SDA', 0.25, [(47.86, 56.0), (47.86, 52.9)]),
    ('via', None, 'I2C2_SDA', 0.6, [(47.86, 52.9)]),
    ('track', 'B.Cu', 'I2C2_SDA', 0.25, [(47.86, 52.9), (61.8, 49.8), (74.2, 49.8), (78.08, 53.68), (78.08, 55.0)]),
    ('track', 'F.Cu', 'GND_PWR', 0.3, [(66.51, 49.0), (66.51, 47.9)]),
    ('via', None, 'GND_PWR', 0.6, [(66.51, 47.9)]),
]
TIE_STRIPS = ["NT2"]
# Mounting holes H1..H4 (native board) for the gap-fill router keepouts, and the
# nets it leaves to the pours (GND_PWR reaches the plane through pour vias).
HOLE_CENTRES_MM = [(5.0, 5.0), (82.0, 5.0), (68.0, 55.0), (5.0, 55.0)]
GAPFILL_SKIP_NETS = {"GND_PWR"}
# Autoroute (connectivity) class parameters. Freerouting cannot neck a wide
# track down into a fine-pitch pin, so power nets are routed at 1.0 mm for
# connectivity and then thickened to the basis width by zones along the route
# (THICKEN_MM); zone fill necks down automatically where neighbours are closer.
# 0.2 mm clearance for all non-switch classes: fine-pitch pins (0.5 mm pitch,
# 0.2 mm gaps) cannot meet 0.3 mm; 0.2 mm is above the JLCPCB 1 oz minimum.
# GND_PWR is stubbed to vias into the In1.Cu plane and poured on F.Cu/B.Cu.
AUTOROUTE_OVERRIDES = {
    "PWR_INPUT_5A": {"track_width": 1.0, "clearance": 0.2},
    "PWR_RAIL_4A": {"track_width": 1.0, "clearance": 0.2},
    "PWR_RETURN_5A": {"track_width": 0.6, "clearance": 0.2},
    "PWR_RAIL_0P3A": {"clearance": 0.2},
    "PWR_LOCAL": {"clearance": 0.2},
    "PWR_SENSE": {"clearance": 0.2},
}
THICKEN_MM = {"PWR_INPUT_5A": 4.0, "PWR_RAIL_4A": 3.0}
THICKEN_CLEARANCE_MM = 0.3
GROUND = {"net": "GND_PWR", "layers": ["F.Cu", "B.Cu"], "inset_mm": 0.5, "clearance_mm": 0.3,
          "stitch_pitch_mm": 3.5, "stitch_keep_mm": 0.75}
# Same-footprint pad spacing of the fine-pitch shunt monitor U2 (VSSOP-10 0.5 mm
# pitch, 0.2 mm gaps) is set by its land pattern, like U3/U4 in ECO-004.
CANDIDATE_DRU_APPEND = """
(rule "U2 VSSOP-10 land pattern"
  (condition "A.memberOfFootprint('U2') && B.memberOfFootprint('U2')")
  (constraint clearance (min 0.19mm))
)
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], **kwargs) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)
    return result.stdout


def docker(*args: str) -> str:
    return run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE, *args])


def project_with_netclasses(source: Path) -> dict:
    project = json.loads(source.read_text(encoding="utf-8"))
    basis = json.loads(BASIS.read_text(encoding="utf-8"))
    template = {
        "bus_width": 12, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
        "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6,
    }
    classes = [dict(template, name="Default", clearance=0.2, track_width=0.25,
                    via_diameter=0.6, via_drill=0.3, priority=2147483647)]
    for index, numeric in enumerate(basis["numeric_classes"]):
        classes.append(dict(
            template,
            name=numeric["name"],
            clearance=numeric["clearance_mm"],
            track_width=numeric["selected_width_mm"],
            via_diameter=numeric.get("via_diameter_mm", 0.6),
            via_drill=numeric.get("via_drill_mm", 0.3),
            priority=index,
        ))
        classes[-1].update(AUTOROUTE_OVERRIDES.get(numeric["name"], {}))
    patterns = [
        {"netclass": cls, "pattern": net}
        for cls, nets in basis["netclass_assignments"].items()
        for net in nets
    ]
    project["net_settings"] = {
        "classes": classes,
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": patterns,
    }
    return project


def freerouting() -> Path:
    cache = ROOT / "build/tools"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "freerouting-2.4.1-linux-x64.zip"
    if not archive.is_file():
        urllib.request.urlretrieve(FREEROUTING_URL, archive)
    assert sha256(archive) == FREEROUTING_SHA256, "Freerouting archive SHA-256 mismatch"
    target = cache / "freerouting"
    if not target.is_dir():
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(target)
    binary = next(target.glob("*/bin/freerouting"))
    binary.chmod(0o755)
    for helper in target.glob("*/lib/runtime/bin/*"):
        helper.chmod(0o755)
    return binary


def pour_spec(segments: list[dict]) -> dict:
    """Host side: union of buffered power routes per net and layer -> zone polygons."""
    try:
        from shapely.geometry import LineString
        from shapely.ops import unary_union
    except ImportError:
        subprocess.run(["python", "-m", "pip", "install", "--quiet", "shapely"], check=True)
        from shapely.geometry import LineString
        from shapely.ops import unary_union
    basis = json.loads(BASIS.read_text(encoding="utf-8"))
    width_by_net = {net: THICKEN_MM[cls] for cls, nets in basis["netclass_assignments"].items()
                    if cls in THICKEN_MM for net in nets}
    grouped: dict[tuple[str, str], list] = collections.defaultdict(list)
    for segment in segments:
        width = width_by_net.get(segment["net"])
        if width is None or segment["layer"] not in {"F.Cu", "B.Cu"}:
            continue
        line = LineString([segment["start"], segment["end"]]) if segment["start"] != segment["end"] else None
        if line is not None:
            grouped[(segment["net"], segment["layer"])].append(line.buffer(width / 2.0, cap_style=1, join_style=1))
    thicken = []
    for priority, ((net, layer), shapes) in enumerate(sorted(grouped.items()), start=10):
        merged = unary_union(shapes).simplify(0.02)
        polygons = [merged] if merged.geom_type == "Polygon" else list(merged.geoms)
        thicken.append({
            "net": net, "layer": layer, "priority": priority, "clearance_mm": THICKEN_CLEARANCE_MM,
            "polygons": [[[round(x, 4), round(y, 4)] for x, y in list(poly.exterior.coords)[:-1]] for poly in polygons],
        })
    return {"thicken": thicken, "ground_net": GROUND["net"], "ground_pour_layers": GROUND["layers"],
            "pour_inset_mm": GROUND["inset_mm"], "pour_clearance_mm": GROUND["clearance_mm"],
            "stitch_pitch_mm": GROUND["stitch_pitch_mm"], "stitch_keep_mm": GROUND["stitch_keep_mm"],
            "hole_refs": HOLE_KEEPOUTS["refs"], "hole_keep_mm": HOLE_KEEPOUTS["radius_mm"] + 0.3}


def gap_fill(board: Path, rel) -> dict:
    """Route what Freerouting left open (KiCad DRC before pours) with the grid A*
    router of tools/pcb_gapfill_router_rev_a.py on the actual copper of this run."""
    try:
        import shapely  # noqa: F401
    except ImportError:
        subprocess.run(["python", "-m", "pip", "install", "--quiet", "shapely", "numpy"], check=True)
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tools"))
    import pcb_gapfill_router_rev_a as gapfill_router

    pre_drc = WORK / "drc_pre_pour.json"
    docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", rel(pre_drc), rel(board))
    geometry_path = WORK / "geometry.json"
    docker("/usr/bin/python3", "tools/kicad_autoroute_stage_rev_a.py", "dump", rel(board), rel(geometry_path))
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    geometry["holes"] = [list(p) for p in HOLE_CENTRES_MM]
    pairs = []
    for item in json.loads(pre_drc.read_text(encoding="utf-8")).get("unconnected_items", []):
        a, b = item["items"][0], item["items"][1]
        match = re.search(r"\[([^\]]+)\]", a.get("description", ""))
        net = match.group(1) if match else ""
        if net in GAPFILL_SKIP_NETS or a["description"].startswith("Zone") or b["description"].startswith("Zone"):
            continue
        pairs.append((net, (a["pos"]["x"], a["pos"]["y"]), (b["pos"]["x"], b["pos"]["y"])))
    settings = project_with_netclasses(NATIVE_DIR / f"{BOARD}.kicad_pro")["net_settings"]
    class_clearance = {c["name"]: c["clearance"] for c in settings["classes"]}
    net_clearance = {p["pattern"]: class_clearance[p["netclass"]] for p in settings["netclass_patterns"]}
    router, failed = gapfill_router.route_all(
        lambda: gapfill_router.GapFillRouter(geometry, ["F.Cu", "B.Cu"], width=0.25, clearance=0.2,
                                             via_size=0.6, via_drill=0.3, edge_keep=0.5,
                                             hole_keep=HOLE_KEEPOUTS["radius_mm"] + 0.3,
                                             net_clearance=net_clearance),
        pairs) if pairs else (None, [])
    routed = router.routed if router else []
    routes_path = WORK / "gapfill.json"
    routes_path.write_text(json.dumps(routed), encoding="utf-8")
    if routed:
        docker("/usr/bin/python3", "tools/kicad_autoroute_stage_rev_a.py", "addroutes", rel(board), rel(routes_path))
    return {"routed": routed, "pairs": [p[0] for p in pairs], "failed": [p[0] for p in failed]}


def summarize(drc_path: Path, candidate: Path, native_sha: str, log_tail: str, stage: dict) -> dict:
    report = json.loads(drc_path.read_text(encoding="utf-8"))
    by_type = collections.Counter(
        (v["severity"], v["type"]) for v in report.get("violations", [])
    )
    unconnected_nets = collections.Counter()
    for item in report.get("unconnected_items", []):
        match = re.search(r"\[([^\]]+)\]", item["items"][0].get("description", ""))
        unconnected_nets[match.group(1) if match else "?"] += 1
    return {
        "schema": "dioneya-pcb-pwr-autoroute-candidate-v1",
        "status": "CANDIDATE_FOR_REVIEW_NOT_APPLIED",
        "native_board_sha256": native_sha,
        "candidate_sha256": sha256(candidate),
        "kicad_image": KICAD_IMAGE,
        "freerouting": {"url": FREEROUTING_URL, "sha256": FREEROUTING_SHA256, "passes": PASSES},
        "planes_added": PLANES,
        "hole_keepouts": HOLE_KEEPOUTS,
        "autoroute_class_overrides": AUTOROUTE_OVERRIDES,
        "thicken_mm": THICKEN_MM,
        "preroute": PREROUTE,
        "tie_strips": TIE_STRIPS,
        "ground": GROUND,
        "stage": stage,
        "drc": {
            "errors": {t: n for (s, t), n in sorted(by_type.items()) if s == "error"},
            "warnings": {t: n for (s, t), n in sorted(by_type.items()) if s == "warning"},
            "error_total": sum(n for (s, _), n in by_type.items() if s == "error"),
            "unconnected_total": len(report.get("unconnected_items", [])),
            "unconnected_by_net": dict(sorted(unconnected_nets.items())),
        },
        "freerouting_log_tail": log_tail,
        "manufacturing_release": False,
    }


def generate() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    board = WORK / f"{STEM}.kicad_pcb"
    project = WORK / f"{STEM}.kicad_pro"
    native_board = NATIVE_DIR / f"{BOARD}.kicad_pcb"
    shutil.copy2(native_board, board)
    project.write_text(json.dumps(project_with_netclasses(NATIVE_DIR / f"{BOARD}.kicad_pro"), indent=2) + "\n",
                       encoding="utf-8")
    native_dru = NATIVE_DIR / f"{BOARD}.kicad_dru"
    dru_text = native_dru.read_text(encoding="utf-8") if native_dru.is_file() else "(version 1)\n"
    (WORK / f"{STEM}.kicad_dru").write_text(dru_text + CANDIDATE_DRU_APPEND, encoding="utf-8")
    rel = lambda path: str(path.relative_to(ROOT))  # noqa: E731
    dsn, ses = WORK / f"{STEM}.dsn", WORK / f"{STEM}.ses"
    exported = docker("/usr/bin/python3", "tools/kicad_autoroute_stage_rev_a.py", "export", rel(board), rel(dsn),
                      json.dumps({"planes": PLANES, "hole_keepouts": HOLE_KEEPOUTS,
                                  "preroute": PREROUTE, "tie_strips": TIE_STRIPS}))
    binary = freerouting()
    env = dict(os.environ, JAVA_TOOL_OPTIONS="-Xmx3g")
    routed = subprocess.run(
        [str(binary), "--gui.enabled=false", "--usage_and_diagnostic_data.disable_analytics=true",
         "-de", str(dsn), "-do", str(ses), "-mp", str(PASSES)],
        capture_output=True, text=True, env=env, timeout=3000,
    )
    log_tail = "\n".join((routed.stdout + routed.stderr).splitlines()[-40:])
    assert ses.is_file(), "Freerouting produced no session:\n" + log_tail
    candidate = WORK / f"{STEM}.routed.kicad_pcb"
    tracks = WORK / "tracks.json"
    imported = docker("/usr/bin/python3", "tools/kicad_autoroute_stage_rev_a.py", "import", rel(board), rel(ses),
                      rel(candidate), rel(tracks))
    shutil.move(candidate, board)
    gapfill = gap_fill(board, rel)
    segments = json.loads(tracks.read_text(encoding="utf-8"))
    for kind, layer, net, width, points in gapfill["routed"]:
        if kind == "track":
            segments += [{"net": net, "layer": layer, "start": list(a), "end": list(b), "width": width}
                         for a, b in zip(points, points[1:])]
    spec = WORK / "pours.json"
    spec.write_text(json.dumps(pour_spec(segments)), encoding="utf-8")
    poured = docker("/usr/bin/python3", "tools/kicad_autoroute_stage_rev_a.py", "pours", rel(board), rel(spec))
    drc = WORK / "drc.json"
    docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", rel(drc), rel(board))
    stage = {"export": json.loads(exported.strip().splitlines()[-1]), "import": json.loads(imported.strip().splitlines()[-1]),
             "pours": json.loads(poured.strip().splitlines()[-1]),
             "gapfill": {"routed_items": len(gapfill["routed"]), "pairs": gapfill["pairs"],
                         "failed": gapfill["failed"]}}
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    for source in (board, project, drc, WORK / f"{STEM}.kicad_dru"):
        shutil.copy2(source, OUT_DIR / source.name)
    summary = summarize(OUT_DIR / "drc.json", OUT_DIR / board.name, sha256(native_board), log_tail, stage)
    (OUT_DIR / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary["drc"], ensure_ascii=False))


def generate_reporting_failures() -> None:
    """Runner logs are not visible to the reviewer: a failure is written to
    OUT_DIR/FAILURE.json (traceback and process output) and committed instead."""
    import traceback

    try:
        generate()
    except Exception as error:  # noqa: BLE001
        detail = {"error": repr(error), "traceback": traceback.format_exc()}
        if isinstance(error, subprocess.CalledProcessError):
            detail["cmd"] = error.cmd
            detail["stdout_tail"] = (error.stdout or "")[-4000:]
            detail["stderr_tail"] = (error.stderr or "")[-4000:]
        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
        OUT_DIR.mkdir(parents=True)
        (OUT_DIR / "FAILURE.json").write_text(json.dumps(detail, indent=2, default=str) + "\n", encoding="utf-8")
        print("autoroute failed; FAILURE.json written")


def check() -> None:
    if (OUT_DIR / "FAILURE.json").is_file():
        print("PCB-PWR autoroute candidate 011: FAILURE report present")
        return
    summary = json.loads((OUT_DIR / "SUMMARY.json").read_text(encoding="utf-8"))
    candidate = OUT_DIR / f"{STEM}.kicad_pcb"
    assert candidate.is_file() and sha256(candidate) == summary["candidate_sha256"], "candidate/summary mismatch"
    assert (OUT_DIR / "drc.json").is_file(), "DRC report missing"
    print(f"PCB-PWR autoroute candidate 011: PRESENT {summary['candidate_sha256']} "
          f"errors={summary['drc']['error_total']} unconnected={summary['drc']['unconnected_total']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate_reporting_failures()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

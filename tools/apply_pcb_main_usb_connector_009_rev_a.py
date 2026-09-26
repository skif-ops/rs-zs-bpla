#!/usr/bin/env python3
"""PCB-MAIN USB connector escape candidate 009; native DRC, no application.

Reroute the P2-generated CC1 crossing on B.Cu, join the duplicated USB-C
contacts with a 0.25/0.15 mm via-in-pad jumper for D+ and a short F.Cu loop
for D-, and connect the matched 90-ohm pair to U25. The small filled/capped
vias require the selected 6-layer manufacturer's process and SI/DFM review.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as gate  # noqa: E402
import pcb_main_ground_domain_002_rev_a as geo  # noqa: E402

BASE = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-GNSS-008/PCB-MAIN_P2_GNSS_008_CANDIDATE_REV_A.kicad_pcb"
BASE_DRC = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-GNSS-008/drc_candidate.json"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-USB-009"
CANDIDATE = OUT / "PCB-MAIN_P2_USB_009_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA = "63de90493a7e8ab5f82ced9c171dc258b6209d2aed68e63e00ff6ac3d54360a1"
NAMESPACE = uuid.UUID("4412c3bb-498c-5ca7-9d93-0d8bc22ee470")
REMOVE_CC1 = {
    "bcd8fbe2-3eca-55c0-a280-e45d6e82d18c",
    "cf835828-a101-58fc-a103-dceb75003e2e",
    "49954fac-1e01-54e0-b10d-3e21144252ce",
    "2549030c-3719-5d96-97e0-3f8fa614ff63",
    "3fed9fc5-ad66-5fc5-b4dd-f8575def18ef",
}

# 0.1537 mm / 0.2032 mm is the accepted L1/L2 USB pair geometry. The main
# connector-to-U25 paths are symmetric (1.5669 mm). The duplicate contacts
# form short connector-side branches; skew/return-via checks remain SI gates.
ROUTES = (
    ("USB_DM_CONN", "F.Cu", .1537, ((41.75, 7.355), (41.75, 6.4),
                                      (42.75, 6.4), (42.75, 7.355))),
    ("USB_DP_CONN", "B.Cu", .1537, ((41.25, 7.355), (42.25, 7.355))),
    ("USB_DM_CONN", "F.Cu", .1537, ((41.75, 7.355), (41.75, 8.05),
                                      (41.817, 8.117), (41.817, 8.3),
                                      (41.65, 8.467), (41.65, 8.825))),
    ("USB_DP_CONN", "F.Cu", .1537, ((42.25, 7.355), (42.25, 8.05),
                                      (42.183, 8.117), (42.183, 8.3),
                                      (42.35, 8.467), (42.35, 8.825))),
    ("USB_CC1", "B.Cu", .15, ((43.25, 7.355), (40.813, 8.617))),
)
VIAS = (("USB_DP_CONN", 41.25, 7.355), ("USB_DP_CONN", 42.25, 7.355),
        ("USB_CC1", 43.25, 7.355), ("USB_CC1", 40.813, 8.617))
VIA_SIZE, VIA_DRILL = .25, .15


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_geometry() -> None:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    layers = geo.LAYERS
    obstacles, owners = ({l: [] for l in layers} for _ in range(2))
    endpoints = set()
    for fp in board.footprints:
        for pad in fp.pads:
            g = geo.pad_geometry(fp, pad)
            n = pad.net.name if pad.net else None
            for l in geo.pad_layers(pad):
                obstacles[l].append(g)
                owners[l].append(n)
                endpoints.add((n, l, round(g.centroid.x, 4), round(g.centroid.y, 4)))
    for n, kind, layer, g, raw in geo.items(board):
        if str(raw.tstamp) in REMOVE_CC1:
            assert n == "USB_CC1" and kind == "track"
            continue
        for l in (layers if kind == "via" else (layer,)):
            obstacles[l].append(g.buffer(raw.size / 2 if kind == "via" else raw.width / 2, 8))
            owners[l].append(n)
    indexes = {l: STRtree(obstacles[l]) for l in layers}

    def clear(n: str, l: str, shape) -> None:
        collisions = [(owners[l][int(i)], int(i)) for i in indexes[l].query(shape)
                      if owners[l][int(i)] != n and obstacles[l][int(i)].intersects(shape)]
        assert not collisions, (n, l, collisions[:8])

    for n, l, width, points in ROUTES:
        line = LineString(points)
        assert line.length < 4, (n, line.length)
        for x, y in (points[0], points[-1]):
            assert ((n, l, round(x, 4), round(y, 4)) in endpoints or
                    (n, x, y) in VIAS), (n, l, x, y)
        ref = geo.zone_outline(board, "GND_DIGITAL", "In1.Cu" if l == "F.Cu" else "In4.Cu")
        assert line.difference(ref).length < 1e-6, (n, l, "reference gap")
        clear(n, l, line.buffer(width / 2 + .20, 8))
    for n, x, y in VIAS:
        assert (n, "F.Cu", x, y) in endpoints or (n, x, y) == ("USB_CC1", 40.813, 8.617)
        for l in layers:
            clear(n, l, Point(x, y).buffer(VIA_SIZE / 2 + .20, 8))
    # Explicit pair separation at the tightest section, using full widths.
    dp = LineString(ROUTES[3][3])
    dm = LineString(ROUTES[2][3])
    assert dp.distance(dm) - .1537 >= .2032, "90-ohm pair gap"
    assert abs(dp.length - dm.length) < 1e-6, "connector-to-U25 skew"


def build() -> str:
    assert sha(BASE) == BASE_SHA
    check_geometry()
    source = BASE.read_text(encoding="utf-8")
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    lines = source.splitlines()
    kept = [line for line in lines if not (line.startswith("  (segment ") and
             any(f"(tstamp {t})" in line for t in REMOVE_CC1))]
    assert len(lines) - len(kept) == len(REMOVE_CC1)
    segments, vias = [], []
    for k, (n, l, width, points) in enumerate(ROUTES):
        for j, (a, b) in enumerate(zip(points, points[1:])):
            segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                            f'(width {width:g}) (layer "{l}") (net {nets[n]}) '
                            f'(tstamp {uuid.uuid5(NAMESPACE, f"route|{k}|{j}")}))')
    for k, (n, x, y) in enumerate(VIAS):
        vias.append(f'  (via (at {x:g} {y:g}) (size {VIA_SIZE:g}) (drill {VIA_DRILL:g}) '
                    f'(layers "F.Cu" "B.Cu") (net {nets[n]}) '
                    f'(tstamp {uuid.uuid5(NAMESPACE, f"via|{k}")}))')
    i = max(i for i, line in enumerate(kept) if line.startswith("  (segment ")) + 1
    kept = kept[:i] + segments + kept[i:]
    i = max(i for i, line in enumerate(kept) if line.startswith("  (via ")) + 1
    kept = kept[:i] + vias + kept[i:]
    return "\n".join(kept) + "\n"


def run_drc() -> dict:
    work = ROOT / "hardware/kicad/native/_p2_usb_009"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(ROOT / "hardware/kicad/native/PCB-MAIN", work)
    try:
        rel = work.relative_to(ROOT)
        shutil.copyfile(BASE, work / "base.kicad_pcb")
        shutil.copyfile(CANDIDATE, work / "candidate.kicad_pcb")
        # This is a candidate-only manufacturing-process overlay. The native
        # project's general 0.50/0.30 mm via rule is never changed. JLCPCB's
        # public 6-layer via-in-pad capability is 0.25/0.15 mm; the nominal
        # annular width is 0.05 mm. Compare both boards under this exact rule.
        project = json.loads((work / "PCB-MAIN.kicad_pro").read_text(encoding="utf-8"))
        rules = project.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
        rules.update({"min_via_diameter": .25, "min_through_hole_diameter": .15,
                      "min_via_annular_width": .05})
        project_text = json.dumps(project, indent=2, sort_keys=True) + "\n"
        for name in ("base", "candidate"):
            (work / f"{name}.kicad_pro").write_text(project_text, encoding="utf-8")
        (OUT / "PCB-MAIN_P2_USB_009_CANDIDATE_REV_A.kicad_pro").write_text(project_text, encoding="utf-8")
        stage = "tools/pcb_main_ground_domain_002_stage_rev_a.py"
        for name in ("base", "candidate"):
            for command in (("/usr/bin/python3", stage, "fill", f"{rel}/{name}.kicad_pcb", f"{rel}/{name}.kicad_pcb"),
                            ("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o",
                             f"{rel}/drc_{name}.json", f"{rel}/{name}.kicad_pcb")):
                result = gate.docker(*command)
                assert result.returncode == 0, (command, result.stdout[-1000:], result.stderr[-1000:])
        gate.docker("chmod", "-R", "a+rwX", str(rel))
        report = json.loads((work / "drc_candidate.json").read_text(encoding="utf-8"))
        baseline = json.loads((work / "drc_base.json").read_text(encoding="utf-8"))
        shutil.copyfile(work / "drc_candidate.json", OUT / "drc_candidate.json")
        shutil.copyfile(work / "drc_base.json", OUT / "drc_base_candidate_rules.json")
        (bfp, bunc), (cfp, cunc) = gate.drc_fingerprints(baseline), gate.drc_fingerprints(report)
        novel = [(key, count - bfp.get(key, 0)) for key, count in cfp.items() if count > bfp.get(key, 0)]
        by_type = Counter()
        for key, count in novel:
            by_type[f"{key[0]}:{key[1]}"] += count
        return {"base_unconnected": bunc, "candidate_unconnected": cunc,
                "new_by_type": dict(by_type),
                "new_errors": sum(count for key, count in novel if key[0] == "error")}
    finally:
        gate.docker("rm", "-rf", str(work.relative_to(ROOT)))
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    if "--check" in sys.argv:
        record = json.loads((OUT / "SUMMARY.json").read_text(encoding="utf-8"))
        assert record["candidate_sha256"] == sha(CANDIDATE)
        assert CANDIDATE.read_text(encoding="utf-8") == build()
        assert record["drc"]["new_errors"] == 0
        assert record["drc"]["candidate_unconnected"] < record["drc"]["base_unconnected"]
        print("PCB-MAIN USB connector 009: PASS", record["drc"])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build(), encoding="utf-8")
    drc = run_drc()
    summary = {"schema": "dioneya-pcb-main-usb-connector-009-v1", "base_sha256": BASE_SHA,
               "candidate_sha256": sha(CANDIDATE), "routes": len(ROUTES), "vias": len(VIAS),
               "ripped_cc1_tracks": len(REMOVE_CC1), "drc": drc,
               "candidate_only_rules": {"min_via_diameter_mm": .25, "min_drill_mm": .15,
                                        "min_annular_width_mm": .05},
               "via_in_pad_filled_capped_process_review": "OPEN",
               "usb_90ohm_si_return_review": "OPEN",
               "applied_to_authoritative_board": False, "manufacturing_release": False}
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    assert drc["new_errors"] == 0 and drc["candidate_unconnected"] < drc["base_unconnected"], drc
    print(summary)


if __name__ == "__main__":
    main()

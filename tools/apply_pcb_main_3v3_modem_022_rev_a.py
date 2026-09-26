#!/usr/bin/env python3
"""Join two 3V3 pullup islands over the In1.Cu GND_MODEM region."""

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

BASE = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-UART-IN3-021/PCB-MAIN_P2_UART_IN3_021_CANDIDATE_REV_A.kicad_pcb"
BASE_DRC = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-UART-IN3-021/drc_candidate.json"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-3V3-MODEM-022"
CANDIDATE = OUT / "PCB-MAIN_P2_3V3_MODEM_022_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA = "5b6290ccbeac173310ef66d600282e702da821538107385cda6325096e157e5c"
NAMESPACE = uuid.UUID("890b082f-8797-40e7-b1b7-56db72388db7")

# Net, width (mm), pad centre, bend and U1 pad centre (mm).
ROUTES = (
    ("3V3_DIGITAL", .25, ((16.925,35.5),(16.925,34.25))),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copper_clearance_check() -> None:
    from shapely.geometry import LineString
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    modem_reference = geo.zone_outline(board, "GND_MODEM", "In1.Cu")
    obstacles, owners = [], []
    endpoints = set()
    for fp in board.footprints:
        for pad in fp.pads:
            if "F.Cu" not in geo.pad_layers(pad):
                continue
            geom = geo.pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            obstacles.append(geom)
            owners.append(net)
            if net:
                endpoints.add((net, round(geom.centroid.x, 4), round(geom.centroid.y, 4)))
    for net, kind, layer, geom, raw in geo.items(board):
        if kind == "via" or layer == "F.Cu":
            obstacles.append(geom.buffer(raw.size / 2 if kind == "via" else raw.width / 2, 8))
            owners.append(net)
    index = STRtree(obstacles)
    for net, width, points in ROUTES:
        for x, y in (points[0], points[-1]):
            assert (net, round(x, 4), round(y, 4)) in endpoints, (net, x, y)
        path = LineString(points)
        assert path.length > .1
        assert path.difference(modem_reference).length < 1e-6, (net, points, "L2 reference gap")
        clearance = path.buffer(width / 2 + .2, 8)
        conflicts = [(owners[int(i)], int(i)) for i in index.query(clearance)
                     if owners[int(i)] != net and obstacles[int(i)].intersects(clearance)]
        assert not conflicts, (net, points, conflicts[:8])


def build() -> str:
    assert sha(BASE) == BASE_SHA, "P2 input SHA-256 changed"
    copper_clearance_check()
    source = BASE.read_text(encoding="utf-8")
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments = []
    for net, width, points in ROUTES:
        for j,(a,b) in enumerate(zip(points,points[1:])):
            key = f"P2-3V3-MODEM-022|{net}|{width}|{j}|{a}|{b}"
            segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                            f'(width {width:g}) (layer "F.Cu") (net {nets[net]}) '
                            f'(tstamp {uuid.uuid5(NAMESPACE, key)}))')
    lines = source.splitlines()
    i = max(i for i, line in enumerate(lines) if line.startswith("  (segment ")) + 1
    return "\n".join(lines[:i] + segments + lines[i:]) + "\n"


def run_drc() -> dict:
    work = ROOT / "hardware/kicad/native/_p2_3v3_modem_022"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(ROOT / "hardware/kicad/native/PCB-MAIN", work)
    try:
        rel = work.relative_to(ROOT)
        shutil.copyfile(CANDIDATE, work / "candidate.kicad_pcb")
        project = json.loads((work / "PCB-MAIN.kicad_pro").read_text(encoding="utf-8"))
        rules = project.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
        rules.update({"min_via_diameter": .25, "min_through_hole_diameter": .15,
                      "min_via_annular_width": .05})
        overlay = json.dumps(project, indent=2, sort_keys=True) + "\n"
        (work / "candidate.kicad_pro").write_text(overlay, encoding="utf-8")
        (OUT / "PCB-MAIN_P2_3V3_MODEM_022_CANDIDATE_REV_A.kicad_pro").write_text(overlay, encoding="utf-8")
        stage = "tools/pcb_main_ground_domain_002_stage_rev_a.py"
        commands = (("/usr/bin/python3", stage, "fill", f"{rel}/candidate.kicad_pcb", f"{rel}/candidate.kicad_pcb"),
                    ("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o",
                     f"{rel}/drc_candidate.json", f"{rel}/candidate.kicad_pcb"))
        for command in commands:
            result = gate.docker(*command)
            assert result.returncode == 0, (command, result.stdout[-1000:], result.stderr[-1000:])
        gate.docker("chmod", "-R", "a+rwX", str(rel))
        report = json.loads((work / "drc_candidate.json").read_text(encoding="utf-8"))
        shutil.copyfile(work / "drc_candidate.json", OUT / "drc_candidate.json")
        before = json.loads(BASE_DRC.read_text(encoding="utf-8"))
        (bfp, bunc), (cfp, cunc) = gate.drc_fingerprints(before), gate.drc_fingerprints(report)
        novel = sorted((key, count - bfp.get(key, 0)) for key, count in cfp.items() if count > bfp.get(key, 0))
        by_type=Counter()
        for key,count in novel:by_type[f"{key[0]}:{key[1]}"]+=count
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
        print("PCB-MAIN 3V3 modem zone 022: PASS", record["drc"])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build(), encoding="utf-8")
    drc = run_drc()
    summary = {"schema": "dioneya-pcb-main-3v3-modem-022-v1", "base_sha256": BASE_SHA,
               "candidate_sha256": sha(CANDIDATE), "track_segments": 1, "width_mm": .25,
               "length_mm": 1.25, "drc": drc, "candidate_only_usb_u1_via_rules": True,
               "power_return_review_b": "OPEN: R28/R33 3V3 over GND_MODEM",
               "applied_to_authoritative_board": False, "manufacturing_release": False}
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    assert drc["new_errors"] == 0, drc
    assert drc["candidate_unconnected"] < drc["base_unconnected"], drc
    print(summary)


if __name__ == "__main__":
    main()

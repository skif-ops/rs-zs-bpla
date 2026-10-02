#!/usr/bin/env python3
"""Join I2C2_SCL_BUS and GNSS_ANT_GATE F.Cu islands over the digital reference."""

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

BASE = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-POWER-016/PCB-MAIN_P2_POWER_016_CANDIDATE_REV_A.kicad_pcb"
BASE_DRC = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-POWER-016/drc_candidate.json"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-CONTROL-017"
CANDIDATE = OUT / "PCB-MAIN_P2_CONTROL_017_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA = "9574bdcaa0b030d74059673ac887cefa7827a68723d77907c70acac6717f09d4"
NAMESPACE = uuid.UUID("306a0886-91ce-4792-9e22-7c29176a126e")

# Net, width (mm), pad centre, legal bends, pad or existing track endpoint.
ROUTES = (
    ("I2C2_SCL_BUS", .2, ((65.2375,29.75),(65.175,29.0),(64.925,28.75),(64.575,28.7),
                           (62.925,29.5),(62.875,29.6),(62.875,30.4),(63.725,31.1),(63.825,31.5))),
    ("GNSS_ANT_GATE", .2, ((49.0,51.175),(49.0,50.6))),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copper_clearance_check() -> None:
    from shapely.geometry import LineString
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    digital_reference = geo.zone_outline(board, "GND_DIGITAL", "In1.Cu")
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
        if kind == "track" and layer == "F.Cu":
            endpoints.add((net, round(raw.start.X,4),round(raw.start.Y,4)))
            endpoints.add((net, round(raw.end.X,4),round(raw.end.Y,4)))
    index = STRtree(obstacles)
    for net, width, points in ROUTES:
        for x, y in (points[0], points[-1]):
            assert (net, round(x, 4), round(y, 4)) in endpoints, (net, x, y)
        path = LineString(points)
        assert path.length > .1
        assert path.difference(digital_reference).length < 1e-6, (net, points, "L2 reference gap")
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
            key = f"P2-CONTROL-017|{net}|{width}|{j}|{a}|{b}"
            segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                            f'(width {width:g}) (layer "F.Cu") (net {nets[net]}) '
                            f'(tstamp {uuid.uuid5(NAMESPACE, key)}))')
    lines = source.splitlines()
    i = max(i for i, line in enumerate(lines) if line.startswith("  (segment ")) + 1
    return "\n".join(lines[:i] + segments + lines[i:]) + "\n"


def run_drc() -> dict:
    work = ROOT / "hardware/kicad/native/_p2_control_017"
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
        (OUT / "PCB-MAIN_P2_CONTROL_017_CANDIDATE_REV_A.kicad_pro").write_text(overlay, encoding="utf-8")
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
        print("PCB-MAIN control links 017: PASS", record["drc"])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build(), encoding="utf-8")
    drc = run_drc()
    from shapely.geometry import LineString
    summary = {"schema": "dioneya-pcb-main-control-links-017-v1", "base_sha256": BASE_SHA,
               "candidate_sha256": sha(CANDIDATE), "routes": len(ROUTES),
               "track_segments": sum(len(r[2])-1 for r in ROUTES), "width_mm": [r[1] for r in ROUTES],
               "total_length_mm": round(sum(LineString(r[2]).length for r in ROUTES), 3),
               "drc": drc, "candidate_only_usb_u1_via_rules": True,
               "applied_to_authoritative_board": False, "manufacturing_release": False}
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    assert drc["new_errors"] == 0, drc
    assert drc["candidate_unconnected"] < drc["base_unconnected"], drc
    print(summary)


if __name__ == "__main__":
    main()

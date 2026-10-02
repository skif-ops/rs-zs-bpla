#!/usr/bin/env python3
"""Build a bounded PCB-MAIN local-routing candidate on top of experimental P2.

The eight short F.Cu connections are checked against all other-net pads and
tracks with 0.20 mm copper clearance, then checked with native KiCad 9 DRC.
Neither the authoritative board nor the P2 input is changed.
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

BASE = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2/PCB-MAIN_FANOUT_P2_CANDIDATE_REV_A.kicad_pcb"
BASE_DRC = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2/drc_candidate.json"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-LOCAL-007"
CANDIDATE = OUT / "PCB-MAIN_P2_LOCAL_007_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA = "6da31a8cdb8522a2d807fd940f8e76e6bb6638647d7b9dd45a287f5789a577c6"
NAMESPACE = uuid.UUID("dad5d0ca-b345-50b5-bb0d-f3ddc2792d51")

# Net, width (mm), first and last pad centres (mm). Deliberately no USB,
# switch node, RF, cross-domain return or modem burst-current route here.
ROUTES = (
    ("3V3_DIGITAL", .25, (44.25, 34.0), (44.25, 33.5)),
    ("1V8_MIC", .25, (56.85, 42.325), (56.85, 41.675)),
    ("3V3_DIGITAL", .25, (26.9, 29.175), (26.9, 29.825)),
    ("1V8_MIC", .25, (52.76, 45.5), (52.425, 44.25)),
    ("1V8_MIC", .25, (56.85, 41.675), (56.425, 40.25)),
    ("3V3_DIGITAL", .25, (41.925, 28.5), (41.55, 30.0)),
    ("1V8_MIC", .25, (49.9, 44.05), (49.675, 42.5)),
    ("1V8_MIC", .25, (49.9, 44.05), (52.425, 44.25)),
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
    index = STRtree(obstacles)
    for net, width, a, b in ROUTES:
        for x, y in (a, b):
            assert (net, round(x, 4), round(y, 4)) in endpoints, (net, x, y)
        path = LineString((a, b))
        assert path.length > .1
        assert path.difference(digital_reference).length < 1e-6, (net, a, b, "L2 reference gap")
        clearance = path.buffer(width / 2 + .2, 8)
        conflicts = [(owners[int(i)], int(i)) for i in index.query(clearance)
                     if owners[int(i)] != net and obstacles[int(i)].intersects(clearance)]
        assert not conflicts, (net, a, b, conflicts[:8])


def build() -> str:
    assert sha(BASE) == BASE_SHA, "P2 input SHA-256 changed"
    copper_clearance_check()
    source = BASE.read_text(encoding="utf-8")
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments = []
    for net, width, a, b in ROUTES:
        key = f"P2-LOCAL-007|{net}|{width}|{a}|{b}"
        segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                        f'(width {width:g}) (layer "F.Cu") (net {nets[net]}) '
                        f'(tstamp {uuid.uuid5(NAMESPACE, key)}))')
    lines = source.splitlines()
    i = max(i for i, line in enumerate(lines) if line.startswith("  (segment ")) + 1
    return "\n".join(lines[:i] + segments + lines[i:]) + "\n"


def run_drc() -> dict:
    work = ROOT / "hardware/kicad/native/_p2_local_007"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(ROOT / "hardware/kicad/native/PCB-MAIN", work)
    try:
        rel = work.relative_to(ROOT)
        shutil.copyfile(CANDIDATE, work / "candidate.kicad_pcb")
        shutil.copyfile(work / "PCB-MAIN.kicad_pro", work / "candidate.kicad_pro")
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
        return {"base_unconnected": bunc, "candidate_unconnected": cunc,
                "new_by_type": dict(Counter(f"{key[0]}:{key[1]}" for key, _ in novel)),
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
        print("PCB-MAIN P2 local 007: PASS", record["drc"])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build(), encoding="utf-8")
    drc = run_drc()
    summary = {"schema": "dioneya-pcb-main-p2-local-007-v1", "base_sha256": BASE_SHA,
               "candidate_sha256": sha(CANDIDATE), "routes": len(ROUTES), "drc": drc,
               "applied_to_authoritative_board": False, "manufacturing_release": False}
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    assert drc["new_errors"] == 0, drc
    assert drc["candidate_unconnected"] < drc["base_unconnected"], drc
    print(summary)


if __name__ == "__main__":
    main()

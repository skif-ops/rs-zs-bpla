#!/usr/bin/env python3
"""Connect the GNSS antenna-short sense pin, R62 and C63 on F.Cu.

The two branches use an unobstructed GND_DIGITAL-referenced corridor. Native
KiCad 9 DRC checks the resulting candidate. No authoritative PCB is changed.
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

BASE = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-LOCAL-007/PCB-MAIN_P2_LOCAL_007_CANDIDATE_REV_A.kicad_pcb"
BASE_DRC = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-LOCAL-007/drc_candidate.json"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-GNSS-008"
CANDIDATE = OUT / "PCB-MAIN_P2_GNSS_008_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA = "d45b5b1de5b8d29b78b90e67949db0c7193629f7e2af608e24883f5ac3906743"
NAMESPACE = uuid.UUID("ecb50661-fcf0-5cca-9f38-24228c11dbb8")

# Net, width (mm), path through pad centres (mm). GNSS_ANT_SHORT_N is the
# MAX-M10S antenna-short status sense signal, not the RF signal path.
ROUTES = (
    ("GNSS_ANT_SHORT_N", .2, ((54.4, 51.25), (53.4, 50.05), (51.6, 50.15),
                               (50.5, 52.25), (50.2, 53.25))),
    ("GNSS_ANT_SHORT_N", .2, ((50.2, 53.25), (49.125, 57.25),
                               (47.025, 57.45), (46.925, 58.0))),
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
        for i, (a, b) in enumerate(zip(points, points[1:])):
            key = f"P2-GNSS-008|{net}|{width}|{i}|{a}|{b}"
            segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                            f'(width {width:g}) (layer "F.Cu") (net {nets[net]}) '
                            f'(tstamp {uuid.uuid5(NAMESPACE, key)}))')
    lines = source.splitlines()
    i = max(i for i, line in enumerate(lines) if line.startswith("  (segment ")) + 1
    return "\n".join(lines[:i] + segments + lines[i:]) + "\n"


def run_drc() -> dict:
    work = ROOT / "hardware/kicad/native/_p2_gnss_008"
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
        print("PCB-MAIN P2 GNSS 008: PASS", record["drc"])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build(), encoding="utf-8")
    drc = run_drc()
    summary = {"schema": "dioneya-pcb-main-p2-gnss-008-v1", "base_sha256": BASE_SHA,
               "candidate_sha256": sha(CANDIDATE), "routes": len(ROUTES), "drc": drc,
               "applied_to_authoritative_board": False, "manufacturing_release": False}
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    assert drc["new_errors"] == 0, drc
    assert drc["candidate_unconnected"] < drc["base_unconnected"], drc
    print(summary)


if __name__ == "__main__":
    main()

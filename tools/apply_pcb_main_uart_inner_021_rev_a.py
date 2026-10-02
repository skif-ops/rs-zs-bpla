#!/usr/bin/env python3
"""Experimental TEST_UART_RX_U1 route on In3.Cu with two standard through vias."""

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

BASE = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-SIM2-VDD-020/PCB-MAIN_P2_SIM2_VDD_020_CANDIDATE_REV_A.kicad_pcb"
BASE_DRC = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-SIM2-VDD-020/drc_candidate.json"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-UART-IN3-021"
CANDIDATE = OUT / "PCB-MAIN_P2_UART_IN3_021_CANDIDATE_REV_A.kicad_pcb"
BASE_SHA = "7d45ad459ac597d2b993e58bc3be758f77f29d72f4b14c024e6c3b4316b1ae6e"
NAMESPACE = uuid.UUID("306a0886-91ce-4792-9e22-7c29176a126e")

NET = "TEST_UART_RX_U1"
WIDTH = .15
VIA_A, VIA_B = (38.375, 33.8), (45.45, 31.0)
FRONT_STUBS = (((38.175, 33.0), VIA_A), (VIA_B, (44.25, 31.0)))
INNER_PATH = (VIA_A, (40.975, 36.9), (41.675, 36.8), (42.875, 35.2),
              (43.475, 35.1), VIA_B)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copper_clearance_check() -> None:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    digital_reference = geo.zone_outline(board, "GND_DIGITAL", "In1.Cu")
    inner_reference = geo.zone_outline(board, "GND_MIC", "In2.Cu")
    obstacles = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    endpoints = set()
    for fp in board.footprints:
        for pad in fp.pads:
            geom = geo.pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            for layer in geo.pad_layers(pad):
                obstacles[layer].append(geom)
                owners[layer].append(net)
            if net and "F.Cu" in geo.pad_layers(pad):
                endpoints.add((net, round(geom.centroid.x, 4), round(geom.centroid.y, 4)))
            if pad.drill is not None and getattr(pad.drill, "diameter", 0):
                holes.append((geom.centroid, pad.drill.diameter / 2, net))
    for net, kind, layer, geom, raw in geo.items(board):
        if kind == "via":
            holes.append((geom, raw.drill / 2, net))
        for ly in geo.LAYERS if kind == "via" else (layer,):
            obstacles[ly].append(geom.buffer(raw.size / 2 if kind == "via" else raw.width / 2, 8))
            owners[ly].append(net)
    index = {layer: STRtree(obstacles[layer]) for layer in geo.LAYERS}
    def clear(layer, shape):
        conflicts = [(owners[layer][int(i)], int(i)) for i in index[layer].query(shape)
                     if owners[layer][int(i)] != NET and obstacles[layer][int(i)].intersects(shape)]
        assert not conflicts, (layer, conflicts[:8])
    for endpoint in (FRONT_STUBS[0][0], FRONT_STUBS[-1][-1]):
        assert (NET, *endpoint) in endpoints, endpoint
    for via in (VIA_A, VIA_B):
        assert digital_reference.contains(Point(via)), (via, "outside digital front reference")
        via_copper = Point(via).buffer(.25 + .205, 8)
        for layer in geo.LAYERS:
            clear(layer, via_copper)
        assert all(other_net == NET or Point(via).distance(hole) >= .15 + radius + .25
                   for hole, radius, other_net in holes), (via, "hole clearance")
    for route in FRONT_STUBS:
        path = LineString(route)
        assert path.difference(digital_reference).length < 1e-6, "front reference gap"
        clear("F.Cu", path.buffer(WIDTH / 2 + .2, 8))
    inner = LineString(INNER_PATH)
    assert inner.difference(inner_reference).length < 1e-6, "inner reference gap"
    clear("In3.Cu", inner.buffer(WIDTH / 2 + .2, 8))


def build() -> str:
    assert sha(BASE) == BASE_SHA, "P2 input SHA-256 changed"
    copper_clearance_check()
    source = BASE.read_text(encoding="utf-8")
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments = []
    for layer, points in (("F.Cu", FRONT_STUBS[0]), ("In3.Cu", INNER_PATH),
                          ("F.Cu", FRONT_STUBS[1])):
        for j,(a,b) in enumerate(zip(points,points[1:])):
            key = f"P2-UART-IN3-021|{NET}|{layer}|{WIDTH}|{j}|{a}|{b}"
            segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                            f'(width {WIDTH:g}) (layer "{layer}") (net {nets[NET]}) '
                            f'(tstamp {uuid.uuid5(NAMESPACE, key)}))')
    vias = []
    for j, (x, y) in enumerate((VIA_A, VIA_B)):
        key = f"P2-UART-IN3-021|{NET}|via|{j}|{x}|{y}"
        vias.append(f'  (via (at {x:g} {y:g}) (size 0.5) (drill 0.3) '
                    f'(layers "F.Cu" "B.Cu") (net {nets[NET]}) '
                    f'(tstamp {uuid.uuid5(NAMESPACE, key)}))')
    lines = source.splitlines()
    i = max(i for i, line in enumerate(lines) if line.startswith("  (segment ")) + 1
    return "\n".join(lines[:i] + segments + vias + lines[i:]) + "\n"


def run_drc() -> dict:
    work = ROOT / "hardware/kicad/native/_p2_uart_in3_021"
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
        (OUT / "PCB-MAIN_P2_UART_IN3_021_CANDIDATE_REV_A.kicad_pro").write_text(overlay, encoding="utf-8")
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
        print("PCB-MAIN UART In3 021: PASS", record["drc"])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build(), encoding="utf-8")
    drc = run_drc()
    from shapely.geometry import LineString
    summary = {"schema": "dioneya-pcb-main-uart-in3-021-v1", "base_sha256": BASE_SHA,
               "candidate_sha256": sha(CANDIDATE), "net": NET, "vias": 2,
               "track_segments": len(INNER_PATH) - 1 + len(FRONT_STUBS), "width_mm": WIDTH,
               "inner_length_mm": round(LineString(INNER_PATH).length, 3),
               "drc": drc, "candidate_only_usb_u1_via_rules": True,
               "inner_reference_review_b": "OPEN: digital UART return over In2.Cu GND_MIC",
               "applied_to_authoritative_board": False, "manufacturing_release": False}
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    assert drc["new_errors"] == 0, drc
    assert drc["candidate_unconnected"] < drc["base_unconnected"], drc
    print(summary)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Join the C19 3V3_DIGITAL island to J_PWR.3 on B.Cu."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as gate
import pcb_main_ground_domain_002_rev_a as geo

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SD-CK-U23-052/PCB-MAIN_P2_SD_CK_U23_052_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-C19-3V3-JPWR-053'
CANDIDATE = OUT / 'PCB-MAIN_P2_C19_3V3_JPWR_053_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_C19_3V3_JPWR_053_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '77c3ebb6098947b7bac7c46183c97cdf66566b4a1eb9cdfa88f2f431f94edbfa'
NAMESPACE = uuid.UUID('bb34561a-fd52-4c8a-a47e-240235943e57')
NET = '3V3_DIGITAL'
VIA = (14.4, 27.75)
ROUTE = (VIA, (12.75, 25.55), (8.92, 23.5))
WIDTH = .30


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_board() -> str:
    assert sha(BASE) == BASE_SHA, '052 changed; review C19 power route again'
    return BASE.read_text(encoding='utf-8')


def check_geometry(source: str) -> None:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    with tempfile.TemporaryDirectory() as tmp:
        board_path = Path(tmp) / 'C19.kicad_pcb'
        board_path.write_text(source)
        board, _ = geo.load(board_path)
    obs = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    pads = []
    for fp in board.footprints:
        for pad in fp.pads:
            shape = geo.pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            if geo.reference(fp) in ('C19', 'J_PWR'):
                pads.append((geo.reference(fp), pad.number, net, shape))
            if pad.drill is not None and getattr(pad.drill, 'diameter', 0):
                holes.append((shape.centroid, pad.drill.diameter / 2, net))
            for layer in geo.pad_layers(pad):
                obs[layer].append(shape)
                owners[layer].append(net)
    for net, kind, layer, shape, raw in geo.items(board):
        if kind == 'via':
            holes.append((shape, raw.drill / 2, net))
        for copper in geo.LAYERS if kind == 'via' else (layer,):
            obs[copper].append(shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 8))
            owners[copper].append(net)
    indices = {layer: STRtree(obs[layer]) for layer in geo.LAYERS}

    def clear(net, layer, shape):
        conflicts = [owners[layer][int(i)] for i in indices[layer].query(shape)
                     if owners[layer][int(i)] != net and obs[layer][int(i)].intersects(shape)]
        assert not conflicts, (net, layer, conflicts[:8])

    assert any(ref == 'C19' and number == '1' and net == NET
               and shape.contains(Point(*VIA)) for ref, number, net, shape in pads)
    assert any(ref == 'J_PWR' and number == '3' and net == NET
               and shape.contains(Point(*ROUTE[-1])) for ref, number, net, shape in pads)
    assert LineString(ROUTE).difference(geo.zone_outline(board, 'GND_MODEM', 'In4.Cu')).length < 1e-6
    for a, c in zip(ROUTE, ROUTE[1:]):
        line = LineString([a, c])
        clear(NET, 'B.Cu', line.buffer(WIDTH / 2 + .20, 16))
        assert not [(n, line.distance(q) - r - WIDTH / 2) for q, r, n in holes
                    if n != NET and line.distance(q) - r - WIDTH / 2 < .25 - 1e-6]
    center = Point(*VIA)
    for layer in geo.LAYERS:
        clear(NET, layer, center.buffer(.125 + .20, 16))
    assert not [(n, center.distance(q) - r - .075) for q, r, n in holes
                if n != NET and center.distance(q) - r - .075 < .25 - 1e-6]


def build() -> str:
    source = source_board()
    check_geometry(source)
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {c[0]:g} {c[1]:g}) '
                f'(width {WIDTH:g}) (layer "B.Cu") (net {nets[NET]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"track|{i}")}))'
                for i, (a, c) in enumerate(zip(ROUTE, ROUTE[1:]))]
    via_text = [f'  (via (at {VIA[0]:g} {VIA[1]:g}) (size 0.25) (drill 0.15) '
                f'(layers "F.Cu" "B.Cu") (net {nets[NET]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, "via|0")}))']
    lines = source.splitlines()
    at = max(i for i, line in enumerate(lines) if line.startswith('  (segment ')) + 1
    lines[at:at] = segments
    at = max(i for i, line in enumerate(lines) if line.startswith('  (via ')) + 1
    lines[at:at] = via_text
    return '\n'.join(lines) + '\n'


def run_drc() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_c19_3v3_jpwr_053'
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(ROOT / 'hardware/kicad/native/PCB-MAIN', work)
    try:
        rel = work.relative_to(ROOT)
        shutil.copyfile(CANDIDATE, work / 'candidate.kicad_pcb')
        shutil.copyfile(PROJECT, work / 'candidate.kicad_pro')
        commands = (
            ('/usr/bin/python3', 'tools/pcb_main_ground_domain_002_stage_rev_a.py', 'fill',
             f'{rel}/candidate.kicad_pcb', f'{rel}/candidate.kicad_pcb'),
            ('kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all',
             '-o', f'{rel}/drc_candidate.json', f'{rel}/candidate.kicad_pcb'),
        )
        runner = (lambda *cmd: subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)) \
            if os.getenv('DIONEYA_KICAD_DIRECT') == '1' else gate.docker
        for command in commands:
            result = runner(*command)
            assert result.returncode == 0, (command, result.stdout[-1000:], result.stderr[-1000:])
        if not os.getenv('DIONEYA_KICAD_DIRECT'):
            gate.docker('chmod', '-R', 'a+rwX', str(rel))
        report = json.loads((work / 'drc_candidate.json').read_text())
        shutil.copyfile(work / 'drc_candidate.json', OUT / 'drc_candidate.json')
        before = json.loads(BASE_DRC.read_text())
        (base_fp, base_open), (new_fp, new_open) = gate.drc_fingerprints(before), gate.drc_fingerprints(report)
        novel = sorted((key, count - base_fp.get(key, 0)) for key, count in new_fp.items()
                       if count > base_fp.get(key, 0))
        by_type = Counter()
        for key, count in novel:
            by_type[f'{key[0]}:{key[1]}'] += count
        return {'base_unconnected': base_open, 'candidate_unconnected': new_open,
                'new_by_type': dict(by_type),
                'new_errors': sum(count for key, count in novel if key[0] == 'error')}
    finally:
        if not os.getenv('DIONEYA_KICAD_DIRECT'):
            gate.docker('rm', '-rf', str(work.relative_to(ROOT)))
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    if '--check' in sys.argv:
        record = json.loads((OUT / 'SUMMARY.json').read_text())
        assert CANDIDATE.read_text() == build()
        assert record['candidate_sha256'] == sha(CANDIDATE)
        assert record['drc']['candidate_unconnected'] < record['drc']['base_unconnected']
        assert record['drc']['new_errors'] == 0
        print('PCB-MAIN C19 3V3 J_PWR 053: PASS', record['drc'])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build())
    project = json.loads((ROOT / 'hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pro').read_text())
    rules = project.setdefault('board', {}).setdefault('design_settings', {}).setdefault('rules', {})
    rules.update({'min_via_diameter': .25, 'min_through_hole_diameter': .15,
                  'min_via_annular_width': .05})
    PROJECT.write_text(json.dumps(project, indent=2, sort_keys=True) + '\n')
    drc = run_drc()
    summary = {'schema': 'dioneya-pcb-main-c19-3v3-jpwr-053-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': sha(CANDIDATE), 'route_points': [list(p) for p in ROUTE],
               'track_segments': 2, 'track_width_mm': WIDTH,
               'route_length_mm': round(sum(math.dist(a, c) for a, c in zip(ROUTE, ROUTE[1:])), 4),
               'small_via_size_drill_mm': [.25, .15],
               'power_current_and_return_review_b': 'OPEN', 'via_in_pad_dfm_review': 'OPEN',
               'candidate_only_usb_u1_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == 0 and drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

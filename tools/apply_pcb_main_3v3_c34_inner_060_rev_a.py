#!/usr/bin/env python3
"""Join the C34 3V3_DIGITAL branch to the existing B.Cu island on In3.Cu."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-3V3-C34-BRANCH-059/PCB-MAIN_P2_3V3_C34_BRANCH_059_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-3V3-C34-INNER-060'
CANDIDATE = OUT / 'PCB-MAIN_P2_3V3_C34_INNER_060_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_3V3_C34_INNER_060_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '41f0652a9115add385006cf82531597033e5c82de51a10c842f94f401033c527'
NAMESPACE = uuid.UUID('e2190620-ed54-4084-961e-ac9bdd8a90d5')
NET = '3V3_DIGITAL'
ROUTE = ((26.9, 29.175), (31.4, 26.1), (32.8, 26.0),
         (33.3, 25.6), (33.7, 25.2), (33.8, 24.6),
         (31.7, 21.0), (31.8, 20.6), (32.4, 19.9), (32.675, 18.9))
WIDTH = .30


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_fraction(net: str, layer: str) -> float:
    from shapely.geometry import LineString
    board, _ = geo.load(BASE)
    line = LineString(ROUTE)
    return line.intersection(geo.zone_outline(board, net, layer)).length / line.length


def source_board() -> str:
    assert sha(BASE) == BASE_SHA, '059 changed; review C34 power path again'
    return BASE.read_text(encoding='utf-8')


def check_geometry(source: str) -> None:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    with tempfile.TemporaryDirectory() as tmp:
        board_path = Path(tmp) / 'C34_INNER_3V3.kicad_pcb'
        board_path.write_text(source)
        board, _ = geo.load(board_path)
    obs = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    vias = []
    for fp in board.footprints:
        for pad in fp.pads:
            shape = geo.pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            if pad.drill is not None and getattr(pad.drill, 'diameter', 0):
                holes.append((shape.centroid, pad.drill.diameter / 2, net))
            for layer in geo.pad_layers(pad):
                obs[layer].append(shape)
                owners[layer].append(net)
    for net, kind, layer, shape, raw in geo.items(board):
        if kind == 'via':
            holes.append((shape, raw.drill / 2, net))
            vias.append((net, shape))
        for copper in geo.LAYERS if kind == 'via' else (layer,):
            obs[copper].append(shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 8))
            owners[copper].append(net)
    indices = {layer: STRtree(obs[layer]) for layer in geo.LAYERS}

    def clear(net, layer, shape):
        conflicts = [owners[layer][int(i)] for i in indices[layer].query(shape)
                     if owners[layer][int(i)] != net and obs[layer][int(i)].intersects(shape)]
        assert not conflicts, (net, layer, conflicts[:8])

    assert all(any(net == NET and shape.distance(Point(*point)) < 1e-6
                   for net, shape in vias) for point in (ROUTE[0], ROUTE[-1]))
    reference = LineString(ROUTE).intersection(geo.zone_outline(board, 'GND_DIGITAL', 'In1.Cu')).length
    mic_reference = LineString(ROUTE).intersection(geo.zone_outline(board, 'GND_MIC', 'In2.Cu')).length
    digital_reference = LineString(ROUTE).intersection(geo.zone_outline(board, 'GND_DIGITAL', 'In4.Cu')).length
    assert reference / LineString(ROUTE).length > .99
    assert mic_reference / LineString(ROUTE).length > .99
    assert digital_reference / LineString(ROUTE).length > .99
    for a, c in zip(ROUTE, ROUTE[1:]):
        line = LineString([a, c])
        clear(NET, 'In3.Cu', line.buffer(WIDTH / 2 + .225, 16))
        assert not [(n, line.distance(q) - r - WIDTH / 2) for q, r, n in holes
                    if n != NET and line.distance(q) - r - WIDTH / 2 < .275 - 1e-6]


def build() -> str:
    source = source_board()
    check_geometry(source)
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {c[0]:g} {c[1]:g}) '
                f'(width {WIDTH:g}) (layer "In3.Cu") (net {nets[NET]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"track|{i}")}))'
                for i, (a, c) in enumerate(zip(ROUTE, ROUTE[1:]))]
    lines = source.splitlines()
    at = max(i for i, line in enumerate(lines) if line.startswith('  (segment ')) + 1
    lines[at:at] = segments
    return '\n'.join(lines) + '\n'


def run_drc() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_3v3_c34_inner_060'
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
        print('PCB-MAIN 3V3_DIGITAL C34 inner 060: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-3v3-c34-inner-060-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': sha(CANDIDATE), 'route_points': [list(p) for p in ROUTE],
               'track_segments': len(ROUTE)-1, 'track_width_mm': WIDTH,
               'route_length_mm': round(sum(math.dist(a, c) for a, c in zip(ROUTE, ROUTE[1:])), 4),
               'new_vias': 0,
               'in1_gnd_digital_reference_fraction': round(reference_fraction('GND_DIGITAL', 'In1.Cu'), 4),
               'in2_gnd_mic_reference_fraction': round(reference_fraction('GND_MIC', 'In2.Cu'), 4),
               'in4_gnd_digital_reference_fraction': round(reference_fraction('GND_DIGITAL', 'In4.Cu'), 4),
               'c34_supply_current_and_return_review_b': 'OPEN',
               'candidate_only_usb_u1_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == 0 and drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

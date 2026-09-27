#!/usr/bin/env python3
"""Join the U1.47 3V3_DIGITAL island to its existing F.Cu supply branch on In3.Cu."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-1V8-MIC-JMIC3-JMIC4-057/PCB-MAIN_P2_1V8_MIC_JMIC3_JMIC4_057_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-3V3-U1-47-058'
CANDIDATE = OUT / 'PCB-MAIN_P2_3V3_U1_47_058_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_3V3_U1_47_058_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '1ae3dd8186881bf6f252c3f87ac2a0f0ab8ae469ed2934f37cf626d1cfcd390d'
NAMESPACE = uuid.UUID('8c98d6a2-d291-4b10-9911-32d4cfa57bee')
NET = '3V3_DIGITAL'
VIA_A = (59.35, 36.3)
VIA_B = (56.5, 38.05)
FRONT = ((59.75, 36.0), VIA_A)
INNER = (VIA_A, (58.3, 37.3), (58.0, 37.65), (58.0, 37.95),
         (57.85, 38.15), (57.6, 38.25), (57.0, 38.25), VIA_B)
WIDTH = .25


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_fraction(net: str, layer: str) -> float:
    from shapely.geometry import LineString
    board, _ = geo.load(BASE)
    line = LineString(INNER)
    return line.intersection(geo.zone_outline(board, net, layer)).length / line.length


def source_board() -> str:
    assert sha(BASE) == BASE_SHA, '057 changed; review U1 supply again'
    return BASE.read_text(encoding='utf-8')


def check_geometry(source: str) -> None:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    with tempfile.TemporaryDirectory() as tmp:
        board_path = Path(tmp) / 'U1_47_3V3.kicad_pcb'
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
            if geo.reference(fp) == 'U1' and pad.number == '47':
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

    assert any(ref == 'U1' and number == '47' and net == NET
               and shape.contains(Point(*VIA_B)) for ref, number, net, shape in pads)
    assert any(kind == 'track' and layer == 'F.Cu' and net == NET
               and shape.distance(Point(*FRONT[0])) < 1e-6
               for net, kind, layer, shape, _ in geo.items(board))
    line = LineString(INNER)
    for domain, layer in (('GND_DIGITAL', 'In1.Cu'), ('GND_MIC', 'In2.Cu'),
                          ('GND_DIGITAL', 'In4.Cu')):
        assert line.intersection(geo.zone_outline(board, domain, layer)).length / line.length > .99
    for layer, points in (('F.Cu', FRONT), ('In3.Cu', INNER)):
        for a, c in zip(points, points[1:]):
            line = LineString([a, c])
            clear(NET, layer, line.buffer(WIDTH / 2 + .225, 16))
            assert not [(n, line.distance(q) - r - WIDTH / 2) for q, r, n in holes
                        if n != NET and line.distance(q) - r - WIDTH / 2 < .275 - 1e-6]
    for x, y in (VIA_A, VIA_B):
        center = Point(x, y)
        for layer in geo.LAYERS:
            clear(NET, layer, center.buffer(.125 + .22, 16))
        assert not [(n, center.distance(q) - r - .075) for q, r, n in holes
                    if n != NET and center.distance(q) - r - .075 < .27 - 1e-6]


def build() -> str:
    source = source_board()
    check_geometry(source)
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    routes = [('F.Cu', FRONT)] + [('In3.Cu', (a, c)) for a, c in zip(INNER, INNER[1:])]
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {c[0]:g} {c[1]:g}) '
                f'(width {WIDTH:g}) (layer "{layer}") (net {nets[NET]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"track|{i}")}))'
                for i, (layer, (a, c)) in enumerate(routes)]
    vias = [f'  (via (at {x:g} {y:g}) (size 0.25) (drill 0.15) '
            f'(layers "F.Cu" "B.Cu") (net {nets[NET]}) '
            f'(tstamp {uuid.uuid5(NAMESPACE, f"via|{i}")}))'
            for i, (x, y) in enumerate((VIA_A, VIA_B))]
    lines = source.splitlines()
    at = max(i for i, line in enumerate(lines) if line.startswith('  (segment ')) + 1
    lines[at:at] = segments
    at = max(i for i, line in enumerate(lines) if line.startswith('  (via ')) + 1
    lines[at:at] = vias
    return '\n'.join(lines) + '\n'


def run_drc() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_3v3_u1_47_058'
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
        print('PCB-MAIN 3V3_DIGITAL U1.47 058: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-3v3-u1-47-058-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': sha(CANDIDATE),
               'front_points': [list(p) for p in FRONT], 'inner_points': [list(p) for p in INNER],
               'track_segments': len(INNER), 'track_width_mm': WIDTH,
               'route_length_mm': round(math.dist(*FRONT) +
                                        sum(math.dist(a, c) for a, c in zip(INNER, INNER[1:])), 4),
               'new_vias': 2, 'via_size_drill_mm': [0.25, 0.15],
               'in1_gnd_digital_reference_fraction': round(reference_fraction('GND_DIGITAL', 'In1.Cu'), 4),
               'in2_gnd_mic_reference_fraction': round(reference_fraction('GND_MIC', 'In2.Cu'), 4),
               'in4_gnd_digital_reference_fraction': round(reference_fraction('GND_DIGITAL', 'In4.Cu'), 4),
               'u1_supply_current_and_return_review_b': 'OPEN',
               'candidate_only_usb_u1_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == 0 and drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

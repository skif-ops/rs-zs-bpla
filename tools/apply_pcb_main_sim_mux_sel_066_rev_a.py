#!/usr/bin/env python3
"""Candidate 066: connect SIM_MUX_SEL from U1.97 to the existing U13 branch."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as gate
import pcb_main_ground_domain_002_rev_a as geo

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-FAULT-RETURN-065/PCB-MAIN_P2_FAULT_RETURN_065_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
BASE_MCU = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-VREF-3V3-062/PCB-MAIN_02_MCU_VREF_062.kicad_sch'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SIM-MUX-SEL-066'
CANDIDATE = OUT / 'PCB-MAIN_P2_SIM_MUX_SEL_066_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_SIM_MUX_SEL_066_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '12130d529609fc1c907f3b6a28508f8ad3e8933c1cc0b2ff380904e06dd4d9cb'
NAMESPACE = uuid.UUID('dd5c8821-7549-4520-a175-ec011458692e')
NET = 'SIM_MUX_SEL'
U1_PAD = (47.5, 22.25)
OLD_TRACK = (40.9, 20.825)
VIAS = ((47.5, 21.4), (41.6, 20.7))
WIDTH = .15
VIA_SIZE, VIA_DRILL = .25, .15
BOTTOM_POINTS = (VIAS[0], (46.5, 19.6), (46.2, 19.4), VIAS[1])
ROUTES = (('F.Cu', U1_PAD, VIAS[0]),) + \
         tuple(('B.Cu', a, b) for a, b in zip(BOTTOM_POINTS, BOTTOM_POINTS[1:])) + \
         (('F.Cu', VIAS[1], OLD_TRACK),)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_geometry() -> dict:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    obstacles = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    pads = {}
    own_track = False
    for fp in board.footprints:
        for pad in fp.pads:
            shape = geo.pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            if (geo.reference(fp), pad.number) == ('U1', '97'):
                pads[(geo.reference(fp), pad.number)] = (net, shape, geo.pad_layers(pad))
            if pad.drill is not None and getattr(pad.drill, 'diameter', 0):
                holes.append((shape.centroid, pad.drill.diameter / 2, net))
            for layer in geo.pad_layers(pad):
                obstacles[layer].append(shape)
                owners[layer].append(net)
    for net, kind, layer, shape, raw in geo.items(board):
        if net == NET and kind == 'track' and layer == 'F.Cu' and shape.distance(Point(*OLD_TRACK)) < 1e-6:
            own_track = True
        if kind == 'via':
            holes.append((shape, raw.drill / 2, net))
        for copper in geo.LAYERS if kind == 'via' else (layer,):
            obstacles[copper].append(shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 8))
            owners[copper].append(net)
    indices = {layer: STRtree(obstacles[layer]) for layer in geo.LAYERS}

    def clear(layer, shape):
        conflicts = [owners[layer][int(i)] for i in indices[layer].query(shape)
                     if owners[layer][int(i)] != NET and obstacles[layer][int(i)].intersects(shape)]
        assert not conflicts, (layer, conflicts[:8])

    assert pads[('U1', '97')][0] == NET and 'F.Cu' in pads[('U1', '97')][2]
    assert pads[('U1', '97')][1].centroid.distance(Point(*U1_PAD)) < 1e-5
    assert own_track
    ground_vias = [shape for net, kind, _, shape, _ in geo.items(board)
                   if net == 'GND_DIGITAL' and kind == 'via']
    ground_distances = [min(Point(*p).distance(sh) for sh in ground_vias) for p in VIAS]
    assert max(ground_distances) <= 1.5, ground_distances
    for via in VIAS:
        for layer in geo.LAYERS:
            clear(layer, Point(*via).buffer(VIA_SIZE / 2 + .20, 16))
        for name, reference in (('GND_DIGITAL', 'In1.Cu'), ('GND_MIC', 'In2.Cu'),
                                ('GND_DIGITAL', 'In4.Cu')):
            assert geo.zone_outline(board, name, reference).contains(Point(*via))
    for layer, a, b in ROUTES:
        line = LineString([a, b])
        clear(layer, line.buffer(WIDTH / 2 + .20, 16))
        for name, reference in (('GND_DIGITAL', 'In1.Cu'), ('GND_MIC', 'In2.Cu'),
                                ('GND_DIGITAL', 'In4.Cu')):
            assert line.difference(geo.zone_outline(board, name, reference)).length < 1e-6
        for center, radius, net in holes:
            if net != NET:
                assert line.distance(center) - radius - WIDTH / 2 >= .25 - 1e-6
    for center, radius, net in holes:
        if net != NET:
            for via in VIAS:
                assert Point(*via).distance(center) - radius - VIA_DRILL / 2 >= .25 - 1e-6
    return {'route_length_mm': round(sum(math.dist(a, b) for _, a, b in ROUTES), 4),
            'reference_outline_fraction': 1.0,
            'signal_to_nearest_digital_ground_vias_mm': [round(d, 4) for d in ground_distances]}


def build() -> str:
    assert sha(BASE) == BASE_SHA, '065 changed; screen the SIM_MUX_SEL route again'
    check_geometry()
    source = BASE.read_text(encoding='utf-8')
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    assert NET in nets
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                f'(width {WIDTH:g}) (layer "{layer}") (net {nets[NET]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"segment|{i}")}))'
                for i, (layer, a, b) in enumerate(ROUTES)]
    vias = [(f'  (via (at {point[0]:g} {point[1]:g}) (size {VIA_SIZE:g}) '
             f'(drill {VIA_DRILL:g}) (layers "F.Cu" "B.Cu") (net {nets[NET]}) '
             f'(tstamp {uuid.uuid5(NAMESPACE, f"via|{i}")}))')
            for i, point in enumerate(VIAS)]
    lines = source.splitlines()
    at = max(i for i, value in enumerate(lines) if value.startswith('  (segment ')) + 1
    lines[at:at] = segments
    at = max(i for i, value in enumerate(lines) if value.startswith('  (via ')) + 1
    lines[at:at] = vias
    return '\n'.join(lines) + '\n'


def run_native() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_sim_mux_sel_066'
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(ROOT / 'hardware/kicad/native/PCB-MAIN', work)
    try:
        rel = work.relative_to(ROOT)
        shutil.copyfile(CANDIDATE, work / 'candidate.kicad_pcb')
        shutil.copyfile(PROJECT, work / 'candidate.kicad_pro')
        shutil.copyfile(BASE_MCU, work / 'PCB-MAIN_02_MCU.kicad_sch')
        commands = (
            ('/usr/bin/python3', 'tools/pcb_main_ground_domain_002_stage_rev_a.py', 'fill',
             f'{rel}/candidate.kicad_pcb', f'{rel}/candidate.kicad_pcb'),
            ('kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all',
             '-o', f'{rel}/drc_candidate.json', f'{rel}/candidate.kicad_pcb'),
            ('kicad-cli', 'sch', 'erc', '--format', 'json', '--severity-all',
             '-o', f'{rel}/erc_candidate.json', f'{rel}/PCB-MAIN.kicad_sch'),
        )
        runner = (lambda *cmd: subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)) \
            if os.getenv('DIONEYA_KICAD_DIRECT') == '1' else gate.docker
        for command in commands:
            result = runner(*command)
            assert result.returncode == 0, (command, result.stdout[-1200:], result.stderr[-1200:])
        if not os.getenv('DIONEYA_KICAD_DIRECT'):
            gate.docker('chmod', '-R', 'a+rwX', str(rel))
        report = json.loads((work / 'drc_candidate.json').read_text())
        erc = json.loads((work / 'erc_candidate.json').read_text())
        shutil.copyfile(work / 'drc_candidate.json', OUT / 'drc_candidate.json')
        shutil.copyfile(work / 'erc_candidate.json', OUT / 'erc_candidate.json')
        before = json.loads(BASE_DRC.read_text())
        (old_fp, old_open), (new_fp, new_open) = gate.drc_fingerprints(before), gate.drc_fingerprints(report)
        novel = [(key, count - old_fp.get(key, 0)) for key, count in new_fp.items()
                 if count > old_fp.get(key, 0)]
        by_type = Counter()
        for key, count in novel:
            by_type[f'{key[0]}:{key[1]}'] += count
        assert 'sheets' in erc
        erc_violations = [v for sheet in erc['sheets'] for v in sheet.get('violations', [])]
        return {'base_unconnected': old_open, 'candidate_unconnected': new_open,
                'new_by_type': dict(by_type),
                'new_errors': sum(count for key, count in novel if key[0] == 'error'),
                'erc_errors': sum(v.get('severity') == 'error' for v in erc_violations),
                'erc_violations': len(erc_violations)}
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
        assert record['drc']['new_errors'] == record['drc']['erc_errors'] == record['drc']['erc_violations'] == 0
        print('PCB-MAIN SIM_MUX_SEL 066: PASS', record['drc'])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build())
    project = json.loads((ROOT / 'hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pro').read_text())
    rules = project.setdefault('board', {}).setdefault('design_settings', {}).setdefault('rules', {})
    rules.update({'min_via_diameter': .25, 'min_through_hole_diameter': .15,
                  'min_via_annular_width': .05})
    PROJECT.write_text(json.dumps(project, indent=2, sort_keys=True) + '\n')
    if '--build-only' in sys.argv:
        print('Candidate generated; native KiCad ERC/DRC pending', sha(CANDIDATE))
        return
    drc = run_native()
    summary = {'schema': 'dioneya-pcb-main-sim-mux-sel-066-v1',
               'base_sha256': BASE_SHA, 'candidate_sha256': sha(CANDIDATE),
               'net': NET, 'routes': [{'layer': layer, 'points': [list(a), list(b)]}
                                      for layer, a, b in ROUTES],
               'track_width_mm': WIDTH, 'new_vias': 2,
               'via_positions_mm': [list(p) for p in VIAS], 'via_size_drill_mm': [VIA_SIZE, VIA_DRILL],
               **check_geometry(), 'review_b': 'OPEN',
               'small_via_dfm': 'OPEN', 'candidate_only_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == drc['erc_errors'] == drc['erc_violations'] == 0
    assert drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Candidate 061: connect the C54/J6 SIM reset island to R50 on In3.Cu."""
from __future__ import annotations

import hashlib
import json
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-3V3-C34-INNER-060/PCB-MAIN_P2_3V3_C34_INNER_060_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SIM1-RST-C54-061'
CANDIDATE = OUT / 'PCB-MAIN_P2_SIM1_RST_C54_061_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_SIM1_RST_C54_061_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '397917294ca238fa72fd17548a77518b56887b77af361606bb4062fbf96afacd'
NAMESPACE = uuid.UUID('c78fa59a-a1d5-4962-b60e-e80b73db62dc')
NET = 'SIM1_RST_CONN'
START = (18.175, 16.0)  # Centered on the existing C54.1 F.Cu track, outside its pad.
END = (24.075, 16.7)    # Existing R50.2 through via.
WIDTH = .15
VIA_SIZE, VIA_DRILL = .25, .15


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_geometry() -> dict:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    line = LineString([START, END])
    obstacles = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    own_front_traces = []
    own_vias = []
    own_pads = []
    for fp in board.footprints:
        for pad in fp.pads:
            shape = geo.pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            if net == NET:
                own_pads.append(shape)
            if pad.drill is not None and getattr(pad.drill, 'diameter', 0):
                holes.append((shape.centroid, pad.drill.diameter / 2, net))
            for layer in geo.pad_layers(pad):
                obstacles[layer].append(shape)
                owners[layer].append(net)
    for net, kind, layer, shape, raw in geo.items(board):
        if kind == 'via':
            holes.append((shape, raw.drill / 2, net))
            if net == NET:
                own_vias.append(shape)
        elif net == NET and layer == 'F.Cu':
            own_front_traces.append((shape, raw.width))
        for copper in geo.LAYERS if kind == 'via' else (layer,):
            obstacles[copper].append(shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 8))
            owners[copper].append(net)
    indices = {layer: STRtree(obstacles[layer]) for layer in geo.LAYERS}

    def clear(layer, shape):
        conflicts = [owners[layer][int(i)] for i in indices[layer].query(shape)
                     if owners[layer][int(i)] != NET and obstacles[layer][int(i)].intersects(shape)]
        assert not conflicts, (layer, conflicts[:8])

    assert any(shape.distance(Point(*START)) < width / 2 - .01
               for shape, width in own_front_traces), 'new via must land within existing copper'
    assert not any(shape.contains(Point(*START)) for shape in own_pads), 'avoid via in pad'
    assert any(shape.distance(Point(*END)) < 1e-6 for shape in own_vias), 'end on existing via'
    for layer in geo.LAYERS:
        clear(layer, Point(*START).buffer(VIA_SIZE / 2 + .20, 16))
    clear('In3.Cu', line.buffer(WIDTH / 2 + .20, 16))
    for center, radius, net in holes:
        if net != NET:
            assert Point(*START).distance(center) - radius - VIA_DRILL / 2 >= .25 - 1e-6
            assert line.distance(center) - radius - WIDTH / 2 >= .25 - 1e-6
    ref4 = line.intersection(geo.zone_outline(board, 'GND_MODEM', 'In4.Cu')).length / line.length
    assert ref4 > .99, 'modem reference outline does not cover route'
    return {'in4_gnd_modem_reference_fraction': round(ref4, 4)}


def build() -> str:
    assert sha(BASE) == BASE_SHA, '060 changed; review the reset route again'
    check_geometry()
    source = BASE.read_text(encoding='utf-8')
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segment = (f'  (segment (start {START[0]:g} {START[1]:g}) (end {END[0]:g} {END[1]:g}) '
               f'(width {WIDTH:g}) (layer "In3.Cu") (net {nets[NET]}) '
               f'(tstamp {uuid.uuid5(NAMESPACE, "track")}))')
    via = (f'  (via (at {START[0]:g} {START[1]:g}) (size {VIA_SIZE:g}) '
           f'(drill {VIA_DRILL:g}) (layers "F.Cu" "B.Cu") (net {nets[NET]}) '
           f'(tstamp {uuid.uuid5(NAMESPACE, "via")}))')
    lines = source.splitlines()
    at = max(i for i, value in enumerate(lines) if value.startswith('  (segment ')) + 1
    lines.insert(at, segment)
    at = max(i for i, value in enumerate(lines) if value.startswith('  (via ')) + 1
    lines.insert(at, via)
    return '\n'.join(lines) + '\n'


def run_drc() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_sim1_rst_c54_061'
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
        (old_fp, old_open), (new_fp, new_open) = gate.drc_fingerprints(before), gate.drc_fingerprints(report)
        novel = [(key, count - old_fp.get(key, 0)) for key, count in new_fp.items()
                 if count > old_fp.get(key, 0)]
        by_type = Counter()
        for key, count in novel:
            by_type[f'{key[0]}:{key[1]}'] += count
        return {'base_unconnected': old_open, 'candidate_unconnected': new_open,
                'new_by_type': dict(by_type),
                'new_errors': sum(count for key, count in novel if key[0] == 'error')}
    finally:
        if not os.getenv('DIONEYA_KICAD_DIRECT'):
            gate.docker('rm', '-rf', str(work.relative_to(ROOT)))
        shutil.rmtree(work, ignore_errors=True)


def main():
    if '--check' in sys.argv:
        record = json.loads((OUT / 'SUMMARY.json').read_text())
        assert CANDIDATE.read_text() == build()
        assert record['candidate_sha256'] == sha(CANDIDATE)
        assert record['drc']['candidate_unconnected'] < record['drc']['base_unconnected']
        assert record['drc']['new_errors'] == 0
        print('PCB-MAIN SIM1 reset C54 061: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-sim1-rst-c54-061-v1',
               'base_sha256': BASE_SHA, 'candidate_sha256': sha(CANDIDATE),
               'net': NET, 'route_points': [list(START), list(END)],
               'track_width_mm': WIDTH, 'route_length_mm': round(__import__('math').dist(START, END), 4),
               'new_vias': 1, 'via_size_drill_mm': [VIA_SIZE, VIA_DRILL],
               **check_geometry(),
               'sim_reset_return_review_b': 'OPEN', 'small_via_dfm': 'OPEN',
               'candidate_only_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == 0 and drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

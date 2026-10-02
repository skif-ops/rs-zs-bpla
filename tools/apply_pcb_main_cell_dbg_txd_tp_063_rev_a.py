#!/usr/bin/env python3
"""Candidate 063: connect the CELL_DBG_TXD test pad with a short inner-layer link."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-VREF-3V3-062/PCB-MAIN_P2_VREF_3V3_062_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
BASE_MCU = BASE.parent / 'PCB-MAIN_02_MCU_VREF_062.kicad_sch'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-CELL-DBG-TXD-TP-063'
CANDIDATE = OUT / 'PCB-MAIN_P2_CELL_DBG_TXD_TP_063_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_CELL_DBG_TXD_TP_063_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'ae099f301e6dff1d93cb67141d0b28c416d8cad86b6f46eb120c9e2d0553be43'
NAMESPACE = uuid.UUID('deac0266-3f02-413b-8b0a-52deae913c4f')
NET = 'CELL_DBG_TXD_TP'
EXISTING_VIA = (46.474, 31.7499)
NEW_VIA = (47.9, 31.4)
TEST_PAD = (49.54, 30.0)
WIDTH = .15
VIA_SIZE, VIA_DRILL = .25, .15
ROUTES = (('In3.Cu', EXISTING_VIA, NEW_VIA), ('B.Cu', NEW_VIA, TEST_PAD))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_geometry() -> dict:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    obstacles = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    own_vias = []
    test_pad = None
    for fp in board.footprints:
        for pad in fp.pads:
            shape = geo.pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            if geo.reference(fp) == 'TP_CELL_DBG' and pad.number == '2':
                assert net == NET and 'B.Cu' in geo.pad_layers(pad)
                test_pad = shape
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
        for copper in geo.LAYERS if kind == 'via' else (layer,):
            obstacles[copper].append(shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 8))
            owners[copper].append(net)
    indices = {layer: STRtree(obstacles[layer]) for layer in geo.LAYERS}

    def clear(layer, shape):
        conflicts = [owners[layer][int(i)] for i in indices[layer].query(shape)
                     if owners[layer][int(i)] != NET and obstacles[layer][int(i)].intersects(shape)]
        assert not conflicts, (layer, conflicts[:8])

    assert any(shape.distance(Point(*EXISTING_VIA)) < 1e-6 for shape in own_vias)
    assert test_pad is not None and test_pad.centroid.distance(Point(*TEST_PAD)) < 1e-5
    assert not test_pad.contains(Point(*NEW_VIA)), 'keep through via outside test pad'
    for layer in geo.LAYERS:
        clear(layer, Point(*NEW_VIA).buffer(VIA_SIZE / 2 + .20, 16))
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
            assert Point(*NEW_VIA).distance(center) - radius - VIA_DRILL / 2 >= .25 - 1e-6
    return {'route_length_mm': round(sum(math.dist(a, b) for _, a, b in ROUTES), 4),
            'reference_outline_fraction': 1.0}


def build() -> str:
    assert sha(BASE) == BASE_SHA, '062 changed; screen the test-pad route again'
    check_geometry()
    source = BASE.read_text(encoding='utf-8')
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    assert NET in nets
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                f'(width {WIDTH:g}) (layer "{layer}") (net {nets[NET]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"segment|{i}")}))'
                for i, (layer, a, b) in enumerate(ROUTES)]
    via = (f'  (via (at {NEW_VIA[0]:g} {NEW_VIA[1]:g}) (size {VIA_SIZE:g}) '
           f'(drill {VIA_DRILL:g}) (layers "F.Cu" "B.Cu") (net {nets[NET]}) '
           f'(tstamp {uuid.uuid5(NAMESPACE, "via")}))')
    lines = source.splitlines()
    at = max(i for i, value in enumerate(lines) if value.startswith('  (segment ')) + 1
    lines[at:at] = segments
    at = max(i for i, value in enumerate(lines) if value.startswith('  (via ')) + 1
    lines.insert(at, via)
    return '\n'.join(lines) + '\n'


def run_native() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_cell_dbg_txd_tp_063'
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
        print('PCB-MAIN CELL_DBG_TXD_TP 063: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-cell-dbg-txd-tp-063-v1',
               'base_sha256': BASE_SHA, 'candidate_sha256': sha(CANDIDATE),
               'net': NET, 'routes': [{'layer': layer, 'points': [list(a), list(b)]}
                                      for layer, a, b in ROUTES],
               'track_width_mm': WIDTH, 'new_vias': 1,
               'via_position_mm': list(NEW_VIA), 'via_size_drill_mm': [VIA_SIZE, VIA_DRILL],
               **check_geometry(), 'testpoint_access_review_b': 'OPEN',
               'small_via_dfm': 'OPEN', 'candidate_only_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == drc['erc_errors'] == drc['erc_violations'] == 0
    assert drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Candidate 062: correct isolated VREF bypass nets and route C10/C11 to 3V3."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SIM1-RST-C54-061/PCB-MAIN_P2_SIM1_RST_C54_061_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
BASE_MCU = ROOT / 'hardware/kicad/native/PCB-MAIN/PCB-MAIN_02_MCU.kicad_sch'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-VREF-3V3-062'
CANDIDATE = OUT / 'PCB-MAIN_P2_VREF_3V3_062_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_VREF_3V3_062_CANDIDATE_REV_A.kicad_pro'
MCU = OUT / 'PCB-MAIN_02_MCU_VREF_062.kicad_sch'
BASE_SHA = 'b733b350b14dcbad0c62e91f7b58a715a891b418bdeac28d17f88277e724b4d0'
NAMESPACE = uuid.UUID('cd510b2b-c848-4fd5-b713-5ea07d1bb613')
ROUTES = (((41.925, 31.5), (41.925, 32.75)),  # C11.1 to C9.1
          ((41.925, 34.0), (41.925, 35.25)))  # C8.1 to C10.1
WIDTH = .25
PAD_UUIDS = ('efcc03e6-e836-4702-9f84-c519b60091d2',  # C10.1
             '6e234d2e-0688-446b-82e4-b09a3e96590a')  # C11.1
LABELS = ((87.63, 210.82), (156.21, 210.82))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corrected_mcu() -> str:
    source = BASE_MCU.read_text(encoding='utf-8')
    for x, y in LABELS:
        old = f'(label "VREF+" (at {x:g} {y:g} 180)'
        assert source.count(old) == 1, old
        source = source.replace(old, f'(label "3V3_DIGITAL" (at {x:g} {y:g} 180)')
    assert source.count('(label "VREF+"') == 0
    return source


def check_geometry() -> dict:
    from shapely.geometry import LineString
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    pads = {}
    obstacles = []
    for fp in board.footprints:
        ref = geo.reference(fp)
        for pad in fp.pads:
            net = pad.net.name if pad.net else None
            shape = geo.pad_geometry(fp, pad)
            if 'F.Cu' in geo.pad_layers(pad):
                pads[(ref, pad.number)] = (net, shape)
                if net not in ('3V3_DIGITAL', 'VREF+'):
                    obstacles.append(shape)
    for net, kind, layer, shape, raw in geo.items(board):
        if net not in ('3V3_DIGITAL', 'VREF+') and (kind == 'via' or layer == 'F.Cu'):
            obstacles.append(shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 8))
    assert all(pads[(ref, '1')][0] == net for ref, net in
               (('C10', 'VREF+'), ('C11', 'VREF+'), ('C8', '3V3_DIGITAL'), ('C9', '3V3_DIGITAL')))
    index = STRtree(obstacles)
    clearances = []
    assert all(pads[(ref, '1')][1].centroid.distance(__import__('shapely').geometry.Point(*point)) < 1e-6
               for ref, point in (('C11', ROUTES[0][0]), ('C9', ROUTES[0][1]),
                                  ('C8', ROUTES[1][0]), ('C10', ROUTES[1][1])))
    for points in ROUTES:
        line = LineString(points)
        area = line.buffer(WIDTH / 2 + .20, 16)
        assert not [int(i) for i in index.query(area) if obstacles[int(i)].intersects(area)], points
        assert line.difference(geo.zone_outline(board, 'GND_DIGITAL', 'In1.Cu')).length < 1e-6
        clearances.append(min(line.distance(shape) - WIDTH / 2 for shape in obstacles))
    return {'minimum_other_net_copper_clearance_mm': round(min(clearances), 4),
            'new_vias': 0, 'track_width_mm': WIDTH, 'route_length_mm': 2.5}


def build() -> str:
    assert sha(BASE) == BASE_SHA, '061 changed; review the VREF ECO again'
    check_geometry()
    source = BASE.read_text(encoding='utf-8')
    for pad_uuid in PAD_UUIDS:
        old = f'(net 186 "VREF+") (thermal_bridge_angle 45) (tstamp {pad_uuid})'
        assert source.count(old) == 1, pad_uuid
        source = source.replace(old, f'(net 2 "3V3_DIGITAL") (thermal_bridge_angle 45) (tstamp {pad_uuid})')
    assert source.count('(net 186 "VREF+") (thermal_bridge_angle') == 0
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                f'(width {WIDTH:g}) (layer "F.Cu") (net 2) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"track|{i}")}))'
                for i, (a, b) in enumerate(ROUTES)]
    lines = source.splitlines()
    at = max(i for i, line in enumerate(lines) if line.startswith('  (segment ')) + 1
    lines[at:at] = segments
    return '\n'.join(lines) + '\n'


def run_native() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_vref_3v3_062'
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(ROOT / 'hardware/kicad/native/PCB-MAIN', work)
    try:
        rel = work.relative_to(ROOT)
        shutil.copyfile(CANDIDATE, work / 'candidate.kicad_pcb')
        shutil.copyfile(PROJECT, work / 'candidate.kicad_pro')
        shutil.copyfile(MCU, work / 'PCB-MAIN_02_MCU.kicad_sch')
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
        assert 'sheets' in erc, 'KiCad ERC result has an unexpected schema'
        erc_violations = [v for sheet in erc['sheets'] for v in sheet.get('violations', [])]
        erc_errors = sum(v.get('severity') == 'error' for v in erc_violations)
        return {'base_unconnected': old_open, 'candidate_unconnected': new_open,
                'new_by_type': dict(by_type),
                'new_errors': sum(count for key, count in novel if key[0] == 'error'),
                'erc_errors': erc_errors, 'erc_violations': len(erc_violations)}
    finally:
        if not os.getenv('DIONEYA_KICAD_DIRECT'):
            gate.docker('rm', '-rf', str(work.relative_to(ROOT)))
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    if '--check' in sys.argv:
        record = json.loads((OUT / 'SUMMARY.json').read_text())
        assert CANDIDATE.read_text() == build()
        assert MCU.read_text() == corrected_mcu()
        assert record['candidate_sha256'] == sha(CANDIDATE)
        assert record['drc']['new_errors'] == record['drc']['erc_errors'] == record['drc']['erc_violations'] == 0
        print('PCB-MAIN VREF to 3V3 062: PASS', record['drc'])
        return
    gate.deps()
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build())
    MCU.write_text(corrected_mcu())
    project = json.loads((ROOT / 'hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pro').read_text())
    rules = project.setdefault('board', {}).setdefault('design_settings', {}).setdefault('rules', {})
    rules.update({'min_via_diameter': .25, 'min_through_hole_diameter': .15,
                  'min_via_annular_width': .05})
    PROJECT.write_text(json.dumps(project, indent=2, sort_keys=True) + '\n')
    if '--build-only' in sys.argv:
        print('Candidate generated; native KiCad ERC/DRC pending', sha(CANDIDATE))
        return
    drc = run_native()
    summary = {'schema': 'dioneya-pcb-main-vref-3v3-062-v1',
               'base_sha256': BASE_SHA, 'candidate_sha256': sha(CANDIDATE),
               'schematic_mcu_sha256': sha(MCU), 'routes': [list(map(list, route)) for route in ROUTES],
               **check_geometry(), 'analog_reference_decoupling_review_b': 'OPEN',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False, 'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == drc['erc_errors'] == drc['erc_violations'] == 0
    assert drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

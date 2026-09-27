#!/usr/bin/env python3
"""Candidate 065: stitch digital ground beside the candidate-064 FAULT via."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-FAULT-JPWR-064/PCB-MAIN_P2_FAULT_JPWR_064_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
BASE_MCU = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-VREF-3V3-062/PCB-MAIN_02_MCU_VREF_062.kicad_sch'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-FAULT-RETURN-065'
CANDIDATE = OUT / 'PCB-MAIN_P2_FAULT_RETURN_065_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_FAULT_RETURN_065_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '393f131f58c8285026b01f99770362970ad631ede069004e0f6735d02accb827'
NAMESPACE = uuid.UUID('5d7d1480-ce27-42f4-9381-8b654c507121')
NET = 'GND_DIGITAL'
SIGNAL_VIA = (25.1, 22.7)
STITCH = (25.1, 23.9)
VIA_SIZE, VIA_DRILL = .5, .3


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_geometry() -> dict:
    from shapely.geometry import Point

    board, _ = geo.load(BASE)
    signal = [shape for net, kind, _, shape, _ in geo.items(board)
              if net == 'FAULT' and kind == 'via' and shape.distance(Point(*SIGNAL_VIA)) < 1e-6]
    assert len(signal) == 1, 'the signal transition moved'
    point = Point(*STITCH)
    for layer in ('In1.Cu', 'In4.Cu'):
        assert geo.zone_outline(board, NET, layer).contains(point), (NET, layer)

    copper = []
    holes = []
    for fp in board.footprints:
        for pad in fp.pads:
            net = pad.net.name if pad.net else None
            shape = geo.pad_geometry(fp, pad)
            if net != NET:
                for layer in geo.pad_layers(pad):
                    copper.append((net, layer, shape))
                if pad.drill is not None and getattr(pad.drill, 'diameter', 0):
                    holes.append((net, shape.centroid, pad.drill.diameter / 2))
    for net, kind, layer, shape, raw in geo.items(board):
        if net == NET:
            continue
        for copper_layer in geo.LAYERS if kind == 'via' else (layer,):
            copper.append((net, copper_layer,
                           shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 16)))
        if kind == 'via':
            holes.append((net, shape, raw.drill / 2))

    clearance = min(point.distance(shape) - VIA_SIZE / 2 for _, _, shape in copper)
    hole_clearance = min(point.distance(center) - radius - VIA_DRILL / 2
                         for _, center, radius in holes)
    assert clearance >= .20 - 1e-6, clearance
    assert hole_clearance >= .25 - 1e-6, hole_clearance
    return {'nearest_other_net_copper_mm': round(clearance, 4),
            'nearest_other_drill_mm': round(hole_clearance, 4),
            'signal_to_ground_stitch_mm': 1.2,
            'digital_reference_zones': ['In1.Cu', 'In4.Cu']}


def build() -> str:
    assert sha(BASE) == BASE_SHA, '064 changed; screen the stitch again'
    check_geometry()
    source = BASE.read_text(encoding='utf-8')
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    assert NET in nets
    via = (f'  (via (at {STITCH[0]:g} {STITCH[1]:g}) (size {VIA_SIZE:g}) '
           f'(drill {VIA_DRILL:g}) (layers "F.Cu" "B.Cu") (net {nets[NET]}) '
           f'(tstamp {uuid.uuid5(NAMESPACE, "via")}))')
    lines = source.splitlines()
    at = max(i for i, value in enumerate(lines) if value.startswith('  (via ')) + 1
    lines.insert(at, via)
    return '\n'.join(lines) + '\n'


def run_native() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_fault_return_065'
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
        assert record['drc']['candidate_unconnected'] == record['drc']['base_unconnected'] == 77
        assert record['drc']['new_errors'] == record['drc']['erc_errors'] == record['drc']['erc_violations'] == 0
        print('PCB-MAIN FAULT return stitch 065: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-fault-return-stitch-065-v1',
               'base_sha256': BASE_SHA, 'candidate_sha256': sha(CANDIDATE),
               'net': NET, 'via_position_mm': list(STITCH),
               'via_size_drill_mm': [VIA_SIZE, VIA_DRILL], 'new_vias': 1,
               **check_geometry(), 'fault_return_review_b': 'OPEN',
               'candidate_only_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == drc['erc_errors'] == drc['erc_violations'] == 0
    assert drc['candidate_unconnected'] == drc['base_unconnected'] == 77, drc
    print(summary)


if __name__ == '__main__':
    main()

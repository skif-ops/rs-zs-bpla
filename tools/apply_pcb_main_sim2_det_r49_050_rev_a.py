#!/usr/bin/env python3
"""Rotate R49 and close its SIM2_DET leg without crossing the 3V3 feed."""
from __future__ import annotations

import hashlib
import json
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-3V3-BRIDGE-049/PCB-MAIN_P2_3V3_BRIDGE_049_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SIM2-DET-R49-050'
CANDIDATE = OUT / 'PCB-MAIN_P2_SIM2_DET_R49_050_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_SIM2_DET_R49_050_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'ca3381d980b8deaeae5d040fbb65d7da6c1930a92d4dbd05aab82931425de5c0'
NAMESPACE = uuid.UUID('ee02cd10-b176-4cd6-88c5-10959646eb53')
FOOTPRINT = 'e87bb550-d0dc-43bf-b8f6-0c6a00e9281f'
RIP = ('d0a3c8e7-e500-5ab2-be62-dfc69d7fc83c',
       '00ace013-b42a-5726-86d2-5d6c004e233c')
ROUTES = (
    ('3V3_DIGITAL', .3, (57.2703, 17.148), (57.675, 17.75)),
    ('SIM2_DET', .2, (58.325, 17.75), (59.425, 16.5)),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepared_source() -> str:
    assert sha(BASE) == BASE_SHA, '049 changed; review R49 placement again'
    source = BASE.read_text(encoding='utf-8')
    marker = f'(tstamp {FOOTPRINT})\n    (at 58 17.75 180)'
    assert source.count(marker) == 1
    source = source.replace(marker, f'(tstamp {FOOTPRINT})\n    (at 58 17.75 0)')
    reference = '(fp_text reference "R49" (at 0 1.2 180)'
    assert source.count(reference) == 1
    source = source.replace(reference, '(fp_text reference "R49" (at 0 -1.2 0)')
    for trace_uuid in RIP:
        pattern = r'^  \(segment [^\n]*\(tstamp ' + trace_uuid + r'\)\)\n'
        source, count = re.subn(pattern, '', source, flags=re.M)
        assert count == 1, (trace_uuid, count)
    return source


def geometry_check(source: str) -> None:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    with tempfile.TemporaryDirectory() as tmp:
        board_path = Path(tmp) / 'R49.kicad_pcb'
        board_path.write_text(source)
        board, _ = geo.load(board_path)
    obs = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    rotated = None
    for fp in board.footprints:
        if geo.reference(fp) == 'R49':
            rotated = {p.number: (p.net.name, geo.pad_geometry(fp, p).centroid)
                       for p in fp.pads}
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
        for copper in geo.LAYERS if kind == 'via' else (layer,):
            obs[copper].append(shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 8))
            owners[copper].append(net)
    assert rotated and rotated['1'][0] == '3V3_DIGITAL' and rotated['2'][0] == 'SIM2_DET'
    assert rotated['1'][1].distance(Point(57.675, 17.75)) < 1e-6
    assert rotated['2'][1].distance(Point(58.325, 17.75)) < 1e-6
    index = STRtree(obs['F.Cu'])
    for net, width, a, c in ROUTES:
        line = LineString((a, c))
        shape = line.buffer(width / 2 + .20, 16)
        conflicts = [owners['F.Cu'][int(i)] for i in index.query(shape)
                     if owners['F.Cu'][int(i)] != net and obs['F.Cu'][int(i)].intersects(shape)]
        assert not conflicts, (net, conflicts[:8])
        assert not [(n, line.distance(q) - radius - width / 2) for q, radius, n in holes
                    if n != net and line.distance(q) - radius - width / 2 < .25 - 1e-6]


def build() -> str:
    source = prepared_source()
    geometry_check(source)
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {c[0]:g} {c[1]:g}) '
                f'(width {width:g}) (layer "F.Cu") (net {nets[net]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"track|{i}")}))'
                for i, (net, width, a, c) in enumerate(ROUTES)]
    lines = source.splitlines()
    at = max(i for i, line in enumerate(lines) if line.startswith('  (segment ')) + 1
    lines[at:at] = segments
    return '\n'.join(lines) + '\n'


def run_drc() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_sim2_det_r49_050'
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
        print('PCB-MAIN SIM2 DET R49 050: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-sim2-det-r49-050-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': sha(CANDIDATE), 'rotation': {'reference': 'R49',
               'from_deg': 180, 'to_deg': 0}, 'removed_tracks': list(RIP),
               'routes': len(ROUTES), 'track_segments': len(ROUTES),
               'sim2_return_review_b': 'OPEN', 'power_return_review_b': 'OPEN',
               'candidate_only_usb_u1_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == 0 and drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

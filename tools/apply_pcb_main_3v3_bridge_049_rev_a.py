#!/usr/bin/env python3
"""Candidate-only short 3V3 bridge near U1; KiCad native DRC is mandatory."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-GNSS-SWITCHED-R62-048/PCB-MAIN_P2_GNSS_SWITCHED_R62_048_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-3V3-BRIDGE-049'
CANDIDATE = OUT / 'PCB-MAIN_P2_3V3_BRIDGE_049_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_3V3_BRIDGE_049_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '2dee54ef4544e5c8c59f48935df1ae1cdc840faa1a3861d2eb46eda1562abe02'
NAMESPACE = uuid.UUID('4dccf98b-d293-40f5-bde1-71c60842ab29')
NET = '3V3_DIGITAL'
VIA_A = (61.675, 27.898)  # on an existing F.Cu power run
VIA_B = (61.35, 25.35)  # off the second run, with a short F.Cu exit
STUB_END = (61.425, 25.25)
ROUTES = (
    ('In3.Cu', .15, (VIA_A, VIA_B)),
    ('F.Cu', .25, (VIA_B, STUB_END)),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_check() -> None:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    board, _ = geo.load(BASE)
    obs = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    front = []
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
        if kind == 'track' and layer == 'F.Cu' and net == NET:
            front.append(shape.buffer(raw.width / 2, 8))
        for copper in geo.LAYERS if kind == 'via' else (layer,):
            obs[copper].append(shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 8))
            owners[copper].append(net)
    indices = {layer: STRtree(obs[layer]) for layer in geo.LAYERS}

    def clear(layer, shape):
        conflicts = [owners[layer][int(i)] for i in indices[layer].query(shape)
                     if owners[layer][int(i)] != NET and obs[layer][int(i)].intersects(shape)]
        assert not conflicts, (layer, conflicts[:8])

    assert all(any(track.distance(Point(*p)) < .005 for track in front) for p in (VIA_A, STUB_END))
    assert LineString((VIA_A, VIA_B)).difference(geo.zone_outline(board, 'GND_DIGITAL', 'In4.Cu')).length < 1e-6
    for layer, width, points in ROUTES:
        path = LineString(points)
        clear(layer, path.buffer(width / 2 + .20, 16))
        assert not [(n, path.distance(c) - r - width / 2) for c, r, n in holes
                    if n != NET and path.distance(c) - r - width / 2 < .25 - 1e-6]
    for x, y in (VIA_A, VIA_B):
        center = Point(x, y)
        for layer in geo.LAYERS:
            clear(layer, center.buffer(.125 + .20, 16))
        assert not [(n, center.distance(c) - r - .075) for c, r, n in holes
                    if n != NET and center.distance(c) - r - .075 < .25 - 1e-6]


def build() -> str:
    assert sha(BASE) == BASE_SHA, '048 changed; review the route again'
    geometry_check()
    source = BASE.read_text(encoding='utf-8')
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                f'(width {width:g}) (layer "{layer}") (net {nets[NET]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"track|{i}")}))'
                for i, (layer, width, (a, b)) in enumerate(ROUTES)]
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
    work = ROOT / 'hardware/kicad/native/_p2_3v3_bridge_049'
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
        print('PCB-MAIN 3V3 bridge 049: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-3v3-bridge-049-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': sha(CANDIDATE), 'routes': 2, 'track_segments': 2,
               'via_size_drill_mm': [.25, .15], 'total_length_mm': 2.69,
               'power_integrity_and_return_review_b': 'OPEN', 'small_via_dfm_review': 'OPEN',
               'candidate_only_usb_u1_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == 0 and drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

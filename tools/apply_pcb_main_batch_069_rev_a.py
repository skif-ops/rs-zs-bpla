#!/usr/bin/env python3
"""Candidate 069: five independently screened PCB-MAIN P2 gap closures."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-BATCH-068/PCB-MAIN_P2_BATCH_068_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
BASE_MCU = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-VREF-3V3-062/PCB-MAIN_02_MCU_VREF_062.kicad_sch'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-BATCH-069'
ROUTES = OUT / 'ROUTES.json'
CANDIDATE = OUT / 'PCB-MAIN_P2_BATCH_069_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_BATCH_069_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'd78d34cf477825f4b15ac1e68294b1cb22be83184ed53c899022f95bcd5025d8'
NAMESPACE = uuid.UUID('a32f36a3-7204-4b2e-b827-a54bf47e1af9')
COPPER_CLEARANCE, HOLE_CLEARANCE = .20, .25
VIA_DRILL = .15


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records() -> list[dict]:
    spec = json.loads(ROUTES.read_text())
    assert spec['schema'] == 'dioneya-pcb-main-batch-routes-069-v1'
    assert spec['base_candidate'] == 68 and len(spec['routes']) == 5
    assert len({r['net'] for r in spec['routes']}) == len(spec['routes'])
    return spec['routes']


def check_geometry() -> dict:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    board, domains = geo.load(BASE)
    routes = records()
    obstacles = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    holes = []
    own = {}
    for fp in board.footprints:
        for pad in fp.pads:
            shape = geo.pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            for layer in geo.pad_layers(pad):
                obstacles[layer].append(shape)
                owners[layer].append(net)
                own.setdefault((net, layer), []).append(shape)
            if pad.drill is not None and getattr(pad.drill, 'diameter', 0):
                holes.append((net, shape.centroid, pad.drill.diameter / 2))
    for net, kind, layer, shape, raw in geo.items(board):
        if kind == 'via':
            holes.append((net, shape, raw.drill / 2))
        for copper in geo.LAYERS if kind == 'via' else (layer,):
            body = shape.buffer(raw.size / 2 if kind == 'via' else raw.width / 2, 16)
            obstacles[copper].append(body)
            owners[copper].append(net)
            own.setdefault((net, copper), []).append(body)
    indices = {layer: STRtree(obstacles[layer]) for layer in geo.LAYERS}
    new = []
    details = []
    for route in routes:
        net = route['net']
        reference = domains[net]
        length = 0.0
        vias = 0
        for ordinal, item in enumerate(route['items']):
            kind, layer = item['kind'], item['layer']
            width = item['width_or_size_mm']
            points = [tuple(p) for p in item['points_mm']]
            assert kind in ('track', 'via') and width == (.15 if kind == 'track' else .25)
            if kind == 'track':
                assert layer in ('F.Cu', 'In3.Cu', 'B.Cu') and len(points) >= 2
                assert all(a != b for a, b in zip(points, points[1:]))
                shape = LineString(points)
                length += shape.length
                layers = (layer,)
                radius = width / 2
            else:
                assert layer is None and len(points) == 1
                shape = Point(points[0])
                layers = geo.LAYERS
                radius = VIA_DRILL / 2
                vias += 1
            copper = shape.buffer(width / 2 + COPPER_CLEARANCE, 16)
            for copper_layer in layers:
                assert not any(owners[copper_layer][int(i)] != net and
                               obstacles[copper_layer][int(i)].intersects(copper)
                               for i in indices[copper_layer].query(copper)), (net, ordinal, copper_layer)
            assert all(shape.distance(center) - drill_radius - radius >= HOLE_CLEARANCE - 1e-6
                       for other, center, drill_radius in holes if other != net), (net, ordinal, 'hole')
            assert shape.bounds[0] >= .6 and shape.bounds[1] >= .6 and \
                   shape.bounds[2] <= 109.4 and shape.bounds[3] <= 74.4, (net, ordinal, 'edge')
            if reference.startswith('CROSS_'):
                # Both digital/modem domains are explicitly a Review B boundary.
                reference_layers = ('In1.Cu', 'In4.Cu') if kind == 'via' else \
                    (('In1.Cu',) if layer == 'F.Cu' else ('In4.Cu',) if layer == 'B.Cu' else ('In2.Cu',))
                for ground_layer in reference_layers:
                    if ground_layer == 'In2.Cu':
                        assert shape.difference(geo.zone_outline(board, 'GND_MIC', ground_layer)).length < 1e-5
                        continue
                    outlines = [geo.zone_outline(board, ground, ground_layer)
                                for ground in ('GND_DIGITAL', 'GND_MODEM')
                                if any(z.netName == ground and z.layers == [ground_layer] for z in board.zones)]
                    assert shape.difference(outlines[0].union(*outlines[1:])).length < 1e-5, \
                        (net, ordinal, ground_layer, 'cross-domain reference')
            else:
                reference_layers = ('In1.Cu', 'In4.Cu') if kind == 'via' else \
                    (('In1.Cu',) if layer == 'F.Cu' else ('In4.Cu',) if layer == 'B.Cu' else ('In2.Cu',))
                for ground_layer in reference_layers:
                    ground = 'GND_MIC' if ground_layer == 'In2.Cu' else \
                        ('GND_DIGITAL' if ground_layer == 'In1.Cu' else reference)
                    assert shape.difference(geo.zone_outline(board, ground, ground_layer)).length < 1e-5, \
                        (net, ordinal, ground_layer, 'reference')
            for other_net, other_kind, other_layer, other_shape, other_copper, other_radius in new:
                if other_net == net:
                    continue
                if kind == 'via' or other_kind == 'via' or layer == other_layer:
                    assert copper.distance(other_copper) >= 0, 'unreachable'
                    assert shape.buffer(width / 2, 16).distance(other_copper) >= COPPER_CLEARANCE - 1e-6, \
                        (net, other_net, ordinal, 'new copper')
                assert shape.distance(other_shape) - radius - other_radius >= HOLE_CLEARANCE - 1e-6 \
                    if (kind == 'via' or other_kind == 'via') else True, \
                    (net, other_net, ordinal, 'new hole')
            new.append((net, kind, layer, shape, shape.buffer(width / 2, 16), radius))
        # Each end lands on copper already on the input board; the route's
        # item order is a continuous polyline including every via transition.
        items = route['items']
        for left, right in zip(items, items[1:]):
            assert tuple(left['points_mm'][-1]) == tuple(right['points_mm'][0]), (net, 'disjoint')
        first, last = items[0], items[-1]
        for item, point in ((first, first['points_mm'][0]), (last, last['points_mm'][-1])):
            landing_layers = geo.LAYERS if item['kind'] == 'via' else (item['layer'],)
            assert any(c.distance(Point(point)) < 1e-6 for layer in landing_layers
                       for c in own.get((net, layer), [])), \
                (net, point, 'end does not touch own copper')
        details.append({'net': net, 'track_length_mm': round(length, 4), 'vias': vias})
    return {'routes': details, 'route_count': len(details), 'new_vias': sum(x['vias'] for x in details),
            'new_track_length_mm': round(sum(x['track_length_mm'] for x in details), 4),
            'reference_outline_fraction': 1.0}


def build() -> str:
    assert sha(BASE) == BASE_SHA, '068 changed; screen the route batch again'
    check_geometry()
    source = BASE.read_text(encoding='utf-8')
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments, vias = [], []
    for route in records():
        net = route['net']
        for i, item in enumerate(route['items']):
            points = item['points_mm']
            if item['kind'] == 'via':
                p = points[0]
                vias.append(f'  (via (at {p[0]:g} {p[1]:g}) (size 0.25) (drill 0.15) '
                            f'(layers "F.Cu" "B.Cu") (net {nets[net]}) '
                            f'(tstamp {uuid.uuid5(NAMESPACE, f"{net}|{i}|via")}))')
            else:
                for j, (a, b) in enumerate(zip(points, points[1:])):
                    segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                                    f'(width 0.15) (layer "{item["layer"]}") (net {nets[net]}) '
                                    f'(tstamp {uuid.uuid5(NAMESPACE, f"{net}|{i}|{j}")}))')
    lines = source.splitlines()
    at = max(i for i, value in enumerate(lines) if value.startswith('  (segment ')) + 1
    lines[at:at] = segments
    at = max(i for i, value in enumerate(lines) if value.startswith('  (via ')) + 1
    lines[at:at] = vias
    return '\n'.join(lines) + '\n'


def run_native() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_batch_069'
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
        assert not record['drc']['new_by_type']
        assert record['drc']['new_errors'] == record['drc']['erc_errors'] == record['drc']['erc_violations'] == 0
        assert record['drc']['candidate_unconnected'] < record['drc']['base_unconnected']
        print('PCB-MAIN batch 069: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-batch-069-v1',
               'base_sha256': BASE_SHA, 'candidate_sha256': sha(CANDIDATE),
               **check_geometry(), 'review_b': 'OPEN', 'candidate_only_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert not drc['new_by_type'], drc
    assert drc['new_errors'] == drc['erc_errors'] == drc['erc_violations'] == 0
    assert drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

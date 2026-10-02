#!/usr/bin/env python3
"""Route U23.5 SD_CK_CARD to the existing B.Cu clock run on In3.Cu."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SD-CMD-U23-051/PCB-MAIN_P2_SD_CMD_U23_051_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC = BASE.parent / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SD-CK-U23-052'
CANDIDATE = OUT / 'PCB-MAIN_P2_SD_CK_U23_052_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_SD_CK_U23_052_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '3bf028120368ca5adf9f13d809cb32d89b0c9206f7794f99b7d31f17560395a2'
NAMESPACE = uuid.UUID('f68f4170-0f7a-482c-a7b2-8c91136a1ca6')
CK_VIAS = ((81.5, 22.0), (79.5, 18.0272))
ROUTES = (
    ('F.Cu', .15, ((82.5825, 22.0), CK_VIAS[0])),
    ('In3.Cu', .20, CK_VIAS),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_board() -> str:
    assert sha(BASE) == BASE_SHA, '051 changed; review U23 escape again'
    return BASE.read_text(encoding='utf-8')


def check_geometry(source: str) -> None:
    from shapely.geometry import LineString, Point
    from shapely.strtree import STRtree

    with tempfile.TemporaryDirectory() as tmp:
        board_path = Path(tmp) / 'U23_CK.kicad_pcb'
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
            if geo.reference(fp) == 'U23':
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

    assert any(ref == 'U23' and number == '5' and net == 'SD_CK_CARD'
               and shape.contains(Point(*ROUTES[0][2][0])) for ref, number, net, shape in pads)
    assert LineString(CK_VIAS).difference(geo.zone_outline(board, 'GND_DIGITAL', 'In4.Cu')).length < 1e-6
    assert any(net == 'SD_CK_CARD' and kind == 'track' and layer == 'B.Cu'
               and shape.distance(Point(*CK_VIAS[1])) < 1e-6
               for net, kind, layer, shape, raw in geo.items(board))
    for layer, width, points in ROUTES:
        line = LineString(points)
        clear('SD_CK_CARD', layer, line.buffer(width / 2 + .20, 16))
        assert not [(n, line.distance(q) - r - width / 2) for q, r, n in holes
                    if n != 'SD_CK_CARD' and line.distance(q) - r - width / 2 < .25 - 1e-6]
    for xy in CK_VIAS:
        net = 'SD_CK_CARD'
        center = Point(*xy)
        for layer in geo.LAYERS:
            clear(net, layer, center.buffer(.125 + .20, 16))
        assert not [(n, center.distance(q) - r - .075) for q, r, n in holes
                    if n != net and center.distance(q) - r - .075 < .25 - 1e-6]


def build() -> str:
    source = source_board()
    check_geometry(source)
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M)}
    segments = [f'  (segment (start {a[0]:g} {a[1]:g}) (end {c[0]:g} {c[1]:g}) '
                f'(width {width:g}) (layer "{layer}") (net {nets["SD_CK_CARD"]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"track|{i}")}))'
                for i, (layer, width, (a, c)) in enumerate(ROUTES)]
    vias = [(xy, 'SD_CK_CARD') for xy in CK_VIAS]
    via_text = [f'  (via (at {xy[0]:g} {xy[1]:g}) (size 0.25) (drill 0.15) '
                f'(layers "F.Cu" "B.Cu") (net {nets[net]}) '
                f'(tstamp {uuid.uuid5(NAMESPACE, f"via|{i}")}))'
                for i, (xy, net) in enumerate(vias)]
    lines = source.splitlines()
    at = max(i for i, line in enumerate(lines) if line.startswith('  (segment ')) + 1
    lines[at:at] = segments
    at = max(i for i, line in enumerate(lines) if line.startswith('  (via ')) + 1
    lines[at:at] = via_text
    return '\n'.join(lines) + '\n'


def run_drc() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_sd_ck_u23_052'
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
        print('PCB-MAIN SD_CK U23 052: PASS', record['drc'])
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
    summary = {'schema': 'dioneya-pcb-main-sd-ck-u23-052-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': sha(CANDIDATE), 'sd_ck_vias': [list(p) for p in CK_VIAS],
               'track_segments': 2, 'small_via_size_drill_mm': [.25, .15],
               'sd_return_review_b': 'OPEN', 'via_in_pad_dfm_review': 'OPEN',
               'candidate_only_usb_u1_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False,
               'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    assert drc['new_errors'] == 0 and drc['candidate_unconnected'] < drc['base_unconnected'], drc
    print(summary)


if __name__ == '__main__':
    main()

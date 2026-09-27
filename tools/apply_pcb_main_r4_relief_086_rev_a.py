#!/usr/bin/env python3
"""Candidate 086: free R4.1 by removing a redundant GND stitch, then join its 3V3 island."""
from __future__ import annotations

import json
import math
import re
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_astar_077_rev_a as native

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-PDM-RELIEF-085'
BOARD = BASE / 'PCB-MAIN_P2_PDM_RELIEF_085_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-R4-RELIEF-086'
CANDIDATE = OUT / 'PCB-MAIN_P2_R4_RELIEF_086_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_R4_RELIEF_086_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '620aabcbffe095401edae7084f1fd026ca266a2411281e05f2dea495175eeeb9'


def build() -> tuple[str, dict]:
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-086-v1'
    assert len(spec['delete']) == 1 and len(spec['routes']) == 5
    board = BOARD.read_text()
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', board, re.M)}
    old = spec['delete'][0]
    assert old.startswith('  (via (at 56.9000 20.0000)') and board.count(old) == 1
    board = board.replace(old, '')
    lines, length, vias = [], 0., 0
    for j, route in enumerate(spec['routes']):
        assert route['net'] == '3V3_DIGITAL'
        net = nets[route['net']]
        if route['kind'] == 'via':
            x, y = route['at']
            assert (route.get('size', .25), route.get('drill', .15)) == (.25, .15)
            vias += 1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                         f'(layers "F.Cu" "B.Cu") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"086|via|{x}|{y}")}))')
            continue
        assert route['kind'] == 'track' and route['layer'] in ('F.Cu', 'In3.Cu')
        assert route['width'] == .25
        for i, (a, b) in enumerate(zip(route['points'], route['points'][1:])):
            assert a != b
            length += math.dist(a, b)
            lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                         f'(width 0.25) (layer "{route["layer"]}") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"086|{j}|{i}|{a}|{b}")}))')
    assert vias == 2
    at = board.index('\n', board.rfind('  (segment ')) + 1
    return board[:at] + '\n'.join(lines) + '\n' + board[at:], {
        'net': '3V3_DIGITAL', 'track_length_mm': round(length, 3),
        'new_segments': len(lines) - vias, 'new_vias': vias,
        'removed_redundant_gnd_digital_stitch_vias': 1,
    }


def main() -> None:
    board, route = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 29
        print('PCB-MAIN candidate 086: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_PDM_RELIEF_085_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE, native.OUT, native.CANDIDATE, native.PROJECT = BASE, OUT, CANDIDATE, PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 30, 'candidate_unconnected': 29, 'new_by_type': {},
                   'new_errors': 0, 'erc_errors': 0, 'erc_violations': 0}, drc
    summary = {'schema': 'dioneya-pcb-main-r4-relief-086-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'route': route, 'drc': drc,
               'review_b': 'OPEN: removed GND_DIGITAL stitch near R4, power return, two small vias/DFM',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

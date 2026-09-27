#!/usr/bin/env python3
"""Candidate 087: move D11 0.4 mm and escape the U23 SD_D3 card pad."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-R4-RELIEF-086'
BOARD = BASE / 'PCB-MAIN_P2_R4_RELIEF_086_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D3-RELIEF-087'
CANDIDATE = OUT / 'PCB-MAIN_P2_SD_D3_RELIEF_087_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_SD_D3_RELIEF_087_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'f529508ae13d3715c245b0dfce5165aafe21ad0c1e45ba88b6cb2caa9e30d30b'


def build() -> tuple[str, dict]:
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-087-v1'
    assert len(spec['replace']) == 1 and len(spec['delete']) == 1 and len(spec['routes']) == 9
    board = BOARD.read_text()
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', board, re.M)}
    old, new = spec['replace'][0]
    assert '(at 80.75 20.5)' in old and '(at 80.35 20.5)' in new
    assert board.count(old) == 1
    board = board.replace(old, new)
    for old in spec['delete']:
        assert board.count(old) == 1 and 'GND_DIGITAL' not in old
        board = board.replace(old, '')
    lines, lengths, vias = [], {}, 0
    for j, route in enumerate(spec['routes']):
        name = route['net']
        assert name in ('3V3_DIGITAL', 'GND_DIGITAL', 'SD_D3_CARD')
        net = nets[name]
        if route['kind'] == 'via':
            assert name == 'SD_D3_CARD'
            x, y = route['at']
            assert (route.get('size', .25), route.get('drill', .15)) == (.25, .15)
            vias += 1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                         f'(layers "F.Cu" "B.Cu") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"087|via|{j}|{x}|{y}")}))')
            continue
        assert route['kind'] == 'track' and route['layer'] in ('F.Cu', 'In3.Cu', 'B.Cu')
        width = route['width']
        assert width == (.3 if name == '3V3_DIGITAL' else .15)
        for i, (a, b) in enumerate(zip(route['points'], route['points'][1:])):
            assert a != b
            lengths[name] = lengths.get(name, 0.) + math.dist(a, b)
            lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                         f'(width {width}) (layer "{route["layer"]}") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"087|{j}|{i}|{a}|{b}")}))')
    assert vias == 3
    at = board.index('\n', board.rfind('  (segment ')) + 1
    return board[:at] + '\n'.join(lines) + '\n' + board[at:], {
        'D11_translation_mm': [-.4, 0], 'new_vias': vias,
        'new_segments': len(lines)-vias, 'removed_ground_segments': 1,
        'new_track_length_by_net_mm': {n: round(v, 3) for n, v in lengths.items()},
    }


def main() -> None:
    board, route = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 28
        print('PCB-MAIN candidate 087: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_R4_RELIEF_086_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE, native.OUT, native.CANDIDATE, native.PROJECT = BASE, OUT, CANDIDATE, PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 29, 'candidate_unconnected': 28, 'new_by_type': {},
                   'new_errors': 0, 'erc_errors': 0, 'erc_violations': 0}, drc
    summary = {'schema': 'dioneya-pcb-main-sd-d3-relief-087-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'route': route, 'drc': drc,
               'review_b': 'OPEN: SDIO timing/skew and return, ESD D11 placement, small vias/DFM',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Candidate 085: relieve U19 PDM escape by rerouting PDM_CLK, modem supply and ground via."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-C46-084'
BOARD = BASE / 'PCB-MAIN_P2_C46_084_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-PDM-RELIEF-085'
CANDIDATE = OUT / 'PCB-MAIN_P2_PDM_RELIEF_085_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_PDM_RELIEF_085_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '2a8111d236f1f84cbb009fd62a1f800e0b67e906d0e90f151b411157a2f38428'


def build() -> tuple[str, dict]:
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-085-v1'
    assert len(spec['delete']) == 4 and len(spec['routes']) == 6
    board = BOARD.read_text()
    nets = dict((name, int(code)) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', board, re.M))
    for old in spec['delete']:
        assert board.count(old) == 1, old
        board = board.replace(old, '')
    lines, lengths, vias = [], {}, 0
    for j, route in enumerate(spec['routes']):
        name = route['net']
        assert name in {'PDM_CLK_1V8_FANOUT', 'PDM_DATA1_1V8', '3V8_MODEM', 'GND_MIC'}
        net = nets[name]
        if route['kind'] == 'via':
            x, y = route['at']
            size, drill = route.get('size', .25), route.get('drill', .15)
            assert (size, drill) == (.25, .15)
            vias += 1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                         f'(layers "F.Cu" "B.Cu") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"085|via|{name}|{x}|{y}")}))')
            continue
        assert route['kind'] == 'track'
        layer, width = route['layer'], route.get('width', .15)
        assert layer in ('F.Cu', 'In3.Cu', 'B.Cu')
        assert width == (.8 if name == '3V8_MODEM' else .15)
        for i, (a, b) in enumerate(zip(route['points'], route['points'][1:])):
            assert a != b
            lengths[name] = lengths.get(name, 0) + math.dist(a, b)
            lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                         f'(width {width}) (layer "{layer}") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"085|{name}|{j}|{i}|{a}|{b}")}))')
    assert vias == 2 and len(lines) > 10
    at = board.index('\n', board.rfind('  (segment ')) + 1
    return board[:at] + '\n'.join(lines) + '\n' + board[at:], {
        'new_segments': len(lines) - vias, 'new_vias': vias,
        'removed_segments': 3, 'relocated_ground_via': 1,
        'new_track_length_by_net_mm': {n: round(v, 3) for n, v in lengths.items()},
    }


def main() -> None:
    board, metrics = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 30
        print('PCB-MAIN candidate 085: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_C46_084_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE = BASE
    native.OUT = OUT
    native.CANDIDATE = CANDIDATE
    native.PROJECT = PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 31, 'candidate_unconnected': 30,
                   'new_by_type': {}, 'new_errors': 0,
                   'erc_errors': 0, 'erc_violations': 0}, drc
    summary = {'schema': 'dioneya-pcb-main-pdm-relief-085-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'route': metrics,
               'review_b': 'OPEN: U19 via-in-pad, MIC return, modem supply and small-via DFM',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False, 'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Candidate 080: local C47 RF supply capacitor branch, pending PI/return Review B."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-AAD-079'
BOARD = BASE / 'PCB-MAIN_P2_AAD_079_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-C47-080'
CANDIDATE = OUT / 'PCB-MAIN_P2_C47_080_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_C47_080_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'd98ee2e91c9faa48d73e3133683d99814764d3be76b1179f714d1bb922654054'


def build() -> tuple[str, dict]:
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-080-v1'
    assert spec['net'] == '3V8_MODEM_RF' and spec['layer'] == 'F.Cu' and spec['width_mm'] == 0.4
    points = spec['points_mm']
    assert len(points) == 7 and points[0] == [5.4, 47.1] and points[-1] == [9.6, 47.0]
    source = BOARD.read_text()
    net = dict((name, int(code)) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M))[spec['net']]
    lines = []
    for i, (a, b) in enumerate(zip(points, points[1:])):
        lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                     f'(width 0.4) (layer "F.Cu") (net {net}) '
                     f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"080|{net}|{i}|{a}|{b}")}))')
    length = round(sum(math.dist(a, b) for a, b in zip(points, points[1:])), 3)
    assert length == 4.324
    at = source.index('\n', source.rfind('  (segment ')) + 1
    return source[:at] + '\n'.join(lines) + '\n' + source[at:], {
        'net': spec['net'], 'width_mm': 0.4, 'track_length_mm': length,
        'segments': len(lines), 'vias': 0,
        'F_Cu_over_In1_GND_DIGITAL_mm': length,
    }


def main() -> None:
    board, metrics = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 35
        print('PCB-MAIN candidate 080: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_AAD_079_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE = BASE
    native.OUT = OUT
    native.CANDIDATE = CANDIDATE
    native.PROJECT = PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 36, 'candidate_unconnected': 35,
                   'new_by_type': {}, 'new_errors': 0,
                   'erc_errors': 0, 'erc_violations': 0}, drc
    summary = {'schema': 'dioneya-pcb-main-c47-080-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'route': metrics,
               'review_b': 'OPEN: RF decoupling current, cross-domain return and 0.4 mm branch PI',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False, 'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

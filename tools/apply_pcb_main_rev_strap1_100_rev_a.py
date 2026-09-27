#!/usr/bin/env python3
"""Candidate 100: short layer-switched REV_STRAP1 escape, native DRC gated."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-CELL-PWRKEY-099'
BOARD = BASE / 'PCB-MAIN_P2_CELL_PWRKEY_099_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-REV-STRAP1-100'
CANDIDATE = OUT / 'PCB-MAIN_P2_REV_STRAP1_100_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_REV_STRAP1_100_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '09fd1ad0eb71f3bcb94dbff8709ccfa25ec9287d437a0467ef3645a98f9b602b'


def build() -> tuple[str, dict]:
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-100-v1'
    assert spec['base_candidate'] == 99 and spec['route_clearance_probe_mm'] == .12
    text = BOARD.read_text()
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', text, re.M)}
    lines = []
    count = {'new_segments': 0, 'new_vias': 0}
    length = 0.0
    for index, item in enumerate(spec['items']):
        kind, layer, net = item['kind'], item['layer'], item['net']
        size, points = item['width_or_size_mm'], item['points_mm']
        assert net == 'REV_STRAP1'
        if kind == 'via':
            assert size == .25 and len(points) == 1
            x, y = points[0]
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                         f'(layers "F.Cu" "B.Cu") (net {nets[net]}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"100|{index}|via|{x}|{y}")}))')
            count['new_vias'] += 1
        else:
            assert kind == 'track' and layer in ('F.Cu', 'In3.Cu', 'B.Cu') and size == .15
            for n, (a, b) in enumerate(zip(points, points[1:])):
                assert a != b
                length += math.dist(a, b)
                count['new_segments'] += 1
                lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                             f'(width 0.15) (layer "{layer}") (net {nets[net]}) '
                             f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"100|{index}|{n}|{a}|{b}")}))')
    assert len(spec['items']) == 13 and count == {'new_segments': 37, 'new_vias': 6}
    at = text.index('\n', text.rfind('  (segment ')) + 1
    return text[:at] + '\n'.join(lines) + '\n' + text[at:], {**count, 'length_mm': round(length, 3)}


def main() -> None:
    board, metrics = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 15
        print('PCB-MAIN candidate 100: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_CELL_PWRKEY_099_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE, native.OUT, native.CANDIDATE, native.PROJECT = BASE, OUT, CANDIDATE, PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 16, 'candidate_unconnected': 15, 'new_by_type': {},
                   'new_errors': 0, 'erc_errors': 0, 'erc_violations': 0}, drc
    summary = {'schema': 'dioneya-pcb-main-rev-strap1-100-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'route': metrics, 'drc': drc,
               'review_b': 'OPEN: REV_STRAP1 test-point return, six vias, signal integrity and DFM',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Candidate 100: connect PDM_DATA2 and restore NRST."""
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
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-PDM-DATA2-100'
CANDIDATE = OUT / 'PCB-MAIN_P2_PDM_DATA2_100_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_PDM_DATA2_100_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '09fd1ad0eb71f3bcb94dbff8709ccfa25ec9287d437a0467ef3645a98f9b602b'
SEGMENT = re.compile(r'^  \(segment \(start ([^)]*)\) \(end ([^)]*)\) \(width ([^)]*)\) '
                     r'\(layer "([^"]*)"\) \(net (\d+)\) \(tstamp [^)]*\)\)\n$')


def build() -> tuple[str, dict]:
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-100-v1' and spec['base_candidate'] == 99
    text = BOARD.read_text()
    nets = {name: int(code) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', text, re.M)}
    assert len(spec['removed_tracks']) == 1 and len(spec['items']) == 17
    removals = {(q['net'], q['layer'], q['width'], tuple(q['start']), tuple(q['end']))
                for q in spec['removed_tracks']}
    assert len(removals) == 1 and all(n == 'NRST' and l == 'In3.Cu' for n, l, *_ in removals)
    kept = []
    for line in text.splitlines(keepends=True):
        match = SEGMENT.match(line)
        if match:
            a, b, width, layer, code = match.groups()
            key = ('NRST', layer, float(width), tuple(map(float, a.split())),
                   tuple(map(float, b.split())))
            if int(code) == nets['NRST'] and key in removals:
                removals.remove(key)
                continue
        kept.append(line)
    assert not removals, removals
    text = ''.join(kept)
    lines = []
    length = 0.0
    counts = {'new_segments': 0, 'new_vias': 0, 'removed_segments': 1}
    for index, item in enumerate(spec['items']):
        kind, layer, net = item['kind'], item['layer'], item['net']
        size, points = item['width_or_size_mm'], item['points_mm']
        assert net in ('PDM_DATA2', 'NRST')
        if kind == 'via':
            assert size == .25 and len(points) == 1
            x, y = points[0]
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                         f'(layers "F.Cu" "B.Cu") (net {nets[net]}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"100|{index}|{net}|{x}|{y}")}))')
            counts['new_vias'] += 1
        else:
            assert kind == 'track' and layer in ('F.Cu', 'In3.Cu', 'B.Cu') and size == .15
            for n, (a, b) in enumerate(zip(points, points[1:])):
                assert a != b
                length += math.dist(a, b)
                lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                             f'(width 0.15) (layer "{layer}") (net {nets[net]}) '
                             f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"100|{index}|{n}|{a}|{b}")}))')
                counts['new_segments'] += 1
    assert counts['new_segments'] == 110 and counts['new_vias'] == 8
    at = text.index('\n', text.rfind('  (segment ')) + 1
    return text[:at] + '\n'.join(lines) + '\n' + text[at:], {**counts, 'length_mm': round(length, 3)}


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
    summary = {'schema': 'dioneya-pcb-main-pdm-data2-100-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'route': metrics, 'drc': drc,
               'review_b': 'OPEN: PDM_DATA2 length, audio skew/return, NRST integrity and via-in-pad DFM review',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

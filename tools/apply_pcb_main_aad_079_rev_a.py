#!/usr/bin/env python3
"""Candidate 079: DRC-screened AAD_CFG_1V8_FANOUT branch from Freerouting session.

The long B.Cu leg is over the In4.Cu digital ground outline. Cross-domain
return and small-via DFM remain open; the authoritative board is unchanged.
"""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-U1-RELIEF-078'
BOARD = BASE / 'PCB-MAIN_P2_U1_RELIEF_078_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-AAD-079'
CANDIDATE = OUT / 'PCB-MAIN_P2_AAD_079_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_AAD_079_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '44fd9e8b36f47511cc48b3450807337c61af1cc5d99a67373a56b5e7e6b29526'


def build() -> tuple[str, dict]:
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-079-v1'
    assert spec['net'] == 'AAD_CFG_1V8_FANOUT' and len(spec['segments']) == 9 and len(spec['vias_mm']) == 2
    text = BOARD.read_text()
    net = dict((name, int(code)) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', text, re.M))[spec['net']]
    lines = []
    length = 0.0
    for i, segment in enumerate(spec['segments']):
        layer, width = segment['layer'], segment['width_mm']
        a, b = segment['start_mm'], segment['end_mm']
        assert layer in ('F.Cu', 'B.Cu') and width == .15 and a != b
        length += math.dist(a, b)
        lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                     f'(width {width}) (layer "{layer}") (net {net}) '
                     f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"079|{net}|{layer}|{i}|{a}|{b}")}))')
    for x, y in spec['vias_mm']:
        lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                     f'(layers "F.Cu" "B.Cu") (net {net}) '
                     f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"079|via|{net}|{x}|{y}")}))')
    assert round(length, 3) == 52.332
    at = text.index('\n', text.rfind('  (segment ')) + 1
    return text[:at] + '\n'.join(lines) + '\n' + text[at:], {
        'net': spec['net'], 'track_length_mm': round(length, 3),
        'segments': len(spec['segments']), 'vias': 2,
        'B_Cu_over_In4_GND_DIGITAL_mm': 49.922,
    }


def main() -> None:
    board, metrics = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 36
        print('PCB-MAIN candidate 079: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_U1_RELIEF_078_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE = BASE
    native.OUT = OUT
    native.CANDIDATE = CANDIDATE
    native.PROJECT = PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 37, 'candidate_unconnected': 36,
                   'new_by_type': {}, 'new_errors': 0,
                   'erc_errors': 0, 'erc_violations': 0}, drc
    summary = {'schema': 'dioneya-pcb-main-aad-079-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'route': metrics,
               'source_session_sha256': json.loads((OUT / 'ROUTES.json').read_text())['source_session_sha256'],
               'review_b': 'OPEN: cross-domain return, edge timing and small-via DFM',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False, 'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

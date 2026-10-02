#!/usr/bin/env python3
"""Candidate 078: reroute two U1 escape obstacles and bridge a 3V3 supply pin.

The U1 pad via and 0.25/0.15 mm drill are candidate-only pending DFM Review B.
PCB-MAIN 003 remains unchanged.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_astar_077_rev_a as previous

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-ASTAR-077'
BOARD = BASE / 'PCB-MAIN_P2_ASTAR_077_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-U1-RELIEF-078'
CANDIDATE = OUT / 'PCB-MAIN_P2_U1_RELIEF_078_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_U1_RELIEF_078_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'e9ea548204565cbe81fd5fac91519c3f238b1cb152650bfe86aa5dec47f62f40'
RIPPED = (
    '  (segment (start 40.8820 33.8936) (end 47.6356 33.8936) (width 0.15) (layer "B.Cu") (net 24) (tstamp 0d5d78de-8960-5d6a-b45d-6a85e2e986e8))',
    '  (segment (start 43.475 35.1) (end 45.45 31) (width 0.15) (layer "In3.Cu") (net 164) (tstamp 3b105106-021d-5043-8a02-f22c9b72b2c2))',
)


def build() -> str:
    assert previous.sha(BOARD) == BASE_SHA
    text = BOARD.read_text()
    for old in RIPPED:
        assert text.count(old) == 1
        text = text.replace(old, '')
    lines = []

    def path(net: int, layer: str, width: float, points: list[tuple[float, float]]) -> None:
        for i, (a, b) in enumerate(zip(points, points[1:])):
            lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {width}) '
                         f'(layer "{layer}") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"078|{net}|{layer}|{i}|{a}|{b}")}))')

    def via(net: int, x: float, y: float) -> None:
        lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                     f'(layers "F.Cu" "B.Cu") (net {net}) '
                     f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"078|via|{net}|{x}|{y}")}))')

    path(24, 'B.Cu', .15, [(40.882, 33.8936), (43.65, 33.8936), (44.0, 33.55),
                           (45.0, 33.55), (45.35, 33.8936), (47.6356, 33.8936)])
    path(164, 'In3.Cu', .15, [(43.475, 35.1), (44.8, 34.6), (44.8, 33.8),
                              (44.75, 32.5), (45.45, 31)])
    via(2, 41.9, 34.5)
    via(2, 44.25, 34)
    path(2, 'F.Cu', .25, [(41.925, 34), (41.9, 34.5)])
    path(2, 'In3.Cu', .25, [(41.9, 34.5), (42.45, 33.95), (42.65, 33.95),
                           (43.55, 33.95), (44.25, 34)])
    at = text.index('\n', text.rfind('  (segment ')) + 1
    return text[:at] + '\n'.join(lines) + '\n' + text[at:]


def main() -> None:
    text = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == text
        s = json.loads((OUT / 'SUMMARY.json').read_text())
        assert s['candidate_sha256'] == previous.sha(CANDIDATE)
        assert s['drc']['candidate_unconnected'] == 37
        print('PCB-MAIN candidate 078: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(text)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_ASTAR_077_CANDIDATE_REV_A.kicad_pro', PROJECT)
    previous.BASE = BASE
    previous.OUT = OUT
    previous.CANDIDATE = CANDIDATE
    previous.PROJECT = PROJECT
    drc = previous.check()
    assert drc == {'base_unconnected': 38, 'candidate_unconnected': 37,
                   'new_by_type': {}, 'new_errors': 0,
                   'erc_errors': 0, 'erc_violations': 0}, drc
    summary = {'schema': 'dioneya-pcb-main-u1-relief-078-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': previous.sha(CANDIDATE),
               'change': 'CELL_RESET_N_CMD B.Cu and TEST_UART_RX_U1 In3.Cu local rip-up; '
                         '3V3_DIGITAL F.Cu/In3.Cu U1.27 bridge with two 0.25/0.15 mm vias',
               'candidate_only_via_rules': True, 'via_in_pad_dfm': 'OPEN',
               'review_b': 'OPEN', 'applied_to_authoritative_board': False,
               'manufacturing_release': False, 'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

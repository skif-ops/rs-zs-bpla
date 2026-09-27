#!/usr/bin/env python3
"""Candidate 082: CELL_USB_BOOT_TP test route pending cross-domain return Review B."""
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

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-CELL-DBG-081'
BOARD = BASE / 'PCB-MAIN_P2_CELL_DBG_081_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-CELL-BOOT-082'
CANDIDATE = OUT / 'PCB-MAIN_P2_CELL_BOOT_082_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_CELL_BOOT_082_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '7e883cc37c0d522e700dd69d3a9a0006e0b0c4de4310ea16e664200792c5b331'


def build() -> tuple[str, dict]:
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-082-v1' and spec['net'] == 'CELL_USB_BOOT_TP'
    source = BOARD.read_text()
    net = dict((name, int(code)) for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', source, re.M))[spec['net']]
    lines, lengths = [], {}
    vias = 0
    for j, item in enumerate(spec['items']):
        if item['kind'] == 'via':
            assert item['width_or_size_mm'] == 0.25
            x, y = item['points_mm'][0]
            vias += 1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                         f'(layers "F.Cu" "B.Cu") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"082|via|{j}|{x}|{y}")}))')
            continue
        layer, width = item['layer'], item['width_or_size_mm']
        assert item['kind'] == 'track' and layer in ('F.Cu', 'In3.Cu', 'B.Cu') and width == .15
        for i, (a, b) in enumerate(zip(item['points_mm'], item['points_mm'][1:])):
            lengths[layer] = lengths.get(layer, 0) + math.dist(a, b)
            lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                         f'(width 0.15) (layer "{layer}") (net {net}) '
                         f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"082|{net}|{layer}|{j}|{i}|{a}|{b}")}))')
    assert vias == 6 and 54 < sum(lengths.values()) < 55
    at = source.index('\n', source.rfind('  (segment ')) + 1
    return source[:at] + '\n'.join(lines) + '\n' + source[at:], {
        'net': spec['net'], 'track_length_mm': round(sum(lengths.values()), 3),
        'segments': len(lines) - vias, 'vias': vias,
        'length_by_layer_mm': {layer: round(value, 3) for layer, value in lengths.items()},
    }


def main() -> None:
    board, metrics = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 33
        print('PCB-MAIN candidate 082: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_CELL_DBG_081_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE = BASE
    native.OUT = OUT
    native.CANDIDATE = CANDIDATE
    native.PROJECT = PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 34, 'candidate_unconnected': 33,
                   'new_by_type': {}, 'new_errors': 0,
                   'erc_errors': 0, 'erc_violations': 0}, drc
    summary = {'schema': 'dioneya-pcb-main-cell-boot-082-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'route': metrics,
               'review_b': 'OPEN: cellular boot test return through MIC/digital reference and fixture timing',
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False, 'drc': drc}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

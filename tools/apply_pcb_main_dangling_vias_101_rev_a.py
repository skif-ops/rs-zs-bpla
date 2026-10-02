#!/usr/bin/env python3
"""Candidate 101: remove six redundant one-layer via barrels."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_astar_077_rev_a as native

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-PDM-DATA2-100'
BOARD = BASE / 'PCB-MAIN_P2_PDM_DATA2_100_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-VIA-CLEANUP-101'
CANDIDATE = OUT / 'PCB-MAIN_P2_VIA_CLEANUP_101_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_VIA_CLEANUP_101_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'bf864d3f869ec033ed529a035d1028d63988805c28b057a22845ea0e32038df0'
VIA = re.compile(r'^  \(via \(at ([^)]*)\) \(size ([^)]*)\) \(drill ([^)]*)\) '
                 r'\(layers "F.Cu" "B.Cu"\) \(net (\d+)\) \(tstamp [^)]*\)\)\n$')
REMOVE = {
    ('BLE_TX_U11', 91.965, 35.3062),
    ('CELL_RI_U16', 18.1507, 32.502),
    ('LORA_SCK_U10', 69.6937, 49.0387),
    ('PDM_DATA2', 63.9642, 43.2885),
    ('SIM2_RST_MUX', 38.1814, 21.575),
    ('TAMPER_IN_U1', 94.4016, 28.0),
}


def build() -> str:
    assert native.sha(BOARD) == BASE_SHA
    text = BOARD.read_text()
    nets = {int(code): name for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', text, re.M)}
    pending = set(REMOVE)
    kept = []
    for line in text.splitlines(keepends=True):
        match = VIA.match(line)
        if match:
            pos, _, _, code = match.groups()
            x, y = map(float, pos.split())
            key = (nets[int(code)], x, y)
            if key in pending:
                pending.remove(key)
                continue
        kept.append(line)
    assert not pending, pending
    return ''.join(kept)


def main() -> None:
    board = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 15
        print('PCB-MAIN candidate 101: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_PDM_DATA2_100_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE, native.OUT, native.CANDIDATE, native.PROJECT = BASE, OUT, CANDIDATE, PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 15, 'candidate_unconnected': 15, 'new_by_type': {},
                   'new_errors': 0, 'erc_errors': 0, 'erc_violations': 0}, drc
    before = json.loads((BASE / 'drc_candidate.json').read_text())
    after = json.loads((OUT / 'drc_candidate.json').read_text())
    count = lambda document: sum(v['type'] == 'via_dangling' for v in document['violations'])
    assert count(before) == 18 and count(after) == 12, (count(before), count(after))
    summary = {'schema': 'dioneya-pcb-main-via-cleanup-101-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'removed_one_layer_vias': len(REMOVE),
               'via_dangling_before': count(before), 'via_dangling_after': count(after),
               'drc': drc, 'candidate_only_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

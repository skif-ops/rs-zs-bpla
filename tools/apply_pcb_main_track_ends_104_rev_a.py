#!/usr/bin/env python3
"""Candidate 104: trim three preexisting dangling track ends."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_astar_077_rev_a as native

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-PAD-STUBS-103'
BOARD = BASE / 'PCB-MAIN_P2_PAD_STUBS_103_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-TRACK-ENDS-104'
CANDIDATE = OUT / 'PCB-MAIN_P2_TRACK_ENDS_104_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_TRACK_ENDS_104_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'a347c8dd632b18c26bbca7710cd673009f31918f15b141a3c8b637d48e068087'
VIA = re.compile(r'^  \(via \(at ([^)]*)\) \(size ([^)]*)\) \(drill ([^)]*)\) '
                 r'\(layers "F.Cu" "B.Cu"\) \(net (\d+)\) \(tstamp [^)]*\)\)\n$')
SEGMENT = re.compile(r'^  \(segment \(start ([^)]*)\) \(end ([^)]*)\) \(width ([^)]*)\) '
                     r'\(layer "([^"]*)"\) \(net (\d+)\) \(tstamp ([^)]*)\)\)\n$')
REMOVE = {
    ('3V8_MODEM_BB', 'B.Cu', (36.46, 50.6789), (36.46, 52.0)),
    ('CELL_DBG_TXD_TP', 'F.Cu', (46.675, 30.0), (46.675, 31.5489)),
    ('CELL_DBG_TXD_TP', 'F.Cu', (46.675, 31.5489), (46.474, 31.7499)),
}
TRIM = ('U8_VDD_EXT_1V8', 'F.Cu', (47.325, 30.0), (47.325, 32.3645))
REMOVE_VIA = ('CELL_DBG_TXD_TP', 46.474, 31.7499)


def build() -> str:
    assert native.sha(BOARD) == BASE_SHA
    text = BOARD.read_text()
    nets = {int(code): name for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', text, re.M)}
    pending = set(REMOVE)
    trim_pending, via_pending = True, True
    kept = []
    for line in text.splitlines(keepends=True):
        match = VIA.match(line)
        if match:
            pos, _, _, code = match.groups()
            x, y = map(float, pos.split())
            if (nets[int(code)], x, y) == REMOVE_VIA:
                assert via_pending
                via_pending = False
                continue
        match = SEGMENT.match(line)
        if match:
            a, b, width, layer, code, stamp = match.groups()
            start, end = tuple(map(float, a.split())), tuple(map(float, b.split()))
            key = (nets[int(code)], layer, start, end)
            if key in pending:
                pending.remove(key)
                continue
            if key == TRIM:
                assert trim_pending
                trim_pending = False
                line = (f'  (segment (start 47.325 30.6) (end {b}) (width {width}) '
                        f'(layer "{layer}") (net {code}) (tstamp {stamp}))\n')
        kept.append(line)
    assert not pending and not trim_pending and not via_pending, (pending, trim_pending, via_pending)
    return ''.join(kept)


def main() -> None:
    board = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 15
        print('PCB-MAIN candidate 104: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_PAD_STUBS_103_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE, native.OUT, native.CANDIDATE, native.PROJECT = BASE, OUT, CANDIDATE, PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 15, 'candidate_unconnected': 15, 'new_by_type': {},
                   'new_errors': 0, 'erc_errors': 0, 'erc_violations': 0}, drc
    before = json.loads((BASE / 'drc_candidate.json').read_text())
    after = json.loads((OUT / 'drc_candidate.json').read_text())
    count = lambda document, kind: sum(v['type'] == kind for v in document['violations'])
    assert count(before, 'track_dangling') == 3 and count(after, 'track_dangling') == 0
    assert count(before, 'via_dangling') == 7 and count(after, 'via_dangling') == 7
    summary = {'schema': 'dioneya-pcb-main-track-ends-104-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'removed_segments': len(REMOVE),
               'trimmed_segments': 1, 'removed_vias': 1,
               'track_dangling_before': 3, 'track_dangling_after': 0, 'drc': drc,
               'candidate_only_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

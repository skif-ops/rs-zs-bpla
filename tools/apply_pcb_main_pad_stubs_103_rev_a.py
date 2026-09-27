#!/usr/bin/env python3
"""Candidate 103: trim three redundant pad-side via stubs."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_astar_077_rev_a as native

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-TAIL-CLEANUP-102'
BOARD = BASE / 'PCB-MAIN_P2_TAIL_CLEANUP_102_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-PAD-STUBS-103'
CANDIDATE = OUT / 'PCB-MAIN_P2_PAD_STUBS_103_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_PAD_STUBS_103_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'e3239975dbb043d15ce43d7e3fae415957cc423b7a553a0bdab8af631b400799'
VIA = re.compile(r'^  \(via \(at ([^)]*)\) \(size ([^)]*)\) \(drill ([^)]*)\) '
                 r'\(layers "F.Cu" "B.Cu"\) \(net (\d+)\) \(tstamp [^)]*\)\)\n$')
SEGMENT = re.compile(r'^  \(segment \(start ([^)]*)\) \(end ([^)]*)\) \(width ([^)]*)\) '
                     r'\(layer "([^"]*)"\) \(net (\d+)\) \(tstamp ([^)]*)\)\)\n$')
VIAS = {('AAD_CFG_1V8_U7', 59.189, 46.225),
        ('GNSS_TX_U1', 45.3734, 35.5),
        ('SD_D3_CARD', 86.195, 8.1184)}
TRACKS = {('GNSS_TX_U1', (44.25, 35.5), (45.3734, 35.5)),
          ('SD_D3_CARD', (86.195, 6.89), (86.195, 8.1184))}
AAD = ('AAD_CFG_1V8_U7', (56.85, 46.225), (59.189, 46.225))


def build() -> str:
    assert native.sha(BOARD) == BASE_SHA
    text = BOARD.read_text()
    nets = {int(code): name for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', text, re.M)}
    via_pending, track_pending, aad_pending = set(VIAS), set(TRACKS), True
    kept = []
    for line in text.splitlines(keepends=True):
        match = VIA.match(line)
        if match:
            pos, _, _, code = match.groups()
            x, y = map(float, pos.split())
            key = (nets[int(code)], x, y)
            if key in via_pending:
                via_pending.remove(key)
                continue
        match = SEGMENT.match(line)
        if match:
            a, b, width, layer, code, stamp = match.groups()
            start, end = tuple(map(float, a.split())), tuple(map(float, b.split()))
            key = (nets[int(code)], start, end)
            if layer == 'F.Cu' and float(width) == .15:
                if key in track_pending:
                    track_pending.remove(key)
                    continue
                if key == AAD:
                    assert aad_pending
                    aad_pending = False
                    line = line.replace('(end 59.189 46.225)', '(end 58 46.2)')
        kept.append(line)
    assert not via_pending and not track_pending and not aad_pending, (via_pending, track_pending, aad_pending)
    return ''.join(kept)


def main() -> None:
    board = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 15
        print('PCB-MAIN candidate 103: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_TAIL_CLEANUP_102_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE, native.OUT, native.CANDIDATE, native.PROJECT = BASE, OUT, CANDIDATE, PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 15, 'candidate_unconnected': 15, 'new_by_type': {},
                   'new_errors': 0, 'erc_errors': 0, 'erc_violations': 0}, drc
    before = json.loads((BASE / 'drc_candidate.json').read_text())
    after = json.loads((OUT / 'drc_candidate.json').read_text())
    count = lambda document: sum(v['type'] == 'via_dangling' for v in document['violations'])
    assert count(before) == 10 and count(after) == 7, (count(before), count(after))
    summary = {'schema': 'dioneya-pcb-main-pad-stubs-103-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'removed_redundant_vias': len(VIAS),
               'removed_segments': len(TRACKS), 'trimmed_segments': 1,
               'via_dangling_before': count(before), 'via_dangling_after': count(after),
               'drc': drc, 'candidate_only_via_rules': True,
               'applied_to_authoritative_board': False, 'manufacturing_release': False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

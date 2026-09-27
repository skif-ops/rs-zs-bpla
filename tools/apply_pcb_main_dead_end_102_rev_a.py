#!/usr/bin/env python3
"""Candidate 102: trim two screened F.Cu dead-end stubs and unused vias."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_astar_077_rev_a as native

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-VIA-CLEANUP-101'
BOARD = BASE / 'PCB-MAIN_P2_VIA_CLEANUP_101_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-TAIL-CLEANUP-102'
CANDIDATE = OUT / 'PCB-MAIN_P2_TAIL_CLEANUP_102_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_TAIL_CLEANUP_102_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = '3225c39d1fd58195111de8019cfb9bfba70a69fda486c8e594ec139a29671001'
VIA = re.compile(r'^  \(via \(at ([^)]*)\) \(size ([^)]*)\) \(drill ([^)]*)\) '
                 r'\(layers "F.Cu" "B.Cu"\) \(net (\d+)\) \(tstamp [^)]*\)\)\n$')
SEGMENT = re.compile(r'^  \(segment \(start ([^)]*)\) \(end ([^)]*)\) \(width ([^)]*)\) '
                     r'\(layer "([^"]*)"\) \(net (\d+)\) \(tstamp [^)]*\)\)\n$')
REMOVE = {
    ('SIM2_DET', 58.9437, 12.9666),
    ('SIM_MUX_EN', 28.4433, 15.223),
}


def build() -> str:
    assert native.sha(BOARD) == BASE_SHA
    text = BOARD.read_text()
    nets = {int(code): name for code, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', text, re.M)}
    pending_vias = set(REMOVE)
    pending_tracks = set(REMOVE)
    kept = []
    for line in text.splitlines(keepends=True):
        match = VIA.match(line)
        if match:
            pos, _, _, code = match.groups()
            x, y = map(float, pos.split())
            key = (nets[int(code)], x, y)
            if key in pending_vias:
                pending_vias.remove(key)
                continue
        match = SEGMENT.match(line)
        if match:
            a, b, width, layer, code = match.groups()
            if layer == 'F.Cu' and float(width) == .15:
                net = nets[int(code)]
                ends = [tuple(map(float, p.split())) for p in (a, b)]
                matches = [key for key in pending_tracks if key[0] == net and key[1:] in ends]
                if matches:
                    assert len(matches) == 1
                    pending_tracks.remove(matches[0])
                    continue
        kept.append(line)
    assert not pending_vias and not pending_tracks, (pending_vias, pending_tracks)
    return ''.join(kept)


def main() -> None:
    board = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 15
        print('PCB-MAIN candidate 102: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_VIA_CLEANUP_101_CANDIDATE_REV_A.kicad_pro', PROJECT)
    native.BASE, native.OUT, native.CANDIDATE, native.PROJECT = BASE, OUT, CANDIDATE, PROJECT
    drc = native.check()
    assert drc == {'base_unconnected': 15, 'candidate_unconnected': 15, 'new_by_type': {},
                   'new_errors': 0, 'erc_errors': 0, 'erc_violations': 0}, drc
    before = json.loads((BASE / 'drc_candidate.json').read_text())
    after = json.loads((OUT / 'drc_candidate.json').read_text())
    count = lambda document: sum(v['type'] == 'via_dangling' for v in document['violations'])
    assert count(before) == 12 and count(after) == 10, (count(before), count(after))
    summary = {'schema': 'dioneya-pcb-main-tail-cleanup-102-v1', 'base_sha256': BASE_SHA,
               'candidate_sha256': native.sha(CANDIDATE), 'removed_dead_end_vias': len(REMOVE),
               'removed_dead_end_segments': len(REMOVE), 'via_dangling_before': count(before),
               'via_dangling_after': count(after), 'drc': drc,
               'candidate_only_via_rules': True, 'applied_to_authoritative_board': False,
               'manufacturing_release': False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

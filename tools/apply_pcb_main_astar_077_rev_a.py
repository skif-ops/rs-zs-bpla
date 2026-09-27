#!/usr/bin/env python3
"""Add the DRC-screened 3V3 bridge to candidate 076, without changing the authoritative PCB."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as gate

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-U3-POWER-076'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-ASTAR-077'
BOARD = BASE / 'PCB-MAIN_P2_U3_POWER_076_CANDIDATE_REV_A.kicad_pcb'
CANDIDATE = OUT / 'PCB-MAIN_P2_ASTAR_077_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_ASTAR_077_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'df2aaafb3e9195c3cc8ac3b03e60f099b527eb0f7fc0447fa3216ab6fa44e64f'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> tuple[str, dict]:
    assert sha(BOARD) == BASE_SHA
    routes = json.loads((OUT / 'ROUTES.json').read_text())
    assert len(routes) == 1 and routes[0]['index'] == 0 and routes[0]['net'] == '3V3_DIGITAL'
    text = BOARD.read_text()
    nets = {name: int(n) for n, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', text, re.M)}
    lines = []
    length = vias = segments = 0
    for route in routes:
        net = route['net']
        for item in route['items']:
            if item['kind'] == 'track':
                layer, width = item['layer'], item['width_or_size_mm']
                assert layer in ('F.Cu', 'In3.Cu', 'B.Cu') and width == 0.25
                for a, b in zip(item['points_mm'], item['points_mm'][1:]):
                    assert a != b
                    length += math.dist(a, b)
                    segments += 1
                    lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) '
                                 f'(width {width}) (layer "{layer}") (net {nets[net]}) '
                                 f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"076|{net}|{layer}|{a}|{b}")}))')
            else:
                assert item['kind'] == 'via' and item['width_or_size_mm'] == 0.25
                x, y = item['points_mm'][0]
                vias += 1
                lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) '
                             f'(layers "F.Cu" "B.Cu") (net {nets[net]}) '
                             f'(tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"076|via|{net}|{x}|{y}")}))')
    at = text.index('\n', text.rfind('  (segment ')) + 1
    return text[:at] + '\n'.join(lines) + '\n' + text[at:], {
        'net': '3V3_DIGITAL', 'track_length_mm': round(length, 3),
        'segments': segments, 'vias': vias, 'via_size_drill_mm': [0.25, 0.15],
    }


def check() -> dict:
    work = ROOT / 'hardware/kicad/native/_p2_astar_077'
    shutil.copytree(ROOT / 'hardware/kicad/native/PCB-MAIN', work, dirs_exist_ok=True)
    shutil.copyfile(CANDIDATE, work / 'candidate.kicad_pcb')
    shutil.copyfile(PROJECT, work / 'candidate.kicad_pro')
    shutil.copyfile(ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-VREF-3V3-062/PCB-MAIN_02_MCU_VREF_062.kicad_sch',
                    work / 'PCB-MAIN_02_MCU.kicad_sch')
    rel = work.relative_to(ROOT)
    commands = [('/usr/bin/python3', 'tools/pcb_main_ground_domain_002_stage_rev_a.py', 'fill',
                 f'{rel}/candidate.kicad_pcb', f'{rel}/candidate.kicad_pcb'),
                ('kicad-cli', 'pcb', 'drc', '--format', 'json', '--severity-all', '-o',
                 f'{rel}/drc_candidate.json', f'{rel}/candidate.kicad_pcb'),
                ('kicad-cli', 'sch', 'erc', '--format', 'json', '--severity-all', '-o',
                 f'{rel}/erc_candidate.json', f'{rel}/PCB-MAIN.kicad_sch')]
    for command in commands:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert done.returncode == 0, (command, done.stdout[-1000:], done.stderr[-1000:])
    shutil.copyfile(work / 'drc_candidate.json', OUT / 'drc_candidate.json')
    shutil.copyfile(work / 'erc_candidate.json', OUT / 'erc_candidate.json')
    before = json.loads((BASE / 'drc_candidate.json').read_text())
    after = json.loads((OUT / 'drc_candidate.json').read_text())
    old_fp, old_open = gate.drc_fingerprints(before)
    new_fp, new_open = gate.drc_fingerprints(after)
    novel = [(key, value-old_fp.get(key, 0)) for key, value in new_fp.items() if value > old_fp.get(key, 0)]
    by_type = Counter()
    for key, count in novel:
        by_type[f'{key[0]}:{key[1]}'] += count
    erc = json.loads((OUT / 'erc_candidate.json').read_text())
    violations = [v for sheet in erc['sheets'] for v in sheet.get('violations', [])]
    return {'base_unconnected': old_open, 'candidate_unconnected': new_open,
            'new_by_type': dict(by_type),
            'new_errors': sum(count for key, count in novel if key[0] == 'error'),
            'erc_errors': sum(v.get('severity') == 'error' for v in violations),
            'erc_violations': len(violations)}


def main() -> None:
    candidate, metrics = build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == candidate
        summary = json.loads((OUT / 'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 38
        print('PCB-MAIN candidate 077: PASS')
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(candidate)
    shutil.copyfile(BASE / 'PCB-MAIN_P2_U3_POWER_076_CANDIDATE_REV_A.kicad_pro', PROJECT)
    drc = check()
    assert drc == {'base_unconnected':39, 'candidate_unconnected':38, 'new_by_type':{},
                   'new_errors':0, 'erc_errors':0, 'erc_violations':0}, drc
    summary = {'schema':'dioneya-pcb-main-astar-077-v1', 'base_sha256':BASE_SHA,
               'candidate_sha256':sha(CANDIDATE), 'route':metrics, 'drc':drc,
               'candidate_only_via_rules':True, 'review_b':'OPEN',
               'applied_to_authoritative_board':False, 'manufacturing_release':False}
    (OUT / 'SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

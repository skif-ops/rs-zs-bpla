#!/usr/bin/env python3
"""Candidate 088: join the upper SD_D3_CARD branch to U23 using two F/B vias."""
from __future__ import annotations
import json, math, re, shutil, sys, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import apply_pcb_main_astar_077_rev_a as native
BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D3-RELIEF-087'
BOARD = BASE / 'PCB-MAIN_P2_SD_D3_RELIEF_087_CANDIDATE_REV_A.kicad_pcb'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D3-TOP-088'
CANDIDATE = OUT / 'PCB-MAIN_P2_SD_D3_TOP_088_CANDIDATE_REV_A.kicad_pcb'
PROJECT = OUT / 'PCB-MAIN_P2_SD_D3_TOP_088_CANDIDATE_REV_A.kicad_pro'
BASE_SHA = 'a41ce5bd9d71d81d3abde9c57116debbc205bf88f97fafa834fc6e9c1076dbfe'

def build():
    assert native.sha(BOARD) == BASE_SHA
    spec = json.loads((OUT / 'ROUTES.json').read_text())
    assert spec['schema'] == 'dioneya-pcb-main-route-088-v1'
    assert not spec['delete'] and len(spec['routes']) == 5
    board = BOARD.read_text()
    nets = {name:int(code) for code,name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', board, re.M)}
    lines, length, vias = [], 0., 0
    for j, route in enumerate(spec['routes']):
        assert route['net'] == 'SD_D3_CARD'
        net = nets[route['net']]
        if route['kind'] == 'via':
            x,y = route['at']
            assert (route.get('size', .25),route.get('drill',.15)) == (.25,.15)
            vias += 1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) (layers "F.Cu" "B.Cu") (net {net}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"088|via|{x}|{y}")}))')
            continue
        assert route['kind'] == 'track' and route['layer'] in ('F.Cu','B.Cu')
        assert route['width'] == .15
        for i,(a,b) in enumerate(zip(route['points'],route['points'][1:])):
            assert a != b
            length += math.dist(a,b)
            lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.15) (layer "{route["layer"]}") (net {net}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL, f"088|{j}|{i}|{a}|{b}")}))')
    assert vias == 2
    at = board.index('\n',board.rfind('  (segment '))+1
    return board[:at]+'\n'.join(lines)+'\n'+board[at:], {'net':'SD_D3_CARD','track_length_mm':round(length,3),'new_segments':len(lines)-vias,'new_vias':vias}

def main():
    board,route=build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text() == board
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert summary['candidate_sha256'] == native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected'] == 27
        print('PCB-MAIN candidate 088: PASS')
        return
    OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE/'PCB-MAIN_P2_SD_D3_RELIEF_087_CANDIDATE_REV_A.kicad_pro',PROJECT)
    native.BASE,native.OUT,native.CANDIDATE,native.PROJECT=BASE,OUT,CANDIDATE,PROJECT
    drc=native.check()
    assert drc == {'base_unconnected':28,'candidate_unconnected':27,'new_by_type':{},'new_errors':0,'erc_errors':0,'erc_violations':0},drc
    summary={'schema':'dioneya-pcb-main-sd-d3-top-088-v1','base_sha256':BASE_SHA,'candidate_sha256':native.sha(CANDIDATE),'route':route,'drc':drc,'review_b':'OPEN: end-to-end SDIO timing/skew and return, two small vias/DFM','candidate_only_via_rules':True,'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__ == '__main__': main()

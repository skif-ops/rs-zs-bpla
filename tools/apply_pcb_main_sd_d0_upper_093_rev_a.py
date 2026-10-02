#!/usr/bin/env python3
"""Candidate 093: join U24.1 SD_D0_CARD to R86.2 on F.Cu."""
from __future__ import annotations
import json,math,re,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_astar_077_rev_a as native
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D0-REPACK-092'
BOARD=BASE/'PCB-MAIN_P2_SD_D0_REPACK_092_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D0-UPPER-093'
CANDIDATE=OUT/'PCB-MAIN_P2_SD_D0_UPPER_093_CANDIDATE_REV_A.kicad_pcb'
PROJECT=OUT/'PCB-MAIN_P2_SD_D0_UPPER_093_CANDIDATE_REV_A.kicad_pro'
BASE_SHA='8af90eebff37cea2cb566ec14311163544f03d0cb3b4af5946dcb9befd67897e'

def build():
    assert native.sha(BOARD)==BASE_SHA
    spec=json.loads((OUT/'ROUTES.json').read_text())
    assert spec['schema']=='dioneya-pcb-main-route-093-v1' and len(spec['routes'])==1
    route=spec['routes'][0]
    assert route['kind']=='track' and route['net']=='SD_D0_CARD' and route['layer']=='F.Cu' and route['width']==.15
    assert route['points'][0]==[87.6,20.0] and route['points'][-1]==[85.0,22.9]
    board=BOARD.read_text()
    nets={name:int(code) for code,name in re.findall(r'^  \(net (\d+) "([^"]*)"\)',board,re.M)}
    lines=[];length=0.
    for i,(a,b) in enumerate(zip(route['points'],route['points'][1:])):
        length+=math.dist(a,b)
        lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.15) (layer "F.Cu") (net {nets["SD_D0_CARD"]}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"093|{i}|{a}|{b}")}))')
    at=board.index('\n',board.rfind('  (segment '))+1
    return board[:at]+'\n'.join(lines)+'\n'+board[at:],{'net':'SD_D0_CARD','length_mm':round(length,3),'new_vias':0,'new_segments':len(lines)}

def main():
    board,route=build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text()==board
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert summary['candidate_sha256']==native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected']==22
        print('PCB-MAIN candidate 093: PASS')
        return
    OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE/'PCB-MAIN_P2_SD_D0_REPACK_092_CANDIDATE_REV_A.kicad_pro',PROJECT)
    native.BASE,native.OUT,native.CANDIDATE,native.PROJECT=BASE,OUT,CANDIDATE,PROJECT
    drc=native.check()
    assert drc=={'base_unconnected':23,'candidate_unconnected':22,'new_by_type':{},'new_errors':0,'erc_errors':0,'erc_violations':0},drc
    summary={'schema':'dioneya-pcb-main-sd-d0-upper-093-v1','base_sha256':BASE_SHA,'candidate_sha256':native.sha(CANDIDATE),'route':route,'drc':drc,'review_b':'OPEN: SD D0 timing, return and ESD coupling','candidate_only_via_rules':True,'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

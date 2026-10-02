#!/usr/bin/env python3
"""Candidate 096: bridge the two main 3V3_DIGITAL islands across north F.Cu."""
from __future__ import annotations
import json,math,re,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_astar_077_rev_a as native
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-PDM-DATA1-095'
BOARD=BASE/'PCB-MAIN_P2_PDM_DATA1_095_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-3V3-NORTH-096'
CANDIDATE=OUT/'PCB-MAIN_P2_3V3_NORTH_096_CANDIDATE_REV_A.kicad_pcb'
PROJECT=OUT/'PCB-MAIN_P2_3V3_NORTH_096_CANDIDATE_REV_A.kicad_pro'
BASE_SHA='3c5941069ec5bcc63bbb81f0c7f2fbdfdf8433ea78acfdd760ecd6c8197637e9'

def build():
    assert native.sha(BOARD)==BASE_SHA
    spec=json.loads((OUT/'ROUTES.json').read_text())
    assert spec['schema']=='dioneya-pcb-main-route-096-v1' and spec['base_candidate']==95
    assert len(spec['routes'])==1 and spec['net']=='3V3_DIGITAL'
    route=spec['routes'][0]
    assert route['kind']=='track' and route['layer']=='F.Cu' and route['net']=='3V3_DIGITAL' and route['width']==.25
    points=route['points'];assert points[0]==[81.9,18.1] and points[-1]==[57.6,18.0]
    board=BOARD.read_text()
    nets={name:int(code) for code,name in re.findall(r'^  \(net (\d+) "([^"]*)"\)',board,re.M)}
    lines=[];length=0.
    for i,(a,b) in enumerate(zip(points,points[1:])):
        length+=math.dist(a,b)
        lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.25) (layer "F.Cu") (net {nets["3V3_DIGITAL"]}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"096|{i}|{a}|{b}")}))')
    assert round(length,3)==spec['length_mm'] and length<40
    at=board.index('\n',board.rfind('  (segment '))+1
    return board[:at]+'\n'.join(lines)+'\n'+board[at:],{'net':'3V3_DIGITAL','length_mm':round(length,3),'new_vias':0,'new_segments':len(lines)}

def main():
    board,route=build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text()==board
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert summary['candidate_sha256']==native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected']==19
        print('PCB-MAIN candidate 096: PASS')
        return
    OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE/'PCB-MAIN_P2_PDM_DATA1_095_CANDIDATE_REV_A.kicad_pro',PROJECT)
    native.BASE,native.OUT,native.CANDIDATE,native.PROJECT=BASE,OUT,CANDIDATE,PROJECT
    drc=native.check()
    assert drc=={'base_unconnected':20,'candidate_unconnected':19,'new_by_type':{},'new_errors':0,'erc_errors':0,'erc_violations':0},drc
    summary={'schema':'dioneya-pcb-main-3v3-north-096-v1','base_sha256':BASE_SHA,'candidate_sha256':native.sha(CANDIDATE),'route':route,'drc':drc,'review_b':'OPEN: 3V3 rail top-edge length, supply impedance and return-current review','candidate_only_via_rules':True,'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

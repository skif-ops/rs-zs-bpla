#!/usr/bin/env python3
"""Candidate 089: route NRST from R1.2 to TP_MCU_SWD with three candidate vias."""
from __future__ import annotations
import json,math,re,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_astar_077_rev_a as native
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D3-TOP-088'
BOARD=BASE/'PCB-MAIN_P2_SD_D3_TOP_088_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-NRST-089'
CANDIDATE=OUT/'PCB-MAIN_P2_NRST_089_CANDIDATE_REV_A.kicad_pcb'
PROJECT=OUT/'PCB-MAIN_P2_NRST_089_CANDIDATE_REV_A.kicad_pro'
BASE_SHA='6a2b1353fa3e0e71c98f4547f667a496f5aee2cad61bc080075cd64472f69e80'

def build():
    assert native.sha(BOARD)==BASE_SHA
    spec=json.loads((OUT/'ROUTES.json').read_text())
    assert spec['schema']=='dioneya-pcb-main-route-089-v1'
    assert len(spec['routes'])==6 and spec['routes'][0]['at']==[62,28.5]
    board=BOARD.read_text()
    nets={name:int(code) for code,name in re.findall(r'^  \(net (\d+) "([^"]*)"\)',board,re.M)}
    lines=[];length=0.;vias=0
    for j,route in enumerate(spec['routes']):
        assert route['net']=='NRST'
        net=nets['NRST']
        if route['kind']=='via':
            x,y=route['at'];vias+=1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) (layers "F.Cu" "B.Cu") (net {net}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"089|via|{j}|{x}|{y}")}))')
        else:
            assert route['kind']=='track' and route['layer'] in ('F.Cu','In3.Cu','B.Cu') and route['width']==.15
            for i,(a,b) in enumerate(zip(route['points'],route['points'][1:])):
                length+=math.dist(a,b)
                lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.15) (layer "{route["layer"]}") (net {net}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"089|{j}|{i}|{a}|{b}")}))')
    assert vias==3
    at=board.index('\n',board.rfind('  (segment '))+1
    return board[:at]+'\n'.join(lines)+'\n'+board[at:],{'net':'NRST','length_mm':round(length,3),'new_vias':vias,'new_segments':len(lines)-vias,'via_in_R1_pad':True}

def main():
    board,route=build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text()==board
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert summary['candidate_sha256']==native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected']==26
        print('PCB-MAIN candidate 089: PASS')
        return
    OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE/'PCB-MAIN_P2_SD_D3_TOP_088_CANDIDATE_REV_A.kicad_pro',PROJECT)
    native.BASE,native.OUT,native.CANDIDATE,native.PROJECT=BASE,OUT,CANDIDATE,PROJECT
    drc=native.check()
    assert drc=={'base_unconnected':27,'candidate_unconnected':26,'new_by_type':{},'new_errors':0,'erc_errors':0,'erc_violations':0},drc
    summary={'schema':'dioneya-pcb-main-nrst-089-v1','base_sha256':BASE_SHA,'candidate_sha256':native.sha(CANDIDATE),'route':route,'drc':drc,'review_b':'OPEN: reset-net integrity, R1.2 via-in-pad, DFM and return','candidate_only_via_rules':True,'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

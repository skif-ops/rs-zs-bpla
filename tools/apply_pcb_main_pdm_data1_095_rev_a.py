#!/usr/bin/env python3
"""Candidate 095: close PDM_DATA1_1V8 through the audio-side corridor."""
from __future__ import annotations
import json,math,re,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_astar_077_rev_a as native
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-AAD-R18-094'
BOARD=BASE/'PCB-MAIN_P2_AAD_R18_094_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-PDM-DATA1-095'
CANDIDATE=OUT/'PCB-MAIN_P2_PDM_DATA1_095_CANDIDATE_REV_A.kicad_pcb'
PROJECT=OUT/'PCB-MAIN_P2_PDM_DATA1_095_CANDIDATE_REV_A.kicad_pro'
BASE_SHA='23ac8f527d669e5c8e7887695f80b5b0cb975a04625917baaef4e8c229939a6f'

def build():
    assert native.sha(BOARD)==BASE_SHA
    spec=json.loads((OUT/'ROUTES.json').read_text())
    assert spec['schema']=='dioneya-pcb-main-route-095-v1' and len(spec['routes'])==15
    assert spec['routes'][0]['points'][0]==[55.8231,42.975]
    assert spec['routes'][-1]['points'][-1]==[8.2,37.95]
    board=BOARD.read_text()
    nets={name:int(code) for code,name in re.findall(r'^  \(net (\d+) "([^"]*)"\)',board,re.M)}
    lines=[];length=0.;vias=0
    for j,route in enumerate(spec['routes']):
        assert route['net']=='PDM_DATA1_1V8'
        net=nets['PDM_DATA1_1V8']
        if route['kind']=='via':
            x,y=route['at'];vias+=1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) (layers "F.Cu" "B.Cu") (net {net}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"095|via|{j}|{x}|{y}")}))')
        else:
            assert route['kind']=='track' and route['layer'] in ('F.Cu','In3.Cu','B.Cu') and route['width']==.15
            for i,(a,b) in enumerate(zip(route['points'],route['points'][1:])):
                length+=math.dist(a,b)
                lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.15) (layer "{route["layer"]}") (net {net}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"095|{j}|{i}|{a}|{b}")}))')
    assert vias==7
    at=board.index('\n',board.rfind('  (segment '))+1
    return board[:at]+'\n'.join(lines)+'\n'+board[at:],{'net':'PDM_DATA1_1V8','length_mm':round(length,3),'new_vias':vias,'new_segments':len(lines)-vias}

def main():
    board,route=build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text()==board
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert summary['candidate_sha256']==native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected']==20
        print('PCB-MAIN candidate 095: PASS')
        return
    OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE/'PCB-MAIN_P2_AAD_R18_094_CANDIDATE_REV_A.kicad_pro',PROJECT)
    native.BASE,native.OUT,native.CANDIDATE,native.PROJECT=BASE,OUT,CANDIDATE,PROJECT
    drc=native.check()
    assert drc=={'base_unconnected':21,'candidate_unconnected':20,'new_by_type':{},'new_errors':0,'erc_errors':0,'erc_violations':0},drc
    summary={'schema':'dioneya-pcb-main-pdm-data1-095-v1','base_sha256':BASE_SHA,'candidate_sha256':native.sha(CANDIDATE),'route':route,'drc':drc,'review_b':'OPEN: PDM audio-domain return, skew/coupling and small-via DFM','candidate_only_via_rules':True,'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

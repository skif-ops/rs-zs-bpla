#!/usr/bin/env python3
"""Candidate 094: move R18 and route AAD_CFG_1V8_FANOUT to its B.Cu branch."""
from __future__ import annotations
import json,math,re,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_astar_077_rev_a as native
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D0-UPPER-093'
BOARD=BASE/'PCB-MAIN_P2_SD_D0_UPPER_093_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-AAD-R18-094'
CANDIDATE=OUT/'PCB-MAIN_P2_AAD_R18_094_CANDIDATE_REV_A.kicad_pcb'
PROJECT=OUT/'PCB-MAIN_P2_AAD_R18_094_CANDIDATE_REV_A.kicad_pro'
BASE_SHA='277ffd2e92bd3096e1607fdc832b21aeb019047e9df7dfb359d63d2bd350cfc2'
OLD='    (tstamp 18974097-31b3-45bb-a0a9-850cf0445e30)\n    (at 64.75 45.25)'

def build():
    assert native.sha(BOARD)==BASE_SHA
    spec=json.loads((OUT/'ROUTES.json').read_text())
    assert spec['schema']=='dioneya-pcb-main-route-094-v1' and spec['move']=={'reference':'R18','from':[64.75,45.25],'to':[65.8,45.0]}
    assert len(spec['routes'])==10 and spec['routes'][0]['net']=='AAD_CFG_1V8_U7'
    board=BOARD.read_text()
    assert board.count(OLD)==1
    board=board.replace(OLD,OLD.split('\n')[0]+'\n    (at 65.8 45.0)')
    nets={name:int(code) for code,name in re.findall(r'^  \(net (\d+) "([^"]*)"\)',board,re.M)}
    lines=[];lengths={'AAD_CFG_1V8_U7':0.,'AAD_CFG_1V8_FANOUT':0.};vias=0
    for j,route in enumerate(spec['routes']):
        net=route['net'];assert net in lengths
        if route['kind']=='via':
            x,y=route['at'];vias+=1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) (layers "F.Cu" "B.Cu") (net {nets[net]}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"094|via|{j}|{x}|{y}")}))')
        else:
            assert route['kind']=='track' and route['layer'] in ('F.Cu','In3.Cu','B.Cu') and route['width']==.15
            for i,(a,b) in enumerate(zip(route['points'],route['points'][1:])):
                lengths[net]+=math.dist(a,b)
                lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.15) (layer "{route["layer"]}") (net {nets[net]}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"094|{j}|{i}|{a}|{b}")}))')
    assert vias==4
    at=board.index('\n',board.rfind('  (segment '))+1
    return board[:at]+'\n'.join(lines)+'\n'+board[at:],{'moved_R18_mm':[65.8,45.0],'added_length_mm':{k:round(v,3) for k,v in lengths.items()},'new_vias':vias,'new_segments':len(lines)-vias}

def main():
    board,route=build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text()==board
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert summary['candidate_sha256']==native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected']==21
        print('PCB-MAIN candidate 094: PASS')
        return
    OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE/'PCB-MAIN_P2_SD_D0_UPPER_093_CANDIDATE_REV_A.kicad_pro',PROJECT)
    native.BASE,native.OUT,native.CANDIDATE,native.PROJECT=BASE,OUT,CANDIDATE,PROJECT
    drc=native.check()
    assert drc=={'base_unconnected':22,'candidate_unconnected':21,'new_by_type':{},'new_errors':0,'erc_errors':0,'erc_violations':0},drc
    summary={'schema':'dioneya-pcb-main-aad-r18-094-v1','base_sha256':BASE_SHA,'candidate_sha256':native.sha(CANDIDATE),'route':route,'drc':drc,'review_b':'OPEN: AAD configuration, audio/LoRa return and R18 placement/DFM','candidate_only_via_rules':True,'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

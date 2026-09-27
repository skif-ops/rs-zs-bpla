#!/usr/bin/env python3
"""Candidate 092: free SD_D0_CARD by rerouting the SD_D2_U1 crossing."""
from __future__ import annotations
import json,math,re,shutil,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_astar_077_rev_a as native
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-USB-DM-091'
BOARD=BASE/'PCB-MAIN_P2_USB_DM_091_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D0-REPACK-092'
CANDIDATE=OUT/'PCB-MAIN_P2_SD_D0_REPACK_092_CANDIDATE_REV_A.kicad_pcb'
PROJECT=OUT/'PCB-MAIN_P2_SD_D0_REPACK_092_CANDIDATE_REV_A.kicad_pro'
BASE_SHA='ba9a0869e472b9ce5a9040024981d60b3dd573f644270b74f9023c240fcaf28d'
SEG=re.compile(r'^  \(segment \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(width ([\d.]+)\) \(layer "([^"]+)"\) \(net (\d+)\) .+\)$')

def build():
    assert native.sha(BOARD)==BASE_SHA
    spec=json.loads((OUT/'ROUTES.json').read_text())
    assert spec['schema']=='dioneya-pcb-main-route-092-v1' and len(spec['removed_segments'])==8
    board=BOARD.read_text()
    nets={name:int(code) for code,name in re.findall(r'^  \(net (\d+) "([^"]*)"\)',board,re.M)}
    pending={(r['net'],r['layer'],tuple(r['start']),tuple(r['end'])) for r in spec['removed_segments']}
    assert len(pending)==8
    kept=[]
    for line in board.splitlines(keepends=True):
        m=SEG.match(line.rstrip('\n'))
        if m:
            x,y,u,v,w,layer,code=m.groups()
            key=('SD_D2_U1',layer,(float(x),float(y)),(float(u),float(v)))
            if int(code)==nets['SD_D2_U1'] and key in pending:
                assert float(w)==.15
                pending.remove(key)
                continue
        kept.append(line)
    assert not pending,pending
    board=''.join(kept)
    lines=[];lengths={'SD_D0_CARD':0.,'SD_D2_U1':0.};vias=0
    for j,route in enumerate(spec['routes']):
        net=route['net'];assert net in lengths
        if route['kind']=='via':
            x,y=route['at'];vias+=1
            lines.append(f'  (via (at {x} {y}) (size 0.25) (drill 0.15) (layers "F.Cu" "B.Cu") (net {nets[net]}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"092|via|{j}|{x}|{y}")}))')
        else:
            assert route['kind']=='track' and route['layer'] in ('F.Cu','In3.Cu','B.Cu') and route['width']==.15
            for i,(a,b) in enumerate(zip(route['points'],route['points'][1:])):
                lengths[net]+=math.dist(a,b)
                lines.append(f'  (segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width 0.15) (layer "{route["layer"]}") (net {nets[net]}) (tstamp {uuid.uuid5(uuid.NAMESPACE_URL,f"092|{j}|{i}|{a}|{b}")}))')
    assert vias==4
    at=board.index('\n',board.rfind('  (segment '))+1
    return board[:at]+'\n'.join(lines)+'\n'+board[at:],{'removed_sd_d2_segments':8,'added_length_mm':{k:round(v,3) for k,v in lengths.items()},'new_vias':vias,'new_segments':len(lines)-vias}

def main():
    board,route=build()
    if '--check' in sys.argv:
        assert CANDIDATE.read_text()==board
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert summary['candidate_sha256']==native.sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected']==23
        print('PCB-MAIN candidate 092: PASS')
        return
    OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(board)
    shutil.copyfile(BASE/'PCB-MAIN_P2_USB_DM_091_CANDIDATE_REV_A.kicad_pro',PROJECT)
    native.BASE,native.OUT,native.CANDIDATE,native.PROJECT=BASE,OUT,CANDIDATE,PROJECT
    drc=native.check()
    assert drc=={'base_unconnected':24,'candidate_unconnected':23,'new_by_type':{},'new_errors':0,'erc_errors':0,'erc_violations':0},drc
    summary={'schema':'dioneya-pcb-main-sd-d0-repack-092-v1','base_sha256':BASE_SHA,'candidate_sha256':native.sha(CANDIDATE),'route':route,'drc':drc,'review_b':'OPEN: SD_D0/SD_D2 timing, skew, return and via DFM','candidate_only_via_rules':True,'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

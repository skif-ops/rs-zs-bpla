#!/usr/bin/env python3
"""Probe still-open PCB-MAIN 088 connections using the pinned grid router."""
import json, math, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import probe_pcb_main_astar_074_rev_a as p
from pcb_gapfill_router_rev_a import GapFillRouter
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D3-TOP-088'
BOARD=BASE/'PCB-MAIN_P2_SD_D3_TOP_088_CANDIDATE_REV_A.kicad_pcb'
DRC=BASE/'drc_candidate.json'
board,_=p.geo.load(BOARD)
g=p.geometry(board)
gaps=json.loads(DRC.read_text())['unconnected_items']
results=[]
for index,v in enumerate(gaps):
    a,b=v['items']
    name=a['description'].split('[')[1].split(']')[0]
    x=(a['pos']['x'],a['pos']['y'])
    y=(b['pos']['x'],b['pos']['y'])
    width=.25 if name in ('3V3_DIGITAL','1V8_MIC','VCORE_1V1') else .15
    r=GapFillRouter(g,['F.Cu','In3.Cu','B.Cu'],width,.20,.25,.15,.6,.25,allow_via_in_own_pad=True)
    st=time.monotonic()
    ok=r.route(name,x,y)
    record={'index':index,'net':name,'gap_mm':round(math.dist(x,y),3),'routed':ok,'seconds':round(time.monotonic()-st,2)}
    if ok:
        record['length_mm']=round(sum(math.dist(a,b) for kind,layer,n,w,pts in r.routed if kind=='track' for a,b in zip(pts,pts[1:])),3)
        record['vias']=sum(kind=='via' for kind,*_ in r.routed)
        record['items']=[{'kind':kind,'layer':layer,'net':n,'width_or_size_mm':w,'points_mm':pts} for kind,layer,n,w,pts in r.routed]
    print('PROBE',json.dumps({k:v for k,v in record.items() if k!='items'}),flush=True)
    results.append(record)
(BASE/'PROBES_089.json').write_text(json.dumps(results,indent=2)+'\n')
print('TOTAL_ROUTABLE',sum(z['routed'] for z in results),flush=True)

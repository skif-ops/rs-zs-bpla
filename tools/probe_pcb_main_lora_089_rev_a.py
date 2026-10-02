#!/usr/bin/env python3
"""Probe LORA_DIO1 In3 relief around the U1.27 3V3 via on candidate 088."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import probe_pcb_main_astar_074_rev_a as p
from pcb_gapfill_router_rev_a import GapFillRouter
BOARD=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D3-TOP-088/PCB-MAIN_P2_SD_D3_TOP_088_CANDIDATE_REV_A.kicad_pcb'
board,_=p.geo.load(BOARD);g=p.geometry(board)
def inside(t):
    return t['net']=='LORA_DIO1' and t['layer']=='In3.Cu' and all(46.2<=v[0]<=46.9 and 34.2<=v[1]<=39.3 for v in (t['start'],t['end']))
removed=[t for t in g['tracks'] if inside(t)]
g['tracks']=[t for t in g['tracks'] if not inside(t)]
g['vias'].append({'net':'3V3_DIGITAL','size':.25,'pos':[46.5,37.6]})
print('LORA_RELIEF_REMOVED',len(removed),json.dumps(removed),flush=True)
for layers in [['In3.Cu'],['F.Cu','In3.Cu','B.Cu']]:
    r=GapFillRouter(g,layers,.15,.2,.25,.15,.6,.25,allow_via_in_own_pad=True)
    st=time.monotonic();ok=r.route('LORA_DIO1',(46.3,34.3),(46.8,39.2))
    print('LORA_RELIEF_RESULT',layers,ok,round(time.monotonic()-st,2),json.dumps(r.routed),flush=True)

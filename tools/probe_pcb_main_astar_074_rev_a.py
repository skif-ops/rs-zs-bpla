#!/usr/bin/env python3
"""Explore DRC gaps on the 073 board; outputs reviewable proposed routes only."""
import json
import math
import sys
from pathlib import Path

from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import pcb_main_ground_domain_002_rev_a as geo
from pcb_gapfill_router_rev_a import GapFillRouter

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-UUID-073'
BOARD = BASE / 'PCB-MAIN_P2_UUID_073_CANDIDATE_REV_A.kicad_pcb'
DRC = BASE / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-ASTAR-074'


def geometry(board):
    names = {n.number: n.name for n in board.nets}
    g = {'outline': [0, 0, 110, 75], 'pads': [], 'tracks': [], 'vias': [], 'holes': []}
    for fp in board.footprints:
        for pad in fp.pads:
            shape = geo.pad_geometry(fp, pad)
            layers = sorted(geo.pad_layers(pad))
            g['pads'].append({'net': pad.net.name if pad.net else None, 'layers': layers,
                              'pos': [shape.centroid.x, shape.centroid.y],
                              'poly': list(map(list, shape.exterior.coords[:-1])) if isinstance(shape, Polygon) else []})
            if pad.drill is not None and getattr(pad.drill, 'diameter', 0):
                g['holes'].append([shape.centroid.x, shape.centroid.y])
    for item in board.traceItems:
        net = names.get(item.net)
        if type(item).__name__ == 'Via':
            g['vias'].append({'net': net, 'size': item.size, 'pos': [item.position.X,item.position.Y]})
        else:
            g['tracks'].append({'net': net, 'layer': item.layer, 'width': item.width,
                                'start': [item.start.X,item.start.Y], 'end':[item.end.X,item.end.Y]})
    return g


def main():
    board, _ = geo.load(BOARD)
    g = geometry(board)
    gaps = json.loads(DRC.read_text())['unconnected_items']
    pairs = []
    for i, gap in enumerate(gaps):
        a,b = gap['items']
        name = a['description'].split('[')[1].split(']')[0]
        p,q = a['pos'],b['pos']
        distance=math.hypot(p['x']-q['x'],p['y']-q['y'])
        pairs.append((distance,i,name,(p['x'],p['y']),(q['x'],q['y'])))
    if '--list' in sys.argv:
        for pair in sorted(pairs): print(pair)
        return
    selected = [int(s) for s in sys.argv[1:] if s.isdigit()] or [i for d,i,*_ in sorted(pairs)[:10]]
    results=[]
    shared = None
    for distance,i,net,a,b in sorted(pairs):
        if i not in selected: continue
        print('TRY',i,net,round(distance,2),flush=True)
        if shared is None or '--sequential' not in sys.argv:
            router=GapFillRouter(g,['F.Cu','B.Cu'] if '--fb' in sys.argv else ['F.Cu','In3.Cu','B.Cu'],
                                 width=.25 if net in ('3V3_DIGITAL','1V8_MIC','VCORE_1V1') else .15,
                                 clearance=.20,via_size=.25,via_drill=.15,edge_keep=.60,hole_keep=.25,
                                 allow_via_in_own_pad=True)
            if '--sequential' in sys.argv: shared = router
        else: router = shared
        before = len(router.routed)
        passed=router.route(net,a,b)
        print('RESULT',i,net,passed,len(router.routed)-before,flush=True)
        if passed:
            results.append({'index':i,'net':net,'distance_mm':distance,'items':[
                {'kind':kind,'layer':layer,'width_or_size_mm':w,'points_mm':pts}
                for kind,layer,_net,w,pts in router.routed[before:]]})
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'PROBES.json').write_text(json.dumps(results,indent=2)+'\n')
    print('wrote',len(results),'routes',flush=True)


if __name__=='__main__': main()

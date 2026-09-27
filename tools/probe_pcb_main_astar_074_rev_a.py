#!/usr/bin/env python3
"""Explore DRC gaps on the 073 board; outputs reviewable proposed routes only."""
import json
import math
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import pcb_main_ground_domain_002_rev_a as geo
from pcb_gapfill_router_rev_a import GapFillRouter

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-UUID-073'
BOARD = BASE / 'PCB-MAIN_P2_UUID_073_CANDIDATE_REV_A.kicad_pcb'
DRC = BASE / 'drc_candidate.json'
OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-ASTAR-074'


class GroundAwareRouter(GapFillRouter):
    def __init__(self, *args, reference_masks, **kwargs):
        super().__init__(*args, **kwargs)
        self.reference_masks = reference_masks

    def _blocked(self, net):
        track, via = super()._blocked(net)
        for k, layer in enumerate(self.layers):
            track[k] |= ~self.reference_masks[layer]
        via |= ~(self.reference_masks['F.Cu'] & self.reference_masks['B.Cu'])
        return track, via


def masks(board, domain, layers):
    x = np.arange(1101) * .1
    y = np.arange(751) * .1
    gx, gy = np.meshgrid(x, y, indexing='ij')
    result = {}
    for layer in layers:
        ground_layer = {'F.Cu':'In1.Cu','In3.Cu':'In2.Cu','B.Cu':'In4.Cu'}[layer]
        if ground_layer == 'In2.Cu':
            shape = geo.zone_outline(board, 'GND_MIC', ground_layer)
        elif domain.startswith(('CROSS_', 'RETURN_AT_LOAD_')):
            shapes = [geo.zone_outline(board, name, ground_layer) for name in ('GND_DIGITAL','GND_MODEM')
                      if any(z.netName == name and z.layers == [ground_layer] for z in board.zones)]
            shape = shapes[0].union(*shapes[1:])
        else:
            shape = geo.zone_outline(board, domain, ground_layer)
        result[layer] = shapely.intersects_xy(shape, gx, gy)
    return result


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
    global BASE, BOARD, DRC, OUT
    if '--base=074' in sys.argv:
        BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-ASTAR-074'
        BOARD = BASE / 'PCB-MAIN_P2_ASTAR_074_CANDIDATE_REV_A.kicad_pcb'
        DRC = BASE / 'drc_candidate.json'
        OUT = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-ASTAR-075'
    board, domains = geo.load(BOARD)
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
    selected = ([i for _,i,*_ in pairs] if '--all' in sys.argv else
                [int(s) for s in sys.argv[1:] if s.isdigit()] or [i for d,i,*_ in sorted(pairs)[:10]])
    results=[]
    shared = None
    mask_cache = {}
    for distance,i,net,a,b in sorted(pairs):
        if i not in selected: continue
        print('TRY',i,net,round(distance,2),flush=True)
        layers=['F.Cu','B.Cu'] if '--fb' in sys.argv else ['F.Cu','In3.Cu','B.Cu']
        if shared is None or '--sequential' not in sys.argv:
            Router = GroundAwareRouter if '--ref' in sys.argv else GapFillRouter
            extra = {}
            if '--ref' in sys.argv:
                key=(domains[net],tuple(layers))
                if key not in mask_cache: mask_cache[key]=masks(board,*key)
                extra['reference_masks']=mask_cache[key]
            router=Router(g,layers,
                                 width=.25 if net in ('3V3_DIGITAL','1V8_MIC','VCORE_1V1') else .15,
                                 clearance=.20,via_size=.25,via_drill=.15,edge_keep=.60,hole_keep=.25,
                                 allow_via_in_own_pad=True,**extra)
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

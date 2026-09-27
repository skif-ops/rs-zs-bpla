#!/usr/bin/env python3
"""Screen straight connections among native DRC gaps of the cleaned 073 board."""
import json
import sys
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import pcb_main_ground_domain_002_rev_a as geo

BASE = ROOT / 'hardware/kicad/candidates/PCB-ROUTING-P2-UUID-073'
BOARD = BASE / 'PCB-MAIN_P2_UUID_073_CANDIDATE_REV_A.kicad_pcb'
DRC = BASE / 'drc_candidate.json'


def main():
    board, domains = geo.load(BOARD)
    names = {n.number: n.name for n in board.nets}
    objects = {}
    obstacle = {layer: [] for layer in geo.LAYERS}
    owners = {layer: [] for layer in geo.LAYERS}
    for fp in board.footprints:
        for pad in fp.pads:
            net = pad.net.name if pad.net else None
            shape = geo.pad_geometry(fp, pad)
            layers = geo.pad_layers(pad)
            objects[pad.tstamp] = (net, shape, layers)
            for layer in layers:
                obstacle[layer].append(shape)
                owners[layer].append(net)
    for item in board.traceItems:
        net = names.get(item.net)
        if type(item).__name__ == 'Via':
            shape = Point(item.position.X, item.position.Y).buffer(item.size / 2)
            layers = set(geo.LAYERS)
        else:
            shape = LineString([(item.start.X, item.start.Y), (item.end.X, item.end.Y)]).buffer(item.width / 2)
            layers = {item.layer}
        objects[item.tstamp] = (net, shape, layers)
        for layer in layers:
            obstacle[layer].append(shape)
            owners[layer].append(net)
    indices = {layer: STRtree(obstacle[layer]) for layer in geo.LAYERS}
    candidates = []
    for k, gap in enumerate(json.loads(DRC.read_text())['unconnected_items']):
        a, b = (objects.get(i['uuid']) for i in gap['items'])
        if not a or not b or a[0] != b[0]:
            continue
        net = a[0]
        for layer in a[2] & b[2] & {'F.Cu','B.Cu','In3.Cu'}:
            start, end = nearest_points(a[1], b[1])
            p, q = (round(start.x, 4), round(start.y, 4)), (round(end.x, 4), round(end.y, 4))
            line = LineString([p, q])
            width = .25 if net in ('3V3_DIGITAL','1V8_MIC','VCORE_1V1') else .15
            body = line.buffer(width/2 + .20 - 1e-5)
            hits = [owners[layer][int(j)] for j in indices[layer].query(body)
                    if owners[layer][int(j)] != net and obstacle[layer][int(j)].intersects(body)]
            if not hits:
                candidates.append((round(line.length,3), k, net, layer, p, q))
    for item in sorted(candidates):
        print(*item)
    print('candidates', len(candidates))


if __name__ == '__main__': main()

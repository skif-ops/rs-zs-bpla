#!/usr/bin/env python3
"""One bounded U1 3V3 escape to the existing 3V3 test point, experimental only."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as gate
import pcb_main_ground_domain_002_rev_a as geo
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-USB-009/PCB-MAIN_P2_USB_009_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-U1-POWER-010'
CANDIDATE=OUT/'PCB-MAIN_P2_U1_POWER_010_CANDIDATE_REV_A.kicad_pcb'
BASE_SHA='c42e099cd366556055db0947ec5e99a0b774bc9a9019723c78ceadd9ca38122b'
NAMESPACE=uuid.UUID('63fde830-fca6-46cd-b19c-2442114b437c')
NET='3V3_DIGITAL'; WIDTH=.25
POINTS=((44.25,26.5),(44.34,23.5),(44.34,22.5),(43.64,21.8),(42.44,21.3),(38.04,20.9),(35.54,23.0))

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def check_geometry():
    from shapely.geometry import LineString,Point
    from shapely.strtree import STRtree
    b,_=geo.load(BASE)
    obstacles={l:[] for l in geo.LAYERS};owners={l:[] for l in geo.LAYERS}
    for fp in b.footprints:
        for p in fp.pads:
            n=p.net.name if p.net else None
            for l in geo.pad_layers(p):
                obstacles[l].append(geo.pad_geometry(fp,p));owners[l].append(n)
    for n,k,l,g,r in geo.items(b):
        for layer in (geo.LAYERS if k=='via' else (l,)):
            obstacles[layer].append(g.buffer(r.size/2 if k=='via' else r.width/2,8));owners[layer].append(n)
    for layer,shape in (('B.Cu',LineString(POINTS).buffer(WIDTH/2+.2,8)),
                        *((l,Point(POINTS[0]).buffer(.125+.2,8)) for l in geo.LAYERS)):
        index=STRtree(obstacles[layer]);bad=[owners[layer][int(i)] for i in index.query(shape)
                if owners[layer][int(i)]!=NET and obstacles[layer][int(i)].intersects(shape)]
        assert not bad,(layer,bad[:10])
    ref=geo.zone_outline(b,'GND_DIGITAL','In4.Cu')
    assert LineString(POINTS).difference(ref).length<1e-6,'In4 reference gap'

def build():
    assert sha(BASE)==BASE_SHA
    check_geometry()
    lines=BASE.read_text().splitlines()
    net=int(re.search(r'^  \(net (\d+) "3V3_DIGITAL"\)',BASE.read_text(),re.M).group(1))
    new=[]
    for j,(a,b) in enumerate(zip(POINTS,POINTS[1:])):
        new.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) (width {WIDTH:g}) (layer "B.Cu") (net {net}) (tstamp {uuid.uuid5(NAMESPACE,f"track|{j}")}))')
    i=max(j for j,line in enumerate(lines) if line.startswith('  (segment '))+1
    lines[i:i]=new
    i=max(j for j,line in enumerate(lines) if line.startswith('  (via '))+1
    lines.insert(i,f'  (via (at 44.25 26.5) (size 0.25) (drill 0.15) (layers "F.Cu" "B.Cu") (net {net}) (tstamp {uuid.uuid5(NAMESPACE,"via|0")}))')
    return '\n'.join(lines)+'\n'

def run_drc():
    work=ROOT/'hardware/kicad/native/_p2_u1_power_010'
    shutil.rmtree(work,ignore_errors=True)
    shutil.copytree(ROOT/'hardware/kicad/native/PCB-MAIN',work)
    try:
        rel=str(work.relative_to(ROOT))
        shutil.copyfile(BASE,work/'base.kicad_pcb')
        shutil.copyfile(CANDIDATE,work/'candidate.kicad_pcb')
        project=json.loads((work/'PCB-MAIN.kicad_pro').read_text())
        rules=project.setdefault('board',{}).setdefault('design_settings',{}).setdefault('rules',{})
        rules.update({'min_via_diameter':.25,'min_through_hole_diameter':.15,'min_via_annular_width':.05})
        overlay=json.dumps(project,indent=2,sort_keys=True)+'\n'
        (OUT/'PCB-MAIN_P2_U1_POWER_010_CANDIDATE_REV_A.kicad_pro').write_text(overlay)
        for n in ('base','candidate'):
            (work/f'{n}.kicad_pro').write_text(overlay)
            for command in (('/usr/bin/python3','tools/pcb_main_ground_domain_002_stage_rev_a.py','fill',f'{rel}/{n}.kicad_pcb',f'{rel}/{n}.kicad_pcb'),
                            ('kicad-cli','pcb','drc','--format','json','--severity-all','-o',f'{rel}/drc_{n}.json',f'{rel}/{n}.kicad_pcb')):
                result=gate.docker(*command)
                assert result.returncode==0,(command,result.stdout[-1000:],result.stderr[-1000:])
        gate.docker('chmod','-R','a+rwX',rel)
        base=json.loads((work/'drc_base.json').read_text());report=json.loads((work/'drc_candidate.json').read_text())
        shutil.copyfile(work/'drc_candidate.json',OUT/'drc_candidate.json')
        (bfp,bu),(cfp,cu)=gate.drc_fingerprints(base),gate.drc_fingerprints(report)
        novel=[(key,count-bfp.get(key,0)) for key,count in cfp.items() if count>bfp.get(key,0)]
        return {'base_unconnected':bu,'candidate_unconnected':cu,
                'new_by_type':dict(Counter({f'{key[0]}:{key[1]}':count for key,count in novel})),
                'new_errors':sum(count for key,count in novel if key[0]=='error')}
    finally:
        gate.docker('rm','-rf',str(work.relative_to(ROOT)))
        shutil.rmtree(work,ignore_errors=True)

def main():
    if '--check' in sys.argv:
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert CANDIDATE.read_text()==build() and summary['candidate_sha256']==sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected']<summary['drc']['base_unconnected']
        assert summary['drc']['new_by_type']=={}
        print('PCB-MAIN U1 power 010: PASS',summary['drc']);return
    gate.deps();OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(build())
    drc=run_drc()
    summary={'schema':'dioneya-pcb-main-u1-power-010-v1','base_sha256':BASE_SHA,
             'candidate_sha256':sha(CANDIDATE),'3v3_route_length_mm':13.97,'width_mm':WIDTH,
             'vias_0_25_0_15':1,'drc':drc,'candidate_only_via_rules':True,
             'power_integrity_review':'OPEN','via_in_pad_dfm_review':'OPEN',
             'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    assert drc['candidate_unconnected']<drc['base_unconnected'] and not drc['new_by_type'],drc
    print(summary)

if __name__=='__main__':main()

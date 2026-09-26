#!/usr/bin/env python3
"""Turn C7 toward U1.6, tie its 3V3 pad and restore the short ground return."""
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
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-CELL-DBG-011/PCB-MAIN_P2_CELL_DBG_011_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-U1-C7-013'
CANDIDATE=OUT/'PCB-MAIN_P2_U1_C7_013_CANDIDATE_REV_A.kicad_pcb'
BASE_SHA='ad6cbb021f9ba8fa3a3b4c18b0820e49c864ea8113a55b0645e37f63928fe0d1'
NAMESPACE=uuid.UUID('40ec670d-4db6-4c3b-a1db-02a2187513fd')
RIP_GND={'48dd2539-6322-4978-88ef-5db8b6dbf405','c7413a3a-4af0-45fb-b97f-bf7537c203f1'}
ROUTES=(
    ('3V3_DIGITAL',.25,((42.875,26.5),(44.25,26.5))),
    ('GND_DIGITAL',.25,((42.225,26.5),(42.225,26.9),(42.425,27.1),(43.1,27.1))),
)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_geometry(source):
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as d:
        path=Path(d)/'candidate.kicad_pcb'
        path.write_text(source)
        b,_=geo.load(path)
    pads=[]; owners=[]
    for fp in b.footprints:
        for p in fp.pads:
            if 'F.Cu' in geo.pad_layers(p):
                pads.append(geo.pad_geometry(fp,p))
                owners.append(p.net.name if p.net else None)
    for n,k,l,g,r in geo.items(b):
        if k=='via' or l=='F.Cu':
            pads.append(g.buffer(r.size/2 if k=='via' else r.width/2,8));owners.append(n)
    index=STRtree(pads)
    for net,width,points in ROUTES:
        line=LineString(points);shape=line.buffer(width/2+.20,8)
        bad=[owners[int(i)] for i in index.query(shape)
             if owners[int(i)]!=net and pads[int(i)].intersects(shape)]
        assert not bad,(net,bad[:8])
        ref=geo.zone_outline(b,'GND_DIGITAL','In1.Cu')
        assert line.difference(ref).length<1e-6,(net,'reference gap')

def build():
    assert sha(BASE)==BASE_SHA
    source=BASE.read_text()
    ref=source.index('(fp_text reference "C7"')
    start=source.rfind('\n  (footprint ',0,ref);end=source.index('\n  (footprint ',ref)
    fp=source[start:end]
    assert fp.count('(at 42.25 26.5)')==1
    source=source[:start]+fp.replace('(at 42.25 26.5)','(at 42.55 26.5 180)')+source[end:]
    lines=source.splitlines()
    kept=[line for line in lines if not
          (line.startswith('  (segment ') and any(f'(tstamp {t})' in line for t in RIP_GND))]
    assert len(lines)-len(kept)==len(RIP_GND)
    nets={n:int(code) for code,n in re.findall(r'^  \(net (\d+) "([^"]*)"\)',source,re.M)}
    segments=[]
    for k,(net,width,points) in enumerate(ROUTES):
        for j,(a,b) in enumerate(zip(points,points[1:])):
            segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) '
                            f'(width {width:g}) (layer "F.Cu") (net {nets[net]}) '
                            f'(tstamp {uuid.uuid5(NAMESPACE,f"route|{k}|{j}")}))')
    i=max(j for j,line in enumerate(kept) if line.startswith('  (segment '))+1
    kept[i:i]=segments
    lines=kept
    check_geometry('\n'.join(lines)+'\n')
    return '\n'.join(lines)+'\n'

def run_drc():
    work=ROOT/'hardware/kicad/native/_p2_u1_c7_013'
    shutil.rmtree(work,ignore_errors=True)
    shutil.copytree(ROOT/'hardware/kicad/native/PCB-MAIN',work)
    try:
        rel=str(work.relative_to(ROOT))
        shutil.copyfile(BASE,work/'base.kicad_pcb')
        shutil.copyfile(CANDIDATE,work/'candidate.kicad_pcb')
        # Carry forward the explicit candidate-only USB/U1 via-process overlay.
        project=json.loads((work/'PCB-MAIN.kicad_pro').read_text())
        rules=project.setdefault('board',{}).setdefault('design_settings',{}).setdefault('rules',{})
        rules.update({'min_via_diameter':.25,'min_through_hole_diameter':.15,'min_via_annular_width':.05})
        overlay=json.dumps(project,indent=2,sort_keys=True)+'\n'
        (OUT/'PCB-MAIN_P2_U1_C7_013_CANDIDATE_REV_A.kicad_pro').write_text(overlay)
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
        by_type=Counter()
        for key,count in novel:by_type[f'{key[0]}:{key[1]}']+=count
        return {'base_unconnected':bu,'candidate_unconnected':cu,'new_by_type':dict(by_type),
                'new_errors':sum(count for key,count in novel if key[0]=='error')}
    finally:
        gate.docker('rm','-rf',str(work.relative_to(ROOT)))
        shutil.rmtree(work,ignore_errors=True)

def main():
    if '--check' in sys.argv:
        summary=json.loads((OUT/'SUMMARY.json').read_text())
        assert CANDIDATE.read_text()==build() and summary['candidate_sha256']==sha(CANDIDATE)
        assert summary['drc']['candidate_unconnected']<summary['drc']['base_unconnected']
        assert not summary['drc']['new_by_type']
        print('PCB-MAIN U1 C7 relief 013: PASS',summary['drc']);return
    gate.deps();OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(build())
    drc=run_drc()
    summary={'schema':'dioneya-pcb-main-u1-c7-relief-013-v1','base_sha256':BASE_SHA,
             'candidate_sha256':sha(CANDIDATE),'moved_c7_mm':[.3,0],'rotated_c7_deg':180,
             'ripped_ground_tracks':len(RIP_GND),'new_short_tracks':sum(len(r[2])-1 for r in ROUTES),
             'drc':drc,'candidate_only_usb_u1_via_rules':True,'c7_power_return_review':'OPEN',
             'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    assert drc['candidate_unconnected']<drc['base_unconnected'] and not drc['new_by_type'],drc
    print(summary)
if __name__=='__main__':main()

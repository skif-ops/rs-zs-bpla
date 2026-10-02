#!/usr/bin/env python3
"""Connect the existing U8_VDD_EXT_1V8 F.Cu run to its B.Cu test pad."""
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
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-U1-POWER-010/PCB-MAIN_P2_U1_POWER_010_CANDIDATE_REV_A.kicad_pcb'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-CELL-DBG-011'
CANDIDATE=OUT/'PCB-MAIN_P2_CELL_DBG_011_CANDIDATE_REV_A.kicad_pcb'
BASE_SHA='6cc9d30c5c2326f1b0ea2eeaa91f2240e5e3b83c335c080e2fb4537f9460da16'
NET='U8_VDD_EXT_1V8'; AT=(47.325,30.6)
NAMESPACE=uuid.UUID('07e39d5c-0c36-49d0-9a7d-6aa3778ded04')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_geometry():
    from shapely.geometry import Point
    from shapely.strtree import STRtree
    b,_=geo.load(BASE)
    shape=Point(*AT).buffer(.25+.2,8)
    own_f=own_b=False
    for fp in b.footprints:
        for p in fp.pads:
            if p.net and p.net.name==NET and 'B.Cu' in geo.pad_layers(p) and geo.pad_geometry(fp,p).contains(Point(*AT)):
                assert geo.reference(fp)=='TP_CELL_DBG' and str(p.number)=='1'
                own_b=True
            if p.net and p.net.name!=NET:
                for l in geo.pad_layers(p):
                    assert not geo.pad_geometry(fp,p).intersects(shape), (l,geo.reference(fp),p.number)
    for n,k,l,g,r in geo.items(b):
        if n==NET and k=='track' and l=='F.Cu' and g.distance(Point(*AT))<1e-5:own_f=True
        if n!=NET and (k=='via' or l in geo.LAYERS):
            for layer in (geo.LAYERS if k=='via' else (l,)):
                if g.buffer(r.size/2 if k=='via' else r.width/2,8).intersects(shape):
                    raise AssertionError((layer,n,k,r.tstamp))
    assert own_f and own_b,'via must overlap the intended two copper islands'

def build():
    assert sha(BASE)==BASE_SHA
    check_geometry()
    source=BASE.read_text();net=int(re.search(r'^  \(net (\d+) "U8_VDD_EXT_1V8"\)',source,re.M).group(1))
    lines=source.splitlines()
    i=max(j for j,line in enumerate(lines) if line.startswith('  (via '))+1
    lines.insert(i,f'  (via (at {AT[0]:g} {AT[1]:g}) (size 0.5) (drill 0.3) (layers "F.Cu" "B.Cu") (net {net}) (tstamp {uuid.uuid5(NAMESPACE,"via|0")}))')
    return '\n'.join(lines)+'\n'

def run_drc():
    work=ROOT/'hardware/kicad/native/_p2_cell_dbg_011'
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
        (OUT/'PCB-MAIN_P2_CELL_DBG_011_CANDIDATE_REV_A.kicad_pro').write_text(overlay)
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
        print('PCB-MAIN cell debug power 011: PASS',summary['drc']);return
    gate.deps();OUT.mkdir(parents=True,exist_ok=True)
    CANDIDATE.write_text(build())
    drc=run_drc()
    summary={'schema':'dioneya-pcb-main-cell-dbg-power-011-v1','base_sha256':BASE_SHA,
             'candidate_sha256':sha(CANDIDATE),'standard_vias_0_5_0_3':1,'drc':drc,
             'candidate_only_usb_u1_via_rules':True,'test_pad_via_in_pad_dfm_review':'OPEN',
             'applied_to_authoritative_board':False,'manufacturing_release':False}
    (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    assert drc['candidate_unconnected']<drc['base_unconnected'] and not drc['new_by_type'],drc
    print(summary)
if __name__=='__main__':main()

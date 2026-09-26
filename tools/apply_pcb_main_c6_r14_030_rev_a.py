#!/usr/bin/env python3
"""Join the R14 I2C pull-up to the C6 3V3 bulk capacitor on In3.Cu."""
from __future__ import annotations
import hashlib,json,re,shutil,sys,uuid
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as gate
import pcb_main_ground_domain_002_rev_a as geo
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D2-029/PCB-MAIN_P2_SD_D2_029_CANDIDATE_REV_A.kicad_pcb'
BASE_DRC=BASE.parent/'drc_candidate.json'
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-C6-R14-030'
CANDIDATE=OUT/'PCB-MAIN_P2_C6_R14_030_CANDIDATE_REV_A.kicad_pcb'
BASE_SHA='cbbc51ed5504c6158925a480e19db11a62735bc61e119fbb1d29be3a8758c21d'
NAMESPACE=uuid.UUID('782326c9-be10-439f-b7a8-69868cdd44e3')
NET='3V3_DIGITAL'
ROUTES=(('F.Cu',.15,((41.55,30.0),(41.75,30.4))),
        ('F.Cu',.15,((40.175,31.5),(40.175,31.7))),
        ('In3.Cu',.15,((41.75,30.4),(40.175,31.7))))
VIAS=((41.75,30.4),(40.175,31.7))

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def check_geometry():
 from shapely.geometry import Point,LineString
 from shapely.strtree import STRtree
 b,_=geo.load(BASE);obs={l:[] for l in geo.LAYERS};owners={l:[] for l in geo.LAYERS};holes=[]
 pads=set()
 for fp in b.footprints:
  for p in fp.pads:
   shape=geo.pad_geometry(fp,p);n=p.net.name if p.net else None
   if p.drill is not None and getattr(p.drill,'diameter',0):holes.append((shape.centroid,p.drill.diameter/2,n))
   for l in geo.pad_layers(p):
    obs[l].append(shape);owners[l].append(n)
    pads.add((n,l,round(shape.centroid.x,4),round(shape.centroid.y,4)))
 for n,k,l,shape,raw in geo.items(b):
  if k=='via':holes.append((shape,raw.drill/2,n))
  for layer in (geo.LAYERS if k=='via' else (l,)):
   obs[layer].append(shape.buffer(raw.size/2 if k=='via' else raw.width/2,8));owners[layer].append(n)
 idx={l:STRtree(obs[l]) for l in geo.LAYERS}
 def clear(layer,shape):
  conflicts=[owners[layer][int(i)] for i in idx[layer].query(shape)
             if owners[layer][int(i)]!=NET and obs[layer][int(i)].intersects(shape)]
  assert not conflicts,(layer,conflicts[:8])
 for layer,width,points in ROUTES:
  line=LineString(points)
  assert line.difference(geo.zone_outline(b,'GND_DIGITAL','In1.Cu' if layer=='F.Cu' else 'In4.Cu')).length<1e-6
  clear(layer,line.buffer(width/2+.20,8))
  for x,y in (points[0],points[-1]):
   assert (NET,layer,x,y) in pads or (x,y) in VIAS
  assert not [(n,line.distance(c)-r-width/2) for c,r,n in holes if n!=NET and line.distance(c)-r-width/2<.25-1e-6]
 for x,y in VIAS:
  assert any((x,y) in points and (NET,'F.Cu',points[0][0],points[0][1]) in pads for layer,width,points in ROUTES if layer=='F.Cu')
  for l in geo.LAYERS:clear(l,Point(x,y).buffer(.125+.20,8))
  assert not [(n,Point(x,y).distance(c)-r-.075) for c,r,n in holes if n!=NET and Point(x,y).distance(c)-r-.075<.25-1e-6]

def build():
 assert sha(BASE)==BASE_SHA
 check_geometry()
 source=BASE.read_text(encoding='utf-8')
 nets={name:int(code) for code,name in re.findall(r'^  \(net (\d+) "([^"]*)"\)',source,re.M)}
 segments=[]
 for k,(layer,width,points) in enumerate(ROUTES):
  for j,(a,b) in enumerate(zip(points,points[1:])):
   segments.append(f'  (segment (start {a[0]:g} {a[1]:g}) (end {b[0]:g} {b[1]:g}) (width {width:g}) (layer "{layer}") (net {nets[NET]}) (tstamp {uuid.uuid5(NAMESPACE,f"track|{k}|{j}")}))')
 vias=[f'  (via (at {x:g} {y:g}) (size 0.25) (drill 0.15) (layers "F.Cu" "B.Cu") (net {nets[NET]}) (tstamp {uuid.uuid5(NAMESPACE,f"via|{k}")}))' for k,(x,y) in enumerate(VIAS)]
 lines=source.splitlines();i=max(i for i,l in enumerate(lines) if l.startswith('  (segment '))+1
 lines=lines[:i]+segments+lines[i:];i=max(i for i,l in enumerate(lines) if l.startswith('  (via '))+1
 return '\n'.join(lines[:i]+vias+lines[i:])+'\n'

def run_drc():
 work=ROOT/'hardware/kicad/native/_p2_c6_r14_030';shutil.rmtree(work,ignore_errors=True)
 shutil.copytree(ROOT/'hardware/kicad/native/PCB-MAIN',work)
 try:
  rel=work.relative_to(ROOT);shutil.copyfile(CANDIDATE,work/'candidate.kicad_pcb')
  project=json.loads((work/'PCB-MAIN.kicad_pro').read_text())
  rules=project.setdefault('board',{}).setdefault('design_settings',{}).setdefault('rules',{})
  rules.update({'min_via_diameter':.25,'min_through_hole_diameter':.15,'min_via_annular_width':.05})
  overlay=json.dumps(project,indent=2,sort_keys=True)+'\n'
  (work/'candidate.kicad_pro').write_text(overlay)
  (OUT/'PCB-MAIN_P2_C6_R14_030_CANDIDATE_REV_A.kicad_pro').write_text(overlay)
  for cmd in (('/usr/bin/python3','tools/pcb_main_ground_domain_002_stage_rev_a.py','fill',f'{rel}/candidate.kicad_pcb',f'{rel}/candidate.kicad_pcb'),('kicad-cli','pcb','drc','--format','json','--severity-all','-o',f'{rel}/drc_candidate.json',f'{rel}/candidate.kicad_pcb')):
   result=gate.docker(*cmd);assert result.returncode==0,(cmd,result.stdout[-1000:],result.stderr[-1000:])
  gate.docker('chmod','-R','a+rwX',str(rel))
  report=json.loads((work/'drc_candidate.json').read_text());shutil.copyfile(work/'drc_candidate.json',OUT/'drc_candidate.json')
  before=json.loads(BASE_DRC.read_text());(bfp,bunc),(cfp,cunc)=gate.drc_fingerprints(before),gate.drc_fingerprints(report)
  novel=sorted((key,count-bfp.get(key,0)) for key,count in cfp.items() if count>bfp.get(key,0))
  by_type=Counter()
  for key,count in novel:by_type[f'{key[0]}:{key[1]}']+=count
  return {'base_unconnected':bunc,'candidate_unconnected':cunc,'new_by_type':dict(by_type),'new_errors':sum(count for key,count in novel if key[0]=='error')}
 finally:
  gate.docker('rm','-rf',str(work.relative_to(ROOT)));shutil.rmtree(work,ignore_errors=True)

def main():
 if '--check' in sys.argv:
  record=json.loads((OUT/'SUMMARY.json').read_text());assert record['candidate_sha256']==sha(CANDIDATE)
  assert CANDIDATE.read_text()==build();assert record['drc']['new_errors']==0
  assert record['drc']['candidate_unconnected']<record['drc']['base_unconnected']
  print('PCB-MAIN C6 R14 030: PASS',record['drc']);return
 gate.deps();OUT.mkdir(parents=True,exist_ok=True);CANDIDATE.write_text(build())
 drc=run_drc();summary={'schema':'dioneya-pcb-main-c6-r14-030-v1','base_sha256':BASE_SHA,
  'candidate_sha256':sha(CANDIDATE),'routes':len(ROUTES),'track_segments':3,
  'via_size_drill_mm':[.25,.15],'total_length_mm':2.689,
  'i2c_pullup_power_review_b':'OPEN','via_in_pad_dfm_review':'OPEN',
  'drc':drc,'candidate_only_usb_u1_via_rules':True,'applied_to_authoritative_board':False,'manufacturing_release':False}
 (OUT/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
 assert drc['new_errors']==0 and drc['candidate_unconnected']<drc['base_unconnected'],drc
 print(summary)
if __name__=='__main__':main()

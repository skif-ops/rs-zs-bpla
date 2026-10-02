#!/usr/bin/env python3
"""Screen R89 placement relief for the trapped SD_D0_CARD connection."""
import json,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as gate
BASE=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-SD-D3-TOP-088'
BOARD=BASE/'PCB-MAIN_P2_SD_D3_TOP_088_CANDIDATE_REV_A.kicad_pcb'
PROJECT=BASE/'PCB-MAIN_P2_SD_D3_TOP_088_CANDIDATE_REV_A.kicad_pro'
old='    (tstamp f88e813f-0e75-4518-8a8d-ae29174cb213)\n    (at 86.5 23)'
data=BOARD.read_text()
assert data.count(old)==1
original=json.loads((BASE/'drc_candidate.json').read_text())
ofp,oopen=gate.drc_fingerprints(original)
out=[]
for x,y in [(86.5,25.5),(86.5,21.0),(90.0,23.0),(90.0,25.5),(89.5,21.0),(86.5,26.0)]:
    work=ROOT/'hardware/kicad/native/_p2_r89_probe'
    shutil.copytree(ROOT/'hardware/kicad/native/PCB-MAIN',work,dirs_exist_ok=True)
    (work/'candidate.kicad_pcb').write_text(data.replace(old,old.split('\n')[0]+f'\n    (at {x} {y})'))
    shutil.copyfile(PROJECT,work/'candidate.kicad_pro')
    shutil.copyfile(ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-VREF-3V3-062/PCB-MAIN_02_MCU_VREF_062.kicad_sch',work/'PCB-MAIN_02_MCU.kicad_sch')
    rel=work.relative_to(ROOT)
    for cmd in [('/usr/bin/python3','tools/pcb_main_ground_domain_002_stage_rev_a.py','fill',f'{rel}/candidate.kicad_pcb',f'{rel}/candidate.kicad_pcb'),('kicad-cli','pcb','drc','--format','json','--severity-all','-o',f'{rel}/drc.json',f'{rel}/candidate.kicad_pcb')]:
        done=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        assert done.returncode==0,(cmd,done.stdout[-500:],done.stderr[-500:])
    new=json.loads((work/'drc.json').read_text())
    fp,opened=gate.drc_fingerprints(new)
    novel=[(str(k),n-ofp.get(k,0)) for k,n in fp.items() if n>ofp.get(k,0) and k[1]!='unconnected_items']
    record={'at_mm':[x,y],'open':opened,'new':novel}
    print('R89_PROBE',json.dumps(record),flush=True)
    out.append(record)
(BASE/'R89_PLACEMENT_089.json').write_text(json.dumps(out,indent=2)+'\n')

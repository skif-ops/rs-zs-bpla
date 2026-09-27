#!/usr/bin/env python3
"""Candidate 073: give distinct copper items distinct UUIDs on the mic rail."""
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
import apply_pcb_main_batch_072_rev_a as prior

BASE=prior.CANDIDATE
OUT=ROOT/'hardware/kicad/candidates/PCB-ROUTING-P2-UUID-073'
CANDIDATE=OUT/'PCB-MAIN_P2_UUID_073_CANDIDATE_REV_A.kicad_pcb'
PROJECT=OUT/'PCB-MAIN_P2_UUID_073_CANDIDATE_REV_A.kicad_pro'
BASE_SHA='42e70280275169e6fe2b06343f09683153a45a228666eb9e4c31f7c437851dee'
NAMESPACE=uuid.UUID('a355db5c-e14b-4cd0-afcf-87003e8b8760')
REDUNDANT='5384ef96-6d84-5825-a572-6cf5d5b9f187'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def build():
    assert sha(BASE)==BASE_SHA
    seen=set();out=[];fixed=[]
    for line in BASE.read_text().splitlines():
        if line.startswith('  (segment ') and f'(tstamp {REDUNDANT})' in line:
            assert '(start 7.9 26) (end 8 25.8)' in line
            continue
        if line.startswith(('  (segment ','  (via ')):
            old=re.search(r'\(tstamp ([0-9a-f-]+)\)',line).group(1)
            if old in seen:
                new=str(uuid.uuid5(NAMESPACE,line))
                assert new not in seen
                line=line.replace(f'(tstamp {old})',f'(tstamp {new})')
                fixed.append((old,new))
                seen.add(new)
            else:seen.add(old)
        out.append(line)
    assert len(fixed)==53,(len(fixed),fixed[:1])
    return '\n'.join(out)+'\n'


def main():
    if '--check' in sys.argv:
        s=json.loads((OUT/'SUMMARY.json').read_text())
        assert CANDIDATE.read_text()==build() and s['candidate_sha256']==sha(CANDIDATE)
        assert s['drc']['new_by_type']=={} and s['drc']['erc_violations']==0
        assert s['drc']['candidate_unconnected']<=s['drc']['base_unconnected']
        print('PCB-MAIN UUID 073 PASS',s['drc'])
        return
    prior.gate.deps()
    OUT.mkdir(exist_ok=True)
    CANDIDATE.write_text(build())
    shutil.copyfile(prior.PROJECT,PROJECT)
    if '--build-only' in sys.argv:
        print('Candidate generated; native KiCad ERC/DRC pending',sha(CANDIDATE))
        return
    prior.OUT,prior.CANDIDATE,prior.PROJECT,prior.BASE_DRC=OUT,CANDIDATE,PROJECT,prior.OUT/'drc_candidate.json'
    # The native work directory is private to this workflow run.
    report=prior.run_native()
    s={'schema':'dioneya-pcb-main-uuid-073-v1','base_sha256':BASE_SHA,
       'candidate_sha256':sha(CANDIDATE),'fixed_duplicate_copper_uuids':53,
       'removed_redundant_segment':REDUNDANT,'review_b':'OPEN',
       'applied_to_authoritative_board':False,'manufacturing_release':False,'drc':report}
    (OUT/'SUMMARY.json').write_text(json.dumps(s,indent=2)+'\n')
    assert report['new_by_type']=={} and report['erc_violations']==0
    assert report['candidate_unconnected']<=report['base_unconnected']
    print(s)

if __name__=='__main__':main()

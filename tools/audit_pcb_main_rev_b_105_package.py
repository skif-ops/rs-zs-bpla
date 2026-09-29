"""Check PCB-MAIN Rev B candidate 105 handoff integrity and assembly sets."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'hardware/kicad/candidates/PCB-MAIN-8L-COMPLETE-105'


def read_json(name):
    return json.loads((CANDIDATE / name).read_text(encoding='utf-8'))


def read_csv(name):
    with (CANDIDATE / 'fab/assembly' / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def check():
    lines = (CANDIDATE / 'FILES.sha256').read_text(encoding='utf-8').splitlines()
    paths = set()
    for line in lines:
        digest, relative = line.split('  ', 1)
        file = CANDIDATE / relative
        assert file.is_file(), relative
        assert hashlib.sha256(file.read_bytes()).hexdigest() == digest, relative
        paths.add(relative)
    actual = {p.relative_to(CANDIDATE).as_posix() for p in CANDIDATE.rglob('*') if p.is_file() and p.name != 'FILES.sha256'}
    assert paths == actual, {'missing': sorted(actual-paths), 'extra': sorted(paths-actual)}

    summary = read_json('SUMMARY.json')
    board = CANDIDATE / 'PCB-MAIN_8L_COMPLETE_105_CANDIDATE_REV_B.kicad_pcb'
    assert summary['board_sha256'] == hashlib.sha256(board.read_bytes()).hexdigest()
    assert summary['copper_layers'] == 8
    drc = read_json('drc_candidate.json')
    assert not drc['unconnected_items']
    assert all(v['severity'] != 'error' for v in drc['violations'])
    assert Counter(v['type'] for v in drc['violations']) == {'silk_over_copper': 23, 'via_dangling': 7}
    erc = read_json('erc_candidate.json')
    assert sum(len(s['violations']) for s in erc['sheets']) == 0
    parity = read_json('drc_schematic_parity.json')
    assert Counter(v['type'] for v in parity['schematic_parity']) == {
        'footprint_symbol_mismatch': 199,
        'footprint_symbol_field_mismatch': 199,
        'net_conflict': 199,
        'extra_footprint': 4,
    }

    bom = read_csv('PCB-MAIN_BOM_PCBA.csv')
    pos = read_csv('PCB-MAIN_POS_TOP_PCBA.csv')
    assert len(bom) == len(pos) == 227
    assert {row['Ref'] for row in bom} == {row['Ref'] for row in pos}
    assert not any('?' in row['Ref'] for row in bom)
    assert len(read_csv('PCB-MAIN_DNP.csv')) == 15
    assert [row['Ref'] for row in read_csv('PCB-MAIN_OFFBOARD_STATION.csv')] == ['U12']

    gerbers = list((CANDIDATE / 'fab/gerber').glob('*'))
    copper = [p for p in gerbers if p.suffix in {'.gtl', '.g1', '.g2', '.g3', '.g4', '.g5', '.g6', '.gbl'}]
    assert len(copper) == 8 and all(p.stat().st_size > 100 for p in copper)
    job = next(p for p in gerbers if p.name.endswith('-job.gbrjob'))
    job_data = json.loads(job.read_text(encoding='utf-8'))
    assert job_data['GeneralSpecs']['LayerNumber'] == 8
    assert job_data['GeneralSpecs']['Finish'] == 'ENIG'
    assert 'MaterialStackup' not in job_data
    stack = read_json('fab/STACKUP_REQUEST.json')
    assert stack['preferred_stack_status'] == 'PROPOSED_NOT_FACTORY_APPROVED'
    assert stack['controlled_job_sha256'] == hashlib.sha256(job.read_bytes()).hexdigest()
    assert len(read_json('via_in_pad_105.json')) == 57
    return {'status':'PASS','board_sha256':summary['board_sha256'],'files':len(paths),'pcba_positions':len(pos),'drc_errors':0,'unconnected':0,'erc_violations':0,'drc_warnings':len(drc['violations']),'fab_stack_approved':False}


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))

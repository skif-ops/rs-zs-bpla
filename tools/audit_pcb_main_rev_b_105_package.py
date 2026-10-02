"""Check PCB-MAIN Rev B candidate 105 handoff integrity and assembly sets."""

import csv
import hashlib
import json
import re
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
    assert stack['preferred_stack_status'] == 'PUBLISHED_STANDARD_EXAMPLE_ORDER_SELECTION_PENDING'
    assert stack['controlled_job_sha256'] == hashlib.sha256(job.read_bytes()).hexdigest()
    assert len(read_json('via_in_pad_105.json')) == 57
    screen = read_json('fab/JLCPCB_OFFICIAL_CAPABILITY_SCREEN_REV_B_105.json')
    assert screen['board_sha256'] == summary['board_sha256']
    assert screen['screen_result'] == 'PUBLISHED_CAPABILITIES_MATCH_ORDER_BASELINE'
    assert screen['board_vias']['flagged_fill_and_cap'] == summary['fill_and_cap_via_count'] == 74
    assert screen['board_vias']['flagged_in_SMD_pad'] == summary['via_in_pad_count'] == 57
    with (CANDIDATE / 'fab/VIA_FILL_CAP_74_REV_B_105.csv').open(encoding='utf-8-sig', newline='') as stream:
        fill_cap_rows = list(csv.DictReader(stream))
    assert len(fill_cap_rows) == 74
    assert sum(row['in_SMD_pad'] == 'YES' for row in fill_cap_rows) == 57
    csv_vias = {(float(row['x_mm_KiCad']), float(row['y_mm_KiCad']), float(row['via_diameter_mm']), float(row['drill_mm'])) for row in fill_cap_rows}
    assert len(csv_vias) == 74
    blocks = re.findall(r'(?ms)^\t\(via\n(.*?)^\t\)', board.read_text(encoding='utf-8'))
    flagged = set()
    for block in blocks:
        if '(filling yes)' in block and '(capping yes)' in block:
            position = re.search(r'\(at ([^)]+)\)', block).group(1).split()
            diameter = re.search(r'\(size ([^)]+)\)', block).group(1)
            drill = re.search(r'\(drill ([^)]+)\)', block).group(1)
            flagged.add((float(position[0]), float(position[1]), float(diameter), float(drill)))
    assert csv_vias == flagged
    assert (CANDIDATE / 'fab/VIA_FILL_CAP_74_MAP_RU_EN.pdf').stat().st_size > 1000
    return {'status':'PASS','board_sha256':summary['board_sha256'],'files':len(paths),'pcba_positions':len(pos),'drc_errors':0,'unconnected':0,'erc_violations':0,'drc_warnings':len(drc['violations']),'official_capability_screen':'PASS','fab_stack_selected_in_order':False}


if __name__ == '__main__':
    print(json.dumps(check(), ensure_ascii=False))

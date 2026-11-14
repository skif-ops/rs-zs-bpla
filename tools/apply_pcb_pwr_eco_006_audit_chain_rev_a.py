#!/usr/bin/env python3
"""Carry the PCB-PWR audit chain to the accepted ECO-006 successor of ECO-005.

Deterministic, idempotent source transformation (run by .github/workflows/ci-apply.yml before
tools/apply_pcb_pwr_eco_006_rev_a.py; the bot commit carries the resulting diff):
  - tools/pcb_pwr_hot_loop_006_board.py: ECO_006 candidate path + SHA-256, is_eco_006() (exact committed
    candidate bytes), accepted next to is_eco_005() in the successor predicates;
  - the 006-010 / ECO-003 / 011 audits and generators: ECO_006_SHA256 / ECO_006_SHA next to every
    ECO-005 constant and in every accepted-hash set, is_eco_006() next to every is_eco_005() call, the
    NT2 180 deg pose override extended to ECO-006 (ECO-006 does not change placement);
  - tools/audit_pcb_pwr_footprints_rev_a.py: TestPoint_DFT_1.7mm_NoPaste mask margin 0.20 -> 0.10 mm.
The capture-status controls do not change (ECO-006 keeps the semantic SHA-256 4c835eae..., 842 trace
items, 33 zones). --check verifies that no ECO-005 acceptance is left without ECO-006.
Record: hardware/reviews/PCB_PWR_ECO_006_REV_A.md.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA6 = "b8c1da6ca80b9e5d2795c4fee5b6926e4ab6169086795295e8e517a18def6ca7"
NOTE = "  # exact committed ECO-006 board (Review B R2 DFM: TP mask 0.1 mm, legend 1.0/0.15 mm; copper unchanged)"
FILES = [
    "tools/audit_pcb_pwr_3v8_output_bulk_routing_010_application_rev_a.py",
    "tools/audit_pcb_pwr_layout_candidate_rev_a.py",
    "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
    "tools/audit_pcb_pwr_routing_authority_rev_a.py",
    "tools/audit_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a.py",
    "tools/audit_pcb_pwr_vbat_sys_shunt_bulk_routing_007_application_rev_a.py",
    "tools/generate_pcb_pwr_3v8_output_bulk_routing_010_application_rev_a.py",
    "tools/generate_pcb_pwr_buck_input_hot_loop_routing_006_application_rev_a.py",
    "tools/generate_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a.py",
    "tools/generate_pcb_pwr_vbat_sys_shunt_bulk_routing_007_application_rev_a.py",
    "tools/run_pcb_pwr_c13_c12_008_historical_audit.py",
    "tools/run_pcb_pwr_hot_loop_006_historical_candidate_audit.py",
    "tools/run_pcb_pwr_shunt_bulk_007_historical_audit.py",
]
BOARDS = "tools/pcb_pwr_hot_loop_006_board.py"
FOOTPRINTS = "tools/audit_pcb_pwr_footprints_rev_a.py"
TP_OLD = '''         ("F.Cu", "F.Mask"), None, 0.20),
    }
    audit_simple_ti_package(library / "TestPoint_DFT_1.7mm_NoPaste.kicad_mod",'''
TP_NEW = '''         ("F.Cu", "F.Mask"), None, 0.10),  # ECO-006 (Review B R2 DFM-PWR-02): 0.20 -> 0.10 mm
    }
    audit_simple_ti_package(library / "TestPoint_DFT_1.7mm_NoPaste.kicad_mod",'''
ECO5_CONST = '''ECO_005_SHA256 = "81f44a7068de6c8d7b3ae1a6951bc9d7a4bc6c2646cdbc4eccea4d9c79e35610"'''
ECO5_FUNC = '''def is_eco_005(payload: bytes) -> bool:
    """Accepted ECO-005 successor of autoroute 011 (Review B R1 remediation): the committed candidate."""
    return (hashlib.sha256(payload).hexdigest() == ECO_005_SHA256
            and payload == ECO_005.read_bytes())
'''
ECO6_CONST = ECO5_CONST + f'''
ECO_006 = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-006/PCB-PWR_ECO_006_CANDIDATE_REV_A.kicad_pcb"
ECO_006_SHA256 = "{SHA6}"'''
ECO6_FUNC = ECO5_FUNC + '''

def is_eco_006(payload: bytes) -> bool:
    """Accepted ECO-006 successor of ECO-005 (Review B R2 DFM: test-point mask 0.1 mm, legend 1.0/0.15 mm;
    copper, placement and nets unchanged): the committed candidate."""
    return (hashlib.sha256(payload).hexdigest() == ECO_006_SHA256
            and payload == ECO_006.read_bytes())
'''


def transform(s: str) -> str:
    s = re.sub(r'^(ECO_005_SHA256 = "[0-9a-f]{64}".*)$', lambda m: m.group(1) + f'\nECO_006_SHA256 = "{SHA6}"' + NOTE,
               s, flags=re.M)
    s = re.sub(r'^(ECO_005_SHA = "[0-9a-f]{64}".*)$', lambda m: m.group(1) + f'\nECO_006_SHA = "{SHA6}"' + NOTE,
               s, flags=re.M)
    s = s.replace("ECO_005_SHA256}", "ECO_005_SHA256, ECO_006_SHA256}")
    s = s.replace("ECO_005_SHA}", "ECO_005_SHA, ECO_006_SHA}")
    s = s.replace("board_sha256 == ECO_005_SHA256", "board_sha256 in {ECO_005_SHA256, ECO_006_SHA256}")
    s = re.sub(r"\bis_eco_005,", "is_eco_005, is_eco_006,", s)
    s = re.sub(r"import (.*)\bis_eco_005\b(?!,)", lambda m: "import " + m.group(1) + "is_eco_005, is_eco_006", s)
    s = re.sub(r"is_eco_005\(([^()]*(?:\([^()]*\))?)\)", r"(is_eco_005(\1) or is_eco_006(\1))", s)
    return s


def applied() -> bool:
    return "def is_eco_006" in (ROOT / BOARDS).read_text(encoding="utf-8")


def apply() -> None:
    if applied():
        print("PCB-PWR ECO-006 audit chain: already applied")
        return
    for name in FILES:
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        new = transform(text)
        assert new != text, f"{name}: no ECO-005 acceptance found"
        path.write_text(new, encoding="utf-8")
    boards = (ROOT / BOARDS).read_text(encoding="utf-8")
    assert boards.count(ECO5_CONST) == 1 and boards.count(ECO5_FUNC) == 1
    boards = boards.replace(ECO5_CONST, ECO6_CONST).replace(ECO5_FUNC, ECO6_FUNC)
    assert boards.count("or is_eco_005(payload)") == 2
    boards = boards.replace("or is_eco_005(payload)", "or is_eco_005(payload) or is_eco_006(payload)")
    (ROOT / BOARDS).write_text(boards, encoding="utf-8")
    fp = (ROOT / FOOTPRINTS).read_text(encoding="utf-8")
    assert fp.count(TP_OLD) == 1, "footprint audit TestPoint expectation is not the ECO-005 0.20 mm"
    (ROOT / FOOTPRINTS).write_text(fp.replace(TP_OLD, TP_NEW), encoding="utf-8")
    check()
    print("PCB-PWR ECO-006 audit chain: applied")


def check() -> None:
    assert applied(), "ECO-006 audit chain is not applied"
    boards = (ROOT / BOARDS).read_text(encoding="utf-8")
    assert boards.count("or is_eco_005(payload) or is_eco_006(payload)") == 2 and SHA6 in boards
    for name in FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        for bare in ("ECO_005_SHA256}", "ECO_005_SHA}", "board_sha256 == ECO_005_SHA256"):
            assert bare not in text, f"{name}: ECO-005 acceptance without ECO-006 ({bare})"
        calls = re.findall(r"is_eco_005\([^()]*(?:\([^()]*\))?\)(?! or is_eco_006)", text)
        assert not calls, f"{name}: is_eco_005() without is_eco_006(): {calls}"
        assert "ECO_006" in text or "is_eco_006" in text, f"{name}: ECO-006 not accepted"
    assert TP_NEW in (ROOT / FOOTPRINTS).read_text(encoding="utf-8"), "footprint audit still expects 0.20 mm"
    print("PCB-PWR ECO-006 audit chain: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

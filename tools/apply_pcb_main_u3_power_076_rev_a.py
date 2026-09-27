#!/usr/bin/env python3
"""Candidate 076: relieve the U3 ground via and close its local 3V3 gap.

The ground via stays connected to U3.6. The 0.25/0.15 mm replacement is
candidate-process copper; DFM and local power/return review remain open.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_main_batch_075_rev_a as previous

BASE_DIR = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-ASTAR-075"
BASE = BASE_DIR / "PCB-MAIN_P2_ASTAR_075_CANDIDATE_REV_A.kicad_pcb"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2-U3-POWER-076"
CANDIDATE = OUT / "PCB-MAIN_P2_U3_POWER_076_CANDIDATE_REV_A.kicad_pcb"
PROJECT = OUT / "PCB-MAIN_P2_U3_POWER_076_CANDIDATE_REV_A.kicad_pro"
BASE_SHA = "749c67134365db87fd4cbf85cd32fab94bb88f07c7aaa6b50065f1b6a518b9d5"
NEW_SEGMENT = (
    '  (segment (start 65.2375 30.25) (end 66.7625 30.25) '
    '(width 0.15) (layer "F.Cu") (net 2) '
    '(tstamp 751fa42a-bd70-59ea-9c6e-d523d59575f7))\n'
)


def replace_one(source: str, old: str, new: str) -> str:
    assert source.count(old) == 1, old
    return source.replace(old, new)


def build() -> str:
    assert hashlib.sha256(BASE.read_bytes()).hexdigest() == BASE_SHA
    source = BASE.read_text()
    source = replace_one(
        source,
        "(segment (start 66.224999 30.725) (end 66.099999 30.6)",
        "(segment (start 66.224999 30.725) (end 66.099999 30.65)",
    )
    source = replace_one(
        source,
        "(via (at 66.099999 30.6) (size 0.5) (drill 0.3)",
        "(via (at 66.099999 30.65) (size 0.25) (drill 0.15)",
    )
    at = source.rfind("  (segment ")
    assert at >= 0 and NEW_SEGMENT not in source
    at = source.index("\n", at) + 1
    return source[:at] + NEW_SEGMENT + source[at:]


def main() -> None:
    if "--check" in sys.argv:
        summary = json.loads((OUT / "SUMMARY.json").read_text())
        assert CANDIDATE.read_text() == build()
        assert summary["candidate_sha256"] == previous.sha(CANDIDATE)
        assert summary["drc"] == {
            "base_unconnected": 40, "candidate_unconnected": 39,
            "new_by_type": {}, "new_errors": 0,
            "erc_errors": 0, "erc_violations": 0,
        }
        print("PCB-MAIN candidate 076: PASS", summary["drc"])
        return
    OUT.mkdir(parents=True, exist_ok=True)
    CANDIDATE.write_text(build())
    shutil.copyfile(BASE_DIR / "PCB-MAIN_P2_ASTAR_075_CANDIDATE_REV_A.kicad_pro", PROJECT)
    previous.BASE = BASE
    previous.BASE_DRC = BASE_DIR / "drc_candidate.json"
    previous.OUT = OUT
    previous.CANDIDATE = CANDIDATE
    previous.PROJECT = PROJECT
    drc = previous.run_native()
    summary = {
        "schema": "dioneya-pcb-main-u3-power-076-v1",
        "base_sha256": BASE_SHA,
        "candidate_sha256": previous.sha(CANDIDATE),
        "change": "U3.6 ground via moved 0.05 mm and reduced to 0.25/0.15 mm; U3.2 to U3.9 local 3V3 F.Cu 0.15 mm, 1.525 mm",
        "candidate_only_via_rules": True,
        "review_b": "OPEN",
        "applied_to_authoritative_board": False,
        "manufacturing_release": False,
        "drc": drc,
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    assert not drc["new_by_type"] and drc["candidate_unconnected"] == 39, drc
    assert drc["new_errors"] == drc["erc_errors"] == drc["erc_violations"] == 0, drc
    print(summary)


if __name__ == "__main__":
    main()

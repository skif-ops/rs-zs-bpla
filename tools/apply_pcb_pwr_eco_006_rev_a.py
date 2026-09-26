#!/usr/bin/env python3
"""Apply PCB-PWR ECO-006 to the authoritative board (Review B R2 DFM-PWR-02 / DFM-PWR-03).

Run by .github/workflows/ci-apply.yml after tools/apply_pcb_pwr_eco_006_audit_chain_rev_a.py, then with
--check. Byte-exact and idempotent:
  hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb
      <- hardware/kicad/candidates/PCB-PWR-ECO-006/PCB-PWR_ECO_006_CANDIDATE_REV_A.kicad_pcb
  hardware/kicad/native/PCB-PWR/libs/DioneyaPWR.pretty/TestPoint_DFT_1.7mm_NoPaste.kicad_mod
      <- hardware/kicad/candidates/PCB-PWR-ECO-006/TestPoint_DFT_1.7mm_NoPaste.kicad_mod
The candidate must be the pinned ECO-006 bytes with a clean candidate summary (delta limited to the
reference designators and the test-point mask margin, copper/semantics unchanged, DRC 0 errors /
0 unconnected). The only accepted source board is ECO-005 (or ECO-006 itself: re-run).
The capture-status controls do not change (semantic SHA-256 4c835eae..., 842 trace items, 33 zones).
Record: hardware/reviews/PCB_PWR_ECO_006_REV_A.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAND_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-006"
CAND_BOARD = CAND_DIR / "PCB-PWR_ECO_006_CANDIDATE_REV_A.kicad_pcb"
CAND_LIB = CAND_DIR / "TestPoint_DFT_1.7mm_NoPaste.kicad_mod"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
LIB = ROOT / "hardware/kicad/native/PCB-PWR/libs/DioneyaPWR.pretty/TestPoint_DFT_1.7mm_NoPaste.kicad_mod"
ECO_005_SHA256 = "81f44a7068de6c8d7b3ae1a6951bc9d7a4bc6c2646cdbc4eccea4d9c79e35610"
ECO_006_SHA256 = "b8c1da6ca80b9e5d2795c4fee5b6926e4ab6169086795295e8e517a18def6ca7"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_candidate() -> dict:
    assert sha256(CAND_BOARD) == ECO_006_SHA256, "ECO-006 candidate SHA-256 drift"
    summary = json.loads((CAND_DIR / "SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["candidate_sha256"] == ECO_006_SHA256 and summary["base_sha256"] == ECO_005_SHA256
    assert summary["library_candidate_sha256"] == sha256(CAND_LIB), "candidate library drift"
    assert summary["delta"]["outside_delta_count"] == 0, "candidate delta is not limited to references and mask"
    inv = summary["invariants"]
    assert inv["semantic_sha256_base"] == inv["semantic_sha256_candidate"]
    assert inv["trace_items_identical"] and inv["zones_identical"] and inv["tp_mask_margins"] == ["0.1"]
    assert summary["drc"]["error_total"] == 0 and summary["drc"]["unconnected_total"] == 0, "candidate DRC not clean"
    return summary


def apply() -> None:
    summary = verify_candidate()
    current = sha256(BOARD)
    assert current in {ECO_005_SHA256, ECO_006_SHA256}, f"unexpected authoritative PCB-PWR board {current}"
    if current == ECO_005_SHA256:
        assert sha256(LIB) == summary["library_base_sha256"], "authoritative TestPoint library is not the ECO-005 one"
    shutil.copyfile(CAND_BOARD, BOARD)
    shutil.copyfile(CAND_LIB, LIB)
    check()


def check() -> None:
    verify_candidate()
    assert BOARD.read_bytes() == CAND_BOARD.read_bytes(), "authoritative PCB-PWR is not the ECO-006 candidate"
    assert LIB.read_bytes() == CAND_LIB.read_bytes(), "authoritative TestPoint library is not the ECO-006 one"
    print(f"PCB-PWR ECO-006 application: PASS {ECO_006_SHA256}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Apply the accepted PCB-PWR autoroute candidate 011 to the authoritative board.

Run by .github/workflows/ci-apply.yml (queued in ci/apply/queue.txt), then with
--check. The application is exact and bounded:

- precondition: the authoritative board is byte-identical to the accepted J2
  placement ECO-003 board and the committed candidate matches its pinned
  SHA-256 (hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/, produced by
  tools/apply_pcb_pwr_autoroute_candidate_rev_a.py in the pinned KiCad 9.0.9
  image, 0 DRC errors, 0 unconnected items);
- the board becomes the candidate byte for byte;
- the project gets the candidate net classes (35 um routing basis with the
  documented autoroute clearance overrides), nothing else in the project changes;
- the rule file becomes the candidate rule file: the ECO-004 U3/U4 land rule
  unchanged plus the U2 VSSOP-10 land-pattern rule.

Record: hardware/reviews/PCB_PWR_AUTOROUTE_011_APPLICATION_REV_A.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "hardware/kicad/native/PCB-PWR"
BOARD = NATIVE / "PCB-PWR.kicad_pcb"
PROJECT = NATIVE / "PCB-PWR.kicad_pro"
RULES = NATIVE / "PCB-PWR.kicad_dru"
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011"
STEM = "PCB-PWR_AUTOROUTE_011_CANDIDATE_REV_A"
CANDIDATE_BOARD = CANDIDATE_DIR / f"{STEM}.kicad_pcb"
CANDIDATE_PROJECT = CANDIDATE_DIR / f"{STEM}.kicad_pro"
CANDIDATE_RULES = CANDIDATE_DIR / f"{STEM}.kicad_dru"
BASE_SHA256 = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"  # J2 placement ECO-003
CANDIDATE_SHA256 = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def candidate_net_settings() -> dict:
    return json.loads(CANDIDATE_PROJECT.read_text(encoding="utf-8"))["net_settings"]


def expected_project() -> str:
    project = json.loads(PROJECT.read_text(encoding="utf-8"))
    project["net_settings"] = candidate_net_settings()
    return json.dumps(project, indent=2) + "\n"


def verify_candidate() -> None:
    assert sha256(CANDIDATE_BOARD.read_bytes()) == CANDIDATE_SHA256, "autoroute 011 candidate SHA-256 drift"
    summary = json.loads((CANDIDATE_DIR / "SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["candidate_sha256"] == CANDIDATE_SHA256, "candidate summary does not bind the candidate"
    assert summary["drc"]["error_total"] == 0 and summary["drc"]["unconnected_total"] == 0, \
        "candidate DRC is not clean"


def apply() -> None:
    verify_candidate()
    assert sha256(BOARD.read_bytes()) == BASE_SHA256, "authoritative PCB-PWR is not the accepted ECO-003 board"
    base_rules = RULES.read_text(encoding="utf-8")
    candidate_rules = CANDIDATE_RULES.read_text(encoding="utf-8")
    assert candidate_rules.startswith(base_rules), "candidate rules do not extend the ECO-004 rule file"
    BOARD.write_bytes(CANDIDATE_BOARD.read_bytes())
    PROJECT.write_text(expected_project(), encoding="utf-8")
    RULES.write_text(candidate_rules, encoding="utf-8")
    print(f"PCB-PWR autoroute 011 applied: {CANDIDATE_SHA256}")


def check() -> None:
    verify_candidate()
    assert BOARD.read_bytes() == CANDIDATE_BOARD.read_bytes(), "authoritative board differs from candidate 011"
    assert json.loads(PROJECT.read_text(encoding="utf-8"))["net_settings"] == candidate_net_settings(), \
        "project net classes differ from candidate 011"
    assert RULES.read_text(encoding="utf-8") == CANDIDATE_RULES.read_text(encoding="utf-8"), \
        "rule file differs from candidate 011"
    print(f"PCB-PWR autoroute 011 application: PASS {CANDIDATE_SHA256}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

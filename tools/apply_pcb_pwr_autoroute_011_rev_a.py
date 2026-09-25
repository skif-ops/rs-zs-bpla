#!/usr/bin/env python3
"""Apply the accepted PCB-PWR autoroute candidate 011 to the authoritative board.

Run by .github/workflows/ci-apply.yml (queued in ci/apply/queue.txt), then with
--check. Idempotent. The application is exact and bounded:

- the board becomes the committed candidate byte for byte (precondition: the
  authoritative board is the accepted J2 placement ECO-003 board, or already the
  candidate; the candidate matches its pinned SHA-256 and its CI DRC is clean);
- the project stays byte-identical to the pre-011 project: the historical
  comparative DRC packets of routing 001-010 / ECO-001/002 copy it next to their
  archived boards, and net classes there would change their accepted evidence
  (hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/HISTORICAL_NETCLASS_DRC_PROBE.json);
- the rule file carries the only net-class clearance that differs from the 0.2 mm
  default - PWR_SWITCH_4A (SW_3V8, SW_3V3) 0.4 mm - as a DRC rule placed first, so
  the later ECO-004 U3/U4 and U2 land-pattern rules keep precedence inside those
  footprints, exactly as with the candidate net classes;
- KiCad 9.0.9 DRC of the authoritative board with this project and rule file is
  recorded in hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/NATIVE_DRC_REV_A.json.

Record: hardware/reviews/PCB_PWR_AUTOROUTE_011_APPLICATION_REV_A.md.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "hardware/kicad/native/PCB-PWR"
BOARD = NATIVE / "PCB-PWR.kicad_pcb"
PROJECT = NATIVE / "PCB-PWR.kicad_pro"
RULES = NATIVE / "PCB-PWR.kicad_dru"
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011"
STEM = "PCB-PWR_AUTOROUTE_011_CANDIDATE_REV_A"
CANDIDATE_BOARD = CANDIDATE_DIR / f"{STEM}.kicad_pcb"
CANDIDATE_RULES = CANDIDATE_DIR / f"{STEM}.kicad_dru"
DRC_REPORT = CANDIDATE_DIR / "NATIVE_DRC_REV_A.json"
BASE_SHA256 = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"  # J2 placement ECO-003
CANDIDATE_SHA256 = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"
PRE_011_COMMIT = "3112a43b23fab117774865473580c64e5cf2e9e1"
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
SW_RULE = """
# PCB-PWR autoroute 011: net class PWR_SWITCH_4A clearance of the 35 um routing
# basis (hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json) as a
# rule, so the project keeps no net classes. First rule: the footprint land-pattern
# rules below take precedence inside U3/U4/U2.
(rule "PWR_SWITCH_4A clearance (SW nodes)"
  (condition "A.NetName == 'SW_3V8' || A.NetName == 'SW_3V3'")
  (constraint clearance (min 0.4mm))
)
"""
HEADER = "(version 1)\n"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def pre_011(path: Path) -> bytes:
    return subprocess.run(["git", "show", f"{PRE_011_COMMIT}:{path.relative_to(ROOT)}"], cwd=ROOT,
                          check=True, capture_output=True).stdout


def expected_rules() -> str:
    candidate = CANDIDATE_RULES.read_text(encoding="utf-8")
    assert candidate.startswith(HEADER), "candidate rule file header differs"
    return HEADER + SW_RULE + candidate[len(HEADER):]


def verify_candidate() -> None:
    assert sha256(CANDIDATE_BOARD.read_bytes()) == CANDIDATE_SHA256, "autoroute 011 candidate SHA-256 drift"
    summary = json.loads((CANDIDATE_DIR / "SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["candidate_sha256"] == CANDIDATE_SHA256, "candidate summary does not bind the candidate"
    assert summary["drc"]["error_total"] == 0 and summary["drc"]["unconnected_total"] == 0, \
        "candidate DRC is not clean"


def native_drc() -> dict:
    work = Path(tempfile.mkdtemp(prefix="native_drc_", dir=ROOT))
    try:
        for source in (BOARD, PROJECT, RULES):
            shutil.copy2(source, work / source.name)
        board = (work / BOARD.name).relative_to(ROOT)
        out = (work / "drc.json").relative_to(ROOT)
        fill = ("import sys, pcbnew\nb = pcbnew.LoadBoard(sys.argv[1])\n"
                "pcbnew.ZONE_FILLER(b).Fill(b.Zones())\nb.Save(sys.argv[1])\n")
        subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                        "bash", "-c", f"/usr/bin/python3 -c '{fill}' {board} && "
                        f"kicad-cli pcb drc --format json --severity-all -o {out} {board}"],
                       check=True, capture_output=True, text=True)
        report = json.loads((ROOT / out).read_text(encoding="utf-8"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    by_type = collections.Counter((v["severity"], v["type"]) for v in report.get("violations", []))
    errors = [{"type": v["type"], "items": [i.get("description", "") for i in v.get("items", [])]}
              for v in report.get("violations", []) if v["severity"] == "error"]
    return {
        "schema": "dioneya-pcb-pwr-native-drc-v1",
        "kicad_image": KICAD_IMAGE,
        "board_sha256": sha256(BOARD.read_bytes()),
        "project_sha256": sha256(PROJECT.read_bytes()),
        "rules_sha256": sha256(RULES.read_bytes()),
        "error_total": sum(n for (s, _), n in by_type.items() if s == "error"),
        "errors": errors,
        "warnings": {t: n for (s, t), n in sorted(by_type.items()) if s == "warning"},
        "unconnected_total": len(report.get("unconnected_items", [])),
    }


def apply() -> None:
    verify_candidate()
    board = BOARD.read_bytes()
    if board != CANDIDATE_BOARD.read_bytes():
        assert sha256(board) == BASE_SHA256, "authoritative PCB-PWR is not the accepted ECO-003 board"
        BOARD.write_bytes(CANDIDATE_BOARD.read_bytes())
    PROJECT.write_bytes(pre_011(PROJECT))
    RULES.write_text(expected_rules(), encoding="utf-8")
    report = native_drc()
    DRC_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PCB-PWR autoroute 011 applied: {CANDIDATE_SHA256}; native DRC errors={report['error_total']} "
          f"unconnected={report['unconnected_total']}")


def check() -> None:
    verify_candidate()
    assert BOARD.read_bytes() == CANDIDATE_BOARD.read_bytes(), "authoritative board differs from candidate 011"
    assert PROJECT.read_bytes() == pre_011(PROJECT), "project differs from the pre-011 project"
    assert RULES.read_text(encoding="utf-8") == expected_rules(), "rule file differs from the 011 rule set"
    report = json.loads(DRC_REPORT.read_text(encoding="utf-8"))
    assert report["board_sha256"] == CANDIDATE_SHA256 and report["rules_sha256"] == sha256(RULES.read_bytes()) \
        and report["project_sha256"] == sha256(PROJECT.read_bytes()), "native DRC report is stale"
    print(f"PCB-PWR autoroute 011 application: PASS {CANDIDATE_SHA256}; native DRC errors="
          f"{report['error_total']} unconnected={report['unconnected_total']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

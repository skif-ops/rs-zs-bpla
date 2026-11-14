#!/usr/bin/env python3
"""Apply the accepted PCB-PWR ECO-005 candidate to the authoritative board (Review B R1).

Run by .github/workflows/ci-apply.yml (queued after tools/apply_pcb_pwr_eco_005_audit_chain_rev_a.py),
then with --check. Idempotent. The application is exact and bounded:

- precondition: the authoritative board is the autoroute 011 board (or already the candidate);
  the candidate matches its pinned SHA-256, its CI DRC has 0 errors / 0 unconnected, and
  CURRENT_EVIDENCE.json is bound to it with no narrow group left for review;
- the board becomes the committed candidate byte for byte;
- the project library gets the candidate's MountingHole_M3_3.4_EVT (F.SilkS r=2.25 circle
  removed - the only difference to the reviewed H1-H4 copies; pads/attributes/models equal);
- project and rule file stay byte-identical;
- KiCad 9.0.9 DRC of the authoritative board with its own project, rules, library table and
  project libraries is recorded in hardware/kicad/candidates/PCB-PWR-ECO-005/NATIVE_DRC_REV_A.json.

Record: hardware/reviews/PCB_PWR_ECO_005_REV_A.md.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "hardware/kicad/native/PCB-PWR"
BOARD = NATIVE / "PCB-PWR.kicad_pcb"
PROJECT = NATIVE / "PCB-PWR.kicad_pro"
RULES = NATIVE / "PCB-PWR.kicad_dru"
LIB_FILE = NATIVE / "libs/DioneyaPWR.pretty/MountingHole_M3_3.4_EVT.kicad_mod"
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-005"
CANDIDATE_BOARD = CANDIDATE_DIR / "PCB-PWR_ECO_005_CANDIDATE_REV_A.kicad_pcb"
CANDIDATE_LIB = CANDIDATE_DIR / "libs/MountingHole_M3_3.4_EVT.kicad_mod"
DRC_REPORT = CANDIDATE_DIR / "NATIVE_DRC_REV_A.json"
BASE_SHA256 = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"       # autoroute 011
CANDIDATE_SHA256 = "81f44a7068de6c8d7b3ae1a6951bc9d7a4bc6c2646cdbc4eccea4d9c79e35610"
CANDIDATE_LIB_SHA256 = "71face70754e834fde856448b0ce96db1471d04c1c872ccf6933c92714c082cb"
PRE_ECO_LIB_SHA256 = "de412317acd8ad73b57fb314a33b90f776b6e80458e46416b1003f9564a9c05b"
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
WORK = NATIVE.parent / "_eco005_native_drc"   # sibling of PCB-PWR: ${KIPRJMOD} library paths resolve


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_candidate() -> None:
    assert sha256(CANDIDATE_BOARD.read_bytes()) == CANDIDATE_SHA256, "ECO-005 candidate SHA-256 drift"
    assert sha256(CANDIDATE_LIB.read_bytes()) == CANDIDATE_LIB_SHA256, "ECO-005 library file SHA-256 drift"
    summary = json.loads((CANDIDATE_DIR / "SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["candidate_sha256"] == CANDIDATE_SHA256, "candidate summary does not bind the candidate"
    assert summary["drc"]["error_total"] == 0 and summary["drc"]["unconnected_total"] == 0, "candidate DRC is not clean"
    evidence = json.loads((CANDIDATE_DIR / "CURRENT_EVIDENCE.json").read_text(encoding="utf-8"))
    assert evidence["board_sha256"] == CANDIDATE_SHA256, "current evidence is not bound to the candidate"
    assert not evidence["narrow_review"], "current evidence leaves narrow copper for review"


def native_drc() -> dict:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir()
    try:
        for source in (BOARD, PROJECT, RULES, NATIVE / "fp-lib-table"):
            shutil.copy2(source, WORK / source.name)
        shutil.copytree(NATIVE / "libs", WORK / "libs")
        rel = WORK.relative_to(ROOT)
        fill = ("import sys, pcbnew\\nb = pcbnew.LoadBoard(sys.argv[1])\\n"
                "pcbnew.ZONE_FILLER(b).Fill(b.Zones())\\nb.Save(sys.argv[1])\\n")
        subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                        "bash", "-c", f"printf '{fill}' > /tmp/fill.py && /usr/bin/python3 /tmp/fill.py "
                        f"{rel}/{BOARD.name} && kicad-cli pcb drc --format json --severity-all "
                        f"-o {rel}/drc.json {rel}/{BOARD.name} && chmod -R a+rwX {rel}"],
                       check=True, capture_output=True, text=True)
        report = json.loads((WORK / "drc.json").read_text(encoding="utf-8"))
    finally:
        subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                        "rm", "-rf", str(WORK.relative_to(ROOT))], capture_output=True)
        shutil.rmtree(WORK, ignore_errors=True)
    by_type = collections.Counter((v["severity"], v["type"]) for v in report.get("violations", []))
    errors = [{"type": v["type"], "items": [i.get("description", "") for i in v.get("items", [])]}
              for v in report.get("violations", []) if v["severity"] == "error"]
    warnings = [{"type": v["type"], "items": [i.get("description", "") for i in v.get("items", [])]}
                for v in report.get("violations", []) if v["severity"] == "warning"]
    return {
        "schema": "dioneya-pcb-pwr-native-drc-v1",
        "kicad_image": KICAD_IMAGE,
        "board_sha256": sha256(BOARD.read_bytes()),
        "project_sha256": sha256(PROJECT.read_bytes()),
        "rules_sha256": sha256(RULES.read_bytes()),
        "library_file_sha256": sha256(LIB_FILE.read_bytes()),
        "with_project_library_table": True,
        "error_total": sum(n for (s, _), n in by_type.items() if s == "error"),
        "errors": errors,
        "warnings": {t: n for (s, t), n in sorted(by_type.items()) if s == "warning"},
        "warning_items": warnings,
        "unconnected_total": len(report.get("unconnected_items", [])),
    }


def apply() -> None:
    verify_candidate()
    board = BOARD.read_bytes()
    if board != CANDIDATE_BOARD.read_bytes():
        assert sha256(board) == BASE_SHA256, "authoritative PCB-PWR is not the autoroute 011 board"
        BOARD.write_bytes(CANDIDATE_BOARD.read_bytes())
    lib = LIB_FILE.read_bytes()
    if lib != CANDIDATE_LIB.read_bytes():
        assert sha256(lib) == PRE_ECO_LIB_SHA256, "project MountingHole library file is not the pre-ECO-005 file"
        LIB_FILE.write_bytes(CANDIDATE_LIB.read_bytes())
    report = native_drc()
    DRC_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PCB-PWR ECO-005 applied: {CANDIDATE_SHA256}; native DRC errors={report['error_total']} "
          f"unconnected={report['unconnected_total']} warnings={report['warnings']}")


def check() -> None:
    verify_candidate()
    assert BOARD.read_bytes() == CANDIDATE_BOARD.read_bytes(), "authoritative board differs from candidate ECO-005"
    assert LIB_FILE.read_bytes() == CANDIDATE_LIB.read_bytes(), "project library file differs from ECO-005"
    report = json.loads(DRC_REPORT.read_text(encoding="utf-8"))
    assert report["board_sha256"] == CANDIDATE_SHA256 and report["rules_sha256"] == sha256(RULES.read_bytes()) \
        and report["project_sha256"] == sha256(PROJECT.read_bytes()) \
        and report["library_file_sha256"] == CANDIDATE_LIB_SHA256, "native DRC report is stale"
    assert report["error_total"] == 0 and report["unconnected_total"] == 0, "native DRC is not clean"
    print(f"PCB-PWR ECO-005 application: PASS {CANDIDATE_SHA256}; native DRC errors={report['error_total']} "
          f"unconnected={report['unconnected_total']} warnings={report['warnings']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

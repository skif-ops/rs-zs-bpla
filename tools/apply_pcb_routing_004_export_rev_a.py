#!/usr/bin/env python3
"""PCB routing 004, step 1 (ci-apply): autorouter input and board state.

- PCB-MAIN: Specctra DSN export of the authoritative board (KiCad 9.0.9, pcbnew.ExportSpecctraDSN) ->
  hardware/kicad/candidates/PCB-ROUTING-004/PCB-MAIN_BASE.dsn
- PCB-PWR, PCB-MIC: zone fill + DRC of copies of the authoritative boards -> drc_<board>.json
- SUMMARY.json: the board hashes the outputs belong to.
Nothing under hardware/kicad/native changes. --check verifies SUMMARY.json against the boards (the steps' logs
are kept in SUMMARY.json whatever their outcome).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
NATIVE = ROOT / "hardware/kicad/native"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-004"
STAGE = "tools/pcb_routing_004_stage_rev_a.py"
BOARDS = ["PCB-MAIN", "PCB-PWR", "PCB-MIC"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w",
                           KICAD_IMAGE, *argv], capture_output=True, text=True)


def main() -> int:
    boards = {name: NATIVE / name / f"{name}.kicad_pcb" for name in BOARDS}
    if "--check" in sys.argv[1:]:
        summary = json.loads((OUT / "SUMMARY.json").read_text(encoding="utf-8"))
        assert all(summary["boards"][n]["sha256"] == sha256(p) for n, p in boards.items()), "board changed"
        print("PCB routing 004 export: PASS")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"schema": "dioneya-pcb-routing-004-export-v1", "kicad_image": KICAD_IMAGE, "boards": {}, "steps": {}}
    work_dirs = []
    try:
        for name, board in boards.items():
            summary["boards"][name] = {"path": str(board.relative_to(ROOT)), "sha256": sha256(board)}
            work = NATIVE / f"_r004_{name}"  # sibling of the native project: ${KIPRJMOD}/libs resolves
            shutil.rmtree(work, ignore_errors=True)
            shutil.copytree(NATIVE / name, work)
            work_dirs.append(work)
            rel = work.relative_to(ROOT)
            if name == "PCB-MAIN":
                step = docker("/usr/bin/python3", STAGE, "dsn", f"{rel}/{name}.kicad_pcb", f"{rel}/base.dsn")
                summary["steps"]["dsn_main"] = {"rc": step.returncode, "log": (step.stdout + step.stderr)[-800:]}
                if step.returncode == 0:
                    shutil.copyfile(work / "base.dsn", OUT / "PCB-MAIN_BASE.dsn")
                    summary["dsn_sha256"] = sha256(OUT / "PCB-MAIN_BASE.dsn")
            else:
                fill = docker("/usr/bin/python3", STAGE, "fill", f"{rel}/{name}.kicad_pcb", f"{rel}/{name}.kicad_pcb")
                drc = docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o",
                             f"{rel}/drc.json", f"{rel}/{name}.kicad_pcb")
                summary["steps"][f"fill_{name}"] = {"rc": fill.returncode, "log": (fill.stdout + fill.stderr)[-400:]}
                summary["steps"][f"drc_{name}"] = {"rc": drc.returncode, "log": (drc.stdout + drc.stderr)[-400:]}
                if (work / "drc.json").is_file():
                    report = json.loads((work / "drc.json").read_text(encoding="utf-8"))
                    shutil.copyfile(work / "drc.json", OUT / f"drc_{name}.json")
                    violations = report.get("violations", [])
                    summary["boards"][name]["drc"] = {
                        "errors": sum(1 for v in violations if v.get("severity") == "error"),
                        "warnings": sum(1 for v in violations if v.get("severity") == "warning"),
                        "unconnected": len(report.get("unconnected_items", []))}
    finally:
        docker("chmod", "-R", "a+rwX", "hardware/kicad/native")
        for work in work_dirs:
            docker("rm", "-rf", str(work.relative_to(ROOT)))
            shutil.rmtree(work, ignore_errors=True)
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

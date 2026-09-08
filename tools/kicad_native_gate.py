#!/usr/bin/env python3
"""Preflight and execute native KiCad checks for EVT-PRE-20 Rev.A.

PCB and schematic are checked independently as soon as each native file exists. The
overall release remains BLOCKED until MAIN/MIC/PWR each have SCH/PCB/PRO, both CLI
checks pass, and project Review A/B are complete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "hardware" / "kicad" / "native"
ART = ROOT / "artifacts" / "kicad-native"
BOARDS = ("PCB-MAIN", "PCB-MIC", "PCB-PWR")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def paths(name: str) -> dict[str, Path]:
    base = NATIVE / name / name
    return {
        "sch": base.with_suffix(".kicad_sch"),
        "pcb": base.with_suffix(".kicad_pcb"),
        "pro": base.with_suffix(".kicad_pro"),
    }


def validate_schematic(cli: str, name: str, sch: Path) -> None:
    out = ART / name
    out.mkdir(parents=True, exist_ok=True)
    run([cli, "sch", "erc", "--format", "json", "--severity-all", "--exit-code-violations",
         "-o", str(out / "erc.json"), str(sch)])
    run([cli, "sch", "export", "pdf", "-o", str(out / f"{name}_schematic.pdf"), str(sch)])


def validate_pcb(cli: str, name: str, pcb: Path) -> None:
    out = ART / name
    out.mkdir(parents=True, exist_ok=True)
    run([cli, "pcb", "drc", "--format", "json", "--severity-all", "--exit-code-violations",
         "-o", str(out / "drc.json"), str(pcb)])
    gerber = out / "gerber"
    gerber.mkdir(exist_ok=True)
    run([cli, "pcb", "export", "gerbers", "-o", str(gerber), "--board-plot-params", str(pcb)])
    drill = out / "drill"
    drill.mkdir(exist_ok=True)
    run([cli, "pcb", "export", "drill", "-o", str(drill), "--format", "excellon", "--generate-map", str(pcb)])
    run([cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
         "-o", str(out / f"{name}_pos.csv"), str(pcb)])


def write_manifest() -> None:
    manifest = []
    for p in sorted(ART.rglob("*")):
        if p.is_file() and p.name != "sha256_manifest.json":
            manifest.append({"path": str(p.relative_to(ART)), "sha256": sha256(p), "bytes": p.stat().st_size})
    (ART / "sha256_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="require all three complete SCH/PCB/PRO native sets")
    ap.add_argument("--run-cli", action="store_true", help="run CLI checks for every available native PCB/SCH")
    args = ap.parse_args()

    ART.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "configuration": "EVT-PRE-20 Rev.A",
        "boards": {},
        "release": "BLOCKED_NOT_FOR_MANUFACTURE",
    }
    all_missing: list[str] = []
    complete_sets: list[str] = []

    for name in BOARDS:
        p = paths(name)
        missing = [str(x.relative_to(ROOT)) for x in p.values() if not x.is_file()]
        all_missing.extend(missing)
        if not missing:
            complete_sets.append(name)
        report["boards"][name] = {
            "source_files": {k: str(x.relative_to(ROOT)) for k, x in p.items()},
            "missing": missing,
            "pcb_state": "SOURCE_PRESENT_PENDING_CLI" if p["pcb"].is_file() else "MISSING",
            "sch_state": "SOURCE_PRESENT_PENDING_CLI" if p["sch"].is_file() else "MISSING",
            "project_state": "PRESENT" if p["pro"].is_file() else "MISSING",
        }

    if args.run_cli:
        cli = shutil.which("kicad-cli")
        if not cli:
            raise SystemExit("kicad-cli not found")
        run([cli, "version"])
        for name in BOARDS:
            p = paths(name)
            if p["pcb"].is_file():
                validate_pcb(cli, name, p["pcb"])
                report["boards"][name]["pcb_state"] = "CLI_DRC_EXPORT_PASS_REVIEW_B_PENDING"
            if p["sch"].is_file():
                validate_schematic(cli, name, p["sch"])
                report["boards"][name]["sch_state"] = "CLI_ERC_PDF_PASS_REVIEW_A_PENDING"
        write_manifest()

    if not all_missing:
        report["release"] = "ALL_NATIVE_SOURCES_PRESENT_REVIEW_A_B_STILL_REQUIRED"
    else:
        report["missing"] = all_missing

    (ART / "native_gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Complete native sets:", ", ".join(complete_sets) if complete_sets else "none")
    print(f"Overall release gate remains BLOCKED; {len(all_missing)} required source files missing")

    if args.strict and all_missing:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

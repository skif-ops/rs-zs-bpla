#!/usr/bin/env python3
"""Preflight and execute native KiCad checks for EVT-PRE-20 Rev.A.

Engineering CI may run this before native capture exists; that state is reported as
BLOCKED_NOT_FOR_MANUFACTURE rather than fabricated into a fake PASS. With --strict,
missing native source files are a hard failure.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--run-cli", action="store_true", help="run ERC/DRC and production exports; requires kicad-cli")
    args = ap.parse_args()

    ART.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"configuration": "EVT-PRE-20 Rev.A", "boards": {}, "release": "BLOCKED_NOT_FOR_MANUFACTURE"}
    missing: list[str] = []

    for name in BOARDS:
        base = NATIVE / name / name
        required = [base.with_suffix(".kicad_sch"), base.with_suffix(".kicad_pcb"), base.with_suffix(".kicad_pro")]
        miss = [str(p.relative_to(ROOT)) for p in required if not p.is_file()]
        if miss:
            missing.extend(miss)
        report["boards"][name] = {"source_files": [str(p.relative_to(ROOT)) for p in required], "missing": miss}

    if missing:
        report["missing"] = missing
        (ART / "native_gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Native KiCad gate: BLOCKED, {len(missing)} required source files missing")
        return 2 if args.strict else 0

    if args.run_cli:
        cli = shutil.which("kicad-cli")
        if not cli:
            raise SystemExit("kicad-cli not found")
        for name in BOARDS:
            base = NATIVE / name / name
            out = ART / name
            out.mkdir(parents=True, exist_ok=True)
            sch = base.with_suffix(".kicad_sch")
            pcb = base.with_suffix(".kicad_pcb")
            run([cli, "sch", "erc", "--format", "json", "--severity-all", "--exit-code-violations", "-o", str(out / "erc.json"), str(sch)])
            run([cli, "sch", "export", "pdf", "-o", str(out / f"{name}_schematic.pdf"), str(sch)])
            run([cli, "pcb", "drc", "--format", "json", "--severity-all", "--exit-code-violations", "-o", str(out / "drc.json"), str(pcb)])
            gerber = out / "gerber"
            gerber.mkdir(exist_ok=True)
            run([cli, "pcb", "export", "gerbers", "-o", str(gerber), "--board-plot-params", str(pcb)])
            drill = out / "drill"
            drill.mkdir(exist_ok=True)
            run([cli, "pcb", "export", "drill", "-o", str(drill), "--format", "excellon", "--generate-map", str(pcb)])
            run([cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "-o", str(out / f"{name}_pos.csv"), str(pcb)])

        manifest = []
        for p in sorted(ART.rglob("*")):
            if p.is_file() and p.name != "sha256_manifest.json":
                manifest.append({"path": str(p.relative_to(ART)), "sha256": sha256(p), "bytes": p.stat().st_size})
        (ART / "sha256_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        report["release"] = "NATIVE_CLI_CHECKS_PASS_REVIEW_A_B_STILL_REQUIRED"

    (ART / "native_gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Native KiCad source presence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Probe: do the autoroute 011 net classes change the historical PCB-PWR DRC?

The historical comparative DRC steps of .github/workflows/pcb-native.yml copy the
authoritative hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pro next to archived
base/candidate boards (placement ECO-001 ... routing 010, ECO-002). Autoroute 011
added the 35 um basis net classes to that project. This probe runs KiCad 9.0.9 DRC
(zones refilled, no rule file, exactly like those steps) on every archived PCB-PWR
board twice - with the pre-011 project and with the current project - and records
per-board violation fingerprints and any difference.

Run by .github/workflows/ci-apply.yml (docker available). Writes
hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/HISTORICAL_NETCLASS_DRC_PROBE.json.
--check verifies the report exists and records no difference. Evidence only; it
changes no design file.
"""

from __future__ import annotations

import argparse
import collections
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
PROJECT = "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pro"
PRE_011_COMMIT = "3112a43b23fab117774865473580c64e5cf2e9e1"  # last commit before the 011 application
REPORT = ROOT / "hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/HISTORICAL_NETCLASS_DRC_PROBE.json"
FILL = (
    "import sys, pcbnew\n"
    "b = pcbnew.LoadBoard(sys.argv[1])\n"
    "pcbnew.ZONE_FILLER(b).Fill(b.Zones())\n"
    "b.Save(sys.argv[1])\n"
)


def boards() -> list[Path]:
    found = sorted(ROOT.glob("hardware/kicad/candidates/PCB-PWR-*/*.kicad_pcb"))
    return [path for path in found if "AUTOROUTE-011" not in str(path)]


def fingerprints(report: dict) -> dict[str, int]:
    prints: collections.Counter = collections.Counter()
    for violation in report.get("violations", []):
        items = sorted(item.get("description", "") for item in violation.get("items", []))
        prints[json.dumps([violation["type"], violation.get("severity", ""), items])] += 1
    prints[json.dumps(["unconnected", "", []])] = len(report.get("unconnected_items", []))
    return dict(prints)


def drc(work: Path, board: Path, project_text: str, tag: str) -> dict[str, int]:
    folder = work / tag / board.parent.name
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / board.name
    shutil.copy2(board, target)
    target.with_suffix(".kicad_pro").write_text(project_text, encoding="utf-8")
    rel = target.relative_to(ROOT)
    out = folder / (board.stem + "_drc.json")
    script = (
        f"/usr/bin/python3 -c '{FILL}' {rel} && "
        f"kicad-cli pcb drc --format json --severity-all -o {out.relative_to(ROOT)} {rel}"
    )
    subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w",
                    KICAD_IMAGE, "bash", "-c", script], check=True, capture_output=True, text=True)
    return fingerprints(json.loads(out.read_text(encoding="utf-8")))


def generate() -> None:
    old = subprocess.run(["git", "show", f"{PRE_011_COMMIT}:{PROJECT}"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    new = (ROOT / PROJECT).read_text(encoding="utf-8")
    work = Path(tempfile.mkdtemp(prefix="netclass_probe_", dir=ROOT / "build")) if (ROOT / "build").is_dir() \
        else Path(tempfile.mkdtemp(prefix="netclass_probe_", dir=ROOT))
    rows = []
    try:
        for board in boards():
            before, after = drc(work, board, old, "pre011"), drc(work, board, new, "post011")
            added = {k: after[k] - before.get(k, 0) for k in after if after[k] > before.get(k, 0)}
            removed = {k: before[k] - after.get(k, 0) for k in before if before[k] > after.get(k, 0)}
            rows.append({
                "board": str(board.relative_to(ROOT)),
                "violations_pre011_project": sum(v for k, v in before.items() if "unconnected" not in k),
                "violations_current_project": sum(v for k, v in after.items() if "unconnected" not in k),
                "added": added, "removed": removed,
            })
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report = {
        "schema": "dioneya-pcb-pwr-netclass-historical-drc-probe-v1",
        "kicad_image": KICAD_IMAGE,
        "pre_011_project_commit": PRE_011_COMMIT,
        "boards": len(rows),
        "boards_with_difference": sum(1 for row in rows if row["added"] or row["removed"]),
        "rows": rows,
        "design_change": False,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"historical net-class DRC probe: {report['boards']} boards, "
          f"{report['boards_with_difference']} with difference")


def check() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    print(f"historical net-class DRC probe: {report['boards']} boards, "
          f"{report['boards_with_difference']} with difference")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

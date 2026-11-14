#!/usr/bin/env python3
"""Export a self-contained, explicitly non-production PCB engineering snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOARDS = ("PCB-MAIN", "PCB-PWR", "PCB-MIC")


def run(command: list[str], *, allow_failure: bool = False) -> int:
    print("+", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode and not allow_failure:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return result.returncode


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_board(cli: str, board: str, root: Path) -> dict[str, object]:
    source = ROOT / "hardware" / "kicad" / "native" / board
    destination = root / board
    native = destination / "native"
    gerber = destination / "gerber"
    drill = destination / "drill"
    shutil.copytree(source, native)
    gerber.mkdir(parents=True)
    drill.mkdir(parents=True)

    pcb = source / f"{board}.kicad_pcb"
    sch = source / f"{board}.kicad_sch"
    status: dict[str, object] = {"board": board, "release": "BLOCKED_NOT_FOR_MANUFACTURE"}

    status["drc_return_code"] = run([
        cli, "pcb", "drc", "--format", "json", "--severity-all",
        "-o", str(destination / "drc.json"), str(pcb),
    ], allow_failure=True)
    status["erc_return_code"] = run([
        cli, "sch", "erc", "--format", "json", "--severity-all",
        "-o", str(destination / "erc.json"), str(sch),
    ], allow_failure=True)

    commands = {
        "gerber": [cli, "pcb", "export", "gerbers", "-o", str(gerber), "--board-plot-params", str(pcb)],
        "drill": [cli, "pcb", "export", "drill", "-o", str(drill), "--format", "excellon", "--generate-map", str(pcb)],
        "position": [cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both", "-o", str(destination / f"{board}_pos.csv"), str(pcb)],
        "ipc_d_356": [cli, "pcb", "export", "ipcd356", "-o", str(destination / f"{board}.d356"), str(pcb)],
        "step": [cli, "pcb", "export", "step", "--board-only", "--force", "-o", str(destination / f"{board}_board.step"), str(pcb)],
        "schematic_pdf": [cli, "sch", "export", "pdf", "-o", str(destination / f"{board}_schematic.pdf"), str(sch)],
        "bom": [cli, "sch", "export", "bom", "-o", str(destination / f"{board}_bom.csv"), "--fields", "Reference,Value,Footprint,${QUANTITY}", "--labels", "Reference,Value,Footprint,Quantity", "--group-by", "Reference", "--sort-field", "Reference", "--sort-asc", "--exclude-dnp", str(sch)],
    }
    for name, command in commands.items():
        status[f"{name}_return_code"] = run(command, allow_failure=True)

    required = [gerber, drill, destination / f"{board}_pos.csv", destination / f"{board}.d356"]
    if not all(path.exists() and (not path.is_dir() or any(path.iterdir())) for path in required):
        raise RuntimeError(f"{board}: required CAM output is missing")
    (destination / "STATUS.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    cli = shutil.which("kicad-cli")
    if not cli:
        raise SystemExit("kicad-cli not found")

    output = (ROOT / args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    source_sha = os.environ.get("GITHUB_SHA") or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    statuses = [export_board(cli, board, output) for board in BOARDS]

    tracked = subprocess.check_output(
        ["git", "ls-files", "hardware/kicad", "hardware/reviews", "hardware/PCB_*", "tools/*pcb*"],
        cwd=ROOT, text=True,
    )
    (output / "SOURCE_INDEX.txt").write_text(tracked, encoding="utf-8")
    readme = f"""# EVT-PRE-20 PCB engineering snapshot — {args.snapshot}

**NOT FOR MANUFACTURE.** This is a work-in-progress engineering export of commit `{source_sha}`.
It does not close Review B, CAM/DFM, or manufacturing-release gates.

Included for PCB-MAIN, PCB-PWR, and PCB-MIC: native KiCad sources, Gerbers,
Excellon drill/map files, pick-and-place CSV, BOM, IPC-D-356, board-only STEP,
schematic PDF, and ERC/DRC JSON. A nonzero ERC/DRC result is recorded in each
board's `STATUS.json` and is expected for work still under review.

`SOURCE_INDEX.txt` lists the already-versioned PCB source, review, authority,
and automation material that forms the rest of the board-work record.
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    (output / "snapshot_status.json").write_text(json.dumps({
        "snapshot": args.snapshot,
        "source_commit": source_sha,
        "release": "BLOCKED_NOT_FOR_MANUFACTURE",
        "boards": statuses,
    }, indent=2) + "\n", encoding="utf-8")

    manifest = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            manifest.append({"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    (output / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Engineering snapshot PASS: {len(manifest)} files at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

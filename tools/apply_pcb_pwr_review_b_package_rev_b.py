#!/usr/bin/env python3
"""Export the PCB-PWR Review B package, Rev B (after ECO-005, response to Review B R1).

Run by .github/workflows/ci-apply.yml (docker available). Uses the pinned KiCad 9.0.9 image on
the authoritative board/project/rules/libraries; changes no design file. The Rev A package stays
untouched as the record of the first review round.
Output: hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_B/
  PCB-PWR_copper_layers.pdf      F.Cu, In1.Cu, In2.Cu, B.Cu (one page each, outline)
  PCB-PWR_assembly.pdf           F/B fabrication + silkscreen pages
  PCB-PWR_top.png / _bottom.png  3D renders
  PCB-PWR_schematic.pdf          native hierarchical schematic
  PCB-PWR_drc.rpt / _drc.json    KiCad DRC with the authoritative rule file and project libraries
  gerber/ drill/                 Gerber X2 (silkscreen minus solder mask), Excellon + map - review only
  PCB-PWR_pos.csv, PCB-PWR.d356  placement and IPC-D-356 netlist
  POWER_COPPER_WIDTH.json        measured power-copper width (method of Rev A, current board)
  CURRENT_EVIDENCE.json          current-carrying evidence of ECO-005 (cases, every narrow group)
  REVIEW_B_CHECKLIST.md          reviewer checklist with the response to every R1 finding
  MANIFEST.json                  inputs (board, project, rules, schematic, libraries), commands,
                                 return codes, SHA-256 of every output
Differences to Rev A: the scratch copy carries PCB-MAIN/libs next to PCB-PWR, so the project
library table resolves DioneyaMain (Rev A reported J2/U5 lib_footprint_issues for that reason);
Gerbers subtract the solder mask from the silkscreen (--subtract-soldermask).
--check verifies MANIFEST.json binds the current board, project, rules and library files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_pwr_review_b_package_rev_a as rev_a  # noqa: E402

KICAD_IMAGE = rev_a.KICAD_IMAGE
NATIVE = "hardware/kicad/native/PCB-PWR"
MAIN_LIBS = "hardware/kicad/native/PCB-MAIN/libs"
BOARD = f"{NATIVE}/PCB-PWR.kicad_pcb"
OUT = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_B"
REL = OUT.relative_to(ROOT)
SCRATCH_ROOT = "build/review_b_rev_b_src"
SCRATCH = f"{SCRATCH_ROOT}/PCB-PWR"
SRC_BOARD = f"{SCRATCH}/PCB-PWR.kicad_pcb"
SRC_SCHEMATIC = f"{SCRATCH}/PCB-PWR.kicad_sch"
EVIDENCE = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-005/CURRENT_EVIDENCE.json"
ECO_RECORD = ROOT / "hardware/reviews/PCB_PWR_ECO_005_REV_A.md"
REV_A_MANIFEST = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_A/MANIFEST.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commands() -> list[tuple[str, list[str]]]:
    board, schematic = SRC_BOARD, SRC_SCHEMATIC
    return [
        ("drc_report", ["kicad-cli", "pcb", "drc", "--format", "report", "--severity-all",
                        "-o", f"{REL}/PCB-PWR_drc.rpt", board]),
        ("drc_json", ["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                      "-o", f"{REL}/PCB-PWR_drc.json", board]),
        ("copper_pdf", ["kicad-cli", "pcb", "export", "pdf", "-o", f"{REL}/copper-pdf",
                        "--layers", "F.Cu,In1.Cu,In2.Cu,B.Cu", "--common-layers", "Edge.Cuts",
                        "--mode-multipage", "--include-border-title", "--drill-shape-opt", "2", board]),
        ("assembly_pdf", ["kicad-cli", "pcb", "export", "pdf", "-o", f"{REL}/assembly-pdf",
                          "--layers", "F.Fab,F.Silkscreen,B.Fab,B.Silkscreen", "--common-layers", "Edge.Cuts",
                          "--mode-multipage", "--sketch-pads-on-fab-layers", "--include-border-title",
                          "--drill-shape-opt", "2", board]),
        ("render_top", ["kicad-cli", "pcb", "render", "-o", f"{REL}/PCB-PWR_top.png", "--side", "top",
                        "--width", "1800", "--height", "1300", "--quality", "basic", board]),
        ("render_bottom", ["kicad-cli", "pcb", "render", "-o", f"{REL}/PCB-PWR_bottom.png", "--side", "bottom",
                           "--width", "1800", "--height", "1300", "--quality", "basic", board]),
        ("schematic_pdf", ["kicad-cli", "sch", "export", "pdf", "-o", f"{REL}/PCB-PWR_schematic.pdf", schematic]),
        ("gerbers", ["kicad-cli", "pcb", "export", "gerbers", "--subtract-soldermask", "-o", f"{REL}/gerber/", board]),
        ("drill", ["kicad-cli", "pcb", "export", "drill", "-o", f"{REL}/drill/", "--format", "excellon",
                   "--generate-map", board]),
        ("pos", ["kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                 "-o", f"{REL}/PCB-PWR_pos.csv", board]),
        ("ipcd356", ["kicad-cli", "pcb", "export", "ipcd356", "-o", f"{REL}/PCB-PWR.d356", board]),
    ]


def inputs() -> dict:
    files = {BOARD: sha256(ROOT / BOARD)}
    for name in ("PCB-PWR.kicad_pro", "PCB-PWR.kicad_dru", "PCB-PWR.kicad_sch", "fp-lib-table", "sym-lib-table"):
        path = ROOT / NATIVE / name
        if path.exists():
            files[f"{NATIVE}/{name}"] = sha256(path)
    for path in sorted((ROOT / NATIVE).glob("PCB-PWR_*.kicad_sch")):
        files[str(path.relative_to(ROOT))] = sha256(path)
    for path in sorted((ROOT / NATIVE / "libs").rglob("*")):
        if path.is_file():
            files[str(path.relative_to(ROOT))] = sha256(path)
    import re

    board_text = (ROOT / BOARD).read_text(encoding="utf-8")
    for name in sorted(set(re.findall(r'\(footprint "DioneyaMain:([^"]+)"', board_text))):
        path = ROOT / MAIN_LIBS / "DioneyaMain.pretty" / f"{name}.kicad_mod"
        files[str(path.relative_to(ROOT))] = sha256(path)  # shared footprints used by PCB-PWR only
    return files


def generate() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    keep = {"REVIEW_B_CHECKLIST.md"}
    for item in OUT.iterdir():
        if item.name not in keep:
            shutil.rmtree(item) if item.is_dir() else item.unlink()
    scratch_root = ROOT / SCRATCH_ROOT
    shutil.rmtree(scratch_root, ignore_errors=True)
    shutil.copytree(ROOT / NATIVE, ROOT / SCRATCH)
    shutil.copytree(ROOT / MAIN_LIBS, scratch_root / "PCB-MAIN" / "libs")
    for sub in ("gerber", "drill", "copper-pdf", "assembly-pdf"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    steps = []
    for name, argv in commands():
        result = rev_a.docker(argv)
        steps.append({"step": name, "command": " ".join(argv), "rc": result.returncode,
                      "stderr_tail": (result.stderr or "")[-1500:]})
    subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                    "chmod", "-R", "a+rwX", str(REL)], capture_output=True)
    subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                    "rm", "-rf", SCRATCH_ROOT], capture_output=True)
    shutil.rmtree(scratch_root, ignore_errors=True)
    rev_a.flatten_pdf(OUT / "copper-pdf", OUT / "PCB-PWR_copper_layers.pdf")
    rev_a.flatten_pdf(OUT / "assembly-pdf", OUT / "PCB-PWR_assembly.pdf")
    try:
        width = rev_a.power_copper_width()
    except Exception as error:  # noqa: BLE001 - recorded, the package still carries the KiCad outputs
        width = {"error": repr(error)}
    (OUT / "POWER_COPPER_WIDTH.json").write_text(json.dumps(width, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["board_sha256"] == sha256(ROOT / BOARD), "current evidence does not bind the current board"
    shutil.copyfile(EVIDENCE, OUT / "CURRENT_EVIDENCE.json")
    drc = json.loads((OUT / "PCB-PWR_drc.json").read_text(encoding="utf-8"))
    counts: dict = {}
    for violation in drc.get("violations", []):
        key = f"{violation['severity']}:{violation['type']}"
        counts[key] = counts.get(key, 0) + 1
    outputs = {str(path.relative_to(OUT)): sha256(path)
               for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "MANIFEST.json"}
    manifest = {
        "schema": "dioneya-pcb-pwr-review-b-package-v2",
        "revision": "REV_B",
        "responds_to": "Review B R1 (REQUEST_CHANGES) - hardware/reviews/PCB_PWR_ECO_005_REV_A.md",
        "kicad_image": KICAD_IMAGE,
        "board_sha256": sha256(ROOT / BOARD),
        "rules_sha256": sha256(ROOT / f"{NATIVE}/PCB-PWR.kicad_dru"),
        "project_sha256": sha256(ROOT / f"{NATIVE}/PCB-PWR.kicad_pro"),
        "eco_record_sha256": sha256(ECO_RECORD),
        "previous_package_manifest_sha256": sha256(REV_A_MANIFEST),
        "inputs": inputs(),
        "drc": {"error_total": sum(n for k, n in counts.items() if k.startswith("error:")),
                "unconnected_total": len(drc.get("unconnected_items", [])), "by_type": counts},
        "steps": steps,
        "outputs": outputs,
        "manufacturing_release": False,
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [s["step"] for s in steps if s["rc"] != 0]
    print(f"PCB-PWR Review B package Rev B: {len(outputs)} files, DRC {manifest['drc']}, failed steps: {failed or 'none'}")
    assert not failed, f"KiCad steps failed: {failed}"


def check() -> None:
    manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["board_sha256"] == sha256(ROOT / BOARD), "Review B package does not bind the current board"
    assert manifest["inputs"] == inputs(), "Review B package inputs (project/rules/schematic/libraries) drifted"
    for name, digest in manifest["outputs"].items():
        assert sha256(OUT / name) == digest, f"package output {name} differs from MANIFEST.json"
    assert manifest["drc"]["error_total"] == 0 and manifest["drc"]["unconnected_total"] == 0, "package DRC not clean"
    print(f"PCB-PWR Review B package Rev B: PASS {len(manifest['outputs'])} files, DRC {manifest['drc']['by_type']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

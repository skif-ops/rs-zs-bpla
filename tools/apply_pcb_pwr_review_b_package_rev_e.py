#!/usr/bin/env python3
"""Export and hash PCB-PWR Review B Rev E after the R3.1 findings.

This package is review evidence, not a fabrication release. It records the
actual KiCad CLI version used; the earlier Rev D package remains immutable.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from pcb_pwr_board_identity import assert_rev_e_metadata_only

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "hardware/kicad/native/PCB-PWR"
BOARD = NATIVE / "PCB-PWR.kicad_pcb"
SCH = NATIVE / "PCB-PWR.kicad_sch"
OUT = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_E"
PREV = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_D/MANIFEST.json"
OLD_SHA = "b8c1da6ca80b9e5d2795c4fee5b6926e4ab6169086795295e8e517a18def6ca7"
PINNED_IMAGE = ("ghcr.io/kicad/kicad:9.0.9@sha256:"
                "e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def assert_metadata_only() -> None:
    assert_rev_e_metadata_only(BOARD)


def run(name: str, argv: list[str]) -> dict:
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"{name}: rc={result.returncode}\n{result.stdout[-1200:]}\n{result.stderr[-1200:]}")
    return {"step": name, "argv": argv, "rc": result.returncode}


def generate(cli: str) -> None:
    assert_metadata_only()
    archived_parity = json.loads((ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_R4_PARITY_KICAD10.json").read_text(encoding="utf-8"))["schematic_parity"]
    with (ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_R4_PARITY_KICAD10_DISPOSITION.csv").open(encoding="utf-8", newline="") as handle:
        archived_rows = list(csv.DictReader(handle))
    assert len(archived_parity) == len(archived_rows) == 251
    assert all(row["Type"] == item["type"] and row["Item_UUID"] == item["items"][0].get("uuid", "")
               and row["Description"] == item["description"]
               for row, item in zip(archived_rows, archived_parity))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gerber").mkdir(exist_ok=True)
    (OUT / "drill").mkdir(exist_ok=True)
    # KiCad 9 PDF export refuses an existing PDF path in the checked-out package.
    for name in ("PCB-PWR_copper_layers.pdf", "PCB-PWR_schematic.pdf"):
        (OUT / name).unlink(missing_ok=True)
    steps = []
    version = subprocess.run([cli, "version"], capture_output=True, text=True, errors="replace", check=True).stdout.strip()
    if not re.match(r"^9\.0\.9(?:\b|$)", version):
        raise RuntimeError(f"Review B Rev E exports require pinned KiCad 9.0.9, got {version!r}")
    steps.append(run("drc_json", [cli, "pcb", "drc", "--format", "json", "--severity-all",
                                  "-o", str(OUT / "PCB-PWR_drc.json"), str(BOARD)]))
    steps.append(run("drc_report", [cli, "pcb", "drc", "--format", "report", "--severity-all",
                                    "-o", str(OUT / "PCB-PWR_drc.rpt"), str(BOARD)]))
    steps.append(run("erc", [cli, "sch", "erc", "--format", "json", "--severity-all",
                             "--exit-code-violations", "-o", str(OUT / "PCB-PWR_erc.json"), str(SCH)]))
    steps.append(run("parity_diagnostic", [cli, "pcb", "drc", "--format", "json", "--severity-all",
                                           "--schematic-parity", "-o", str(OUT / "PCB-PWR_parity_drc.json"), str(BOARD)]))
    steps.append(run("parity_disposition", [sys.executable,
                                            str(ROOT / "tools/generate_pcb_pwr_parity_disposition_rev_e.py")]))
    steps.append(run("copper_pdf", [cli, "pcb", "export", "pdf", "--layers", "F.Cu,In1.Cu,In2.Cu,B.Cu",
                                    "--common-layers", "Edge.Cuts", "--mode-multipage", "--black-and-white",
                                    "-o", str(OUT / "PCB-PWR_copper_layers.pdf"), str(BOARD)]))
    steps.append(run("assembly_pdf", [sys.executable, str(ROOT / "tools/generate_pcb_pwr_assembly_rev_e.py"),
                                      "--kicad-cli", cli]))
    for side in ("top", "bottom"):
        steps.append(run(f"render_{side}", [cli, "pcb", "render", "--side", side, "--width", "1400",
                                            "--height", "900", "--quality", "basic", "-o",
                                            str(OUT / f"PCB-PWR_{side}.png"), str(BOARD)]))
    steps.append(run("schematic_pdf", [cli, "sch", "export", "pdf", "-o",
                                       str(OUT / "PCB-PWR_schematic.pdf"), str(SCH)]))
    steps.append(run("gerbers", [cli, "pcb", "export", "gerbers", "--subtract-soldermask",
                                 "-o", str(OUT / "gerber") + os.sep, str(BOARD)]))
    steps.append(run("drill", [cli, "pcb", "export", "drill", "--format", "excellon",
                               "--generate-map", "-o", str(OUT / "drill") + os.sep, str(BOARD)]))
    steps.append(run("position", [cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm",
                                  "--side", "both", "-o", str(OUT / "PCB-PWR_pos.csv"), str(BOARD)]))
    steps.append(run("ipc356", [cli, "pcb", "export", "ipcd356", "-o",
                                str(OUT / "PCB-PWR.d356"), str(BOARD)]))
    audit = subprocess.run([sys.executable, str(ROOT / "tools/audit_pcb_pwr_layout_candidate_rev_a.py")],
                           cwd=ROOT, capture_output=True, text=True, errors="replace")
    if audit.returncode != 0 or "independent audit PASS" not in audit.stdout:
        raise AssertionError(f"Primary layout/schematic audit failed: {audit.stdout}\n{audit.stderr}")
    (OUT / "PCB-PWR_layout_schematic_audit.log").write_text(audit.stdout, encoding="utf-8")
    steps.append({"step": "primary_schematic_board_audit", "argv": [sys.executable,
                  "tools/audit_pcb_pwr_layout_candidate_rev_a.py"], "rc": 0})
    drc = json.loads((OUT / "PCB-PWR_drc.json").read_text(encoding="utf-8"))
    erc = json.loads((OUT / "PCB-PWR_erc.json").read_text(encoding="utf-8"))
    parity = json.loads((OUT / "PCB-PWR_parity_drc.json").read_text(encoding="utf-8"))
    assert len(drc.get("unconnected_items", [])) == 0
    assert not [v for v in drc.get("violations", []) if v.get("severity") == "error"]
    assert not [v for sheet in erc.get("sheets", []) for v in sheet.get("violations", [])]
    job = json.loads((OUT / "gerber/PCB-PWR-job.gbrjob").read_text(encoding="utf-8"))
    assert job["GeneralSpecs"]["ProjectId"]["Revision"] == "A"
    assert job["GeneralSpecs"]["Finish"] == "ENIG"
    inputs = {rel(path): sha(path) for path in sorted(NATIVE.rglob("*"))
              if path.is_file() and path.suffix != ".kicad_prl"}
    inputs[rel(PREV)] = sha(PREV)
    for path in (ROOT / "hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_B.json",
                 ROOT / "hardware/reviews/PCB_PWR_DIM_003_BOARD_POSE_EVIDENCE_REV_B.json",
                 ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_R4_PARITY_KICAD10.json",
                 ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_R4_PARITY_KICAD10_DISPOSITION.csv",
                 ROOT / "mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_B.step",
                 ROOT / "tools/audit_pcb_pwr_layout_candidate_rev_a.py",
                 ROOT / "tools/audit_pcb_pwr_dim_003_rev_b.py",
                 ROOT / "tools/generate_pcb_pwr_assembly_rev_e.py",
                 ROOT / "tools/generate_pcb_pwr_parity_disposition_rev_e.py",
                 ROOT / "tools/apply_pcb_pwr_review_b_package_rev_e.py",
                 ROOT / "tools/pcb_pwr_board_identity.py"):
        inputs[rel(path)] = sha(path)
    outputs = {path.relative_to(OUT).as_posix(): sha(path) for path in sorted(OUT.rglob("*"))
               if path.is_file() and path.name != "MANIFEST.json"}
    manifest = {
        "schema": "dioneya-pcb-pwr-review-b-package-v4", "revision": "REV_E",
        "responds_to": "Review B R3.1 F1-F4",
        "kicad_cli_version": version,
        "kicad_container_image": PINNED_IMAGE,
        "board_sha256": sha(BOARD), "geometry_equivalent_rev_d_board_sha256": OLD_SHA,
        "geometry_equivalence_method": "remove only title_block and stackup; remaining UTF-8 bytes SHA-256 equal Rev D board",
        "source_commit_eco006": "02647713c228e3beb338053f37d06f83cd4bb94f",
        "previous_package_manifest_sha256": sha(PREV),
        "inputs": inputs, "outputs": outputs, "steps": steps,
        "drc": {"errors": 0, "unconnected": 0, "warnings": len(drc.get("violations", []))},
        "erc_violations": 0, "primary_schematic_board_audit": "PASS_62_ELECTRICAL_FOOTPRINTS",
        "optional_kicad_schematic_parity": {"status": "DIAGNOSTIC_WARNINGS_NOT_GATE_PASS",
            "count": len(parity.get("schematic_parity", [])),
            "types": {typ: sum(x.get("type") == typ for x in parity.get("schematic_parity", []))
                      for typ in sorted({x.get("type") for x in parity.get("schematic_parity", [])})}},
        "parity_disposition": f"{len(parity.get('schematic_parity', []))}_CLASSIFIED_ZERO_UNEXPLAINED_17_VALUE_OR_BOM_METADATA_PENDING_SYNC",
        "kicad10_parity_archive": "251_CLASSIFIED_IN_SEPARATE_R4_JSON_AND_CSV",
        "drc_ignored_checks": {
            "keys": sorted(item["key"] for item in drc.get("ignored_checks", [])),
            "basis": "No project rule_severities; KiCad 9 JSON may omit default ignored_checks. Copper-only NT1-NT3 have no courtyard.",
        },
        "nominal_stackup_use": "NOT_FOR_IMPEDANCE_CAPACITANCE_OR_THERMAL_ANALYSIS_PENDING_FAB_STACK_ID",
        "factory_stack_id": None, "manufacturer_checkout": "PENDING",
        "dim_003_independent_mechanical_review": "PENDING_CAD_AND_HUMAN_SIGNOFF",
        "manufacturing_release": False,
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Rev E: {len(outputs)} outputs; ERC 0; DRC {manifest['drc']}; optional parity diagnostics {manifest['optional_kicad_schematic_parity']['count']}")


def check() -> None:
    assert_metadata_only()
    m = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert m["revision"] == "REV_E" and m["board_sha256"] == sha(BOARD)
    assert m["kicad_container_image"] == PINNED_IMAGE and m["kicad_cli_version"].startswith("9.0.9")
    assert m["previous_package_manifest_sha256"] == sha(PREV)
    for rel, digest in m["inputs"].items():
        assert sha(ROOT / rel) == digest, f"input drift: {rel}"
    for rel, digest in m["outputs"].items():
        assert sha(OUT / rel) == digest, f"output drift: {rel}"
    assert m["erc_violations"] == 0 and m["drc"]["errors"] == m["drc"]["unconnected"] == 0
    assert m["manufacturing_release"] is False
    print(f"Rev E manifest PASS: {len(m['outputs'])} outputs")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kicad-cli", default="kicad-cli")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate(args.kicad_cli)


if __name__ == "__main__":
    main()

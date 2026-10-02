#!/usr/bin/env python3
"""Audit the signed PCB-MIC Rev B controlled first-article release."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from audit_pcb_mic_review_b_preflight_rev_a import (
    EXPECTED_COMPONENTS,
    EXPECTED_GERBERS,
    HOLES,
    flashes_at,
    parse_gerber,
)


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pcb"
STATUS = ROOT / "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json"
APPROVAL = ROOT / "hardware/reviews/PCB_MIC_REVIEW_B_APPROVAL_REV_B.json"
PARITY = ROOT / "hardware/reviews/PCB_MIC_PARITY_DISPOSITION_REV_B.csv"


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_bytes(commit: str, path: Path) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{commit}:{path.relative_to(ROOT).as_posix()}"], cwd=ROOT
    )


def cli_reports(root: Path) -> dict[str, Any]:
    drc = json_file(root / "drc.json")
    erc = json_file(root / "erc.json")
    require(str(drc.get("kicad_version", "")).startswith(("9.0.", "10.0.")),
            "DRC KiCad version is outside the controlled 9/10 range")
    require(drc.get("violations") == [], "DRC violations remain")
    require(drc.get("unconnected_items") == [], "unrouted items remain")
    sheets = erc.get("sheets", [])
    violations = [item for sheet in sheets for item in sheet.get("violations", [])]
    require(not violations, "ERC violations remain")
    return {
        "status": "PASS",
        "kicad_drc_version": drc.get("kicad_version"),
        "kicad_erc_version": erc.get("kicad_version"),
        "drc_violations": 0,
        "unrouted_items": 0,
        "erc_violations": 0,
    }


def cam_identity(root: Path) -> dict[str, Any]:
    record = json_file(root / "cam_source_transform.json")
    require(record.get("schema") == "dioneya-controlled-cam-source-identity-v2",
            "CAM source is not the Rev B byte-identical source")
    require(record.get("source_sha256") == sha256(BOARD), "CAM source hash mismatch")
    derived = root / "cam-source/PCB-MIC.kicad_pcb"
    require(derived.read_bytes() == BOARD.read_bytes(), "CAM input differs from native board")
    require(record.get("transformations") == [], "CAM source contains a hidden transform")
    return {"status": "PASS_BYTE_IDENTICAL", "sha256": sha256(derived)}


def gerbers(root: Path) -> dict[str, Any]:
    folder = root / "gerber"
    parsed = {name: parse_gerber(folder / name) for name in EXPECTED_GERBERS}
    for side in ("F", "B"):
        layer = parsed[f"PCB-MIC-{side}_Paste.gbr"]
        for label, (x, y, _) in HOLES.items():
            require(not flashes_at(layer, x, y), f"{side}.Paste flash remains at {label}")
    require(not parsed["PCB-MIC-Edge_Cuts.gbr"]["flashes"],
            "Edge.Cuts contains drill-guide flashes")
    top_paste = (folder / "PCB-MIC-F_Paste.gbr").read_text(encoding="utf-8")
    require(top_paste.count("G02*") == 4, "T5838 four-segment paste ring is missing")
    job = json_file(folder / "PCB-MIC-job.gbrjob")
    specs = job.get("GeneralSpecs", {})
    require(specs.get("ProjectId", {}).get("Revision") == "B", "Gerber job revision mismatch")
    require(specs.get("LayerNumber") == 2, "Gerber job layer count mismatch")
    require(abs(float(specs.get("BoardThickness", 0)) - 1.0) < 1e-9,
            "Gerber job thickness mismatch")
    require(specs.get("Finish") == "ENIG", "Gerber job finish mismatch")
    return {
        "status": "PASS",
        "files": len(parsed),
        "drill_guide_flashes": 0,
        "paste_flashes_at_npth": 0,
        "t5838_paste_segments": 4,
        "finish": "ENIG",
    }


def parse_drill(path: Path) -> tuple[dict[float, int], dict[float, set[tuple[float, float]]]]:
    text = path.read_text(encoding="utf-8")
    definitions = {tool: float(dia) for tool, dia in re.findall(r"^T(\d+)C([0-9.]+)$", text, re.M)}
    active = None
    hits: dict[str, list[tuple[float, float]]] = {tool: [] for tool in definitions}
    for raw in text.splitlines():
        line = raw.strip()
        match = re.fullmatch(r"T(\d+)", line)
        if match:
            active = match.group(1)
            continue
        match = re.fullmatch(r"X(-?[0-9.]+)Y(-?[0-9.]+)", line)
        if match and active in hits:
            hits[active].append((float(match.group(1)), float(match.group(2))))
    counts = {definitions[tool]: len(points) for tool, points in hits.items()}
    points = {definitions[tool]: set(values) for tool, values in hits.items()}
    return counts, points


def drills(root: Path) -> dict[str, Any]:
    pth = root / "drill/PCB-MIC-PTH.drl"
    npth = root / "drill/PCB-MIC-NPTH.drl"
    require(pth.is_file() and npth.is_file(), "separate PTH/NPTH files are missing")
    pth_counts, _ = parse_drill(pth)
    npth_counts, npth_points = parse_drill(npth)
    require(pth_counts == {0.3: 5}, f"PTH drill mismatch: {pth_counts}")
    require(npth_counts == {0.8: 1, 2.2: 2}, f"NPTH drill mismatch: {npth_counts}")
    require(npth_points[0.8] == {(12.0, -16.65)}, "acoustic NPTH coordinate mismatch")
    require(npth_points[2.2] == {(4.0, -16.65), (20.0, -16.65)},
            "mounting NPTH coordinates mismatch")
    return {"status": "PASS_SEPARATE_PTH_NPTH", "pth_hits": 5, "npth_hits": 3}


def boms(root: Path) -> dict[str, Any]:
    path = root / "PCB-MIC_manufacturing_bom.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_ref = {row["Reference"]: row for row in rows}
    require(set(by_ref) == set(EXPECTED_COMPONENTS), "manufacturing BOM reference set mismatch")
    for ref, expected in EXPECTED_COMPONENTS.items():
        require(by_ref[ref].get("Manufacturer") == expected["manufacturer"],
                f"{ref} manufacturer mismatch")
        require(by_ref[ref].get("MPN") == expected["mpn"], f"{ref} MPN mismatch")
    return {"status": "PASS_EXACT_MPN", "fitted_references": sorted(by_ref)}


def approval(commit_sha: str) -> dict[str, Any]:
    status = json_file(STATUS)
    signed = json_file(APPROVAL)
    review = status.get("review_b", {})
    require(status.get("release_state") == "REVIEW_B_PASS_CONTROLLED_FIRST_ARTICLE",
            "capture status is not the signed controlled first-article release")
    require(status.get("manufacturing_release") is True, "manufacturing release flag is false")
    require(review.get("complete") is True and review.get("decision") == "ACCEPT_CONTROLLED_FIRST_ARTICLE",
            "Review B decision is incomplete")
    require(review.get("reviewer") == "Скиф" and review.get("date") == "2026-09-30",
            "Review B reviewer/date mismatch")
    board_hash = sha256(BOARD)
    require(signed.get("native_board_sha256") == board_hash, "approval board hash mismatch")
    design_commit = signed.get("reviewed_design_commit_sha", "")
    require(re.fullmatch(r"[0-9a-f]{40}", design_commit) is not None,
            "approval design commit is invalid")
    require(git_bytes(design_commit, BOARD) == BOARD.read_bytes(),
            "approved board differs from the reviewed design commit")
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == commit_sha,
            "release evidence commit does not equal HEAD")
    with PARITY.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 55 and all(row.get("Disposition") for row in rows),
            "schematic parity disposition is incomplete")
    return {
        "status": "PASS_SIGNED",
        "reviewer": "Скиф",
        "date": "2026-09-30",
        "decision": "ACCEPT_CONTROLLED_FIRST_ARTICLE",
        "reviewed_design_commit_sha": design_commit,
        "release_evidence_commit_sha": commit_sha,
        "native_board_sha256": board_hash,
        "parity_items_disposed": 55,
    }


def audit(root: Path, commit_sha: str) -> dict[str, Any]:
    checks = {
        "approval": approval(commit_sha),
        "cli": cli_reports(root),
        "cam_source": cam_identity(root),
        "gerber": gerbers(root),
        "drill": drills(root),
        "bom": boms(root),
    }
    return {
        "schema": "dioneya-pcb-mic-review-b-release-v2",
        "status": "PASS_REVIEW_B_CONTROLLED_FIRST_ARTICLE_RELEASE",
        "configuration": "EVT-PRE-20",
        "assembly": "PCB-MIC",
        "checks": checks,
        "physical_evt": "REQUIRED_AFTER_ASSEMBLY",
        "fabrication_authorized": True,
        "scope": "CONTROLLED_FIRST_ARTICLE_THEN_REMAINDER_AFTER_INSPECTION",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    args = parser.parse_args()
    try:
        report = audit(args.artifact_root.resolve(), args.commit_sha)
        code = 0
    except Exception as exc:
        report = {"status": "FAIL_PCB_MIC_REVIEW_B_RELEASE", "error": str(exc)}
        code = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report["status"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())

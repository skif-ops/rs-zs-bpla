#!/usr/bin/env python3
"""Independent commit-bound PCB-MIC Review-B internal CAM preflight.

This audit consumes only committed native sources, frozen production authority and
the files emitted by KiCad 9. It is deliberately independent from the PCB generator
and from ``kicad_native_gate.py`` export logic. It can validate either a signed
Review-A source set or a post-ECO candidate. A candidate PASS does not close Review A.
An accepted copper-return subgate clears only its matching human-review flag. The
remaining Review-B signature, panelization, fabricator/assembler DFM, acoustic stack
validation, physical EVT and manufacturing release remain open.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pcb"
SCHEMATIC = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_sch"
PROJECT = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pro"
FABRICATION_METADATA = ROOT / "hardware/kicad/native/PCB-MIC/fabrication_metadata.json"
STATUS = ROOT / "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json"
PRODUCTION_BOM = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
NATIVE_GATE = ROOT / "tools/kicad_native_gate.py"
COPPER_RETURN_AUDIT = ROOT / "tools/audit_pcb_mic_copper_return_rev_a.py"
COPPER_RETURN_PACKET = ROOT / "hardware/reviews/PCB_MIC_REVIEW_B_COPPER_RETURN_REV_A.md"
GENERATOR = ROOT / "tools/generate_pcb_mic_clean_rev_a.py"
NATIVE_WORKFLOW = ROOT / ".github/workflows/pcb-native.yml"

EXPECTED_COMPONENTS = {
    "C1": {
        "value": "100nF X7R",
        "footprint": "Capacitor_SMD:C_0402_1005Metric",
        "manufacturer": "TDK",
        "mpn": "CGA2B3X7R1E104K050BB",
        "item_id": "C-MIC",
        "pnp": (14.1, -13.25, 0.0, "C_0402_1005Metric", "100nF X7R"),
    },
    "J1": {
        "value": "5040500691",
        "footprint": "Dioneya:Molex_5040500691",
        "manufacturer": "Molex",
        "mpn": "5040500691",
        "item_id": "J-MIC",
        "pnp": (12.0, -5.0, 180.0, "Molex_5040500691", "5040500691"),
    },
    "MK1": {
        "value": "MMICT5838-00-012",
        "footprint": "Dioneya:T5838_RevA",
        "manufacturer": "TDK InvenSense",
        "mpn": "MMICT5838-00-012",
        "item_id": "MK1",
        "pnp": (12.0, -16.0, 0.0, "T5838_RevA", "T5838"),
    },
    "R1": {
        "value": "0R EVT_SI_TUNE",
        "footprint": "Resistor_SMD:R_0402_1005Metric",
        "manufacturer": "Panasonic Industry",
        "mpn": "ERJ-2GE0R00X",
        "item_id": "R-MIC",
        "pnp": (11.25, -10.55, -90.0, "R_0402_1005Metric", "0R EVT_SI_TUNE"),
    },
}

HOLES = {
    "ACOUSTIC": (12.0, -16.65, 0.8),
    "H1": (4.0, -16.65, 2.2),
    "H2": (20.0, -16.65, 2.2),
}

EXPECTED_GERBERS = {
    "PCB-MIC-F_Cu.gbr": ("Copper,L1,Top", "Positive"),
    "PCB-MIC-B_Cu.gbr": ("Copper,L2,Bot", "Positive"),
    "PCB-MIC-F_Paste.gbr": ("SolderPaste,Top", "Positive"),
    "PCB-MIC-B_Paste.gbr": ("SolderPaste,Bot", "Positive"),
    "PCB-MIC-F_Silkscreen.gbr": ("Legend,Top", "Positive"),
    "PCB-MIC-B_Silkscreen.gbr": ("Legend,Bot", "Positive"),
    "PCB-MIC-F_Mask.gbr": ("SolderMask,Top", "Negative"),
    "PCB-MIC-B_Mask.gbr": ("SolderMask,Bot", "Negative"),
    "PCB-MIC-Edge_Cuts.gbr": ("Profile", "Positive"),
}

EXPECTED_TRACE_SIGNATURE = {
    ("1V8_MIC", "F.Cu"): 3,
    ("1V8_MIC", "B.Cu"): 3,
    ("1V8_MIC", "via"): 2,
    ("GND", "F.Cu"): 4,
    ("GND", "B.Cu"): 5,
    ("GND", "via"): 3,
    ("PDM_CLK", "F.Cu"): 4,
    ("PDM_DATA", "F.Cu"): 1,
    ("MIC_WAKE", "F.Cu"): 2,
    ("AAD_CFG", "F.Cu"): 3,
    ("PDM_DATA_MIC", "F.Cu"): 2,
}

COPPER_RETURN_GATE = "independent human copper-return and decoupling review"
REMAINING_EXTERNAL_GATES = [
    COPPER_RETURN_GATE,
    "panelization, tooling rails and MEMS-safe depanel method",
    "fabricator and assembler DFM acceptance",
    "adhesive and conformal-coating keepout acceptance",
    "membrane and cavity tolerance-stack freeze",
    "assembled acoustic inspection and physical EVT calibration",
    "independent Review-B signature and manufacturing release",
]
REPEAT_REVIEW_A_GATE = "repeat PCB-MIC Review A against the copper ECO candidate commit"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def close(actual: float, expected: float, tolerance: float, label: str) -> None:
    require(
        abs(actual - expected) <= tolerance,
        f"{label}: {actual:.6f} != {expected:.6f} +/- {tolerance:.6f}",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None, f"CSV header missing: {path}")
        return list(reader)


def git_bytes(commit: str, path: Path) -> bytes:
    relative = path.relative_to(ROOT)
    return subprocess.check_output(
        ["git", "show", f"{commit}:{relative}"], cwd=ROOT
    )


def audit_commit_binding(commit_sha: str, status: dict[str, Any]) -> dict[str, Any]:
    require(re.fullmatch(r"[0-9a-f]{40}", commit_sha) is not None,
            f"invalid evidence commit SHA: {commit_sha!r}")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    require(head == commit_sha, f"evidence commit {commit_sha} != checked-out HEAD {head}")

    controlled = [
        BOARD, SCHEMATIC, PROJECT, FABRICATION_METADATA, STATUS,
        PRODUCTION_BOM, NATIVE_GATE, COPPER_RETURN_AUDIT,
        COPPER_RETURN_PACKET, GENERATOR, NATIVE_WORKFLOW, Path(__file__).resolve(),
    ]
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", *[str(p.relative_to(ROOT)) for p in controlled]],
        cwd=ROOT,
        text=True,
    ).strip()
    require(not dirty, f"commit-bound source set is dirty: {dirty}")

    current_source_hashes: dict[str, str] = {}
    for path in (BOARD, SCHEMATIC, PROJECT, FABRICATION_METADATA):
        current = path.read_bytes()
        committed = git_bytes(commit_sha, path)
        require(current == committed,
                f"{path.relative_to(ROOT)} differs from evidence commit {commit_sha}")
        current_source_hashes[str(path.relative_to(ROOT))] = hashlib.sha256(current).hexdigest()

    review_a = status["review_a"]
    if status["release_state"] == "REVIEW_A_PASS":
        signed_commit = str(review_a.get("commit_sha", ""))
        require(re.fullmatch(r"[0-9a-f]{40}", signed_commit) is not None,
                f"invalid signed Review-A commit SHA: {signed_commit!r}")
        for path in (BOARD, SCHEMATIC, PROJECT, FABRICATION_METADATA):
            require(path.read_bytes() == git_bytes(signed_commit, path),
                    f"{path.relative_to(ROOT)} drifted from signed Review-A commit {signed_commit}")
        review_a_state = "SIGNED_PASS"
        prior_signature = None
    else:
        require(status["release_state"] == "REVIEW_A_REQUIRED_AFTER_COPPER_ECO",
                "unexpected PCB-MIC release state")
        signed_commit = None
        prior_signature = review_a.get("superseded_signature", {})
        prior_commit = str(prior_signature.get("commit_sha", ""))
        require(re.fullmatch(r"[0-9a-f]{40}", prior_commit) is not None,
                "invalid superseded Review-A commit SHA")
        require(BOARD.read_bytes() != git_bytes(prior_commit, BOARD),
                "post-ECO board still matches the superseded Review-A board")
        for path in (SCHEMATIC, PROJECT, FABRICATION_METADATA):
            require(path.read_bytes() == git_bytes(prior_commit, path),
                    f"post-ECO change escaped board-only scope: {path.relative_to(ROOT)}")
        review_a_state = "ECO_CANDIDATE_REPEAT_REVIEW_A_REQUIRED"

    return {
        "status": "PASS",
        "evidence_commit_sha": commit_sha,
        "signed_review_a_commit_sha": signed_commit,
        "review_a_state": review_a_state,
        "current_source_continuity": current_source_hashes,
        "superseded_review_a_signature": prior_signature,
        "controlled_source_dirty_lines": 0,
    }


def audit_release_state() -> tuple[dict[str, Any], dict[str, Any]]:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    require(status.get("assembly") == "PCB-MIC", "capture status assembly mismatch")
    require(status.get("manufacturing_release") is False,
            "manufacturing release must remain false during Review-B preflight")
    review_a = status.get("review_a", {})
    review_b = status.get("review_b", {})
    require(review_b.get("complete") is False, "Review B must remain open")
    require(review_b.get("reviewer") is None and review_b.get("date") is None,
            "unsigned Review B unexpectedly has reviewer/date")
    if status.get("release_state") == "REVIEW_A_PASS":
        require(review_a.get("complete") is True and review_a.get("status") == "PASS",
                "signed Review A is not complete/pass")
        require(review_a.get("reviewer") and review_a.get("date") and review_a.get("commit_sha"),
                "signed Review-A traceability is incomplete")
        gate = review_b.get("copper_return_gate", {})
        gate_accepted = gate.get("complete") is True
        if gate_accepted:
            current_decision = gate.get("current_review_b_decision", {})
            require(
                review_b.get("status") ==
                "OPEN_REMAINING_REVIEW_B_GATES_AFTER_COPPER_RETURN_ACCEPTANCE",
                "Review B status does not preserve the accepted copper-return subgate",
            )
            require(
                gate.get("status") ==
                "PASS_ACCEPT_COPPER_RETURN_REVIEW_B_REMAINS_OPEN"
                and gate.get("decision") == "ACCEPT_COPPER_RETURN"
                and current_decision.get("status") ==
                "ACCEPTED_INDEPENDENT_HUMAN_REVIEW"
                and current_decision.get("approval_scope") ==
                "PCB_MIC_REVIEW_B_COPPER_RETURN_SUBGATE_ONLY"
                and current_decision.get("decision") == "ACCEPT_COPPER_RETURN",
                "copper-return acceptance record is incomplete",
            )
            require(
                gate.get("reviewer") == current_decision.get("reviewer")
                and gate.get("date") == current_decision.get("date")
                and gate.get("commit_sha") == current_decision.get("reviewed_commit_sha")
                and gate.get("decision_evidence_commit_sha") ==
                current_decision.get("reviewed_commit_sha"),
                "copper-return acceptance signature fields mismatch",
            )
            require(current_decision.get("native_board_sha256") == sha256(BOARD),
                    "copper-return acceptance board hash mismatch")
            initial_decision = gate.get("initial_eco_decision", {})
            require(
                initial_decision.get("decision") == "ECO_REQUIRED"
                and initial_decision.get("reviewer")
                and initial_decision.get("date")
                and initial_decision.get("decision_evidence_commit_sha"),
                "initial ECO_REQUIRED decision history is incomplete",
            )
            acceptance_evidence = gate.get("acceptance_state_evidence", {})
            require(
                re.fullmatch(
                    r"[0-9a-f]{40}",
                    str(acceptance_evidence.get("evidence_commit_sha", "")),
                ) is not None
                and acceptance_evidence.get("native_board_sha256") == sha256(BOARD)
                and acceptance_evidence.get("sha256_manifest_entries_verified") == 62
                and acceptance_evidence.get("source_hashes_verified") == 12
                and acceptance_evidence.get("pcb_mic_output_hashes_verified") == 27,
                "post-acceptance commit-bound evidence is incomplete",
            )
            require(
                acceptance_evidence.get("review_b_preflight_status") ==
                "PASS_INTERNAL_CAM_PREFLIGHT_REVIEW_B_REMAINS_OPEN"
                and acceptance_evidence.get("copper_return_disposition") ==
                "PASS_HUMAN_ACCEPTED_COPPER_RETURN_SUBGATE_REVIEW_B_REMAINS_OPEN"
                and acceptance_evidence.get("copper_return_gate_complete") is True
                and acceptance_evidence.get("review_b_complete") is False
                and acceptance_evidence.get("manufacturing_release") is False,
                "post-acceptance evidence does not preserve the bounded release state",
            )
            release_status = (
                "PASS_REVIEW_A_SIGNED_COPPER_RETURN_ACCEPTED_REVIEW_B_OPEN"
            )
        else:
            require(review_b.get("status") ==
                    "OPEN_COPPER_RETURN_AND_REMAINING_REVIEW_B_GATES",
                    "open copper-return Review B status mismatch")
            release_status = "PASS_REVIEW_A_SIGNED_REVIEW_B_OPEN"
        review_record = {
            "reviewer": review_a["reviewer"],
            "date": review_a["date"],
            "commit_sha": review_a["commit_sha"],
        }
    else:
        require(status.get("release_state") == "REVIEW_A_REQUIRED_AFTER_COPPER_ECO",
                "PCB-MIC is neither signed nor an explicit post-ECO candidate")
        require(review_a.get("complete") is False
                and review_a.get("status") == "REVIEW_REQUIRED_AFTER_COPPER_ECO",
                "post-ECO Review A must be open")
        require(all(review_a.get(field) is None for field in ("reviewer", "date", "commit_sha")),
                "post-ECO Review A unexpectedly retains an active signature")
        require(review_b.get("status") == "BLOCKED_PENDING_REPEAT_REVIEW_A_AFTER_COPPER_ECO",
                "Review B is not blocked on repeat Review A")
        gate = review_b.get("copper_return_gate", {})
        require(gate.get("decision") == "ECO_REQUIRED"
                and gate.get("reviewer") and gate.get("date"),
                "ECO_REQUIRED decision traceability is incomplete")
        release_status = "PASS_ECO_CANDIDATE_REVIEW_A_REQUIRED_REVIEW_B_BLOCKED"
        review_record = {
            "reviewer": None,
            "date": None,
            "commit_sha": None,
            "superseded_signature": review_a.get("superseded_signature"),
        }
    return status, {
        "status": release_status,
        "review_a": review_record,
        "review_b_status": review_b.get("status"),
        "copper_return_gate_complete": (
            review_b.get("copper_return_gate", {}).get("complete") is True
        ),
        "manufacturing_release": False,
    }


def audit_cli_reports(artifact_root: Path) -> dict[str, Any]:
    drc = json.loads((artifact_root / "drc.json").read_text(encoding="utf-8"))
    require(str(drc.get("kicad_version", "")).startswith("9.0."),
            f"DRC was not generated by KiCad 9.0.x: {drc.get('kicad_version')!r}")
    require(drc.get("source") == BOARD.name, "DRC source mismatch")
    require(drc.get("violations") == [], "DRC violations are present")
    require(drc.get("unconnected_items") == [], "DRC unrouted items are present")
    require(drc.get("schematic_parity") == [], "DRC schematic parity items are present")

    erc = json.loads((artifact_root / "erc.json").read_text(encoding="utf-8"))
    require(str(erc.get("kicad_version", "")).startswith("9.0."),
            f"ERC was not generated by KiCad 9.0.x: {erc.get('kicad_version')!r}")
    require(erc.get("source") == SCHEMATIC.name, "ERC source mismatch")
    sheets = erc.get("sheets")
    require(isinstance(sheets, list) and sheets, "ERC sheet results missing")
    violations = [item for sheet in sheets for item in sheet.get("violations", [])]
    require(not violations, f"ERC violations are present: {len(violations)}")
    return {
        "status": "PASS",
        "kicad_drc_version": drc["kicad_version"],
        "kicad_erc_version": erc["kicad_version"],
        "drc_violations": 0,
        "unrouted_items": 0,
        "schematic_parity_items": 0,
        "erc_violations": 0,
    }


def audit_cam_transform(artifact_root: Path, commit_sha: str) -> dict[str, Any]:
    transform_path = artifact_root / "cam_source_transform.json"
    transform = json.loads(transform_path.read_text(encoding="utf-8"))
    require(transform.get("schema") == "dioneya-controlled-cam-source-transform-v1",
            "unexpected CAM transform schema")
    require(transform.get("board") == "PCB-MIC", "CAM transform board mismatch")
    require(transform.get("source_commit_sha") == commit_sha, "CAM transform commit mismatch")
    require(transform.get("source_path") == str(BOARD.relative_to(ROOT)),
            "CAM transform source path mismatch")
    require(transform.get("source_sha256") == sha256(BOARD), "CAM source hash mismatch")
    require(transform.get("derived_path") == "PCB-MIC/cam-source/PCB-MIC.kicad_pcb",
            "CAM derived path mismatch")
    require(transform.get("design_geometry_modified") is False,
            "CAM transform claims a design-geometry change")
    require(transform.get("review_b_complete") is False,
            "CAM transform must not complete Review B")
    require(transform.get("manufacturing_release") is False,
            "CAM transform must not grant manufacturing release")

    changes = transform.get("transformations")
    require(isinstance(changes, list) and len(changes) == 1,
            "CAM transform must contain exactly one controlled change")
    change = changes[0]
    require(
        change.get("field") == "pcbplotparams.drillshape"
        and change.get("before") == 1
        and change.get("after") == 0
        and change.get("count") == 1,
        f"unexpected CAM transform: {change}",
    )

    derived = artifact_root / "cam-source/PCB-MIC.kicad_pcb"
    require(derived.is_file(), f"archived CAM input missing: {derived}")
    require(transform.get("derived_sha256") == sha256(derived), "CAM derived hash mismatch")

    source_text = BOARD.read_text(encoding="utf-8")
    require(re.findall(r"\(drillshape\s+(\d+)\)", source_text) == ["1"],
            "native source does not contain only drillshape 1")
    pattern = re.compile(
        r"(?m)^(?P<prefix>[ \t]*\(drillshape[ \t]+)1(?P<suffix>\)[ \t]*)$"
    )
    expected_text, replacements = pattern.subn(r"\g<prefix>0\g<suffix>", source_text)
    require(replacements == 1, f"native source drillshape transform count: {replacements}")
    require(derived.read_text(encoding="utf-8") == expected_text,
            "archived CAM input differs by more than the controlled drillshape field")
    require(len(re.findall(r"\(drillshape\s+0\)", expected_text)) == 1,
            "archived CAM input does not contain exactly one drillshape 0 field")
    return {
        "status": "PASS_EXACT_ONE_FIELD_TRANSFORM",
        "source_sha256": sha256(BOARD),
        "derived_sha256": sha256(derived),
        "field": "pcbplotparams.drillshape",
        "before": 1,
        "after": 0,
        "design_geometry_modified": False,
    }


def parse_gerber(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    format_match = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", text)
    require(format_match is not None, f"Gerber coordinate format missing: {path.name}")
    x_decimals = int(format_match.group(2))
    y_decimals = int(format_match.group(4))
    apertures = {
        int(code): specification
        for code, specification in re.findall(r"%ADD(\d+)([^*]+)\*%", text)
    }
    file_function_match = re.search(r"%TF\.FileFunction,([^*]+)\*%", text)
    polarity_match = re.search(r"%TF\.FilePolarity,([^*]+)\*%", text)

    selected_aperture: int | None = None
    current_x: float | None = None
    current_y: float | None = None
    flashes: list[dict[str, Any]] = []
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    coordinate = re.compile(r"^(?:X(-?\d+))?(?:Y(-?\d+))?D0([123])\*$")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        aperture_select = re.fullmatch(r"D(\d+)\*", line)
        if aperture_select and int(aperture_select.group(1)) >= 10:
            selected_aperture = int(aperture_select.group(1))
            continue
        match = coordinate.fullmatch(line)
        if not match:
            continue
        previous = (current_x, current_y)
        if match.group(1) is not None:
            current_x = int(match.group(1)) / (10 ** x_decimals)
        if match.group(2) is not None:
            current_y = int(match.group(2)) / (10 ** y_decimals)
        require(current_x is not None and current_y is not None,
                f"Gerber coordinate lacks an initial X/Y: {path.name}: {line}")
        operation = match.group(3)
        if operation == "3":
            require(selected_aperture is not None,
                    f"Gerber flash has no selected aperture: {path.name}: {line}")
            flashes.append({
                "x": current_x,
                "y": current_y,
                "aperture": selected_aperture,
                "specification": apertures.get(selected_aperture, ""),
            })
        elif operation == "1":
            require(previous[0] is not None and previous[1] is not None,
                    f"Gerber draw has no start coordinate: {path.name}: {line}")
            segments.append(((float(previous[0]), float(previous[1])), (current_x, current_y)))

    return {
        "text": text,
        "file_function": file_function_match.group(1) if file_function_match else None,
        "polarity": polarity_match.group(1) if polarity_match else None,
        "apertures": apertures,
        "flashes": flashes,
        "segments": segments,
    }


def circular_diameter(specification: str) -> float | None:
    match = re.fullmatch(r"C,([0-9.]+)", specification)
    return float(match.group(1)) if match else None


def flashes_at(parsed: dict[str, Any], x: float, y: float, tolerance: float = 0.002) -> list[dict[str, Any]]:
    return [
        flash for flash in parsed["flashes"]
        if abs(float(flash["x"]) - x) <= tolerance
        and abs(float(flash["y"]) - y) <= tolerance
    ]


def normalized_segment(
    segment: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    points = tuple(sorted((tuple(round(value, 6) for value in segment[0]),
                           tuple(round(value, 6) for value in segment[1]))))
    return points[0], points[1]


def audit_gerbers(artifact_root: Path) -> dict[str, Any]:
    gerber_root = artifact_root / "gerber"
    controlled_copy = artifact_root / "PCB-MIC_fabrication_metadata.json"
    require(controlled_copy.read_bytes() == FABRICATION_METADATA.read_bytes(),
            "archived fabrication metadata differs from controlled source")
    job_path = gerber_root / "PCB-MIC-job.gbrjob"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    version = str(job.get("Header", {}).get("GenerationSoftware", {}).get("Version", ""))
    require(version.startswith("9.0."), f"Gerbers were not generated by KiCad 9.0.x: {version!r}")
    specs = job.get("GeneralSpecs", {})
    require(specs.get("ProjectId", {}).get("Name") == "PCB-MIC", "Gerber job project mismatch")
    require(specs.get("ProjectId", {}).get("Revision") == "A", "Gerber job revision mismatch")
    require(int(specs.get("LayerNumber", -1)) == 2, "Gerber job copper-layer count mismatch")
    close(float(specs.get("BoardThickness", -1.0)), 1.0, 0.001, "Gerber job thickness")
    require(specs.get("Finish") == "ENIG", "Gerber job finish mismatch")
    materials = [
        str(layer.get("Material", "")).replace("-", "").upper()
        for layer in job.get("MaterialStackup", [])
        if layer.get("Type") == "Dielectric"
    ]
    require("FR4" in materials, f"Gerber stackup does not contain FR-4: {materials}")

    job_files = {
        entry["Path"]: (entry.get("FileFunction"), entry.get("FilePolarity"))
        for entry in job.get("FilesAttributes", [])
    }
    require(job_files == EXPECTED_GERBERS,
            f"Gerber job file/layer/polarity set mismatch: {job_files}")

    parsed: dict[str, dict[str, Any]] = {}
    for filename, (expected_function, expected_polarity) in EXPECTED_GERBERS.items():
        path = gerber_root / filename
        require(path.is_file() and path.stat().st_size > 100, f"Gerber missing/empty: {filename}")
        layer = parse_gerber(path)
        parsed[filename] = layer
        header_function = layer["file_function"]
        normalized_expected = expected_function.replace("SolderPaste", "Paste").replace("SolderMask", "Soldermask")
        if expected_function == "Profile":
            require(str(header_function).startswith("Profile"),
                    f"{filename}: X2 file function mismatch: {header_function!r}")
        else:
            require(header_function == normalized_expected,
                    f"{filename}: X2 file function mismatch: {header_function!r}")
        if layer["polarity"] is not None:
            require(layer["polarity"] == expected_polarity,
                    f"{filename}: X2 polarity mismatch: {layer['polarity']!r}")

    guide_flash_hits: list[dict[str, Any]] = []
    for filename, layer in parsed.items():
        for label, (x, y, _) in HOLES.items():
            for flash in flashes_at(layer, x, y):
                diameter = circular_diameter(str(flash["specification"]))
                if diameter is not None and abs(diameter - 0.35) <= 0.001:
                    guide_flash_hits.append({"file": filename, "hole": label, "diameter_mm": diameter})
    require(not guide_flash_hits,
            f"non-design 0.35 mm drill guide flashes remain in Gerbers: {guide_flash_hits}")

    for side in ("F", "B"):
        paste = parsed[f"PCB-MIC-{side}_Paste.gbr"]
        for label, (x, y, _) in HOLES.items():
            require(not flashes_at(paste, x, y),
                    f"{side}.Paste contains a flash at {label} hole ({x},{y})")
        mask = parsed[f"PCB-MIC-{side}_Mask.gbr"]
        for label, (x, y, diameter) in HOLES.items():
            opening_flashes = flashes_at(mask, x, y)
            opening_diameters = [
                circular_diameter(str(flash["specification"]))
                for flash in opening_flashes
            ]
            require(opening_diameters == [diameter],
                    f"{side}.Mask {label} opening mismatch: {opening_diameters} != {[diameter]}")

    edge = parsed["PCB-MIC-Edge_Cuts.gbr"]
    expected_outline = {
        normalized_segment(((0.0, 0.0), (24.0, 0.0))),
        normalized_segment(((24.0, 0.0), (24.0, -22.0))),
        normalized_segment(((24.0, -22.0), (0.0, -22.0))),
        normalized_segment(((0.0, -22.0), (0.0, 0.0))),
    }
    outline = {normalized_segment(segment) for segment in edge["segments"]}
    require(outline == expected_outline, f"Gerber outline mismatch: {sorted(outline)}")
    require(not edge["flashes"], "profile Gerber contains non-outline flashes")

    return {
        "status": "PASS",
        "generator_version": version,
        "gerber_files": len(parsed),
        "copper_layers": 2,
        "board_thickness_mm": 1.0,
        "surface_finish": "ENIG",
        "material": "FR-4",
        "outline_mm": [24.0, 22.0],
        "drill_guide_flashes": 0,
        "paste_flashes_at_acoustic_or_mount_holes": 0,
        "mask_openings_verified": 6,
    }


def audit_drill(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "drill/PCB-MIC.drl"
    text = path.read_text(encoding="utf-8")
    require("KiCad 9.0." in text, "Excellon was not generated by KiCad 9.0.x")
    definitions = {tool: float(diameter) for tool, diameter in re.findall(r"^T(\d+)C([0-9.]+)$", text, re.M)}
    body_parts = re.split(r"^%$", text, maxsplit=1, flags=re.M)
    require(len(body_parts) == 2, "Excellon header/body delimiter missing")
    active: str | None = None
    hits: dict[str, list[tuple[float, float]]] = {tool: [] for tool in definitions}
    for line in body_parts[1].splitlines():
        tool_match = re.fullmatch(r"T(\d+)", line.strip())
        if tool_match:
            active = tool_match.group(1)
            continue
        point = re.fullmatch(r"X(-?[0-9.]+)Y(-?[0-9.]+)", line.strip())
        if point:
            require(active in definitions, f"Excellon hit without known tool: {line}")
            hits[active].append((float(point.group(1)), float(point.group(2))))

    summary = {round(definitions[tool], 3): len(points) for tool, points in hits.items()}
    require(summary == {0.3: 5, 0.8: 1, 2.2: 2}, f"Excellon tool/hit mismatch: {summary}")
    expected_holes = {
        0.8: {(12.0, -16.65)},
        2.2: {(4.0, -16.65), (20.0, -16.65)},
    }
    for diameter, expected in expected_holes.items():
        matching_tools = [tool for tool, value in definitions.items() if abs(value - diameter) <= 0.001]
        require(len(matching_tools) == 1, f"Excellon {diameter} mm tool count mismatch")
        actual = {(round(x, 3), round(y, 3)) for x, y in hits[matching_tools[0]]}
        require(actual == expected, f"Excellon {diameter} mm hole positions mismatch: {actual}")
    return {
        "status": "PASS",
        "tool_hit_counts": {f"{diameter:.3f}": count for diameter, count in sorted(summary.items())},
        "acoustic_port_mm": [12.0, -16.65, 0.8],
        "mounting_holes_mm": [[4.0, -16.65, 2.2], [20.0, -16.65, 2.2]],
    }


def audit_pnp(artifact_root: Path) -> dict[str, Any]:
    rows = csv_rows(artifact_root / "PCB-MIC_pos.csv")
    by_ref = {row.get("Ref", ""): row for row in rows}
    require(len(by_ref) == len(rows), "PnP contains duplicate references")
    require(set(by_ref) == set(EXPECTED_COMPONENTS),
            f"PnP reference mismatch: {sorted(by_ref)}")
    placements: dict[str, dict[str, Any]] = {}
    for ref, expected in EXPECTED_COMPONENTS.items():
        row = by_ref[ref]
        x, y, rotation, package, value = expected["pnp"]
        close(float(row["PosX"]), x, 0.001, f"PnP {ref} X")
        close(float(row["PosY"]), y, 0.001, f"PnP {ref} Y")
        close(float(row["Rot"]), rotation, 0.001, f"PnP {ref} rotation")
        require(row["Side"] == "top", f"PnP {ref} side mismatch: {row['Side']!r}")
        require(row["Package"] == package, f"PnP {ref} package mismatch: {row['Package']!r}")
        require(row["Val"] == value, f"PnP {ref} value mismatch: {row['Val']!r}")
        placements[ref] = {
            "x_mm": x, "y_mm": y, "rotation_deg": rotation,
            "side": "top", "package": package, "value": value,
        }
    return {"status": "PASS", "placements": placements, "mechanical_refs_excluded": ["H1", "H2"]}


def audit_boms(artifact_root: Path) -> dict[str, Any]:
    kicad_rows = csv_rows(artifact_root / "PCB-MIC_kicad_bom.csv")
    by_ref = {row.get("Reference", ""): row for row in kicad_rows}
    require(len(by_ref) == len(kicad_rows), "KiCad BOM contains duplicate references")
    require(set(by_ref) == set(EXPECTED_COMPONENTS),
            f"KiCad BOM reference mismatch: {sorted(by_ref)}")
    for ref, expected in EXPECTED_COMPONENTS.items():
        row = by_ref[ref]
        require(row.get("Value") == expected["value"],
                f"KiCad BOM {ref} value mismatch: {row.get('Value')!r}")
        require(row.get("Footprint") == expected["footprint"],
                f"KiCad BOM {ref} footprint mismatch: {row.get('Footprint')!r}")
        require(row.get("Quantity") in ("1", "1.0"),
                f"KiCad BOM {ref} quantity mismatch: {row.get('Quantity')!r}")

    production_rows = {row["Item_ID"]: row for row in csv_rows(PRODUCTION_BOM)}
    manufacturing_rows = csv_rows(artifact_root / "PCB-MIC_manufacturing_bom.csv")
    manufacturing = {row.get("Reference", ""): row for row in manufacturing_rows}
    require(len(manufacturing) == len(manufacturing_rows),
            "manufacturing BOM contains duplicate references")
    require(set(manufacturing) == set(EXPECTED_COMPONENTS),
            f"manufacturing BOM reference mismatch: {sorted(manufacturing)}")
    traceability: dict[str, dict[str, str]] = {}
    for ref, expected in EXPECTED_COMPONENTS.items():
        row = manufacturing[ref]
        authority = production_rows.get(str(expected["item_id"]))
        require(authority is not None, f"production BOM item missing: {expected['item_id']}")
        required = {
            "Quantity_per_board": "1",
            "Native_Value": str(expected["value"]),
            "Native_Footprint": str(expected["footprint"]),
            "Manufacturer": str(expected["manufacturer"]),
            "MPN": str(expected["mpn"]),
            "Qty_per_station": "4",
            "Population": "FITTED",
            "Source_Item_ID": str(expected["item_id"]),
            "Source_BOM": str(PRODUCTION_BOM.relative_to(ROOT)),
        }
        for field, value in required.items():
            require(row.get(field) == value,
                    f"manufacturing BOM {ref} {field}: {row.get(field)!r} != {value!r}")
        require(authority["Manufacturer"] == row["Manufacturer"], f"{ref} manufacturer authority drift")
        require(authority["MPN"] == row["MPN"], f"{ref} MPN authority drift")
        require(authority["Package"] == row["Package"], f"{ref} package authority drift")
        require(authority["Value"] == row["Procurement_Value"], f"{ref} value authority drift")
        traceability[ref] = {
            "item_id": row["Source_Item_ID"],
            "manufacturer": row["Manufacturer"],
            "mpn": row["MPN"],
        }
    return {
        "status": "PASS",
        "kicad_native_refs": sorted(by_ref),
        "manufacturing_bom_refs": sorted(manufacturing),
        "procurement_traceability": traceability,
    }


def audit_ipc356(artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / "PCB-MIC.d356"
    text = path.read_text(encoding="utf-8")
    require(text.rstrip().endswith("999"), "IPC-D-356 terminator missing")
    required_nets = {"1V8_MIC", "GND", "PDM_CLK", "PDM_DATA", "MIC_WAKE", "AAD_CFG", "PDM_DATA_MIC"}
    required_refs = {"C1", "J1", "MK1", "R1"}
    missing_nets = sorted(net for net in required_nets if net not in text)
    missing_refs = sorted(ref for ref in required_refs if re.search(rf"\b{re.escape(ref)}\b", text) is None)
    require(not missing_nets, f"IPC-D-356 nets missing: {missing_nets}")
    require(not missing_refs, f"IPC-D-356 references missing: {missing_refs}")
    return {
        "status": "PASS",
        "required_nets": sorted(required_nets),
        "required_references": sorted(required_refs),
        "records": sum(1 for line in text.splitlines() if line.startswith(("317", "327", "367"))),
    }


def segment_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    parameter = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    closest = (x1 + parameter * dx, y1 + parameter * dy)
    return math.hypot(px - closest[0], py - closest[1])


def pad_net_name(pad: Any) -> str | None:
    net = getattr(pad, "net", None)
    return str(net.name) if net is not None else None


def audit_native_topology(status: dict[str, Any]) -> dict[str, Any]:
    board = Board().from_file(BOARD)
    require(board is not None, "kiutils could not parse PCB-MIC")
    net_names = {int(net.number): str(net.name) for net in board.nets}
    signature: Counter[tuple[str, str]] = Counter()
    for item in board.traceItems:
        net_name = net_names.get(int(item.net), f"UNKNOWN_{item.net}")
        item_type = type(item).__name__
        key = "via" if item_type == "Via" else str(item.layer)
        signature[(net_name, key)] += 1
    require(dict(signature) == EXPECTED_TRACE_SIGNATURE,
            f"native trace/via signature mismatch: {dict(signature)}")

    footprints = {str(fp.properties.get("Reference", "")): fp for fp in board.footprints}
    require(set(footprints) == {"C1", "J1", "MK1", "R1", "H1", "H2"},
            f"native footprint set mismatch: {sorted(footprints)}")
    expected_positions = {
        "C1": (14.1, 13.25, 0.0),
        "J1": (12.0, 5.0, 180.0),
        "MK1": (12.0, 16.0, 0.0),
        "R1": (11.25, 10.55, -90.0),
        "H1": (4.0, 16.65, 0.0),
        "H2": (20.0, 16.65, 0.0),
    }
    for ref, (x, y, angle) in expected_positions.items():
        position = footprints[ref].position
        close(float(position.X), x, 0.001, f"native {ref} X")
        close(float(position.Y), y, 0.001, f"native {ref} Y")
        close(float(position.angle or 0.0), angle, 0.001, f"native {ref} angle")

    c1_pads = {str(pad.number): pad_net_name(pad) for pad in footprints["C1"].pads}
    require(c1_pads == {"1": "1V8_MIC", "2": "GND"},
            f"C1 decoupling net assignment mismatch: {c1_pads}")
    mic_pads = {
        str(pad.number): pad_net_name(pad)
        for pad in footprints["MK1"].pads
        if str(pad.number) in {"1", "2", "3", "4", "5", "6", "7"}
    }
    require(mic_pads.get("7") == "1V8_MIC" and mic_pads.get("2") == "GND" and mic_pads.get("3") == "GND",
            f"MK1 power/return pad assignment mismatch: {mic_pads}")

    require(not board.zones,
            f"explicit-routing-only ECO must contain zero zones, got {len(board.zones)}")

    gnd_bcu = [
        item for item in board.traceItems
        if type(item).__name__ == "Segment" and net_names.get(int(item.net)) == "GND" and item.layer == "B.Cu"
    ]
    clearances = [
        segment_distance(
            (12.0, 16.65),
            (float(segment.start.X), float(segment.start.Y)),
            (float(segment.end.X), float(segment.end.Y)),
        ) - float(segment.width) / 2.0 - 0.4
        for segment in gnd_bcu
    ]
    require(clearances and min(clearances) >= 0.8,
            f"B.Cu GND acoustic-port copper clearance is too small: {min(clearances):.3f} mm")

    decoupling_distance = math.hypot(
        float(footprints["C1"].position.X) - float(footprints["MK1"].position.X),
        float(footprints["C1"].position.Y) - float(footprints["MK1"].position.Y),
    )
    require(decoupling_distance < 3.6,
            f"C1-to-MK1 center distance too large: {decoupling_distance:.3f} mm")
    copper_gate = status.get("review_b", {}).get("copper_return_gate", {})
    copper_return_accepted = (
        status.get("release_state") == "REVIEW_A_PASS"
        and copper_gate.get("complete") is True
        and copper_gate.get("decision") == "ACCEPT_COPPER_RETURN"
    )
    return {
        "status": "PASS_MACHINE_TOPOLOGY_PREFLIGHT",
        "segments": sum(signature.values()) - signature.get(("1V8_MIC", "via"), 0) - signature.get(("GND", "via"), 0),
        "vias": signature.get(("1V8_MIC", "via"), 0) + signature.get(("GND", "via"), 0),
        "trace_signature": {
            f"{net}:{layer}": count for (net, layer), count in sorted(signature.items())
        },
        "bcu_gnd_zone": None,
        "copper_model": "EXPLICIT_ROUTING_ONLY",
        "minimum_bcu_gnd_edge_to_acoustic_hole_clearance_mm": round(min(clearances), 6),
        "c1_to_mk1_center_distance_mm": round(decoupling_distance, 6),
        "human_review_still_required": not copper_return_accepted,
        "copper_return_gate_complete": copper_return_accepted,
        "copper_return_decision": copper_gate.get("decision"),
    }


def audit_documents(artifact_root: Path) -> dict[str, Any]:
    pdfs = {
        "schematic": (artifact_root / "PCB-MIC_schematic.pdf", None),
        "assembly_fabrication": (
            artifact_root / "PCB-MIC_assembly_fabrication.pdf", 4
        ),
        "drill_map": (artifact_root / "drill/PCB-MIC-drl_map.pdf", None),
    }
    sizes: dict[str, int] = {}
    pages: dict[str, int] = {}
    for label, (path, expected_pages) in pdfs.items():
        data = path.read_bytes()
        require(data.startswith(b"%PDF-"), f"{label} PDF header missing")
        require(len(data) > 1000, f"{label} PDF unexpectedly small: {len(data)} bytes")
        sizes[label] = len(data)
        page_count = len(re.findall(rb"/Type\s*/Page\b", data))
        if expected_pages is not None:
            require(page_count == expected_pages,
                    f"{label} PDF page count {page_count} != {expected_pages}")
        pages[label] = page_count

    step = artifact_root / "PCB-MIC_board.step"
    step_data = step.read_bytes()
    require(step_data.startswith(b"ISO-10303-21;"), "board STEP header missing")
    require(b"END-ISO-10303-21;" in step_data, "board STEP terminator missing")
    require(len(step_data) > 1000, f"board STEP unexpectedly small: {len(step_data)} bytes")
    return {
        "status": "PASS",
        "pdf_bytes": sizes,
        "pdf_pages": pages,
        "board_step_bytes": len(step_data),
    }


def svg_mm_dimension(value: str, label: str) -> float:
    match = re.fullmatch(
        r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)mm\s*", value
    )
    require(match is not None, f"{label} must use explicit millimetres: {value!r}")
    return float(match.group(1))


def find_svg_board_outline(root: ET.Element) -> tuple[float, float, float, float]:
    """Independently locate the four 24x22 mm Edge.Cuts paths in a layer SVG."""
    number_pattern = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    segments: list[tuple[float, float, float, float]] = []
    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        path_data = element.attrib.get("d", "")
        if re.findall(r"[A-Za-z]", path_data) != ["M", "L"]:
            continue
        values = [float(value) for value in re.findall(number_pattern, path_data)]
        if len(values) == 4:
            segments.append(tuple(values))

    tolerance = 0.01
    horizontal = [
        (min(x1, x2), max(x1, x2), (y1 + y2) / 2.0)
        for x1, y1, x2, y2 in segments
        if abs(y1 - y2) <= tolerance and abs(abs(x2 - x1) - 24.0) <= tolerance
    ]
    vertical = [
        ((x1 + x2) / 2.0, min(y1, y2), max(y1, y2))
        for x1, y1, x2, y2 in segments
        if abs(x1 - x2) <= tolerance and abs(abs(y2 - y1) - 22.0) <= tolerance
    ]
    for left, right, y1 in horizontal:
        for other_left, other_right, y2 in horizontal:
            if (
                abs(left - other_left) > tolerance
                or abs(right - other_right) > tolerance
                or abs(abs(y2 - y1) - 22.0) > tolerance
            ):
                continue
            top, bottom = sorted((y1, y2))
            sides = {
                "left": any(
                    abs(x - left) <= tolerance
                    and abs(start - top) <= tolerance
                    and abs(end - bottom) <= tolerance
                    for x, start, end in vertical
                ),
                "right": any(
                    abs(x - right) <= tolerance
                    and abs(start - top) <= tolerance
                    and abs(end - bottom) <= tolerance
                    for x, start, end in vertical
                ),
            }
            if all(sides.values()):
                return left, top, right, bottom
    raise RuntimeError(
        f"24x22 mm four-edge board outline missing from copper-review SVG; "
        f"simple_segments={len(segments)}"
    )


def audit_copper_review_svgs(artifact_root: Path) -> dict[str, Any]:
    files = {
        "F.Cu": artifact_root / "PCB-MIC_F_Cu_review.svg",
        "B.Cu": artifact_root / "PCB-MIC_B_Cu_review.svg",
    }
    results: dict[str, Any] = {}
    contents: dict[str, bytes] = {}
    for layer, path in files.items():
        data = path.read_bytes()
        require(len(data) > 1000, f"{layer} copper-review SVG unexpectedly small")
        require(b"<svg" in data[:1000], f"{layer} copper-review SVG root missing")
        root = ET.fromstring(data)
        require(root.tag.endswith("svg"), f"{layer} copper-review document is not SVG")
        view_box = root.attrib.get("viewBox", "").replace(",", " ").split()
        require(len(view_box) == 4, f"{layer} copper-review SVG viewBox missing")
        dimensions = [float(value) for value in view_box]
        view_x, view_y, width, height = dimensions
        require(width > 0 and height > 0, f"{layer} copper-review SVG has invalid size")
        page_width = svg_mm_dimension(root.attrib.get("width", ""), f"{layer} SVG width")
        page_height = svg_mm_dimension(root.attrib.get("height", ""), f"{layer} SVG height")
        require(abs(page_width - width) <= 0.01 and abs(page_height - height) <= 0.01,
                f"{layer} SVG physical size/viewBox mismatch")
        left, top, right, bottom = find_svg_board_outline(root)
        require(
            left >= view_x - 0.01
            and top >= view_y - 0.01
            and right <= view_x + width + 0.01
            and bottom <= view_y + height + 0.01,
            f"{layer} 24x22 board outline falls outside the SVG viewBox",
        )
        coverage = [24.0 / width, 22.0 / height]
        # Independent usability bound: KiCad's fitted export is ~0.706 in X;
        # the same 24 mm outline on an A4-width canvas would be only ~0.114.
        require(min(coverage) >= 0.65,
                f"{layer} board is a thumbnail on SVG canvas: coverage={coverage}")
        contents[layer] = data
        results[layer] = {
            "path": str(path.relative_to(artifact_root)),
            "sha256": sha256(path),
            "bytes": len(data),
            "view_box": dimensions,
            "physical_page_mm": [page_width, page_height],
            "board_outline": [left, top, right, bottom],
            "outline_canvas_fraction": coverage,
            "board_fitted": True,
            "drawing_sheet_excluded": b"Dioneya / ZS-BPLA" not in data,
        }
        require(results[layer]["drawing_sheet_excluded"],
                f"{layer} copper-review SVG still contains the A4 drawing sheet")
    require(contents["F.Cu"] != contents["B.Cu"],
            "F.Cu and B.Cu review SVGs are unexpectedly identical")
    return {
        "status": "PASS_BOARD_SIZED_ZOOMABLE_LAYER_DRAWINGS",
        "layers": results,
        "layer_files_distinct": True,
    }


def audit_copper_return_report(artifact_root: Path, commit_sha: str) -> dict[str, Any]:
    path = artifact_root / "copper_return_review_audit.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    require(
        report.get("schema") == "dioneya-pcb-mic-copper-return-review-b-precheck-v2",
        "unexpected copper-return audit schema",
    )
    require(
        report.get("machine_status") == "PASS_REPRODUCIBLE_ECO_TOPOLOGY_MEASUREMENT",
        "copper-return topology measurement did not pass",
    )
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    gate = status.get("review_b", {}).get("copper_return_gate", {})
    expected_disposition = (
        "ECO_CANDIDATE_EXPLICIT_LOCAL_RETURN_READY_FOR_REPEAT_REVIEW_A"
        if status.get("release_state") == "REVIEW_A_REQUIRED_AFTER_COPPER_ECO" else
        "PASS_HUMAN_ACCEPTED_COPPER_RETURN_SUBGATE_REVIEW_B_REMAINS_OPEN"
        if gate.get("complete") is True else
        "READY_FOR_INDEPENDENT_HUMAN_COPPER_RETURN_REVIEW"
    )
    require(
        report.get("review_b_disposition") == expected_disposition,
        "copper-return disposition does not match the Review-A state",
    )
    require(report.get("review_b_complete") is False,
            "copper-return precheck must not complete Review B")
    require(report.get("manufacturing_release") is False,
            "copper-return precheck must not grant manufacturing release")
    findings = {item.get("id"): item for item in report.get("findings", [])}
    if gate.get("complete") is True:
        require(
            findings.get("PCB-MIC-RB-CU-002", {}).get("severity") ==
            "ACCEPTED_BY_INDEPENDENT_REVIEWER",
            "accepted copper-return report still requests a human decision",
        )
    binding = report.get("commit_binding", {})
    require(binding.get("evidence_commit_sha") == commit_sha,
            "copper-return audit commit binding mismatch")
    require(binding.get("board_sha256") == sha256(BOARD),
            "copper-return audit board hash mismatch")
    topology = report.get("topology", {})
    paths = topology.get("paths", {})
    require(
        paths.get("C1.1_to_MK1.7_vdd_local", {}).get("connected") is True
        and paths.get("C1.2_to_MK1.2_ground_return", {}).get("connected") is True,
        "copper-return audit lacks connected local supply/return paths",
    )
    require(paths["C1.2_to_MK1.2_ground_return"].get("trace_length_mm") == 7.10815,
            "post-ECO C1-to-MK1 return length mismatch")
    explicit = report.get("explicit_local_return", {})
    require(explicit.get("status") == "PASS_DIRECT_BCU_C1_RETURN"
            and explicit.get("legacy_remote_branch_present") is False,
            "direct explicit C1 return control is missing")
    source_zone = report.get("ground_zone", {}).get("source", {})
    require(source_zone.get("source_zone_present") is False
            and source_zone.get("copper_model") == "EXPLICIT_ROUTING_ONLY",
            "source copper model is not explicit-routing-only")
    cam = report.get("ground_zone", {}).get("cam", {})
    require(cam.get("checked") is True
            and cam.get("materialized_gnd_region") is False
            and cam.get("gnd_region_count") == 0,
            "explicit-routing-only CAM unexpectedly contains a GND region")
    return {
        "status": report["machine_status"],
        "review_b_disposition": report["review_b_disposition"],
        "decoupling_loop_trace_length_mm": topology.get(
            "measured_decoupling_loop_trace_length_mm"
        ),
        "ground_return_trace_length_mm": paths[
            "C1.2_to_MK1.2_ground_return"
        ]["trace_length_mm"],
        "ground_return_reduction_mm": topology.get("ground_return_reduction_mm"),
        "bcu_gnd_region_count": cam.get("gnd_region_count"),
        "copper_model": source_zone.get("copper_model"),
        "copper_return_gate_complete": gate.get("complete") is True,
        "copper_return_decision": gate.get("decision"),
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def output_hashes(artifact_root: Path) -> dict[str, dict[str, Any]]:
    relative_paths = [
        "PCB-MIC.d356",
        "PCB-MIC_assembly_fabrication.pdf",
        "PCB-MIC_B_Cu_review.svg",
        "PCB-MIC_F_Cu_review.svg",
        "PCB-MIC_board.step",
        "PCB-MIC_fabrication_metadata.json",
        "PCB-MIC_kicad_bom.csv",
        "PCB-MIC_manufacturing_bom.csv",
        "PCB-MIC_pos.csv",
        "PCB-MIC_schematic.pdf",
        "cam-source/PCB-MIC.kicad_pcb",
        "cam_source_transform.json",
        "copper_return_review_audit.json",
        "drc.json",
        "drill/PCB-MIC-drl_map.pdf",
        "drill/PCB-MIC.drl",
        "erc.json",
        "gerber/PCB-MIC-job.gbrjob",
        *[f"gerber/{name}" for name in EXPECTED_GERBERS],
    ]
    hashes: dict[str, dict[str, Any]] = {}
    for relative in relative_paths:
        path = artifact_root / relative
        require(path.is_file(), f"required Review-B preflight output missing: {relative}")
        hashes[relative] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    return hashes


def audit(artifact_root: Path, commit_sha: str) -> dict[str, Any]:
    status, release_check = audit_release_state()
    signed_commit = status["review_a"].get("commit_sha")
    checks = {
        "release_state": release_check,
        "commit_binding": audit_commit_binding(commit_sha, status),
        "cli_reports": audit_cli_reports(artifact_root),
        "cam_source_transform": audit_cam_transform(artifact_root, commit_sha),
        "native_topology": audit_native_topology(status),
        "gerber_job_and_layers": audit_gerbers(artifact_root),
        "excellon": audit_drill(artifact_root),
        "pick_and_place": audit_pnp(artifact_root),
        "bom": audit_boms(artifact_root),
        "ipc_d_356": audit_ipc356(artifact_root),
        "documents": audit_documents(artifact_root),
        "copper_review_drawings": audit_copper_review_svgs(artifact_root),
        "copper_return_review": audit_copper_return_report(artifact_root, commit_sha),
    }
    source_paths = [
        BOARD, SCHEMATIC, PROJECT, FABRICATION_METADATA, STATUS,
        PRODUCTION_BOM, NATIVE_GATE, COPPER_RETURN_AUDIT,
        COPPER_RETURN_PACKET, GENERATOR, NATIVE_WORKFLOW, Path(__file__).resolve(),
    ]
    report_status = (
        "PASS_ECO_CANDIDATE_CAM_PREFLIGHT_REPEAT_REVIEW_A_REQUIRED"
        if status["release_state"] == "REVIEW_A_REQUIRED_AFTER_COPPER_ECO" else
        "PASS_INTERNAL_CAM_PREFLIGHT_REVIEW_B_REMAINS_OPEN"
    )
    remaining_external_gates = list(REMAINING_EXTERNAL_GATES)
    if status["release_state"] == "REVIEW_A_REQUIRED_AFTER_COPPER_ECO":
        remaining_external_gates.insert(0, REPEAT_REVIEW_A_GATE)
    elif status["review_b"]["copper_return_gate"].get("complete") is True:
        remaining_external_gates.remove(COPPER_RETURN_GATE)
    return {
        "schema": "dioneya-pcb-mic-review-b-internal-preflight-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MIC",
        "status": report_status,
        "evidence_commit_sha": commit_sha,
        "signed_review_a_commit_sha": signed_commit,
        "review_b_complete": False,
        "manufacturing_release": False,
        "checks": checks,
        "source_hashes": {display_path(path): sha256(path) for path in source_paths},
        "output_hashes": output_hashes(artifact_root),
        "remaining_external_gates": remaining_external_gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit-sha", required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = audit(args.artifact_root.resolve(), args.commit_sha)
    except Exception as exc:
        report = {
            "schema": "dioneya-pcb-mic-review-b-internal-preflight-v1",
            "configuration": "EVT-PRE-20 Rev.A",
            "assembly": "PCB-MIC",
            "status": "FAIL_INTERNAL_CAM_PREFLIGHT",
            "evidence_commit_sha": args.commit_sha,
            "review_b_complete": False,
            "manufacturing_release": False,
            "error": f"{type(exc).__name__}: {exc}",
            "remaining_external_gates": [REPEAT_REVIEW_A_GATE, *REMAINING_EXTERNAL_GATES],
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"PCB-MIC Review-B internal CAM preflight FAIL: {exc}")
        return 1

    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PCB-MIC CAM preflight PASS: {report['status']}")
    if report["signed_review_a_commit_sha"]:
        print("Review A is signed; Review B remains OPEN; manufacturing release remains FALSE")
    else:
        print("Review A/Review B remain OPEN as recorded; manufacturing release remains FALSE")
    print(f"evidence commit: {args.commit_sha}")
    print(f"hashed source files: {len(report['source_hashes'])}")
    print(f"hashed output files: {len(report['output_hashes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

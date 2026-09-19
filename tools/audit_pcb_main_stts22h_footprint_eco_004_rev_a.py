#!/usr/bin/env python3
"""Audit the reviewed and applied PCB-MAIN STTS22H footprint ECO-004.

The signed candidate corrects only the U4 land-pattern row spacing, courtyard
height and reference-text position.  The audit reconstructs the historical
baseline and proves that the authoritative board is the exact reviewed result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board
from kiutils.footprint import Footprint
from kiutils.utils import sexpr

from materialize_pcb_main_stts22h_footprint_eco_004_rev_a import (
    BOARD_REPLACEMENTS,
    candidate_bytes,
    historical_base_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_NATIVE_BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
BASE_BOARD = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-001"
    / "PCB-MAIN_GROUND_DOMAIN_BASE_REV_A.kicad_pcb"
)
BASE_FOOTPRINT = (
    ROOT
    / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty/STTS22H_UDFN-6L.kicad_mod"
)
CANDIDATE_ROOT = ROOT / "hardware/kicad/candidates/PCB-MAIN-STTS22H-ECO-004"
CANDIDATE_BOARD_NAME = "PCB-MAIN_STTS22H_ECO_004.kicad_pcb"
CANDIDATE_FOOTPRINT = CANDIDATE_ROOT / "STTS22H_UDFN-6L_ECO_004.kicad_mod"
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_STTS22H_FOOTPRINT_ECO_004_CANDIDATE_REV_A.json"
PROPOSAL_RECORD = ROOT / "hardware/reviews/PCB_MAIN_STTS22H_FOOTPRINT_ECO_004_CANDIDATE_REV_A.md"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_STTS22H_FOOTPRINT_ECO_004_APPROVAL.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_STTS22H_FOOTPRINT_ECO_004_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_STTS22H_FOOTPRINT_ECO_004_APPLICATION.json"
FOOTPRINT_REGISTER = ROOT / "hardware/reviews/PCB_MAIN_KICAD_FOOTPRINT_REVIEW_REV_A.csv"
FOOTPRINT_DISPOSITION = ROOT / "hardware/reviews/PCB_MAIN_FOOTPRINT_DISPOSITION_REV_A.md"
CAPTURE_MANIFEST = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN_capture_manifest.json"

BASE_BOARD_SHA256 = "dfcd8780cb3f189fe89cca98f32e3ee9693947a9a28d25e0154f7cce65d51684"
BASE_FOOTPRINT_SHA256 = "d3421087f45b39626defa0608f8fd269f02033f4c4b7ff15bb708af18b573a93"
CANDIDATE_BOARD_SHA256 = "a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8"
CANDIDATE_FOOTPRINT_SHA256 = "e06136e5f2ebd67798141ff1ef99db94d895d139d20b3c98a671e34bbbfa277f"
PROPOSAL_SHA256 = "4b7da50ef11415385317f4811a26301c189988e349d3fcef0b0107692a443df8"
PROPOSAL_RECORD_SHA256 = "35b7c9455fad54013959b2f589fa3068830b8d2dbb812ce924fb42ebd6d4e772"
REVIEWED_GITHUB_COMMIT = "059ecd0e2e35fc56a56f48d62cce4f72a93755c0"
REVIEWED_TREE = "d6805c8f15ce319410a996f143132c6f8f58f35e"
APPROVAL_COMMIT = "3f133c2cb2075b4bdc8d4044366014f1b9d17add"
APPLICATION_COMMIT = "6bbcc0a1179bc945c9ee915fd89d299c2808ad10"
EXPECTED_UNCONNECTED = 718
EXPECTED_SIGNAL_TO_EP_GAP_MM = 0.190

FOOTPRINT_REPLACEMENTS = {
    "  (fp_rect (start -1.25 -1.25) (end 1.25 1.25)":
        "  (fp_rect (start -1.25 -1.5) (end 1.25 1.5)",
    '  (pad "1" smd rect (at -0.65 0.54) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask"))':
        '  (pad "1" smd rect (at -0.65 0.865) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask"))',
    '  (pad "2" smd roundrect (at 0 0.54) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))':
        '  (pad "2" smd roundrect (at 0 0.865) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))',
    '  (pad "3" smd roundrect (at 0.65 0.54) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))':
        '  (pad "3" smd roundrect (at 0.65 0.865) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))',
    '  (pad "4" smd roundrect (at 0.65 -0.54) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))':
        '  (pad "4" smd roundrect (at 0.65 -0.865) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))',
    '  (pad "5" smd roundrect (at 0 -0.54) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))':
        '  (pad "5" smd roundrect (at 0 -0.865) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))',
    '  (pad "6" smd roundrect (at -0.65 -0.54) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))':
        '  (pad "6" smd roundrect (at -0.65 -0.865) (size 0.27 0.70) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.20))',
}

EXPECTED_PAD_POSITIONS = {
    "1": (-0.65, 0.865),
    "2": (0.0, 0.865),
    "3": (0.65, 0.865),
    "4": (0.65, -0.865),
    "5": (0.0, -0.865),
    "6": (-0.65, -0.865),
    "EP": (0.0, 0.0),
}

EXPECTED_NETS = {
    "1": "I2C2_SCL_BUS",
    "2": None,
    "3": "3V3_DIGITAL",
    "4": "GND_DIGITAL",
    "5": "GND_DIGITAL",
    "6": "I2C2_SDA_BUS",
    "EP": None,
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_bytes(commit: str, path: Path) -> bytes:
    relative = path.relative_to(ROOT)
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"cannot read {relative} from {commit}")
    return completed.stdout


def git_tree(commit: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"cannot resolve reviewed tree for {commit}")
    return completed.stdout.strip()


def git_blob_sha(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def close(first: float, second: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(float(first), float(second), rel_tol=0.0, abs_tol=tolerance)


def ref_of(footprint: Any) -> str:
    references = [
        str(item.text)
        for item in footprint.graphicItems
        if getattr(item, "type", None) == "reference"
    ]
    require(len(references) <= 1, f"duplicate reference graphics: {references}")
    return references[0] if references else str(footprint.properties.get("Reference", ""))


def u4_of(board: Board) -> Any:
    matches = [footprint for footprint in board.footprints if ref_of(footprint) == "U4"]
    require(len(matches) == 1, f"expected one U4 footprint, found {len(matches)}")
    return matches[0]


def apply_exact_replacements(text: str, replacements: dict[str, str], label: str) -> str:
    for old, new in replacements.items():
        require(text.count(old) == 1, f"{label}: expected exactly one source line {old!r}")
        require(new not in text, f"{label}: replacement already present before controlled transform")
        text = text.replace(old, new)
    return text


def courtyard_bounds(footprint: Any) -> tuple[float, float, float, float]:
    items = [
        item
        for item in footprint.graphicItems
        if getattr(item, "layer", None) == "F.CrtYd"
    ]
    require(len(items) == 1 and type(items[0]).__name__ == "FpRect",
            "U4 must have exactly one rectangular F.CrtYd")
    item = items[0]
    return (
        float(item.start.X),
        float(item.start.Y),
        float(item.end.X),
        float(item.end.Y),
    )


def audit_u4(footprint: Any, *, board_instance: bool) -> dict[str, Any]:
    pads = {str(pad.number): pad for pad in footprint.pads}
    require(set(pads) == set(EXPECTED_PAD_POSITIONS),
            f"U4 pad set drift: {sorted(pads)}")
    for number, (expected_x, expected_y) in EXPECTED_PAD_POSITIONS.items():
        pad = pads[number]
        require(close(pad.position.X, expected_x) and close(pad.position.Y, expected_y),
                f"U4.{number}: unexpected pad position {pad.position}")
        expected_size = (1.45, 0.65) if number == "EP" else (0.27, 0.70)
        require(close(pad.size.X, expected_size[0]) and close(pad.size.Y, expected_size[1]),
                f"U4.{number}: pad-size drift")
        require(pad.layers == ["F.Cu", "F.Paste", "F.Mask"],
                f"U4.{number}: copper/paste/mask layer drift")
        expected_shape = "rect" if number in {"1", "EP"} else "roundrect"
        require(pad.shape == expected_shape, f"U4.{number}: pad-shape drift")
        if expected_shape == "roundrect":
            require(close(pad.roundrectRatio, 0.20), f"U4.{number}: corner-ratio drift")
        if board_instance:
            actual_net = pad.net.name if pad.net is not None else None
            require(actual_net == EXPECTED_NETS[number],
                    f"U4.{number}: net drift {actual_net!r}")
            require(close(pad.clearance, 0.18),
                    f"U4.{number}: local clearance is not 0.18 mm")

    ep = pads["EP"]
    gaps = []
    for number in ("1", "2", "3", "4", "5", "6"):
        pad = pads[number]
        gap = abs(float(pad.position.Y) - float(ep.position.Y)) \
            - float(pad.size.Y) / 2.0 - float(ep.size.Y) / 2.0
        require(close(gap, EXPECTED_SIGNAL_TO_EP_GAP_MM),
                f"U4.{number}: signal-to-EP copper gap {gap:.6f} mm")
        gaps.append(round(gap, 6))
    require(courtyard_bounds(footprint) == (-1.25, -1.5, 1.25, 1.5),
            f"U4 courtyard drift: {courtyard_bounds(footprint)}")
    return {
        "pads": len(pads),
        "signal_pad_row_y_mm": [-0.865, 0.865],
        "signal_to_ep_copper_gaps_mm": sorted(set(gaps)),
        "courtyard_mm": [-1.25, -1.5, 1.25, 1.5],
    }


def parse_drc(path: Path) -> dict[str, Any]:
    require(path.is_file() and path.stat().st_size > 0, f"missing DRC report: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"(?m)^\[([^]]+)\]:[^\n]*\n", text)
    counts: Counter[tuple[str, str]] = Counter()
    for index in range(1, len(parts), 2):
        category = parts[index]
        body = parts[index + 1]
        # KiCad 7 emits ``Severity: error`` while KiCad 9 emits a terminal
        # ``; error`` on the rule/local-override line.
        match = re.search(
            r"(?mi)(?:Severity:\s*|;\s*)(error|warning|exclusion)\s*$",
            body,
        )
        severity = match.group(1).lower() if match else "unknown"
        counts[(category, severity)] += 1
    require(counts, f"DRC report contains no parseable violations: {path}")
    return {
        "path": str(path),
        "counts": {
            f"{category}:{severity}": count
            for (category, severity), count in sorted(counts.items())
        },
        "errors": {
            category: count
            for (category, severity), count in sorted(counts.items())
            if severity == "error"
        },
    }


def compare_drc(base_path: Path, candidate_path: Path) -> dict[str, Any]:
    base = parse_drc(base_path)
    candidate = parse_drc(candidate_path)
    require(base["errors"].get("clearance") == 6,
            f"expected six baseline U4 clearance errors: {base['errors']}")
    require(base["errors"].get("solder_mask_bridge") == 6,
            f"expected six baseline U4 mask-bridge errors: {base['errors']}")
    require(candidate["errors"].get("clearance", 0) == 0,
            f"candidate retains clearance errors: {candidate['errors']}")
    require(candidate["errors"].get("solder_mask_bridge", 0) == 0,
            f"candidate retains mask-bridge errors: {candidate['errors']}")
    require(candidate["errors"].get("unconnected_items") ==
            base["errors"].get("unconnected_items"),
            "candidate connectivity error count differs from baseline")
    added = {
        category: count - base["errors"].get(category, 0)
        for category, count in candidate["errors"].items()
        if count > base["errors"].get(category, 0)
    }
    require(not added, f"candidate introduces DRC errors: {added}")
    return {
        "status": "PASS_EXACT_U4_ERROR_REMOVAL_NO_NEW_ERROR",
        "removed_error_counts": {"clearance": 6, "solder_mask_bridge": 6},
        "base": base,
        "candidate": candidate,
    }


def native_connectivity(candidate_path: Path | None) -> dict[str, Any]:
    try:
        import pcbnew  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on KiCad system Python
        raise AssertionError("--kicad-connectivity requires the KiCad pcbnew module") from exc

    with tempfile.TemporaryDirectory(prefix="pcb-main-stts22h-eco004-") as temp_dir:
        baseline_path = Path(temp_dir) / "PCB-MAIN_STTS22H_ECO_004_BASE.kicad_pcb"
        baseline_path.write_bytes(historical_base_bytes())
        if candidate_path is None:
            candidate_path = Path(temp_dir) / CANDIDATE_BOARD_NAME
            candidate_path.write_bytes(candidate_bytes())
        require(candidate_path.is_file(), f"missing materialized candidate: {candidate_path}")
        require(sha256(candidate_path) == CANDIDATE_BOARD_SHA256,
                "materialized candidate SHA-256 drift")
        counts: dict[str, int] = {}
        for label, path in (("baseline", baseline_path), ("candidate", candidate_path)):
            board = pcbnew.LoadBoard(str(path))
            require(board is not None, f"KiCad cannot load {path}")
            board.BuildConnectivity()
            counts[label] = int(board.GetConnectivity().GetUnconnectedCount(False))
    require(counts == {"baseline": EXPECTED_UNCONNECTED, "candidate": EXPECTED_UNCONNECTED},
            f"unexpected connectivity counts: {counts}")
    result = {
        "status": "PASS_NO_CONNECTIVITY_CHANGE",
        "baseline_unconnected_count": counts["baseline"],
        "candidate_unconnected_count": counts["candidate"],
    }
    return result


def static_audit() -> dict[str, Any]:
    for path in (
        BASE_BOARD,
        BASE_FOOTPRINT,
        CANDIDATE_FOOTPRINT,
        PROPOSAL,
        PROPOSAL_RECORD,
        APPROVAL,
        MAPPING,
        APPLICATION,
        FOOTPRINT_REGISTER,
        FOOTPRINT_DISPOSITION,
        CAPTURE_MANIFEST,
    ):
        require(path.is_file() and path.stat().st_size > 0, f"missing ECO-004 input: {path}")
    require(sha256(BASE_BOARD) == CANDIDATE_BOARD_SHA256,
            "ECO-004 applied authoritative board SHA-256 drift")
    require(sha256(BASE_FOOTPRINT) == CANDIDATE_FOOTPRINT_SHA256,
            "ECO-004 applied controlled footprint SHA-256 drift")
    require(sha256(CANDIDATE_FOOTPRINT) == CANDIDATE_FOOTPRINT_SHA256,
            "ECO-004 candidate footprint SHA-256 drift")
    require(sha256(PROPOSAL) == PROPOSAL_SHA256,
            "ECO-004 reviewed proposal SHA-256 drift")
    require(sha256(PROPOSAL_RECORD) == PROPOSAL_RECORD_SHA256,
            "ECO-004 reviewed proposal record SHA-256 drift")

    baseline_payload = historical_base_bytes()
    require(hashlib.sha256(baseline_payload).hexdigest() == BASE_BOARD_SHA256,
            "ECO-004 historical baseline board SHA-256 drift")
    candidate_payload = candidate_bytes()
    candidate_sha256 = hashlib.sha256(candidate_payload).hexdigest()
    require(candidate_sha256 == CANDIDATE_BOARD_SHA256,
            "ECO-004 generated candidate board SHA-256 drift")
    require(candidate_payload == BASE_BOARD.read_bytes(),
            "authoritative board differs from the exact reviewed ECO-004 candidate")
    baseline_footprint = git_bytes(REVIEWED_GITHUB_COMMIT, BASE_FOOTPRINT)
    require(hashlib.sha256(baseline_footprint).hexdigest() == BASE_FOOTPRINT_SHA256,
            "ECO-004 historical baseline footprint SHA-256 drift")
    transformed_footprint = apply_exact_replacements(
        baseline_footprint.decode("utf-8"), FOOTPRINT_REPLACEMENTS, "footprint"
    )
    require(transformed_footprint == CANDIDATE_FOOTPRINT.read_text(encoding="utf-8"),
            "candidate library footprint contains changes outside the bounded U4 delta")
    require(BASE_FOOTPRINT.read_bytes() == CANDIDATE_FOOTPRINT.read_bytes(),
            "applied controlled footprint differs from the reviewed candidate footprint")

    base = Board.from_sexpr(sexpr.parse_sexp(baseline_payload.decode("utf-8")))
    candidate = Board.from_sexpr(sexpr.parse_sexp(candidate_payload.decode("utf-8")))
    require(len(base.footprints) == len(candidate.footprints) == 251,
            "PCB-MAIN footprint-count drift")
    require(len(base.traceItems) == len(candidate.traceItems) == 0,
            "ECO-004 candidate must remain unrouted")
    require(len(base.zones) == len(candidate.zones) == 0,
            "ECO-004 candidate must not contain copper zones")
    require([(net.number, net.name) for net in base.nets] ==
            [(net.number, net.name) for net in candidate.nets],
            "ECO-004 candidate net table differs from baseline")

    baseline_u4 = u4_of(base)
    candidate_u4 = u4_of(candidate)
    require((float(baseline_u4.position.X), float(baseline_u4.position.Y),
             float(baseline_u4.position.angle or 0.0)) == (66.0, 36.5, 0.0),
            "baseline U4 placement drift")
    require((float(candidate_u4.position.X), float(candidate_u4.position.Y),
             float(candidate_u4.position.angle or 0.0)) == (66.0, 36.5, 0.0),
            "candidate U4 placement changed")
    baseline_pads = {str(pad.number): pad for pad in baseline_u4.pads}
    baseline_gap = abs(float(baseline_pads["1"].position.Y)) \
        - float(baseline_pads["1"].size.Y) / 2.0 \
        - float(baseline_pads["EP"].size.Y) / 2.0
    require(close(baseline_gap, -0.135),
            f"expected baseline copper overlap of 0.135 mm, got {baseline_gap:.6f}")

    board_geometry = audit_u4(candidate_u4, board_instance=True)
    reference_items = [
        item for item in candidate_u4.graphicItems
        if getattr(item, "type", None) == "reference"
    ]
    require(len(reference_items) == 1 and
            close(reference_items[0].position.X, 0.0) and
            close(reference_items[0].position.Y, -1.8),
            "candidate U4 reference-text position drift")

    library = Footprint.from_file(str(BASE_FOOTPRINT), encoding="utf-8")
    require(library.entryName == "STTS22H_UDFN-6L",
            f"candidate footprint identity drift: {library.entryName!r}")
    library_geometry = audit_u4(library, board_instance=False)

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    require(proposal["proposal_id"] == "PCB-MAIN-STTS22H-FOOTPRINT-ECO-004",
            "ECO-004 proposal identity drift")
    require(proposal["status"] == "READY_FOR_MACHINE_GATE_AND_INDEPENDENT_HUMAN_REVIEW",
            "ECO-004 proposal status drift")
    require(proposal["baseline"]["board_sha256"] == BASE_BOARD_SHA256,
            "ECO-004 proposal baseline hash drift")
    require(proposal["candidate"]["board_sha256"] == CANDIDATE_BOARD_SHA256,
            "ECO-004 proposal candidate-board hash drift")
    require(proposal["candidate"]["board"] == f"MATERIALIZED:{CANDIDATE_BOARD_NAME}" and
            proposal["candidate"]["materializer"] ==
            "tools/materialize_pcb_main_stts22h_footprint_eco_004_rev_a.py",
            "ECO-004 proposal materializer binding drift")
    require(proposal["candidate"]["footprint_sha256"] == CANDIDATE_FOOTPRINT_SHA256,
            "ECO-004 proposal candidate-footprint hash drift")
    require(proposal["decision_boundary"] == {
        "proposal_only": True,
        "applied_to_authoritative_board": False,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }, "ECO-004 decision boundary drift")

    require(git_tree(REVIEWED_GITHUB_COMMIT) == REVIEWED_TREE,
            "ECO-004 reviewed GitHub tree drift")
    reviewed_payloads = {
        PROPOSAL: (PROPOSAL_SHA256, "612dd5e86df658d8ffbb27452965347413572ac9"),
        PROPOSAL_RECORD: (PROPOSAL_RECORD_SHA256, "5c26894aaad16ad3ff36bf55c74708bd501c7a21"),
        CANDIDATE_FOOTPRINT: (CANDIDATE_FOOTPRINT_SHA256,
                              "4d86d583554d3770d137ab826faf59b1cc70762a"),
    }
    for path, (expected_sha256, expected_blob) in reviewed_payloads.items():
        payload = git_bytes(REVIEWED_GITHUB_COMMIT, path)
        require(hashlib.sha256(payload).hexdigest() == expected_sha256 and
                git_blob_sha(payload) == expected_blob,
                f"reviewed ECO-004 blob drift: {path.relative_to(ROOT)}")
    require(git_blob_sha(git_bytes(REVIEWED_GITHUB_COMMIT, Path(__file__))) ==
            "996b3f9cfecc3e04016421bf75407fe8cd9cb4b8",
            "reviewed ECO-004 audit blob drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(approval.get("proposal_id") == "PCB-MAIN-STTS22H-FOOTPRINT-ECO-004" and
            approval.get("reviewer") == "Скиф" and
            approval.get("decision_date") == "2026-09-19" and
            approval.get("decision") == "ACCEPT_STTS22H_FOOTPRINT_ECO_004" and
            approval.get("reviewed_github_commit_sha") == REVIEWED_GITHUB_COMMIT and
            approval.get("reviewed_tree_sha") == REVIEWED_TREE and
            approval.get("reviewed_proposal_sha256") == PROPOSAL_SHA256 and
            approval.get("reviewed_proposal_record_sha256") == PROPOSAL_RECORD_SHA256 and
            approval.get("reviewed_candidate_footprint_sha256") ==
            CANDIDATE_FOOTPRINT_SHA256 and
            approval.get("reviewed_materialized_board_sha256") == CANDIDATE_BOARD_SHA256 and
            authorization.get("apply_bounded_u4_land_pattern_correction") is True and
            authorization.get("continue_pcb_main_routing_engineering") is True and
            authorization.get("candidate_or_future_copper_final_authorized") is False and
            authorization.get("review_b_complete") is False and
            authorization.get("cam_or_manufacturing_release") is False,
            "ECO-004 approval binding or release boundary drift")

    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    require(mapping.get("reviewed_github_commit_sha") == REVIEWED_GITHUB_COMMIT and
            mapping.get("reviewed_tree_sha") == REVIEWED_TREE and
            mapping.get("proposal_blob_sha") == "612dd5e86df658d8ffbb27452965347413572ac9" and
            mapping.get("proposal_record_blob_sha") == "5c26894aaad16ad3ff36bf55c74708bd501c7a21" and
            mapping.get("candidate_footprint_blob_sha") ==
            "4d86d583554d3770d137ab826faf59b1cc70762a" and
            mapping.get("materialized_candidate_board_sha256") == CANDIDATE_BOARD_SHA256 and
            mapping.get("audit_blob_sha") == "996b3f9cfecc3e04016421bf75407fe8cd9cb4b8" and
            mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS" and
            mapping.get("review_b_complete") is False and
            mapping.get("manufacturing_release") is False,
            "ECO-004 review-commit mapping drift")

    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    applied = application.get("applied", {})
    require(application.get("proposal_id") == "PCB-MAIN-STTS22H-FOOTPRINT-ECO-004" and
            application.get("approval") == str(APPROVAL.relative_to(ROOT)) and
            application.get("reviewed_proposal_commit_sha") == REVIEWED_GITHUB_COMMIT and
            application.get("approval_commit_sha") == APPROVAL_COMMIT and
            application.get("reviewed_proposal_sha256") == PROPOSAL_SHA256 and
            application.get("reviewed_candidate_footprint_sha256") ==
            CANDIDATE_FOOTPRINT_SHA256 and
            application.get("reviewed_materialized_board_sha256") ==
            CANDIDATE_BOARD_SHA256 and
            application.get("decision") == "ACCEPT_STTS22H_FOOTPRINT_ECO_004" and
            application.get("status") ==
            "APPLIED_BOUNDED_U4_CORRECTION_ROUTING_ENGINEERING_CONTINUES" and
            application.get("routing_engineering_continuation_authorized") is True and
            application.get("candidate_or_future_copper_final_authorized") is False and
            application.get("routing_complete") is False and
            application.get("review_b_complete") is False and
            application.get("cam_or_manufacturing_release") is False,
            "ECO-004 application binding or release boundary drift")
    require(applied.get("board_sha256") == CANDIDATE_BOARD_SHA256 and
            applied.get("controlled_footprint_sha256") == CANDIDATE_FOOTPRINT_SHA256 and
            applied.get("footprint_review_register_sha256") == sha256(FOOTPRINT_REGISTER) and
            applied.get("footprint_disposition_sha256") == sha256(FOOTPRINT_DISPOSITION) and
            applied.get("capture_manifest_sha256") == hashlib.sha256(
                git_bytes(APPLICATION_COMMIT, CAPTURE_MANIFEST)
            ).hexdigest() and
            applied.get("changed_references") == ["U4"] and
            applied.get("exact_board_line_replacements") == len(BOARD_REPLACEMENTS) and
            applied.get("track_segments") == 0 and
            applied.get("vias") == 0 and
            applied.get("copper_zones") == 0,
            "ECO-004 applied source/hash record drift")

    return {
        "schema_version": "dioneya.pcb-main-stts22h-footprint-eco-audit.v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "proposal_id": proposal["proposal_id"],
        "status": "PASS_APPROVED_APPLIED_BOUNDED_U4_CORRECTION",
        "baseline": {
            "board": f"GIT:{REVIEWED_GITHUB_COMMIT}:{HISTORICAL_NATIVE_BOARD.relative_to(ROOT)}",
            "board_sha256": BASE_BOARD_SHA256,
            "u4_signal_to_ep_overlap_mm": round(-baseline_gap, 6),
        },
        "candidate": {
            "board": str(BASE_BOARD.relative_to(ROOT)),
            "board_sha256": candidate_sha256,
            "footprint": str(BASE_FOOTPRINT.relative_to(ROOT)),
            "footprint_sha256": sha256(BASE_FOOTPRINT),
            "board_geometry": board_geometry,
            "library_geometry": library_geometry,
            "exact_board_line_replacements": len(BOARD_REPLACEMENTS),
            "exact_footprint_line_replacements": len(FOOTPRINT_REPLACEMENTS),
            "tracks": len(candidate.traceItems),
            "zones": len(candidate.zones),
        },
        "authorization_boundary": {
            "routing_engineering_continuation_authorized": True,
            "candidate_or_future_copper_final_authorized": False,
            "routing_complete": False,
            "review_b_complete": False,
            "cam_or_manufacturing_release": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-drc", type=Path)
    parser.add_argument("--candidate-drc", type=Path)
    parser.add_argument("--candidate-board", type=Path)
    parser.add_argument("--kicad-connectivity", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require((args.base_drc is None) == (args.candidate_drc is None),
            "--base-drc and --candidate-drc must be supplied together")

    report = static_audit()
    if args.base_drc is not None:
        report["comparative_drc"] = compare_drc(args.base_drc, args.candidate_drc)
    if args.kicad_connectivity:
        report["native_connectivity"] = native_connectivity(args.candidate_board)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN STTS22H footprint ECO-004 audit: PASS")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

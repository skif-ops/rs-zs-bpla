#!/usr/bin/env python3
"""PCB-MAIN board lineage after the accepted inner-reroute 003 application.

The audits of earlier PCB-MAIN sub-gates (RF, GNSS, OctoSPI R8, USB, ground domain 001, requests to the
stackup and assembly suppliers) prove properties of the board they accepted. Once 003 is applied the
authoritative board is the 003 candidate; those audits then read its exact predecessor instead:

  historical_board()     -> the cellular USB fixture 001 candidate (2dd9bdf2..., byte-identical to the board
                            003 was built on) if 003 is applied, else the authoritative board;
  historical_placement() -> the placement manifest as it was before 003 (df7cdbfc...) if 003 is applied, else
                            the authoritative manifest.

inner_reroute_003_applied() is true only when the authoritative board is byte-identical to the accepted 003
candidate, the 003 application record carries ACCEPT_INNER_REROUTE_003, both predecessor files have their pinned
SHA-256 and the authoritative manifest differs from the predecessor manifest only in the R9/R10/R11 rows, set
to the accepted 003 positions. Any other change of the authoritative board keeps failing every earlier audit.
The 003 state itself is audited by tools/audit_pcb_main_inner_reroute_003_application_rev_a.py.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE_BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
PLACEMENT = ROOT / "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv"
CANDIDATES = ROOT / "hardware/kicad/candidates"
PRE_003_BOARD = (CANDIDATES / "PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001"
                 / "PCB-MAIN_USB_CELL_FIXTURE_CANDIDATE_REV_A.kicad_pcb")
PRE_003_PLACEMENT = CANDIDATES / "PCB-MAIN-INNER-REROUTE-003" / "PCB_MAIN_PLACEMENT_REPACK_PRE_003_REV_A.csv"
INNER_003_CANDIDATE = (CANDIDATES / "PCB-MAIN-INNER-REROUTE-003"
                       / "PCB-MAIN_INNER_REROUTE_003_CANDIDATE_REV_A.kicad_pcb")
INNER_003_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_INNER_REROUTE_003_APPLICATION_REV_A.json"
CAPTURE_STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
PRE_003_STATUS = CANDIDATES / "PCB-MAIN-INNER-REROUTE-003" / "PCB_MAIN_CAPTURE_STATUS_PRE_003_ROUTING_REV_A.json"

PRE_003_BOARD_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
PRE_003_PLACEMENT_SHA256 = "df7cdbfc2ac023d43ac040b14eb99440fc392d402793d5a3b03f2fd560af6a6f"
INNER_003_BOARD_SHA256 = "30c6c93e5afbbc0888ed7c7e8693af6c6f0c7df8f5c4525e02c6d5a4c47b8739"
PRE_003_STATUS_SHA256 = "1d8f81d09a93a9e1910faa7ee24130e634e46600c4033daef9ca3bdea2fd30ab"
INNER_003_POSES = {"R9": ("60.5", "19.75", "90"), "R10": ("62", "19.75", "90"), "R11": ("63.5", "19.75", "90")}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def placement_delta(before: str, after: str) -> dict:
    """{RefDes: (X, Y, Rotation)} of the rows that differ; any other difference raises."""
    rows_b = list(csv.DictReader(io.StringIO(before)))
    rows_a = list(csv.DictReader(io.StringIO(after)))
    if [r["RefDes"] for r in rows_b] != [r["RefDes"] for r in rows_a]:
        raise AssertionError("placement manifest row set changed")
    out = {}
    for b, a in zip(rows_b, rows_a):
        if b != a:
            if {k for k in a if a[k] != b[k]} - {"X_mm", "Y_mm", "Rotation_deg"}:
                raise AssertionError(f"{a['RefDes']}: placement manifest change outside the pose columns")
            out[a["RefDes"]] = (a["X_mm"], a["Y_mm"], a["Rotation_deg"])
    return out


def inner_reroute_003_applied() -> bool:
    if not (NATIVE_BOARD.is_file() and INNER_003_APPLICATION.is_file()):
        return False
    if sha256(NATIVE_BOARD) != INNER_003_BOARD_SHA256:
        return False
    application = json.loads(INNER_003_APPLICATION.read_text(encoding="utf-8"))
    if application.get("decision") != "ACCEPT_INNER_REROUTE_003":
        return False
    if not (sha256(INNER_003_CANDIDATE) == INNER_003_BOARD_SHA256
            and NATIVE_BOARD.read_bytes() == INNER_003_CANDIDATE.read_bytes()
            and sha256(PRE_003_BOARD) == PRE_003_BOARD_SHA256
            and sha256(PRE_003_PLACEMENT) == PRE_003_PLACEMENT_SHA256):
        return False
    delta = placement_delta(PRE_003_PLACEMENT.read_text(encoding="utf-8"), PLACEMENT.read_text(encoding="utf-8"))
    return delta == INNER_003_POSES


class _AliasPath(type(Path())):
    """A path that reads the predecessor file but names itself (relative_to) by the authoritative path, so path
    bindings in application records and `git show <commit>:<path>` of earlier commits keep their meaning."""

    _alias = None

    def relative_to(self, *other, **kwargs):
        if self._alias is None:
            return super().relative_to(*other, **kwargs)
        return self._alias.relative_to(*other, **kwargs)


def _aliased(real: Path, alias: Path) -> Path:
    path = _AliasPath(real)
    path._alias = alias
    return path


def historical_board() -> Path:
    return _aliased(PRE_003_BOARD, NATIVE_BOARD) if inner_reroute_003_applied() else NATIVE_BOARD


def historical_placement() -> Path:
    return _aliased(PRE_003_PLACEMENT, PLACEMENT) if inner_reroute_003_applied() else PLACEMENT


def historical_status() -> Path:
    """The capture status as the earlier sub-gates left it (before the 003 routing-constraint control update)
    once 003 is applied; the current routing-constraint control is audited by
    tools/audit_pcb_main_routing_authority_rev_a.py."""
    if inner_reroute_003_applied() and PRE_003_STATUS.is_file() and sha256(PRE_003_STATUS) == PRE_003_STATUS_SHA256:
        return _aliased(PRE_003_STATUS, CAPTURE_STATUS)
    return CAPTURE_STATUS

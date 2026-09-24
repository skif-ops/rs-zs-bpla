"""Exact board identities for the accepted PCB-PWR hot-loop 006 application.

Historical review packets remain bound to the ECO-002 board. Their auditors may
read that archived board when the authoritative board is the exact 006 successor.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-POWER-STAGE-ECO-002/PCB-PWR_BUCK_POWER_STAGE_ECO_002_CANDIDATE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-INPUT-HOT-LOOP-ROUTING-006/PCB-PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_CANDIDATE_REV_A.kicad_pcb"
SHUNT_BULK_007 = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-SHUNT-BULK-ROUTING-007/PCB-PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_CANDIDATE_REV_A.kicad_pcb"
C13_C12_008 = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-C13-C12-ROUTING-008/PCB-PWR_VBAT_SYS_C13_C12_ROUTING_008_CANDIDATE_REV_A.kicad_pcb"
SHA256 = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"
SHUNT_BULK_007_SHA256 = "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"
C13_C12_008_SHA256 = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
SEMANTIC_SHA256 = "4da495603ca0c4ed2f7c4a3cb1197a133856408ac6f262ac976c1dab5667f687"


def is_exact_application(board: Path) -> bool:
    payload = board.read_bytes()
    return (hashlib.sha256(payload).hexdigest() == SHA256
            and payload == CANDIDATE.read_bytes())


def is_controlled_application_or_successor(board: Path) -> bool:
    payload = board.read_bytes()
    return (is_exact_application(board)
            or (hashlib.sha256(payload).hexdigest() == SHUNT_BULK_007_SHA256
                and payload == SHUNT_BULK_007.read_bytes())
            or (hashlib.sha256(payload).hexdigest() == C13_C12_008_SHA256
                and payload == C13_C12_008.read_bytes()))


def historical_basis_board(active: Path) -> Path:
    """Choose the archived ECO-002 basis for an immutable historical request."""
    payload = active.read_bytes()
    if is_controlled_application_or_successor(active):
        return PREDECESSOR
    return active


def hot_loop_application_board(active: Path) -> Path:
    """Return exact 006 board while the active board is its accepted 007 successor."""
    payload = active.read_bytes()
    if ((hashlib.sha256(payload).hexdigest() == SHUNT_BULK_007_SHA256
         and payload == SHUNT_BULK_007.read_bytes())
            or (hashlib.sha256(payload).hexdigest() == C13_C12_008_SHA256
                and payload == C13_C12_008.read_bytes())):
        return CANDIDATE
    return active

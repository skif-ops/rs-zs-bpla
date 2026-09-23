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
SHA256 = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"
SEMANTIC_SHA256 = "4da495603ca0c4ed2f7c4a3cb1197a133856408ac6f262ac976c1dab5667f687"


def is_exact_application(board: Path) -> bool:
    payload = board.read_bytes()
    return (hashlib.sha256(payload).hexdigest() == SHA256
            and payload == CANDIDATE.read_bytes())


def historical_basis_board(active: Path) -> Path:
    """Choose the archived ECO-002 basis for an immutable historical request."""
    if is_exact_application(active):
        return PREDECESSOR
    return active

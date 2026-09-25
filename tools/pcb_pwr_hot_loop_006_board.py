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
C13_C11_009 = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-C13-C11-ROUTING-009/PCB-PWR_VBAT_SYS_C13_C11_ROUTING_009_CANDIDATE_REV_A.kicad_pcb"
OUTPUT_BULK_010 = ROOT / "hardware/kicad/candidates/PCB-PWR-3V8-OUTPUT-BULK-ROUTING-010/PCB-PWR_3V8_OUTPUT_BULK_ROUTING_010_CANDIDATE_REV_A.kicad_pcb"
SHA256 = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"
SHUNT_BULK_007_SHA256 = "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"
C13_C12_008_SHA256 = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
C13_C11_009_SHA256 = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
OUTPUT_BULK_010_SHA256 = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
SEMANTIC_SHA256 = "4da495603ca0c4ed2f7c4a3cb1197a133856408ac6f262ac976c1dab5667f687"
J2_PLACEMENT_ECO_003_SHA256 = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"
AUTOROUTE_011 = ROOT / "hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/PCB-PWR_AUTOROUTE_011_CANDIDATE_REV_A.kicad_pcb"
AUTOROUTE_011_SHA256 = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"


def is_j2_placement_eco_003(payload: bytes) -> bool:
    """Accepted ECO-003 successor of routing 010 (placement lines only)."""
    if hashlib.sha256(payload).hexdigest() != J2_PLACEMENT_ECO_003_SHA256:
        return False
    import generate_pcb_pwr_j2_placement_eco_003_candidate_rev_a as eco_003

    return payload == eco_003.candidate_bytes(OUTPUT_BULK_010.read_bytes())


def is_autoroute_011(payload: bytes) -> bool:
    """Accepted autoroute 011 successor of ECO-003: the committed CI candidate."""
    return (hashlib.sha256(payload).hexdigest() == AUTOROUTE_011_SHA256
            and payload == AUTOROUTE_011.read_bytes())


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
                and payload == C13_C12_008.read_bytes())
            or (hashlib.sha256(payload).hexdigest() == C13_C11_009_SHA256
                and payload == C13_C11_009.read_bytes())
            or (hashlib.sha256(payload).hexdigest() == OUTPUT_BULK_010_SHA256
                and payload == OUTPUT_BULK_010.read_bytes())
            or is_j2_placement_eco_003(payload)
            or is_autoroute_011(payload))


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
                and payload == C13_C12_008.read_bytes())
            or (hashlib.sha256(payload).hexdigest() == C13_C11_009_SHA256
                and payload == C13_C11_009.read_bytes())
            or (hashlib.sha256(payload).hexdigest() == OUTPUT_BULK_010_SHA256
                and payload == OUTPUT_BULK_010.read_bytes())
            or is_j2_placement_eco_003(payload)
            or is_autoroute_011(payload)):
        return CANDIDATE
    return active

#!/usr/bin/env python3
"""Apply the accepted PCB-PWR J2 placement ECO-003 to the authoritative sources.

Acceptance: candidate SHA-256 b12f445d... accepted by the customer in chat on
2026-09-24 together with the decision "outer layers 1 oz" (the stackup change is
a separate ECO-004).  This script is deterministic and idempotent-checked: it
refuses to run unless the authoritative board is the routing-010 base, and
--check verifies an already applied tree without writing.

Edits:
1. native board <- ECO-003 candidate (placement lines only);
2. placement geometry: rotate() in the PCB-PWR placement-clearance audit follows
   KiCad's y-down convention; the nine accepted ECO-003 poses are an exact
   override bound to the ECO-003 board SHA (same pattern as ECO-002), so the
   placement authority CSV, the DIM-003 record and every historical packet that
   binds their SHA-256 stay byte-identical;
3. the ECO-003 successor SHA joins every predecessor interlock that accepts
   routing 010 as a successor; routing 010 is replayed historically;
4. capture-status placement and pre-route controls recomputed by their audits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_pcb_pwr_j2_placement_eco_003_candidate_rev_a as candidate  # noqa: E402

BOARD = candidate.NATIVE
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
ECO_003_SHA256 = candidate.CANDIDATE_SHA256
OUTPUT_BULK_010_SHA256 = candidate.BASE_SHA256

NEW_POSITIONS = {
    "J2": (81.08, 40.00), "U5": (74.40, 46.00), "C7": (74.40, 50.00), "C8": (74.90, 54.00),
    "NT1": (75.60, 40.12), "NT2": (75.60, 48.52), "NT3": (75.60, 52.00),
    "R13": (74.60, 56.50), "R14": (74.60, 58.00),
}

POSES_BLOCK = (
    "# Exact accepted ECO-003 poses; the placement authority CSV and the DIM-003\n"
    "# record stay byte-identical because historical packets bind their SHA-256.\n"
    "J2_PLACEMENT_ECO_003_POSES = {\n"
    + "".join(
        f'    "{ref}": ({x}, {y}, {270.0 if ref == "J2" else 0.0}),\n'
        for ref, (x, y) in NEW_POSITIONS.items()
    )
    + "}\n"
)

# Exact textual edits of existing tools: (path, old, new).
TOOL_EDITS: list[tuple[str, str, str]] = [
    (
        "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
        "    return x * cosine - y * sine, x * sine + y * cosine\n",
        "    # KiCad boards are y-down: a footprint angle a maps local (x, y) to\n"
        "    # (x cos a + y sin a, -x sin a + y cos a).  ECO-003 corrected the former\n"
        "    # y-up sign, which mirrored +/-90 degree footprints such as J2.\n"
        "    return x * cosine + y * sine, -x * sine + y * cosine\n",
    ),
    (
        "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
        'OUTPUT_BULK_010_SHA256 = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA256 = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA256 = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
        "C13_C12_008_SHA256, C13_C11_009_SHA256, OUTPUT_BULK_010_SHA256}",
        "C13_C12_008_SHA256, C13_C11_009_SHA256, OUTPUT_BULK_010_SHA256, J2_PLACEMENT_ECO_003_SHA256}",
    ),
    (
        "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
        "        expected = (\n            ECO_002_POSES[ref]\n",
        "        expected = (\n"
        "            J2_PLACEMENT_ECO_003_POSES[ref]\n"
        "            if board_sha256 == J2_PLACEMENT_ECO_003_SHA256 and ref in J2_PLACEMENT_ECO_003_POSES\n"
        "            else ECO_002_POSES[ref]\n",
    ),
    (
        "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
        "ECO_002_POSES = {\n",
        POSES_BLOCK + "ECO_002_POSES = {\n",
    ),
    (
        "tools/pcb_pwr_hot_loop_006_board.py",
        'SEMANTIC_SHA256 = "4da495603ca0c4ed2f7c4a3cb1197a133856408ac6f262ac976c1dab5667f687"\n',
        'SEMANTIC_SHA256 = "4da495603ca0c4ed2f7c4a3cb1197a133856408ac6f262ac976c1dab5667f687"\n'
        f'J2_PLACEMENT_ECO_003_SHA256 = "{ECO_003_SHA256}"\n'
        "\n\n"
        "def is_j2_placement_eco_003(payload: bytes) -> bool:\n"
        '    """Accepted ECO-003 successor of routing 010 (placement lines only)."""\n'
        "    if hashlib.sha256(payload).hexdigest() != J2_PLACEMENT_ECO_003_SHA256:\n"
        "        return False\n"
        "    import generate_pcb_pwr_j2_placement_eco_003_candidate_rev_a as eco_003\n"
        "\n"
        "    return payload == eco_003.candidate_bytes(OUTPUT_BULK_010.read_bytes())\n",
    ),
    (
        "tools/pcb_pwr_hot_loop_006_board.py",
        "            or (hashlib.sha256(payload).hexdigest() == OUTPUT_BULK_010_SHA256\n"
        "                and payload == OUTPUT_BULK_010.read_bytes()))\n",
        "            or (hashlib.sha256(payload).hexdigest() == OUTPUT_BULK_010_SHA256\n"
        "                and payload == OUTPUT_BULK_010.read_bytes())\n"
        "            or is_j2_placement_eco_003(payload))\n",
    ),
    (
        "tools/pcb_pwr_hot_loop_006_board.py",
        "            or (hashlib.sha256(payload).hexdigest() == OUTPUT_BULK_010_SHA256\n"
        "                and payload == OUTPUT_BULK_010.read_bytes())):\n",
        "            or (hashlib.sha256(payload).hexdigest() == OUTPUT_BULK_010_SHA256\n"
        "                and payload == OUTPUT_BULK_010.read_bytes())\n"
        "            or is_j2_placement_eco_003(payload)):\n",
    ),
    (
        "tools/audit_pcb_pwr_vbat_sys_shunt_bulk_routing_007_application_rev_a.py",
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/audit_pcb_pwr_vbat_sys_shunt_bulk_routing_007_application_rev_a.py",
        "ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA}",
        "ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA}",
    ),
    (
        "tools/audit_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a.py",
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/audit_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a.py",
        "    assert board_sha in {CANDIDATE_SHA, SUCCESSOR_SHA, OUTPUT_BULK_010_SHA}\n",
        "    assert board_sha in {CANDIDATE_SHA, SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA}\n",
    ),
    (
        "tools/audit_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a.py",
        "if board_sha in {SUCCESSOR_SHA, OUTPUT_BULK_010_SHA} else BOARD)",
        "if board_sha in {SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA} else BOARD)",
    ),
    (
        "tools/run_pcb_pwr_hot_loop_006_historical_candidate_audit.py",
        "    assert active_sha in {SHUNT_BULK_007_SHA256, C13_C12_008_SHA256, C13_C11_009_SHA256, OUTPUT_BULK_010_SHA256}\n",
        "    if is_j2_placement_eco_003(payload):\n"
        "        payload, active_sha = OUTPUT_BULK_010.read_bytes(), OUTPUT_BULK_010_SHA256\n"
        "    assert active_sha in {SHUNT_BULK_007_SHA256, C13_C12_008_SHA256, C13_C11_009_SHA256, OUTPUT_BULK_010_SHA256}\n",
    ),
    (
        "tools/run_pcb_pwr_hot_loop_006_historical_candidate_audit.py",
        "    OUTPUT_BULK_010_SHA256,\n",
        "    OUTPUT_BULK_010_SHA256,\n    is_j2_placement_eco_003,\n",
    ),
    (
        "tools/run_pcb_pwr_shunt_bulk_007_historical_audit.py",
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/run_pcb_pwr_shunt_bulk_007_historical_audit.py",
        "    assert active_sha in {CANDIDATE_SHA, SUCCESSOR_SHA, ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA}\n",
        "    assert active_sha in {CANDIDATE_SHA, SUCCESSOR_SHA, ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA,\n"
        "                          J2_PLACEMENT_ECO_003_SHA}\n",
    ),
    (
        "tools/run_pcb_pwr_c13_c12_008_historical_audit.py",
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/run_pcb_pwr_c13_c12_008_historical_audit.py",
        "in {CANDIDATE_SHA, ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA}\n",
        "in {CANDIDATE_SHA, ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA,\n"
        "                                                     J2_PLACEMENT_ECO_003_SHA}\n",
    ),
    (
        "tools/audit_pcb_pwr_layout_candidate_rev_a.py",
        'OUTPUT_BULK_010_SHA256 = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA256 = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA256 = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/audit_pcb_pwr_layout_candidate_rev_a.py",
        "ECO_002_POSES = {\n",
        POSES_BLOCK + "ECO_002_POSES = {\n",
    ),
    (
        "tools/audit_pcb_pwr_layout_candidate_rev_a.py",
        "        wanted_pose = (\n            ECO_002_POSES[ref]\n"
        "            if board_sha256 in {ECO_002_SHA256, HOT_LOOP_006_SHA256, SHUNT_BULK_007_SHA256, "
        "C13_C12_008_SHA256, C13_C11_009_SHA256, OUTPUT_BULK_010_SHA256} and ref in ECO_002_POSES\n",
        "        wanted_pose = (\n"
        "            J2_PLACEMENT_ECO_003_POSES[ref]\n"
        "            if board_sha256 == J2_PLACEMENT_ECO_003_SHA256 and ref in J2_PLACEMENT_ECO_003_POSES\n"
        "            else ECO_002_POSES[ref]\n"
        "            if board_sha256 in {ECO_002_SHA256, HOT_LOOP_006_SHA256, SHUNT_BULK_007_SHA256, "
        "C13_C12_008_SHA256, C13_C11_009_SHA256, OUTPUT_BULK_010_SHA256, J2_PLACEMENT_ECO_003_SHA256} "
        "and ref in ECO_002_POSES\n",
    ),
    (
        "tools/generate_pcb_pwr_buck_input_hot_loop_routing_006_application_rev_a.py",
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/generate_pcb_pwr_buck_input_hot_loop_routing_006_application_rev_a.py",
        "        assert digest(BOARD) in {CANDIDATE_SHA, SHUNT_BULK_007_SHA, C13_C12_008_SHA, C13_C11_009_SHA, OUTPUT_BULK_010_SHA}, \\\n",
        "        assert digest(BOARD) in {CANDIDATE_SHA, SHUNT_BULK_007_SHA, C13_C12_008_SHA, C13_C11_009_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA}, \\\n",
    ),
    (
        "tools/generate_pcb_pwr_vbat_sys_shunt_bulk_routing_007_application_rev_a.py",
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/generate_pcb_pwr_vbat_sys_shunt_bulk_routing_007_application_rev_a.py",
        "        assert digest(BOARD) in {CANDIDATE_SHA, SUCCESSOR_SHA, ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA}, \\\n",
        "        assert digest(BOARD) in {CANDIDATE_SHA, SUCCESSOR_SHA, ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA}, \\\n",
    ),
    (
        "tools/generate_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a.py",
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n',
        'OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"\n'
        f'J2_PLACEMENT_ECO_003_SHA = "{ECO_003_SHA256}"\n',
    ),
    (
        "tools/generate_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a.py",
        "        assert digest(BOARD) in {CANDIDATE_SHA, SUCCESSOR_SHA, OUTPUT_BULK_010_SHA}, \\\n",
        "        assert digest(BOARD) in {CANDIDATE_SHA, SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA}, \\\n",
    ),
    (
        "tools/generate_pcb_pwr_3v8_output_bulk_routing_010_application_rev_a.py",
        '        assert BOARD.read_bytes() == payload, "authoritative PCB-PWR is not exact accepted 010"\n',
        "        from pcb_pwr_hot_loop_006_board import is_j2_placement_eco_003\n"
        "\n"
        "        active = BOARD.read_bytes()\n"
        "        assert active == payload or is_j2_placement_eco_003(active), \\\n"
        '            "authoritative PCB-PWR is not exact accepted 010 or its ECO-003 successor"\n',
    ),
    (
        "tools/audit_pcb_pwr_3v8_output_bulk_routing_010_application_rev_a.py",
        'SEMANTIC_SHA = "d6810b6ea293bfd931f09e73ff64698d18d0a64b465db7b71c712f64a36b2980"\n',
        'SEMANTIC_SHA = "d6810b6ea293bfd931f09e73ff64698d18d0a64b465db7b71c712f64a36b2980"\n'
        "\n"
        "# After the accepted J2 placement ECO-003 the authoritative board is the exact\n"
        "# placement-only successor; replay the 010 application on its committed candidate.\n"
        "from pcb_pwr_hot_loop_006_board import is_j2_placement_eco_003  # noqa: E402\n"
        "\n"
        "if is_j2_placement_eco_003(BOARD.read_bytes()):\n"
        "    BOARD = CANDIDATE\n",
    ),
]


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def replace_json_values(text: str, anchor: str, old: dict, new: dict) -> str:
    """Replace changed scalar values inside the block that starts at anchor,
    preserving the file's own formatting."""
    start = text.index(anchor)
    for key, value in new.items():
        if old.get(key) == value:
            continue
        before = f'"{key}": {json.dumps(old[key])}'
        after = f'"{key}": {json.dumps(value)}'
        position = text.index(before, start)
        text = text[:position] + after + text[position + len(before):]
    return text


def run_audit(script: str, *args: str) -> dict:
    output = Path(subprocess.check_output(["mktemp"], text=True).strip())
    subprocess.run([sys.executable, str(ROOT / "tools" / script), *args, "--output", str(output)],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(output.read_text(encoding="utf-8"))


def recompute_status() -> None:
    import audit_pcb_pwr_placement_clearance_rev_a as clearance

    text = STATUS.read_text(encoding="utf-8")
    status = json.loads(text)
    report = run_audit("audit_pcb_pwr_placement_clearance_rev_a.py", "--no-status-check")
    text = replace_json_values(
        text, '"placement_clearance": {',
        status["native_layout"]["placement_clearance"]["control"], clearance.expected_control(report))
    routing = run_audit("audit_pcb_pwr_routing_authority_rev_a.py", "--no-status-check")
    text = replace_json_values(
        text, '"pre_route_constraints": {',
        status["pre_route_constraints"]["control"],
        {"board_semantic_sha256": routing["board"]["semantic_sha256"]})
    STATUS.write_text(text, encoding="utf-8")


def apply() -> None:
    require(sha256_bytes(BOARD.read_bytes()) == OUTPUT_BULK_010_SHA256,
            "authoritative board is not the routing-010 base; ECO-003 is not applicable")
    BOARD.write_bytes(candidate.candidate_bytes(BOARD.read_bytes()))
    for relative, old, new in TOOL_EDITS:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        require(text.count(old) == 1, f"{relative}: edit anchor drift")
        path.write_text(text.replace(old, new), encoding="utf-8")
    recompute_status()


def check() -> None:
    require(sha256_bytes(BOARD.read_bytes()) == ECO_003_SHA256, "ECO-003 is not applied to the board")
    for relative, _old, new in TOOL_EDITS:
        require(new in (ROOT / relative).read_text(encoding="utf-8"), f"{relative}: ECO-003 edit missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
        print(f"PCB-PWR J2 placement ECO-003 application: PRESENT {ECO_003_SHA256}")
    else:
        apply()
        print(f"PCB-PWR J2 placement ECO-003 applied: {ECO_003_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

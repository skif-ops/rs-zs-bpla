#!/usr/bin/env python3
"""Bring the PCB-MAIN routing-constraint control to the applied inner reroute 003 board. Run by ci-apply.

After the 003 application the routing-authority audit still checked the 003 predecessor. The routing authority
itself (hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv/.md) needs no change: it states constraints (GND_DIGITAL
reference, continuous local reference, return via at each layer change, length groups), not layers of individual
runs, and 003 routes the OctoSPI/SDIO/EN_MODEM nets within them. This tool:

1. keeps the capture status as the earlier sub-gates left it as
   hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/PCB_MAIN_CAPTURE_STATUS_PRE_003_ROUTING_REV_A.json;
2. points tools/audit_pcb_main_routing_authority_rev_a.py at the current board: with 003 applied it requires the
   003 board hash, 1069 track items, 10 zones and the 003 application record, and its status control carries
   inner_reroute_003_subgate;
3. updates routing_constraint_control in hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json accordingly (board hash,
   trace_items, copper_zones, inner_reroute_003_subgate) and nothing else;
4. lets the six application audits that compare capture-status fields with their own application read the
   pre-update status through tools/pcb_main_lineage_rev_a.historical_status();
5. regenerates the capture manifest with tools/generate_pcb_main_schematic_rev_a.py (only the status hash changes)
   and runs the Python PCB-MAIN CI chain; any failure aborts.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _bootstrap() -> None:
    """kiutils / numpy as pcb-native.yml installs them for these audits (a fresh ci-apply runner has kiutils only)."""
    try:
        import kiutils  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "--break-system-packages", "kiutils==1.4.8", "numpy==2.0.2"], check=True)


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
SNAPSHOT = ROOT / "hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/PCB_MAIN_CAPTURE_STATUS_PRE_003_ROUTING_REV_A.json"
MANIFEST = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN_capture_manifest.json"
ROUTING_AUDIT = "tools/audit_pcb_main_routing_authority_rev_a.py"
CHAIN = ROOT / "hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/CI_CHAIN_COMMANDS.txt"
PRE_STATUS_SHA256 = "1d8f81d09a93a9e1910faa7ee24130e634e46600c4033daef9ca3bdea2fd30ab"
PRE_BOARD_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
BOARD_003_SHA256 = "30c6c93e5afbbc0888ed7c7e8693af6c6f0c7df8f5c4525e02c6d5a4c47b8739"
SUBGATE = '"inner_reroute_003_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PASS"'
STATUS_READERS = [
    "tools/audit_pcb_main_octospi_r8_eco_application_rev_a.py",
    "tools/audit_pcb_main_rf_p0_application_rev_a.py",
    "tools/audit_pcb_main_usb_cell_fixture_routing_001_application_rev_a.py",
    "tools/audit_pcb_main_usb_cell_modem_routing_001_application_rev_a.py",
    "tools/audit_pcb_main_usb_placement_eco_001_application_rev_a.py",
    "tools/audit_pcb_main_usb_source_routing_001_application_rev_a.py",
]
ALLOWED_CHANGES = {"hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json",
                   "hardware/kicad/native/PCB-MAIN/PCB-MAIN_capture_manifest.json", ROUTING_AUDIT, *STATUS_READERS}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text: str, old: str, new: str, where: str) -> str:
    require(text.count(old) == 1, f"{where}: expected exactly one match for {old[:70]!r}")
    return text.replace(old, new)


def edit_routing_audit() -> None:
    path = ROOT / ROUTING_AUDIT
    t = path.read_text(encoding="utf-8")
    w = ROUTING_AUDIT
    t = once(t, "DEFAULT_BOARD = _lineage.historical_board()\n",
             'DEFAULT_BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"  # current board (003 checked below)\n', w)
    t = once(t, 'DEFAULT_AUTHORITY = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"\n',
             'DEFAULT_AUTHORITY = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"\n'
             'INNER_003 = _lineage.inner_reroute_003_applied()\n', w)
    t = once(t, """    authority_sha256: str,
) -> dict[str, Any]:
    return {""", """    authority_sha256: str,
) -> dict[str, Any]:
    control = {""", w)
    t = once(t, """        "trace_items": 1023,
        "copper_zones": 8,
        "ground_domain_subgate\"""", """        "trace_items": 1069 if INNER_003 else 1023,
        "copper_zones": 10 if INNER_003 else 8,
        "ground_domain_subgate\"""", w)
    t = once(t, """        "routing_complete": False,
        "manufacturing_release": False,
    }


def audit(""", """        "routing_complete": False,
        "manufacturing_release": False,
    }
    if INNER_003:
        # accepted inner reroute 003: OCTOSPI/SDIO/EN_MODEM on F.Cu/B.Cu over GND_DIGITAL, In4 split, R9-R11 row
        control["inner_reroute_003_subgate"] = "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PASS"
    return control


def audit(""", w)
    t = once(t, """    require(trace_items == 1023 and copper_zones == 8,
            "authoritative board does not contain the accepted RF remediations")
    board_digest = sha256(board_path)
    require(board_digest == ACTIVE_BOARD_SHA256,
            "authoritative board SHA-256 differs from the accepted USB placement successor")""",
             """    board_digest = sha256(board_path)
    if INNER_003:
        # the 003 application audit proves the 003 delta; the earlier sub-gates below are checked on its predecessor
        inner = json.loads(_lineage.INNER_003_APPLICATION.read_text(encoding="utf-8"))
        require(trace_items == 1069 and copper_zones == 10
                and board_digest == _lineage.INNER_003_BOARD_SHA256
                and inner.get("applied", {}).get("predecessor_board_sha256") == ACTIVE_BOARD_SHA256
                and inner.get("routing_complete") is False and inner.get("manufacturing_release") is False,
                "authoritative board is not the accepted inner reroute 003 successor")
    else:
        require(trace_items == 1023 and copper_zones == 8,
                "authoritative board does not contain the accepted RF remediations")
        require(board_digest == ACTIVE_BOARD_SHA256,
                "authoritative board SHA-256 differs from the accepted USB placement successor")""", w)
    path.write_text(t, encoding="utf-8")


def edit_status() -> None:
    text = STATUS.read_text(encoding="utf-8")
    start = text.index('"routing_constraint_control"')
    end = text.index("\n    }", start)
    block = text[start:end]
    block = once(block, f'"board_sha256": "{PRE_BOARD_SHA256}"', f'"board_sha256": "{BOARD_003_SHA256}"', "status")
    block = once(block, '"trace_items": 1023', '"trace_items": 1069', "status")
    block = once(block, '"copper_zones": 8', '"copper_zones": 10', "status")
    m = re.search(r'\n(\s*)"usb_cell_fixture_routing_subgate": "[^"]*"', block)
    require(m is not None, "status: usb_cell_fixture_routing_subgate not found")
    block = block[:m.end()] + f",\n{m.group(1)}{SUBGATE}" + block[m.end():]
    STATUS.write_text(text[:start] + block + text[end:], encoding="utf-8")


def edit_status_readers() -> None:
    for rel in STATUS_READERS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        require("import pcb_main_lineage_rev_a as _lineage" in text, f"{rel}: lineage import missing")
        path.write_text(once(text, 'STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"\n',
                             "STATUS = _lineage.historical_status()\n", rel), encoding="utf-8")


def git_lines(*args: str) -> list[str]:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
    return done.stdout.split()


def run_chain() -> list[str]:
    Path("/tmp/o").mkdir(parents=True, exist_ok=True)
    before = set(git_lines("ls-files", "--others", "--exclude-standard"))
    failures = []
    for command in CHAIN.read_text(encoding="utf-8").split("\n"):
        command = command.strip()
        if not command or command.startswith("#"):
            continue
        done = subprocess.run([sys.executable] + command.split(), cwd=ROOT, capture_output=True, text=True)
        if done.returncode:
            tail = (done.stdout + done.stderr).strip().splitlines()[-1:] or [""]
            failures.append(f"{command}: {tail[0][:200]}")
    for rel in sorted(set(git_lines("ls-files", "--others", "--exclude-standard")) - before):
        (ROOT / rel).unlink()
    return failures


def main() -> int:
    _bootstrap()
    sys.path.insert(0, str(ROOT / "tools"))
    import pcb_main_lineage_rev_a as lineage
    require(lineage.inner_reroute_003_applied(), "PCB-MAIN is not in the applied 003 state")
    if "--check" in sys.argv[1:]:
        require(sha256(SNAPSHOT) == PRE_STATUS_SHA256 and SUBGATE in STATUS.read_text(encoding="utf-8"),
                "routing-constraint control is not at the 003 state")
    else:
        require(sha256(STATUS) == PRE_STATUS_SHA256, "capture status is not the pre-003 routing state")
        require(hasattr(lineage, "historical_status") and lineage.PRE_003_STATUS_SHA256 == PRE_STATUS_SHA256,
                "lineage module without the capture-status snapshot")
        shutil.copyfile(STATUS, SNAPSHOT)
        edit_routing_audit()
        edit_status()
        edit_status_readers()
        subprocess.run([sys.executable, "tools/generate_pcb_main_schematic_rev_a.py"], cwd=ROOT, check=True,
                       capture_output=True, text=True)
        changed = set(git_lines("diff", "--name-only"))
        require(changed == ALLOWED_CHANGES, f"unexpected changes: {sorted(changed ^ ALLOWED_CHANGES)}")
    failures = run_chain()
    require(not failures, "PCB-MAIN chain fails:\n" + "\n".join(failures))
    print(f"PCB-MAIN routing-constraint control at 003: PASS (status {sha256(STATUS)}, manifest {sha256(MANIFEST)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

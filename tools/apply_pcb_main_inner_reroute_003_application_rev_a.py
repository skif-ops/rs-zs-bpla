#!/usr/bin/env python3
"""Apply the accepted PCB-MAIN inner reroute 003 (decision ACCEPT_INNER_REROUTE_003). Run by ci-apply.

1. Pre-state: the authoritative board is the cellular USB fixture 001 candidate (2dd9bdf2...), the placement
   manifest is df7cdbfc..., the 003 candidate is 30c6c93e... and its SUMMARY.json matches it.
2. The pre-003 placement manifest is kept as hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/
   PCB_MAIN_PLACEMENT_REPACK_PRE_003_REV_A.csv; the 003 candidate becomes the authoritative board (byte copy); the
   R9/R10/R11 rows of the manifest take the 003 poses (tools/pcb_main_inner_reroute_003_rev_a.RESISTOR_MOVES).
3. Audit chain: the audits and generators of the earlier sub-gates read the exact predecessor through
   tools/pcb_main_lineage_rev_a.py (historical_board / historical_placement); the layout audit accepts the applied
   003 copper inventory; the footprint materialization binds the 003 board hash. Every edit is an exact
   replacement that must match once.
4. The whole Python PCB-MAIN chain run by CI is executed; any failure aborts the application.
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
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
PLACEMENT = ROOT / "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv"
CAND_DIR = ROOT / "hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003"
CANDIDATE = CAND_DIR / "PCB-MAIN_INNER_REROUTE_003_CANDIDATE_REV_A.kicad_pcb"
PRE_PLACEMENT = CAND_DIR / "PCB_MAIN_PLACEMENT_REPACK_PRE_003_REV_A.csv"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_INNER_REROUTE_003_APPLICATION_REV_A.json"
PRE_BOARD_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
PRE_PLACEMENT_SHA256 = "df7cdbfc2ac023d43ac040b14eb99440fc392d402793d5a3b03f2fd560af6a6f"
CANDIDATE_SHA256 = "30c6c93e5afbbc0888ed7c7e8693af6c6f0c7df8f5c4525e02c6d5a4c47b8739"
POSES = {"R9": ("60.5", "19.75", "90"), "R10": ("62", "19.75", "90"), "R11": ("63.5", "19.75", "90")}

NATIVE = "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
MANIFEST = "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv"
IMPORT = ('sys.path.insert(0, str(ROOT / "tools")) if str(ROOT / "tools") not in sys.path else None\n'
          'import pcb_main_lineage_rev_a as _lineage  # noqa: E402  (PCB-MAIN 003: earlier sub-gates read the predecessor)\n')
HIST_BOARD = {
    "tools/audit_pcb_main_ground_domain_routing_candidate_rev_a.py": "ACTIVE_BOARD",
    "tools/audit_pcb_main_mech_eco_002_rev_a.py": "BOARD",
    "tools/audit_pcb_main_octospi_r8_eco_application_rev_a.py": "BOARD",
    "tools/audit_pcb_main_rf_p0_application_rev_a.py": "BOARD",
    "tools/audit_pcb_main_rf_p0_candidate_rev_a.py": "ACTIVE",
    "tools/audit_pcb_main_rf_remediation_application_rev_a.py": "BOARD",
    "tools/audit_pcb_main_rf_return_001_candidate_rev_a.py": "ACTIVE",
    "tools/audit_pcb_main_routing_authority_rev_a.py": "DEFAULT_BOARD",
    "tools/audit_pcb_main_signal_hard_nets_candidate_rev_a.py": "ACTIVE",
    "tools/audit_pcb_main_usb_cell_fixture_routing_001_application_rev_a.py": "BOARD",
    "tools/audit_pcb_main_usb_cell_fixture_routing_candidate_rev_a.py": "ACTIVE",
    "tools/audit_pcb_main_usb_cell_modem_routing_001_application_rev_a.py": "BOARD",
    "tools/audit_pcb_main_usb_cell_modem_routing_candidate_rev_a.py": "ACTIVE",
    "tools/audit_pcb_main_usb_placement_eco_001_application_rev_a.py": "BOARD",
    "tools/audit_pcb_main_usb_placement_eco_001_candidate_rev_a.py": "ACTIVE",
    "tools/audit_pcb_main_usb_source_routing_001_application_rev_a.py": "BOARD",
    "tools/audit_pcb_main_usb_source_routing_candidate_rev_a.py": "ACTIVE",
    "tools/generate_pcb_main_placement_repack_rev_a.py": "BOARD",
    "tools/generate_pcb_main_usb_cell_fixture_routing_001_application_rev_a.py": "BOARD",
    "tools/generate_pcb_main_usb_cell_fixture_routing_candidate_rev_a.py": "SOURCE",
    "tools/generate_pcb_main_usb_cell_modem_routing_001_application_rev_a.py": "BOARD",
    "tools/generate_pcb_main_usb_cell_modem_routing_candidate_rev_a.py": "SOURCE",
    "tools/generate_pcb_main_usb_source_routing_candidate_rev_a.py": "SOURCE",
    "tools/audit_pcb_main_placement_clearance_rev_a.py": "DEFAULT_BOARD",
}
HIST_PLACEMENT = [
    "tools/audit_pcb_main_mech_eco_002_rev_a.py",
    "tools/audit_pcb_main_octospi_r8_eco_application_rev_a.py",
    "tools/audit_pcb_main_usb_placement_eco_001_application_rev_a.py",
    "tools/generate_pcb_main_placement_repack_rev_a.py",
    "tools/audit_pcb_main_assembler_dfm_stencil_request_rev_a.py",
    "tools/audit_pcb_main_stackup_impedance_request_rev_a.py",
]
LAYOUT = "tools/audit_pcb_main_layout_candidate_rev_a.py"
MATERIALIZE = "tools/materialize_pcb_main_manufacturer_footprints_rev_a.py"
CHAIN = ROOT / "hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/CI_CHAIN_COMMANDS.txt"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text: str, old: str, new: str, where: str) -> str:
    require(text.count(old) == 1, f"{where}: expected exactly one match for {old[:70]!r}")
    return text.replace(old, new)


def with_import(text: str, where: str) -> str:
    if "import pcb_main_lineage_rev_a as _lineage" in text:
        return text
    m = re.search(r"^ROOT = .*\n", text, re.M)
    require(m is not None, f"{where}: ROOT definition not found")
    text = text[:m.end()] + IMPORT + text[m.end():]
    if not re.search(r"^import sys$", text, re.M):
        text = once(text, "from pathlib import Path\n", "import sys\nfrom pathlib import Path\n", where) \
            if text.count("from pathlib import Path\n") == 1 else text
        require(re.search(r"^import sys$", text, re.M) is not None, f"{where}: cannot add import sys")
    return text


def edit_chain() -> list[str]:
    edited = []
    for rel in sorted(set(HIST_BOARD) | set(HIST_PLACEMENT)):
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        if rel in HIST_BOARD:
            var = HIST_BOARD[rel]
            new = f"{var} = _lineage.historical_board()\n"
            if rel.endswith("placement_clearance_rev_a.py"):
                new = f"{var} = _lineage.historical_board()  # the 003 board itself: --board, and the 003 application audit\n"
            text = once(text, f'{var} = ROOT / "{NATIVE}"\n', new, rel)
        if rel in HIST_PLACEMENT:
            text = once(text, f'PLACEMENT = ROOT / "{MANIFEST}"\n', "PLACEMENT = _lineage.historical_placement()\n", rel)
        path.write_text(with_import(text, rel), encoding="utf-8")
        edited.append(rel)
    path = ROOT / LAYOUT
    text = path.read_text(encoding="utf-8")
    text = once(text, '''    require(hashlib.sha256(PCB.read_bytes()).hexdigest() ==
            "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273" and''',
                '''    require(((hashlib.sha256(PCB.read_bytes()).hexdigest() ==
              "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273" and
              len(board.traceItems) == 1023 and len(board.zones) == 8) or
             # accepted inner reroute 003: OctoSPI/SDIO/EN_MODEM off In2/In3, In4 split, R9-R11 row
             (_lineage.inner_reroute_003_applied() and
              len(board.traceItems) == 1069 and len(board.zones) == 10)) and''', LAYOUT)
    text = once(text, '''            len(board.traceItems) == 1023 and len(board.zones) == 8,
            "authoritative board accepted routing-subgate application drift")''',
                '''            True,
            "authoritative board accepted routing-subgate application drift")''', LAYOUT)
    path.write_text(with_import(text, LAYOUT), encoding="utf-8")
    edited.append(LAYOUT)
    path = ROOT / MATERIALIZE
    text = path.read_text(encoding="utf-8")
    text = once(text, f'ACTIVE_BOARD_SHA256 = "{PRE_BOARD_SHA256}"',
                f'ACTIVE_BOARD_SHA256 = "{CANDIDATE_SHA256}"  # accepted inner reroute 003 (footprints unchanged)',
                MATERIALIZE)
    path.write_text(text, encoding="utf-8")
    edited.append(MATERIALIZE)
    return edited


def update_manifest() -> None:
    lines = PLACEMENT.read_text(encoding="utf-8").split("\n")
    done = set()
    for i, line in enumerate(lines):
        fields = line.split(",")
        if fields and fields[0] in POSES:
            fields[1:4] = POSES[fields[0]]
            lines[i] = ",".join(fields)
            done.add(fields[0])
    require(done == set(POSES), f"placement rows not found: {set(POSES) - done}")
    PLACEMENT.write_text("\n".join(lines), encoding="utf-8")


def untracked() -> set[str]:
    done = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT,
                          capture_output=True, text=True, check=True)
    return set(done.stdout.split())


def run_chain() -> list[str]:
    Path("/tmp/o").mkdir(parents=True, exist_ok=True)
    failures = []
    for command in CHAIN.read_text(encoding="utf-8").split("\n"):
        command = command.strip()
        if not command or command.startswith("#"):
            continue
        done = subprocess.run([sys.executable] + command.split(), cwd=ROOT, capture_output=True, text=True)
        if done.returncode:
            tail = (done.stdout + done.stderr).strip().splitlines()[-1:] or [""]
            failures.append(f"{command}: {tail[0][:200]}")
    return failures


def check() -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    import pcb_main_lineage_rev_a as lineage
    require(lineage.inner_reroute_003_applied(), "PCB-MAIN is not in the applied 003 state")
    before = untracked()
    failures = run_chain()
    for rel in sorted(untracked() - before):
        (ROOT / rel).unlink()
    require(not failures, "PCB-MAIN chain fails in the applied 003 state:\n" + "\n".join(failures))
    print(f"PCB-MAIN inner reroute 003 application: PASS (board {sha256(BOARD)}, chain PASS)")
    return 0


def main() -> int:
    _bootstrap()
    if "--check" in sys.argv[1:]:
        return check()
    require(APPLICATION.is_file(), "003 application record is missing")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "003 candidate drift")
    require(sha256(BOARD) == PRE_BOARD_SHA256, "authoritative PCB-MAIN is not the 003 predecessor")
    require(sha256(PLACEMENT) == PRE_PLACEMENT_SHA256, "placement manifest is not the 003 predecessor")
    shutil.copyfile(PLACEMENT, PRE_PLACEMENT)
    shutil.copyfile(CANDIDATE, BOARD)
    update_manifest()
    edited = edit_chain()
    before = untracked()
    failures = run_chain()
    for rel in sorted(untracked() - before):  # reports written by the chain tools are not part of the application
        (ROOT / rel).unlink()
    require(not failures, "PCB-MAIN chain fails after the 003 application:\n" + "\n".join(failures))
    print(f"PCB-MAIN inner reroute 003 applied: board {sha256(BOARD)}, manifest {sha256(PLACEMENT)}, "
          f"{len(edited)} chain files, chain PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

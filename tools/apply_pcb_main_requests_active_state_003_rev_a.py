#!/usr/bin/env python3
"""Record the applied PCB-MAIN inner reroute 003 as the active board in the two closed supplier requests.

The assembler DFM/stencil request and the stackup/impedance request are closed by the accepted EVT process
baseline and stay bound to their historical request basis (source_binding unchanged). Each also carries an
informational `active_native_routing_state` and a sentence naming the active board, still at the 003 predecessor
(2dd9bdf2..., 1023 track items, 8 zones). This tool updates both to the 003 board and records the controlled review
the assembler request requires for any board-byte change:

- U2, U25, U26 and U9 (the request's subject: lands, mask, paste, stencil) have byte-identical footprint blocks in
  the 003 board and its predecessor; 003 moves only R9/R10/R11 (0402, 22 ohm). Checked here from the boards.
- The 12 rerouted nets are NOT_CONTROLLED_IMPEDANCE in the routing authority; 003 changes neither stackup nor
  layer count. Checked here from the routing authority.

Then the two request audits and the Python PCB-MAIN CI chain run. --check verifies the result.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _bootstrap() -> None:
    try:
        import kiutils  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "--break-system-packages", "kiutils==1.4.8", "numpy==2.0.2"], check=True)


ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "hardware/reviews"
ASM_JSON = REVIEWS / "PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.json"
ASM_MD = REVIEWS / "PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.md"
STK_JSON = REVIEWS / "PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json"
STK_MD = REVIEWS / "PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.md"
ROUTING = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"
CHAIN = ROOT / "hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/CI_CHAIN_COMMANDS.txt"
OLD = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
NEW = "30c6c93e5afbbc0888ed7c7e8693af6c6f0c7df8f5c4525e02c6d5a4c47b8739"
SUBJECT = ["U2", "U25", "U26", "U9"]
NETS = ["NOR_CLK_U1", "NOR_IO0_U1", "NOR_IO1_U1", "NOR_IO2_U1", "NOR_CLK_U2", "NOR_IO0_U2", "NOR_IO1_U2",
        "NOR_IO2_U2", "NOR_IO3_U2", "SD_D2_U1", "EN_MODEM", "NOR_NCS_U2"]
STATE = {"board": "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb", "board_sha256": NEW, "trace_items": 1069,
         "copper_zones": 10, "routing_complete": False, "manufacturing_release": False}
ASM_OLD = f"""The bound SHA above is the historical pre-route request basis. The active native
successor is SHA-256
`{OLD}`
with 1023 trace items and eight copper zones; routing remains incomplete. No
Gerber, paste Gerber, centroid or assembly drawing is released by this packet.
Any footprint or board-byte change requires a new controlled review.
"""
ASM_NEW = f"""The bound SHA above is the historical pre-route request basis. The active native
board is SHA-256
`{NEW}`
(PCB-MAIN inner reroute 003, accepted and applied 2026-09-25) with 1069 trace items
and ten copper zones; routing remains incomplete. No Gerber, paste Gerber, centroid
or assembly drawing is released by this packet; centroid and paste come from
controlled CAM of the native board after DRC. Any footprint or board-byte change
requires a new controlled review.

Controlled review of 003 for this subgate: the `U2`, `U25`, `U26` and `U9`
footprint blocks (position, rotation, lands, mask, paste, nets) are byte-identical
in the 003 board and its predecessor
`{OLD}`;
003 moves only `R9`, `R10` and `R11` (0402, 22 ohm) and reroutes non-impedance-
controlled OctoSPI/SDIO/EN_MODEM runs. The accepted process baseline and the
closed response register are unaffected.
"""
STK_OLD = f"""pre-route candidate. The active native successor is SHA-256
`{OLD}`
with 1023 trace items and eight copper zones; routing remains incomplete. No
vendor may treat this historical packet or the active board as released
fabrication data.
"""
STK_NEW = f"""pre-route candidate. The active native board is SHA-256
`{NEW}`
(PCB-MAIN inner reroute 003, accepted and applied 2026-09-25) with 1069 trace items
and ten copper zones; routing remains incomplete. 003 changes neither the stackup
nor the layer count, and none of its rerouted nets is impedance-controlled. No
vendor may treat this historical packet or the active board as released
fabrication data.
"""


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def once(text: str, old: str, new: str, where: str) -> str:
    require(text.count(old) == 1, f"{where}: expected exactly one match")
    return text.replace(old, new)


def controlled_review() -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    import pcb_main_lineage_rev_a as lineage
    require(lineage.inner_reroute_003_applied(), "PCB-MAIN is not in the applied 003 state")
    pre = lineage.PRE_003_BOARD.read_text(encoding="utf-8")
    now = lineage.NATIVE_BOARD.read_text(encoding="utf-8")

    def block(text: str, ref: str) -> str:
        i = text.index(f'(fp_text reference "{ref}"')
        return text[text.rfind("\n  (footprint ", 0, i):text.index("\n  )", i)]

    for ref in SUBJECT:
        require(block(pre, ref) == block(now, ref), f"{ref}: footprint block changed by 003")
    rows = {r["Net_Name"]: r for r in csv.DictReader(ROUTING.open(encoding="utf-8"))}
    require(all(rows[n]["Impedance_Target"] == "NOT_CONTROLLED_IMPEDANCE" for n in NETS),
            "a rerouted 003 net is impedance-controlled")


def update_json(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    require(data["active_native_routing_state"]["board_sha256"] == OLD, f"{path.name}: unexpected active state")
    data["active_native_routing_state"] = STATE
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(commands: list[str]) -> list[str]:
    Path("/tmp/o").mkdir(parents=True, exist_ok=True)
    listing = ["git", "ls-files", "--others", "--exclude-standard"]
    before = set(subprocess.run(listing, cwd=ROOT, capture_output=True, text=True, check=True).stdout.split())
    failures = []
    for command in commands:
        done = subprocess.run([sys.executable] + command.split(), cwd=ROOT, capture_output=True, text=True)
        if done.returncode:
            tail = (done.stdout + done.stderr).strip().splitlines()[-1:] or [""]
            failures.append(f"{command}: {tail[0][:200]}")
    after = set(subprocess.run(listing, cwd=ROOT, capture_output=True, text=True, check=True).stdout.split())
    for rel in sorted(after - before):
        (ROOT / rel).unlink()
    return failures


def main() -> int:
    _bootstrap()
    controlled_review()
    if "--check" in sys.argv[1:]:
        for path in (ASM_JSON, STK_JSON):
            require(json.loads(path.read_text(encoding="utf-8"))["active_native_routing_state"] == STATE,
                    f"{path.name}: active state is not the 003 board")
        require(ASM_NEW in ASM_MD.read_text(encoding="utf-8") and STK_NEW in STK_MD.read_text(encoding="utf-8"),
                "request records do not name the 003 board")
    else:
        for path in (ASM_JSON, STK_JSON):
            original = path.read_text(encoding="utf-8")
            require(original == json.dumps(json.loads(original), indent=2, ensure_ascii=False) + "\n",
                    f"{path.name}: not in canonical JSON form")
            update_json(path)
        ASM_MD.write_text(once(ASM_MD.read_text(encoding="utf-8"), ASM_OLD, ASM_NEW, ASM_MD.name), encoding="utf-8")
        STK_MD.write_text(once(STK_MD.read_text(encoding="utf-8"), STK_OLD, STK_NEW, STK_MD.name), encoding="utf-8")
    commands = [c.strip() for c in CHAIN.read_text(encoding="utf-8").split("\n") if c.strip() and not c.startswith("#")]
    failures = run(commands)
    require(not failures, "PCB-MAIN chain fails:\n" + "\n".join(failures))
    print("PCB-MAIN supplier requests name the applied 003 board: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

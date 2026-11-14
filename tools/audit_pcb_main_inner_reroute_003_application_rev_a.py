#!/usr/bin/env python3
"""Audit the applied PCB-MAIN inner reroute 003 (the current authoritative board and placement manifest).

The earlier sub-gate audits read the 003 predecessor (tools/pcb_main_lineage_rev_a.py); this audit checks the
003 state itself: lineage predicate, application record, candidate evidence (SUMMARY.json: KiCad 9.0.9 DRC
without new violations, unchanged unconnected count), R9-R11 poses on the board, footprint set equal to the
predecessor, no digital run of the 12 rerouted nets left on In2/In3, and the strict placement-clearance audit of
the authoritative board.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pcb_main_lineage_rev_a as lineage  # noqa: E402

SUMMARY = ROOT / "hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/SUMMARY.json"
RECORD = ROOT / "hardware/reviews/PCB_MAIN_INNER_REROUTE_003_APPLICATION_REV_A.json"
NETS = ["NOR_CLK_U1", "NOR_IO0_U1", "NOR_IO1_U1", "NOR_IO2_U1", "NOR_CLK_U2", "NOR_IO0_U2", "NOR_IO1_U2",
        "NOR_IO2_U2", "NOR_IO3_U2", "SD_D2_U1", "EN_MODEM", "NOR_NCS_U2"]


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    from kiutils.board import Board

    require(lineage.inner_reroute_003_applied(), "authoritative PCB-MAIN is not the applied 003 state")
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    applied = record.get("applied", {})
    require(record.get("decision") == "ACCEPT_INNER_REROUTE_003"
            and applied.get("board_sha256") == lineage.INNER_003_BOARD_SHA256
            and applied.get("exact_candidate_byte_identity") is True
            and applied.get("predecessor_board_sha256") == lineage.PRE_003_BOARD_SHA256
            and applied.get("predecessor_placement_manifest_sha256") == lineage.PRE_003_PLACEMENT_SHA256
            and applied.get("placement_manifest_sha256") == lineage.sha256(lineage.PLACEMENT)
            and record.get("manufacturing_release") is False,
            "003 application record binding drift")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    drc = summary.get("drc", {})
    require(summary.get("candidate_sha256") == lineage.INNER_003_BOARD_SHA256
            and drc.get("new_errors") == 0 and drc.get("new_fingerprint_count") == 0
            and drc.get("candidate", {}).get("unconnected") == drc.get("base", {}).get("unconnected")
            and all(step.get("rc") == 0 for step in summary.get("steps", {}).values()),
            "003 candidate KiCad evidence drift")
    board = Board.from_file(str(lineage.NATIVE_BOARD), encoding="utf-8")
    before = Board.from_file(str(lineage.PRE_003_BOARD), encoding="utf-8")

    def reference(fp):
        for item in fp.graphicItems:
            if getattr(item, "type", None) == "reference":
                return item.text
        return fp.properties.get("Reference") if isinstance(fp.properties, dict) else None

    now = {reference(fp): fp for fp in board.footprints}
    old = {reference(fp): fp for fp in before.footprints}
    require(sorted(now) == sorted(old) and len(now) == 251, "footprint set differs from the predecessor")
    for ref, (x, y, rot) in lineage.INNER_003_POSES.items():
        p = now[ref].position
        require(abs(p.X - float(x)) < 1e-3 and abs(p.Y - float(y)) < 1e-3 and abs((p.angle or 0) - float(rot)) < 1e-3,
                f"{ref}: pose differs from the accepted 003 row")
    inner = [(t.net, t.layer) for t in board.traceItems if getattr(t, "layer", None) in ("In2.Cu", "In3.Cu")
             and any(n.number == t.net and n.name in NETS for n in board.nets)]
    require(not inner, f"rerouted nets still on In2/In3: {inner[:5]}")
    with tempfile.TemporaryDirectory() as tmp:
        done = subprocess.run([sys.executable, str(ROOT / "tools/audit_pcb_main_placement_clearance_rev_a.py"),
                               "--board", str(lineage.NATIVE_BOARD), "--no-status-check", "--strict",
                               "--output", str(Path(tmp) / "clearance.json")],
                              cwd=ROOT, capture_output=True, text=True)
        require(done.returncode == 0, "strict placement clearance of the 003 board fails: "
                + (done.stdout + done.stderr).strip()[-300:])
        clearance = json.loads((Path(tmp) / "clearance.json").read_text(encoding="utf-8"))["summary"]
    report = {"state": "PASS", "board_sha256": lineage.INNER_003_BOARD_SHA256,
              "placement_manifest_sha256": lineage.sha256(lineage.PLACEMENT),
              "footprints": len(now), "tracks": len(board.traceItems), "zones": len(board.zones),
              "placement_clearance": {k: clearance[k] for k in ("state", "confirmed_component_collisions",
                                                                "screening_component_collisions")}}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PCB-MAIN inner reroute 003 application: PASS {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

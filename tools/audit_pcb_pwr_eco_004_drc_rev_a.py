#!/usr/bin/env python3
"""Comparative KiCad DRC audit for PCB-PWR ECO-004 (U3/U4 LMR60440 land rule).

Inputs are two KiCad 9 DRC JSON reports of the same authoritative board: one
without and one with hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_dru.
PASS requires: exactly the four U3/U4 pad-2 to pad-6/7 clearance errors removed,
no new error or warning fingerprint, unconnected items unchanged. Since the
accepted autoroute 011 the same rule file also carries the U2 VSSOP-10 land
pattern rule; clearance errors between two pads of U2 may additionally vanish,
nothing else.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

EXPECTED_REMOVED = {
    ("clearance", ("Pad 2 [GND_PWR] of U3 on F.Cu", "Pad 6 [FB_3V8] of U3 on F.Cu")),
    ("clearance", ("Pad 2 [GND_PWR] of U3 on F.Cu", "Pad 7 [MODE_3V8] of U3 on F.Cu")),
    ("clearance", ("Pad 2 [GND_PWR] of U4 on F.Cu", "Pad 6 [3V3_DIGITAL] of U4 on F.Cu")),
    ("clearance", ("Pad 2 [GND_PWR] of U4 on F.Cu", "Pad 7 [MODE_3V3] of U4 on F.Cu")),
}


def is_u2_land_pattern(key) -> bool:
    """Clearance error between two pads of U2 (VSSOP-10 0.5 mm pitch)."""
    kind, items = key
    return (kind == "clearance" and len(items) == 2
            and all(item.startswith("Pad ") and " of U2 on " in item for item in items))


def fingerprints(path: Path) -> tuple[Counter, int]:
    report = json.loads(path.read_text(encoding="utf-8"))
    prints: Counter = Counter()
    for violation in report.get("violations", []):
        items = tuple(sorted(item.get("description", "") for item in violation.get("items", [])))
        prints[(violation["type"], items)] += 1
    return prints, len(report.get("unconnected_items", []))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-without-rule", type=Path, required=True)
    parser.add_argument("--drc-with-rule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base, base_unconnected = fingerprints(args.drc_without_rule)
    candidate, candidate_unconnected = fingerprints(args.drc_with_rule)
    removed = {key for key in base if candidate[key] < base[key]}
    added = sorted(str(key) for key in candidate if candidate[key] > base[key])
    blockers = []
    extra = removed - EXPECTED_REMOVED
    if not EXPECTED_REMOVED <= removed or not all(is_u2_land_pattern(key) for key in extra):
        blockers.append(f"removed fingerprints differ: {sorted(map(str, removed))}")
    if added:
        blockers.append(f"new fingerprints: {added}")
    if candidate_unconnected != base_unconnected:
        blockers.append(f"unconnected {base_unconnected} -> {candidate_unconnected}")
    result = {
        "schema": "dioneya-pcb-pwr-eco-004-drc-audit-v1",
        "status": "PASS_ECO_004_U3_U4_LAND_RULE" if not blockers else "BLOCKED",
        "violations": [sum(base.values()), sum(candidate.values())],
        "unconnected": [base_unconnected, candidate_unconnected],
        "removed": sorted(map(str, removed)),
        "removed_u2_land_pattern": sorted(map(str, extra)),
        "blockers": blockers,
        "manufacturing_release": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PCB-PWR ECO-004 DRC: {result['status']} violations {result['violations']} unconnected {result['unconnected']}")
    for blocker in blockers:
        print(f"  - {blocker}")
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())

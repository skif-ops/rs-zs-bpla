#!/usr/bin/env python3
"""Carry the PCB-PWR audit chain to the accepted ECO-005 successor of autoroute 011.

Applies hardware/reviews/PCB_PWR_ECO_005_AUDIT_CHAIN_REV_A.patch (pinned SHA-256) with git:
is_eco_005() in tools/pcb_pwr_hot_loop_006_board.py (exact committed candidate bytes), the
ECO-005 SHA-256 next to the 011 SHA-256 in every accepted-hash set of the 006-010 / ECO-003 /
011 audits, the NT2 180 deg pose override (the only placement change of ECO-005) and the
capture-status controls (semantic SHA-256 4c835eae..., 842 trace items, 33 zones).
Idempotent; --check verifies the patch is in place.
Record: hardware/reviews/PCB_PWR_ECO_005_REV_A.md.
Run by .github/workflows/ci-apply.yml before tools/apply_pcb_pwr_eco_005_rev_a.py.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "hardware/reviews/PCB_PWR_ECO_005_AUDIT_CHAIN_REV_A.patch"
PATCH_SHA256 = "95500e6a43407ef4cd82edd4621074cef3a0c632edb8365b1a1afac21aa7acd6"


def git_apply(*flags: str) -> bool:
    result = subprocess.run(["git", "apply", *flags, str(PATCH)], cwd=ROOT, capture_output=True, text=True)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    assert hashlib.sha256(PATCH.read_bytes()).hexdigest() == PATCH_SHA256, "audit-chain patch SHA-256 drift"
    applied = git_apply("--reverse", "--check")
    if args.check:
        assert applied, "ECO-005 audit-chain patch is not applied"
        print("PCB-PWR ECO-005 audit chain: PASS")
        return 0
    if applied:
        print("PCB-PWR ECO-005 audit chain: already applied")
        return 0
    assert git_apply("--check"), "ECO-005 audit-chain patch does not apply cleanly"
    assert git_apply(), "git apply failed"
    print("PCB-PWR ECO-005 audit chain: applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

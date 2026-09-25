#!/usr/bin/env python3
"""Carry the PCB-PWR audit chain to the accepted autoroute 011 successor.

Applies hardware/reviews/PCB_PWR_AUTOROUTE_011_AUDIT_CHAIN_REV_A.patch (pinned
SHA-256) with git: the successor recognition in tools/pcb_pwr_hot_loop_006_board.py,
the 011 SHA-256 in the accepted-hash sets of the 006-010 / ECO-003 audits, the
copper-count bypass for the exact 011 board, the ECO-004 DRC allowance for the U2
land-pattern rule and the capture-status controls (semantic SHA-256, 873 trace
items, 33 zones). Idempotent; --check verifies the patch is in place.
Record: hardware/reviews/PCB_PWR_AUTOROUTE_011_APPLICATION_REV_A.md.
Run by .github/workflows/ci-apply.yml before tools/apply_pcb_pwr_autoroute_011_rev_a.py.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "hardware/reviews/PCB_PWR_AUTOROUTE_011_AUDIT_CHAIN_REV_A.patch"
PATCH_SHA256 = "2565981dea77c36464dbf7ebd0dff59f5587c186bccef34c7cf56cb0d62ae5df"


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
        assert applied, "autoroute 011 audit-chain patch is not applied"
        print("PCB-PWR autoroute 011 audit chain: PASS")
        return 0
    if applied:
        print("PCB-PWR autoroute 011 audit chain: already applied")
        return 0
    assert git_apply("--check"), "autoroute 011 audit-chain patch does not apply cleanly"
    assert git_apply(), "git apply failed"
    print("PCB-PWR autoroute 011 audit chain: applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

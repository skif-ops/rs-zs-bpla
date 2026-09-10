#!/usr/bin/env python3
"""Fail when EVT-MB deliverables or runtime identity leak into EVT-PRE-20."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_BRANCH = "evt-pre-20"
FORBIDDEN_TOKENS = (b"evt-mb", b"evt_mb")

# These files define or document the separation rule, so they may name the other
# branch. No implementation, release or deployment file is allowed this exception.
MENTION_ALLOWLIST = {
    "BRANCH_SCOPE.md",
    "BRANCHING.md",
    "README.md",
    "config/EVT_PRE_20_BASELINE.yaml",
    "docs/DECISION_LOG.csv",
    "hardware/EVT_PRE_20_HARDWARE_ARCHITECTURE_v0_1.md",
    "hardware/PCB_DOUBLE_REVIEW_GATE.md",
    "mechanics/README.md",
    "releases/RELEASE_INDEX.md",
    "releases/evt/v0.7/README.md",
    "server/EVT_PRE_20_RELEASE_AUDIT.md",
    "server/RELEASE_NOTES_EVT_PRE_20_0_1.md",
    "tests/EVT_MASTER_PLAN.md",
    "tools/audit_evt_branch_isolation.py",
}

REQUIRED_PATHS = {
    "BRANCH_SCOPE.md",
    "config/EVT_PRE_20_BASELINE.yaml",
    "docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv",
    "server/RELEASE_NOTES_EVT_PRE_20_0_1.md",
}

IDENTITY_RULES = {
    "README.md": ("EVT-PRE-20",),
    "config/EVT_PRE_20_BASELINE.yaml": (
        "configuration_id: EVT-PRE-20",
        "working_branch: evt-pre-20",
        "forbidden_direct_sources: [evt-mb]",
        "allowed_promotion_targets: [develop, main]",
    ),
    "server/config.py": ('app_version: str = "1.2.0-evt-pre-20.1"',),
    "server/deploy/README.md": ("EVT-PRE-20", "Public APN/CGNAT"),
}


def tracked_paths(root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def audit(paths: list[str], root: Path = ROOT) -> list[str]:
    tracked = set(paths)
    failures: list[str] = []

    missing = sorted(REQUIRED_PATHS - tracked)
    failures.extend(f"required EVT-PRE-20 path missing: {path}" for path in missing)

    for relative in paths:
        lowered_path = relative.lower().encode("utf-8")
        if any(token in lowered_path for token in FORBIDDEN_TOKENS):
            failures.append(f"EVT-MB-specific tracked path is forbidden: {relative}")
            continue

        path = root / relative
        if not path.is_file() or relative in MENTION_ALLOWLIST:
            continue
        try:
            payload = path.read_bytes().lower()
        except OSError as exc:
            failures.append(f"cannot inspect tracked path {relative}: {exc}")
            continue
        if any(token in payload for token in FORBIDDEN_TOKENS):
            failures.append(f"unexpected EVT-MB marker in tracked content: {relative}")

    for relative, required_fragments in IDENTITY_RULES.items():
        path = root / relative
        if relative not in tracked or not path.is_file():
            failures.append(f"runtime identity path missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in required_fragments:
            if fragment not in text:
                failures.append(f"{relative}: required branch identity missing: {fragment}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()

    if args.branch != POLICY_BRANCH:
        raise SystemExit(f"unsupported isolation policy branch: {args.branch}")

    paths = tracked_paths()
    failures = audit(paths)
    if failures:
        print("EVT branch isolation FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"EVT branch isolation PASS: {len(paths)} tracked paths; policy={POLICY_BRANCH}")
    print("EVT-MB deliverables absent; promotion targets limited to reviewed develop/main changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

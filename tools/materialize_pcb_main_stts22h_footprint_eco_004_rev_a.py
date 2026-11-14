#!/usr/bin/env python3
"""Materialize the bounded PCB-MAIN STTS22H footprint ECO-004 candidate."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
HISTORICAL_BASE_COMMIT = "059ecd0e2e35fc56a56f48d62cce4f72a93755c0"
EXPECTED_BASE_SHA256 = "dfcd8780cb3f189fe89cca98f32e3ee9693947a9a28d25e0154f7cce65d51684"
EXPECTED_CANDIDATE_SHA256 = "a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8"

BOARD_REPLACEMENTS = {
    '    (fp_text reference "U4" (at 0 -1.2) (layer "F.SilkS")':
        '    (fp_text reference "U4" (at 0 -1.8) (layer "F.SilkS")',
    "    (fp_rect (start -1.25 -1.25) (end 1.25 1.25)":
        "    (fp_rect (start -1.25 -1.5) (end 1.25 1.5)",
    '    (pad "1" smd rect (at -0.65 0.54) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask")':
        '    (pad "1" smd rect (at -0.65 0.865) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask")',
    '    (pad "2" smd roundrect (at 0 0.54) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)':
        '    (pad "2" smd roundrect (at 0 0.865) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)',
    '    (pad "3" smd roundrect (at 0.65 0.54) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)':
        '    (pad "3" smd roundrect (at 0.65 0.865) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)',
    '    (pad "4" smd roundrect (at 0.65 -0.54) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)':
        '    (pad "4" smd roundrect (at 0.65 -0.865) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)',
    '    (pad "5" smd roundrect (at 0 -0.54) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)':
        '    (pad "5" smd roundrect (at 0 -0.865) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)',
    '    (pad "6" smd roundrect (at -0.65 -0.54) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)':
        '    (pad "6" smd roundrect (at -0.65 -0.865) (size 0.27 0.7) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.2)',
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def materialize_text(base_text: str) -> str:
    marker = '  (footprint "STTS22H_UDFN-6L" (layer "F.Cu")'
    start = base_text.find(marker)
    require(start >= 0, "U4 STTS22H footprint block is missing")
    end = base_text.find("\n  (footprint ", start + len(marker))
    require(end >= 0, "cannot locate end of U4 footprint block")
    block = base_text[start:end]
    for old, new in BOARD_REPLACEMENTS.items():
        require(block.count(old) == 1, f"expected exactly one U4 source line {old!r}")
        require(new not in block, "ECO-004 replacement already present in baseline")
        block = block.replace(old, new)
    return base_text[:start] + block + base_text[end:]


def historical_base_bytes() -> bytes:
    relative = BASE_BOARD.relative_to(ROOT)
    completed = subprocess.run(
        ["git", "show", f"{HISTORICAL_BASE_COMMIT}:{relative}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0,
            f"cannot read ECO-004 baseline from {HISTORICAL_BASE_COMMIT}")
    base_payload = completed.stdout
    require(sha256_bytes(base_payload) == EXPECTED_BASE_SHA256,
            "ECO-004 baseline board SHA-256 drift")
    return base_payload


def candidate_bytes() -> bytes:
    base_payload = historical_base_bytes()
    candidate = materialize_text(base_payload.decode("utf-8")).encode("utf-8")
    require(sha256_bytes(candidate) == EXPECTED_CANDIDATE_SHA256,
            "ECO-004 materialized candidate SHA-256 drift")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-output", type=Path)
    args = parser.parse_args()
    if args.baseline_output is not None:
        args.baseline_output.parent.mkdir(parents=True, exist_ok=True)
        args.baseline_output.write_bytes(historical_base_bytes())
    payload = candidate_bytes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"PCB-MAIN STTS22H ECO-004 candidate: {args.output}")
    print(f"sha256={sha256_bytes(payload)} replacements={len(BOARD_REPLACEMENTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

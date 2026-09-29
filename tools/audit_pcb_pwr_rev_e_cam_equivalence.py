#!/usr/bin/env python3
"""Check Rev E CAM drawing commands against the pinned KiCad 9 Rev D exports.

Only export timestamps and the Gerber project revision attribute are ignored.
All aperture, draw, flash, drill-coordinate and placement records must match.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REV_D = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_D"
REV_E = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_E"
FILES = (
    "gerber/PCB-PWR-F_Cu.gtl",
    "gerber/PCB-PWR-In1_Cu.g1",
    "gerber/PCB-PWR-In2_Cu.g2",
    "gerber/PCB-PWR-B_Cu.gbl",
    "gerber/PCB-PWR-F_Mask.gts",
    "gerber/PCB-PWR-B_Mask.gbs",
    "gerber/PCB-PWR-F_Paste.gtp",
    "gerber/PCB-PWR-B_Paste.gbp",
    "gerber/PCB-PWR-Edge_Cuts.gm1",
    "drill/PCB-PWR.drl",
    "PCB-PWR_pos.csv",
)


def controlled_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if path.suffix in {".drl"}:
        result = []
        for line in lines:
            if line.startswith("; #@! TF.CreationDate,"):
                continue
            if re.match(r"^; DRILL file \{KiCad 9\.0\.9\} date ", line):
                line = "; DRILL file {KiCad 9.0.9} date <timestamp>"
            result.append(line)
        return result
    if path.parent.name == "gerber":
        result = []
        for line in lines:
            if line.startswith(("%TF.CreationDate,", "G04 Created by KiCad")):
                continue
            if line.startswith("%TF.ProjectId,"):
                match = re.fullmatch(r"(%TF\.ProjectId,[^,]+,[^,]+,)[^,]*\*%", line)
                assert match, f"Unexpected Gerber project ID: {line}"
                line = match.group(1) + "<revision>*%"
            result.append(line)
        return result
    return lines


def main() -> None:
    for name in FILES:
        old, new = REV_D / name, REV_E / name
        assert old.is_file() and new.is_file(), f"Missing CAM evidence: {name}"
        original, current = controlled_lines(old), controlled_lines(new)
        if original != current:
            first = next((index + 1 for index, pair in enumerate(zip(original, current))
                          if pair[0] != pair[1]), min(len(original), len(current)) + 1)
            raise AssertionError(f"CAM drawing drift in {name}, normalized line {first}")
    print(f"PCB-PWR Rev E CAM identity PASS: {len(FILES)} manufacturing outputs equal Rev D after header metadata normalization")


if __name__ == "__main__":
    main()

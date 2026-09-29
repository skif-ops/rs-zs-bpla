"""Exact identity of the PCB-PWR Review B Rev E metadata-only board.

Historical candidate audits may use the ECO-006 geometry only after this
byte-level proof succeeds. A digest alone is not used as a geometric shortcut.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ECO_006_SHA256 = "b8c1da6ca80b9e5d2795c4fee5b6926e4ab6169086795295e8e517a18def6ca7"
REV_E_SHA256 = "de2a723bbbc0d37b9f4fc5f55e24bfa287f892a081925daf4a24b8a7fa6c901d"


def strip_review_metadata(payload: bytes) -> bytes:
    """Remove exactly one title block and one stackup block from Rev E."""
    payload, titles = re.subn(rb'\t\(title_block\n(?:\t.*\n)*?\t\)\n', b'', payload, count=1)
    payload, stacks = re.subn(rb'\t\t\(stackup\n(?:\t\t\t.*\n)*?\t\t\)\n', b'', payload, count=1)
    if (titles, stacks) != (1, 1):
        raise ValueError("Rev E title block and stackup must each occur exactly once")
    return payload


def is_rev_e_metadata_only(payload: bytes) -> bool:
    if hashlib.sha256(payload).hexdigest() != REV_E_SHA256:
        return False
    try:
        source = strip_review_metadata(payload)
    except ValueError:
        return False
    return hashlib.sha256(source).hexdigest() == ECO_006_SHA256


def assert_rev_e_metadata_only(board: Path) -> None:
    if not is_rev_e_metadata_only(board.read_bytes()):
        raise AssertionError("Rev E board is not a metadata-only ECO-006 successor")

#!/usr/bin/env python3
"""Restore large versioned server assets from gzip files after checkout."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def restore(relative_path: str) -> None:
    target = ROOT / relative_path
    source = target.with_suffix(target.suffix + ".gz")
    if target.exists():
        print(f"exists: {target.relative_to(ROOT)}")
        return
    if not source.exists():
        raise SystemExit(f"missing compressed asset: {source.relative_to(ROOT)}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(source, "rb") as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    print(f"restored: {target.relative_to(ROOT)}")


if __name__ == "__main__":
    restore("dataset/features.csv")


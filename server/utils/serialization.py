"""Serialization helpers for reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def write_json(path: Path, data: BaseModel | dict[str, Any] | list[Any]) -> Path:
    """Write a Pydantic model or JSON-compatible object to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, BaseModel):
        payload = json.loads(data.model_dump_json())
    else:
        payload = data
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_track_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write track rows to CSV."""

    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def public_artifact(path: Path) -> str:
    """Convert a local artifact path to a route-friendly string."""

    return str(path)

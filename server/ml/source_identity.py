"""Leakage-safe source identity for grouped recordings.

Several files can describe one physical pass (for example, three videos of the
same aircraft at different ranges).  ``source_file`` remains the immutable
provenance key, while ``meta_source_group`` is the statistical identity used
for source balancing, readiness counts and whole-source holdouts.
"""

from __future__ import annotations

import pandas as pd


SOURCE_GROUP_COLUMN = "meta_source_group"
SOURCE_ID_COLUMN = "_source_identity"


def source_identity_series(frame: pd.DataFrame) -> pd.Series:
    """Return the statistical source id, falling back to the physical file."""

    if "source_file" in frame.columns:
        fallback = frame["source_file"].fillna("").astype(str).str.strip()
    else:
        fallback = pd.Series(
            (f"row:{index}" for index in frame.index),
            index=frame.index,
            dtype="object",
        )
    if SOURCE_GROUP_COLUMN not in frame.columns:
        return fallback

    grouped = frame[SOURCE_GROUP_COLUMN].fillna("").astype(str).str.strip()
    invalid = grouped.eq("") | grouped.str.lower().isin({"nan", "none", "null"})
    return grouped.mask(invalid, fallback)


def with_source_identity(
    frame: pd.DataFrame,
    *,
    column: str = SOURCE_ID_COLUMN,
) -> pd.DataFrame:
    """Copy a frame and attach its leakage-safe statistical source id."""

    result = frame.copy()
    result[column] = source_identity_series(result)
    return result

from __future__ import annotations

import pandas as pd

from ml.source_identity import source_identity_series, with_source_identity


def test_source_group_overrides_file_without_destroying_provenance():
    frame = pd.DataFrame(
        {
            "source_file": ["view-a.wav", "view-b.wav", "independent.wav"],
            "meta_source_group": ["flight-1", "flight-1", None],
        }
    )

    identities = source_identity_series(frame).tolist()
    grouped = with_source_identity(frame)

    assert identities == ["flight-1", "flight-1", "independent.wav"]
    assert grouped["source_file"].tolist() == frame["source_file"].tolist()
    assert grouped["_source_identity"].nunique() == 2


def test_blank_source_group_falls_back_to_file():
    frame = pd.DataFrame(
        {
            "source_file": ["a.wav", "b.wav", "c.wav"],
            "meta_source_group": ["", "  ", "nan"],
        }
    )

    assert source_identity_series(frame).tolist() == ["a.wav", "b.wav", "c.wav"]

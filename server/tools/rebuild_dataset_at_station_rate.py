#!/usr/bin/env python3
"""Re-extract every recording of the dataset at the station's analysis rate (32 kHz).

The station computes the 43 features on 32 kHz audio; rows extracted at a recording's native 44.1/48 kHz
are not comparable (YIN f0, MFCC and the mel bank are rate-dependent). With
``settings.target_analysis_sample_rate_hz = 32000`` the loader now resamples on load, so re-running the
extraction over the raw recordings rebuilds ``dataset/features.csv`` consistently:

* groups the current CSV by (label, source_file), keeps each group's ``meta_*`` metadata,
* re-extracts the raw file through ``SoundDatasetManager.add_recording`` into a fresh CSV,
* reports recordings whose raw file is missing (their rows are dropped unless --keep-missing),
* backs the old CSV up to dataset/_backups/ and replaces it.

    cd server && python tools/rebuild_dataset_at_station_rate.py [--dry-run] [--keep-missing]

Afterwards regenerate the station table: python tools/export_station_model.py --report
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import settings  # noqa: E402
from ml.dataset import SoundDatasetManager  # noqa: E402
from models.schemas import RecordingMetadata, UploadedFileInfo  # noqa: E402


def metadata_from_rows(group: pd.DataFrame) -> RecordingMetadata | None:
    meta_cols = [c for c in group.columns if c.startswith("meta_")]
    if not meta_cols:
        return None
    first = group.iloc[0]
    values = {}
    for c in meta_cols:
        v = first[c]
        if pd.isna(v) or v == "":
            continue
        key = c[len("meta_"):]
        if key in ("is_drone",):
            v = str(v).strip().lower() in ("true", "1", "yes")
        values[key] = v
    try:
        return RecordingMetadata(**values)
    except Exception as exc:  # noqa: BLE001 - metadata is best effort
        print(f"  metadata skipped ({exc})")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=settings.feature_dataset_path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-missing", action="store_true", help="keep the old rows of recordings whose raw file is gone")
    a = ap.parse_args()
    if settings.target_analysis_sample_rate_hz != 32000:
        print("settings.target_analysis_sample_rate_hz must be 32000", file=sys.stderr)
        return 2
    df = pd.read_csv(a.dataset)
    base = settings.base_dir
    fresh = a.dataset.with_name("features.rebuild.csv")
    if fresh.exists():
        fresh.unlink()
    manager = SoundDatasetManager(feature_dataset_path=fresh)
    kept_old: list[pd.DataFrame] = []
    missing, rebuilt, windows = [], 0, 0
    for (label, source), group in df.groupby(["label", "source_file"], sort=False):
        raw = base / str(source)
        if not raw.exists():
            missing.append((label, source, len(group)))
            if a.keep_missing:
                kept_old.append(group)
            continue
        print(f"{label:28s} {Path(str(source)).name[:48]:48s} {len(group):4d} rows -> ", end="", flush=True)
        if a.dry_run:
            print("would rebuild")
            continue
        info = UploadedFileInfo(original_name=str(group.iloc[0].get("original_name", raw.name)), stored_path=str(raw), size_bytes=raw.stat().st_size)
        result = manager.add_recording(label, info, metadata=metadata_from_rows(group))
        added = int(getattr(result, "windows_added", 0))
        print(f"{added} windows at 32 kHz")
        rebuilt += 1
        windows += int(added)
    print(f"\nrebuilt {rebuilt} recordings, {windows} windows; missing raw files: {len(missing)}")
    for label, source, n in missing:
        print(f"  MISSING {label:28s} {source} ({n} rows{' kept' if a.keep_missing else ' dropped'})")
    if a.dry_run or not fresh.exists():
        return 0
    new = pd.read_csv(fresh)
    if kept_old:
        new = pd.concat([new] + kept_old, ignore_index=True)
    backups = a.dataset.parent / "_backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"features.native-rate.{time.strftime('%Y%m%d-%H%M%S')}.csv"
    shutil.copy2(a.dataset, backup)
    new.to_csv(a.dataset, index=False)
    fresh.unlink()
    print(f"written {a.dataset} ({len(new)} rows); previous CSV backed up to {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

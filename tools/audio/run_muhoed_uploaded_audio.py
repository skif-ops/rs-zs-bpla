#!/usr/bin/env python3
"""Replay uploaded video audio through the accepted Muhoed analyzer."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
SERVER = (
    BASE
    / "evt_refresh_work_v13/full/РС_Дионея_EVT_MB_v1_2_ASSEMBLY_RELEASE_OPEN"
    / "06_ПО_Мухоед/server_muhoed_v1_2"
)
INPUT = BASE / "audio_run_20260907/wav"
OUTPUT = BASE / "audio_run_20260907/results"

sys.path.insert(0, str(SERVER))

from audio.analyzer import AudioAnalysisService  # noqa: E402
from audio.loader import AudioLoader  # noqa: E402
from audio.separation import DroneSeparator  # noqa: E402
from ml.raw_temporal_diagnostics import (  # noqa: E402
    RAW_DIAGNOSTIC_COLUMNS,
    raw_temporal_diagnostics,
)
from models.schemas import UploadedFileInfo  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_windows(path: Path) -> dict[str, object]:
    """Use the accepted 2 s / 1 s replay gate from the v0.7 benchmark."""

    audio = AudioLoader().load_audio(path)
    separator = DroneSeparator()
    sr = audio.sample_rate
    window = max(int(round(2.0 * sr)), 1)
    hop = max(int(round(1.0 * sr)), 1)
    rows: list[dict[str, object]] = []
    for start in range(0, max(len(audio.signal) - window + 1, 0), hop):
        findings = separator.separate(audio.signal[start : start + window], sr).findings
        rows.append(
            {
                "start_seconds": round(start / sr, 3),
                "end_seconds": round(start / sr + 2.0, 3),
                "drone_present": bool(findings.drone_present),
                "confidence": round(float(findings.confidence), 6),
                "fundamental_hz": round(float(findings.fundamental_hz), 3),
                "harmonic_snr_db": round(float(findings.harmonic_snr_db), 3),
                "persistence": round(float(findings.persistence), 6),
            }
        )
    positive = [row for row in rows if row["drone_present"]]
    first = next(
        (
            float(row["end_seconds"])
            for row in rows
            if row["drone_present"] and float(row["confidence"]) >= 0.55
        ),
        None,
    )
    return {
        "first_detection_seconds": first,
        "positive_windows": len(positive),
        "total_windows": len(rows),
        "best_window_confidence": max((float(row["confidence"]) for row in rows), default=0.0),
        "windows": rows,
    }


def raw_diagnostics(path: Path) -> dict[str, float]:
    """Median v0.7 raw diagnostics over available 3-10 second horizons."""

    audio = AudioLoader().load_audio(path)
    x = audio.signal
    sr = audio.sample_rate
    horizon = min(10.0, max(3.0, len(x) / sr))
    samples = int(round(horizon * sr))
    if len(x) < samples:
        return {name: 0.0 for name in RAW_DIAGNOSTIC_COLUMNS}
    starts = np.arange(0, len(x) - samples + 1, max(int(sr), 1), dtype=int)
    rows = [raw_temporal_diagnostics(x[start : start + samples], sr) for start in starts]
    return {
        name: round(float(np.median([row[name] for row in rows])), 8)
        for name in RAW_DIAGNOSTIC_COLUMNS
    }


def summary_from(report: dict[str, object], replay: dict[str, object], wav: Path) -> dict[str, object]:
    decision = report["decision"]
    separation = report["separation"]
    family = report.get("family_classification") or {}
    ml = report.get("ml_classification") or {}
    passport = report["passport"]
    quality = report["quality"]
    return {
        "file": wav.name,
        "ground_truth": "UAV_CONFIRMED",
        "ground_truth_source": "user_verified_2026-09-07",
        "detection_outcome": "TRUE_POSITIVE" if bool(decision["drone_present"]) else "FALSE_NEGATIVE",
        "wav_sha256": sha256(wav),
        "duration_seconds": round(float(quality["duration_seconds"]), 3),
        "sample_rate_hz": int(quality["sample_rate"]),
        "channels": int(quality["channels"]),
        "decision_status": decision["status"],
        "decision_label": decision["display_label"],
        "decision_confidence": round(float(decision["confidence"]), 6),
        "drone_present": bool(decision["drone_present"]),
        "needs_review": bool(decision["needs_review"]),
        "first_detection_seconds": replay["first_detection_seconds"],
        "positive_windows": int(replay["positive_windows"]),
        "total_windows": int(replay["total_windows"]),
        "best_window_confidence": round(float(replay["best_window_confidence"]), 6),
        "fundamental_hz": round(float(separation["fundamental_hz"]), 3),
        "harmonic_count": int(separation["harmonic_count"]),
        "harmonic_snr_db": round(float(separation["harmonic_snr_db"]), 3),
        "persistence": round(float(separation["persistence"]), 6),
        "likely_source": separation["likely_source"],
        "family": family.get("best_family", "UNKNOWN"),
        "family_confidence": round(float(family.get("confidence", 0.0)), 6),
        "family_status": family.get("status", "unavailable"),
        "family_conditional_on_air": bool(family.get("conditional_on_air_target", False)),
        "ml_label": ml.get("best_label", "UNKNOWN"),
        "ml_confidence": round(float(ml.get("confidence", 0.0)), 6),
        "ml_status": ml.get("status", "unavailable"),
        "operational_type": passport["drone_type"],
        "quality_warnings": quality["warnings"],
    }


def run() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    service = AudioAnalysisService()
    summaries: list[dict[str, object]] = []
    for wav in sorted(INPUT.glob("*.wav")):
        analysis_id = wav.stem
        out_dir = OUTPUT / analysis_id
        out_dir.mkdir(parents=True, exist_ok=True)
        source = UploadedFileInfo(
            original_name=wav.name,
            stored_path=str(wav),
            size_bytes=wav.stat().st_size,
        )
        report_model = service.analyze(analysis_id, source, out_dir)
        report = report_model.model_dump(mode="json")
        replay = candidate_windows(wav)
        raw = raw_diagnostics(wav)
        combined = {
            "ground_truth": {
                "target_present": True,
                "target_class": "UAV",
                "exact_type": "UNKNOWN",
                "verification": "user_verified_2026-09-07",
                "detection_outcome": "TRUE_POSITIVE" if report["decision"]["drone_present"] else "FALSE_NEGATIVE",
            },
            "report": report,
            "candidate_replay": replay,
            "raw_diagnostics": raw,
        }
        (out_dir / "complete_result.json").write_text(
            json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summaries.append(summary_from(report, replay, wav))

    (OUTPUT / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if summaries:
        with (OUTPUT / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
            writer.writeheader()
            writer.writerows(summaries)
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()

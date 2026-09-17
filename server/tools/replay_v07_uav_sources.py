#!/usr/bin/env python3
"""v0.7 whole-recording replay and raw diagnostic audit."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from audio.loader import AudioLoader
from audio.separation import DroneSeparator
from ml.online_type_classifier import OnlineTemporalTypeClassifier
from ml.raw_temporal_diagnostics import RAW_DIAGNOSTIC_COLUMNS, raw_temporal_diagnostics
from ml.type_readiness import assess_type_readiness

DATASET = ROOT / "dataset" / "features.csv"
POLICY = ROOT / "dataset" / "source_policy_v07.json"
OUT = ROOT / "output" / "v07_benchmark"
TARGETS = ("Лютый", "FP-1")


def candidate_time(path: Path) -> tuple[float | None, float, int, int]:
    audio = AudioLoader().load_audio(path)
    sep = DroneSeparator()
    sr = audio.sample_rate
    win = max(int(round(2.0 * sr)), 1)
    hop = max(int(round(1.0 * sr)), 1)
    first = None
    best = 0.0
    present = total = 0
    if len(audio.signal) < win:
        return None, 0.0, 0, 0
    for start in range(0, len(audio.signal) - win + 1, hop):
        result = sep.separate(audio.signal[start:start + win], sr).findings
        total += 1
        best = max(best, float(result.confidence))
        if result.drone_present:
            present += 1
        if first is None and result.drone_present and result.confidence >= 0.55:
            first = start / sr + 2.0
    return first, best, present, total


def raw_source_summary(path: Path) -> dict[str, float]:
    audio = AudioLoader().load_audio(path)
    x = audio.signal
    sr = audio.sample_rate
    horizon = min(10.0, max(3.0, len(x) / sr))
    n = int(round(horizon * sr))
    if len(x) < n:
        return {name: 0.0 for name in RAW_DIAGNOSTIC_COLUMNS}
    starts = np.arange(0, len(x) - n + 1, max(int(sr), 1), dtype=int)
    if len(starts) > 24:
        starts = starts[np.unique(np.linspace(0, len(starts)-1, 24).round().astype(int))]
    rows = [raw_temporal_diagnostics(x[start:start+n], sr) for start in starts]
    return {name: float(np.median([row[name] for row in rows])) for name in RAW_DIAGNOSTIC_COLUMNS}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATASET)
    manifest = json.loads(POLICY.read_text(encoding="utf-8"))["sources"]
    # Benchmark the six latest user recordings. Older confirmed Lutyi sources
    # remain in training but do not need the expensive detection replay again.
    sources = [
        src for src, meta in manifest.items()
        if "v06_user_sources" in src and meta.get("label") in TARGETS
        and (ROOT / src).exists() and (df["source_file"].astype(str) == src).any()
    ]
    if not sources:
        raise SystemExit(
            "Whole-recording replay unavailable: no policy-listed raw v06 UAV audio "
            "is present in this source checkout. Restore the traceable raw sources "
            "before running the field replay gate."
        )
    cached_v06 = {}
    old_csv = ROOT / "output" / "v06_benchmark" / "whole_recording_lofo.csv"
    if old_csv.exists():
        old = pd.read_csv(old_csv)
        cached_v06 = {str(row.source_file): (row.candidate_detection_seconds, row.candidate_best_confidence, int(row.candidate_present_windows), int(row.candidate_total_windows)) for row in old.itertuples()}

    # Persist the full research model separately from each LOFO fold.
    full_clf = OnlineTemporalTypeClassifier()
    full_model = full_clf.train(df)
    readiness = assess_type_readiness(df[df["label"].astype(str).isin(TARGETS)], TARGETS).to_dict()

    records = []
    timelines: dict[str, list[dict[str, object]]] = {}
    raw_rows = []
    for src in sorted(sources):
        meta = manifest[src]
        test = df[df["source_file"].astype(str) == src].copy()
        raw = ROOT / src
        if src in cached_v06:
            detect_s, best_det, present, total = cached_v06[src]
        else:
            detect_s, best_det, present, total = candidate_time(raw)
        train = df[df["source_file"].astype(str) != src].copy()
        with tempfile.TemporaryDirectory() as td:
            clf = OnlineTemporalTypeClassifier(model_path=Path(td) / "temporal.json")
            model = clf.train(train)
            replay = clf.replay(test, source_file=src, candidate_detection_seconds=detect_s, model=model)
        audio = AudioLoader().load_audio(raw)
        records.append({
            "source_file": src,
            "file_name": raw.name,
            "label": meta["label"],
            "label_confidence": meta.get("label_confidence", "unknown"),
            "recording_quality_score": meta.get("recording_quality_score", 0.0),
            "duration_seconds": round(float(len(audio.signal) / audio.sample_rate), 2),
            "candidate_detection_seconds": detect_s,
            "candidate_best_confidence": round(best_det, 4),
            "candidate_present_windows": present,
            "candidate_total_windows": total,
            "first_type_hypothesis_seconds": replay.first_type_hypothesis_seconds,
            "research_stable_seconds": replay.research_stable_seconds,
            "final_type": replay.final_label,
            "final_status": replay.final_status,
            "type_lock_allowed": replay.type_lock_allowed,
            "type_snapshot_count": len(replay.snapshots),
        })
        timelines[src] = [item.model_dump() for item in replay.snapshots]
        raw_rows.append({"source_file": src, "label": meta["label"], "label_confidence": meta.get("label_confidence", "unknown"), **raw_source_summary(raw)})

    out = pd.DataFrame(records)
    raw_df = pd.DataFrame(raw_rows)
    out.to_csv(OUT / "whole_recording_lofo.csv", index=False)
    raw_df.to_csv(OUT / "raw_diagnostics_source_summary.csv", index=False)
    (OUT / "timelines.json").write_text(json.dumps(timelines, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "type_readiness.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    confirmed = out[out["label_confidence"] == "confirmed"]
    weak = out[out["label_confidence"] == "weak"]
    within2 = int((out["candidate_detection_seconds"].fillna(999) <= 2.0).sum())
    confirmed_any = int((confirmed["final_type"] != "UNKNOWN").sum())
    confirmed_correct = int(((confirmed["final_type"] == confirmed["label"]) & (confirmed["final_type"] != "UNKNOWN")).sum())
    md = [
        "# Мухоед v0.7 - type evidence benchmark",
        "",
        "Каждый source полностью исключается из своего LOFO fold. FP-1 остаётся weak-labelled и не используется как ground-truth accuracy.",
        "",
        f"- Target sources с доступным raw audio: {len(out)} ({len(confirmed)} confirmed Лютый, {len(weak)} weak FP-1).",
        f"- Candidate detection <=2 s: {within2}/{len(out)}.",
        f"- Operational type lock: {int(out['type_lock_allowed'].astype(bool).sum())}.",
        f"- Confirmed Лютый: финальная ненулевая research-гипотеза {confirmed_any}/{len(confirmed)}, из них совпала с меткой {confirmed_correct}/{len(confirmed)}.",
        f"- Dataset readiness: {readiness['mode']}.",
        "",
        "## Политика v0.7",
        "",
        "- Решение использует ограниченную серию 4-8 окон и temporal horizons 4/6/8 s.",
        "- Противоречие горизонтов уменьшает confidence, а не усредняется в ложную уверенность.",
        "- Type lock дополнительно заблокирован dataset-readiness gate до появления подтверждённой и замороженной контрастной выборки каждого типа.",
        "- Raw diagnostics (1-3 Hz envelope modulation, 4-8/8-12 kHz relative bands) пока диагностические и не обучают тип: подтверждённого FP-1 ground truth нет.",
        "- 40-60 s - доступное время наблюдения, не время ожидания решения.",
        "",
        "## Критерий продвижения type-classifier",
        "",
        "Для перевода FP-1 из weak в confirmed нужен источник с проверенной идентификацией. После этого новые raw/temporal признаки можно включать в supervised type model только если whole-recording LOFO улучшается без роста ложной уверенности на confirmed Лютый.",
    ]
    (OUT / "README.md").write_text("\n".join(md), encoding="utf-8")
    print(out.to_string(index=False))
    print("\nreadiness:", json.dumps(readiness, ensure_ascii=False))


if __name__ == "__main__":
    main()

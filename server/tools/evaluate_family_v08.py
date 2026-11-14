#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.acoustic_family import AcousticFamily, family_for_label
from ml.family_classifier import AcousticFamilyClassifier
from ml.source_identity import SOURCE_ID_COLUMN, with_source_identity


def main() -> int:
    frame = with_source_identity(pd.read_csv(ROOT / "dataset" / "features.csv"))
    frame["expected_family"] = frame["label"].map(lambda x: family_for_label(str(x)).value)
    frame = frame[frame["expected_family"] != AcousticFamily.UNKNOWN.value].copy()
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for source_id, holdout in frame.groupby(SOURCE_ID_COLUMN, sort=False):
            expected = str(holdout["expected_family"].iloc[0])
            train = frame[frame[SOURCE_ID_COLUMN].astype(str) != str(source_id)].copy()
            source_files = sorted(set(holdout["source_file"].astype(str)))
            remaining = set(train["expected_family"].astype(str))
            if expected not in remaining:
                rows.append({
                    "source_group": str(source_id), "source_files": "|".join(source_files),
                    "label": str(holdout["label"].iloc[0]),
                    "expected_family": expected, "predicted_family": "NOT_EVALUABLE",
                    "confidence": 0.0, "margin": 0.0, "correct": None,
                })
                continue
            clf = AcousticFamilyClassifier(model_path=Path(td) / "family.json")
            model = clf.train(train)
            is_air = expected in {AcousticFamily.PROP_PISTON.value, AcousticFamily.ROTOR_ELECTRIC.value, AcousticFamily.TURBINE_JET.value}
            pred = clf.predict_rows(holdout, model, air_target_confirmed=is_air)
            rows.append({
                "source_group": str(source_id), "source_files": "|".join(source_files),
                "label": str(holdout["label"].iloc[0]),
                "expected_family": expected,
                "predicted_family": pred.best_family if pred else "NONE",
                "confidence": round(float(pred.confidence if pred else 0.0), 6),
                "margin": round(float(pred.margin if pred else 0.0), 6),
                "correct": bool(pred and pred.best_family == expected),
            })
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "models" / "family_v08_whole_source_lofo.csv", index=False)
    evaluable = out[out["correct"].notna()].copy()
    summary = {
        "evaluable_sources": int(len(evaluable)),
        "correct_sources": int(evaluable["correct"].sum()) if not evaluable.empty else 0,
        "accuracy": float(evaluable["correct"].mean()) if not evaluable.empty else None,
        "unknown_sources": int((evaluable["predicted_family"] == "UNKNOWN").sum()) if not evaluable.empty else 0,
        "not_evaluable_sources": int((out["predicted_family"] == "NOT_EVALUABLE").sum()),
        "by_family": {},
    }
    for family, group in evaluable.groupby("expected_family"):
        summary["by_family"][family] = {
            "sources": int(len(group)),
            "correct": int(group["correct"].sum()),
            "accuracy": float(group["correct"].mean()),
            "unknown": int((group["predicted_family"] == "UNKNOWN").sum()),
        }
    (ROOT / "models" / "family_v08_whole_source_lofo.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export the station centroid model (firmware/generated/zs_model_centroids.h) from the dataset.

Level 1 of the hierarchy is what the station must get right: *is there a UAV* (class ids 1/2/3 of
zs_types.h) versus everything else.  The firmware classifier (zs_classifier.c) is a nearest-centroid
over the 43 standardized features; this tool fits it from ``server/dataset/features.csv.gz``:

* z-score with the global mean/std over the training windows;
* per label up to ``--k`` centroids (k-means with a fixed seed on the label's z-vectors, groups with
  fewer than 5 windows dropped), each mapped to the label's zs class id — several centroids per
  label is what lifts «Лютый»/FP-1 recall without touching the C code;
* radius = 95th percentile of the member distances (confidence = 1 - d / (1.5 * radius)).

``--report`` prints the presence metrics (recall / false-positive rate on background) both in-sample
and on a temporal holdout (last 30 % of windows of every source file trained out); ``--check``
verifies that the committed header is what this dataset produces.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "server" / "dataset" / "features.csv.gz"
HEADER = ROOT / "firmware" / "generated" / "zs_model_centroids.h"
FEATURE_ORDER = ROOT / "server" / "tools" / "golden" / "feature_order.txt"

# label -> zs_class_id_t (firmware/include/zs_types.h)
LABEL_CLASS = {
    "Лютый": 1, "FP-1": 1,                        # ZS_CLASS_PISTON_UAV
    "DJI Mini 3 Pro": 3,                          # ZS_CLASS_ELECTRIC_UAV
    "городской транспорт": 10,                    # ZS_CLASS_ROAD_TRAFFIC
    "трактор": 14,                                # ZS_CLASS_AGRICULTURAL
    "птицы": 15,                                  # ZS_CLASS_BIRDS
    "цикады и насекомые": 16,                     # ZS_CLASS_INSECTS
    "стрельба": 17,                               # ZS_CLASS_GUNFIRE
    "природный фон": 18,                          # ZS_CLASS_WIND
}
UAV_CLASSES = (1, 2, 3)
TRAINING_ROLES = {"training", "training_provisional", "training_provisional_weak"}
DEFAULT_K = 3


def load_dataset(path: Path = DATASET):
    order = FEATURE_ORDER.read_text(encoding="utf-8").split()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["label"] in LABEL_CLASS and r.get("meta_dataset_role", "training") in TRAINING_ROLES]
    X = np.array([[float(r[c]) for c in order] for r in rows], dtype=np.float64)
    labels = np.array([r["label"] for r in rows])
    files = np.array([r["source_file"] for r in rows])
    starts = np.array([float(r["start_seconds"]) for r in rows])
    return order, X, labels, files, starts


def kmeans(Z: np.ndarray, k: int, seed: int = 0, iters: int = 30) -> np.ndarray:
    rng = np.random.default_rng(seed)
    c = Z[rng.choice(len(Z), k, replace=False)]
    for _ in range(iters):
        a = np.linalg.norm(Z[:, None, :] - c[None, :, :], axis=2).argmin(1)
        c = np.array([Z[a == j].mean(0) if (a == j).any() else c[j] for j in range(k)])
    return a


def fit(X: np.ndarray, labels: np.ndarray, k: int):
    mean, std = X.mean(0), X.std(0)
    Z = (X - mean) / (std + 1e-6)
    cents, ids, radii, names = [], [], [], []
    for label in sorted(set(labels), key=lambda l: (LABEL_CLASS[l], l)):
        Zl = Z[labels == label]
        kk = min(k, max(1, len(Zl) // 20))
        groups = [Zl] if kk == 1 else [Zl[a == j] for a, j in ((kmeans(Zl, kk), j) for j in range(kk)) if (a == j).sum() >= 5]
        for g in groups:
            c = g.mean(0)
            cents.append(c); ids.append(LABEL_CLASS[label]); names.append(label)
            radii.append(float(np.percentile(np.linalg.norm(g - c, axis=1), 95)))
    return {"mean": mean, "std": std, "centroids": np.array(cents), "class_id": np.array(ids), "radius": np.array(radii), "label": names}


def predict(model, X: np.ndarray):
    """Exact mirror of zs_classifier_predict_centroid (z-score, Euclidean argmin, radius confidence)."""
    Z = (X - model["mean"]) / (model["std"] + 1e-6)
    D = np.linalg.norm(Z[:, None, :] - model["centroids"][None, :, :], axis=2)
    bi = D.argmin(1)
    conf = np.clip(1.0 - D.min(1) / (model["radius"][bi] * 1.5 + 1e-6), 0.0, 1.0)
    return model["class_id"][bi], conf


def presence_metrics(class_id, conf, labels, threshold: float = 0.0):
    truth = np.array([LABEL_CLASS[l] in UAV_CLASSES for l in labels])
    pred = np.isin(class_id, UAV_CLASSES) & (conf >= threshold)
    tp, fp = int((pred & truth).sum()), int((pred & ~truth).sum())
    fn, tn = int((~pred & truth).sum()), int((~pred & ~truth).sum())
    per_label = {l: float(pred[labels == l].mean()) for l in sorted(set(labels))}
    return {"recall": tp / max(1, tp + fn), "fpr": fp / max(1, fp + tn), "precision": tp / max(1, tp + fp), "per_label": per_label}


def temporal_holdout_mask(files, starts, fraction: float = 0.3):
    test = np.zeros(len(files), dtype=bool)
    for f in set(files):
        idx = np.where(files == f)[0]
        idx = idx[np.argsort(starts[idx])]
        test[idx[int(len(idx) * (1 - fraction)):]] = True
    return test


def render_header(model, order) -> str:
    def fl(v):
        t = f"{float(v):.9g}"
        if "." not in t and "e" not in t and "inf" not in t and "nan" not in t:
            t += ".0"                                   # "14f" is not a C float literal
        return t + "f"
    n = len(model["centroids"])
    lines = ["#ifndef ZS_MODEL_CENTROIDS_H", "#define ZS_MODEL_CENTROIDS_H", "#include <stdint.h>",
             "/* Generated by server/tools/export_station_model.py from server/dataset/features.csv.gz; do not edit.",
             f" * {n} centroids (up to {DEFAULT_K} per label), 43 features in the order of server/tools/golden/feature_order.txt.",
             " * Labels: " + ", ".join(f"{i}:{l}" for i, l in enumerate(model["label"])) + " */",
             f"#define ZS_MODEL_CLASS_COUNT {n}",
             "static const float zs_model_mean[43] = {" + ",".join(fl(v) for v in model["mean"]) + "};",
             "static const float zs_model_std[43] = {" + ",".join(fl(v) for v in model["std"]) + "};",
             f"static const uint8_t zs_model_class_id[ZS_MODEL_CLASS_COUNT]={{{','.join(str(int(i)) for i in model['class_id'])}}};",
             f"static const float zs_model_radius[ZS_MODEL_CLASS_COUNT]={{{','.join(fl(v) for v in model['radius'])}}};",
             "static const float zs_model_centroid[ZS_MODEL_CLASS_COUNT][43]={"]
    lines += ["{" + ",".join(fl(v) for v in c) + "}," for c in model["centroids"]]
    lines += ["};", "#endif", ""]
    assert len(order) == 43
    return "\n".join(lines)


def parse_header(text: str):
    def arr(name):
        m = re.search(name + r"\[[^=]*=\s*\{(.*?)\};", text, re.S)
        return np.array([float(v.rstrip("f")) for v in re.findall(r"-?[\d.]+(?:e-?\d+)?f", m.group(1))])
    m = re.search(r"zs_model_centroid\[.*?=\{(.*)\};", text, re.S)
    cents = np.array([float(v.rstrip("f")) for v in re.findall(r"-?[\d.]+(?:e-?\d+)?f", m.group(1))]).reshape(-1, 43)
    ids = np.array([int(v) for v in re.search(r"zs_model_class_id\[[^=]*=\{(.*?)\}", text).group(1).split(",")])
    return {"mean": arr("zs_model_mean"), "std": arr("zs_model_std"), "centroids": cents, "class_id": ids, "radius": arr("zs_model_radius"), "label": []}


def report(model, X, labels, files, starts, k):
    def line(tag, m):
        print(f"{tag}: UAV recall {m['recall']:.3f}, background FPR {m['fpr']:.3f}, precision {m['precision']:.3f}")
        print("   predicted-UAV share per label: " + ", ".join(f"{l} {v:.2f}" for l, v in m["per_label"].items()))
    cid, conf = predict(model, X)
    line("in-sample (dataset the header is built from)", presence_metrics(cid, conf, labels))
    test = temporal_holdout_mask(files, starts)
    m2 = fit(X[~test], labels[~test], k)
    cid, conf = predict(m2, X[test])
    line("temporal holdout (last 30 % of every file)", presence_metrics(cid, conf, labels[test]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=DATASET)
    ap.add_argument("--out", type=Path, default=HEADER)
    ap.add_argument("--k", type=int, default=DEFAULT_K, help="max centroids per label")
    ap.add_argument("--check", action="store_true", help="fail if the header differs from what the dataset produces")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    order, X, labels, files, starts = load_dataset(a.dataset)
    model = fit(X, labels, a.k)
    text = render_header(model, order)
    if a.report:
        report(model, X, labels, files, starts, a.k)
    if a.check:
        if a.out.read_text(encoding="utf-8") != text:
            print(f"{a.out} is stale: regenerate with export_station_model.py", file=sys.stderr)
            return 1
        print(f"{a.out.name}: up to date ({len(model['centroids'])} centroids)")
        return 0
    a.out.write_text(text, encoding="utf-8")
    print(f"{a.out} written: {len(model['centroids'])} centroids from {len(X)} windows")
    return 0


if __name__ == "__main__":
    sys.exit(main())

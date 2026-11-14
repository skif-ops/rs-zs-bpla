#!/usr/bin/env python3
"""Run the whole station level 1 (zs_dsp features -> centroid votes + AIR gate -> zs_presence; host build
zs_presence_eval) over a directory of WAVs.

Layout: <root>/<label>/*.wav (any sample rate / channels; resampled to 32 kHz mono like the station).
Prints, per label and per file, the share of windows at each presence level (confirmed / engine / suspect /
none), i.e. what the station would report on the Muhoed recordings.  Build the tool first:

    cmake -S firmware -B build && cmake --build build --target zs_presence_eval
    python server/tools/eval_presence_wavs.py --root <dir> --tool build/zs_presence_eval [--csv out.csv]
"""
from __future__ import annotations
import argparse, csv, io, subprocess, sys, tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

WARMUP = 2  # windows before the gate has any history


def load_pcm(path: Path) -> np.ndarray:
    import soundfile as sf
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != 32000:
        import librosa
        y = librosa.resample(y, orig_sr=sr, target_sr=32000)
    return np.clip(y * 32767.0, -32768, 32767).astype("<i2")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--tool", type=Path, required=True)
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args()
    rows = []
    per_label = defaultdict(lambda: [0, 0])   # [confirmed, windows, per-file level dicts...]
    for wav in sorted(a.root.rglob("*.wav")):
        label = wav.parent.name if wav.parent != a.root else "(root)"
        pcm = load_pcm(wav)
        with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as tmp:
            tmp.write(pcm.tobytes())
            tmp_path = tmp.name
        out = subprocess.run([str(a.tool), tmp_path], capture_output=True, text=True, check=True).stdout
        Path(tmp_path).unlink()
        wins = list(csv.DictReader(io.StringIO(out)))
        judged = [w for w in wins if int(w["window"]) >= WARMUP]
        levels = {k: sum(w["level"] == k for w in judged) for k in ("confirmed", "engine", "suspect", "none")}
        per_label[label][0] += levels["confirmed"]
        per_label[label][1] += len(judged)
        per_label[label].append(levels)
        n = max(1, len(judged))
        print(f"{label:24s} {wav.name:40s} windows {len(judged):4d} confirmed {levels['confirmed'] / n:5.1%} engine {levels['engine'] / n:5.1%} suspect {levels['suspect'] / n:5.1%}")
        for w in wins:
            rows.append({"label": label, "file": wav.name, **w})
    print("\nper label (share of windows: confirmed / engine / suspect):")
    for label, entry in sorted(per_label.items(), key=lambda kv: -kv[1][0] / max(1, kv[1][1])):
        n = max(1, entry[1])
        tot = {k: sum(d[k] for d in entry[2:]) for k in ("confirmed", "engine", "suspect")}
        print(f"  {label:24s} {tot['confirmed'] / n:5.1%} / {tot['engine'] / n:5.1%} / {tot['suspect'] / n:5.1%}  ({entry[1]} windows)")
    if a.csv and rows:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            wr.writeheader(); wr.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())

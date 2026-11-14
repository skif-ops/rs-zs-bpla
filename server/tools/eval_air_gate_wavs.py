#!/usr/bin/env python3
"""Run the station AIR gate (firmware zs_air_gate, host build zs_air_gate_eval) over a directory of WAVs.

Layout: <root>/<label>/*.wav (any sample rate / channels; resampled to 32 kHz mono like the station).
Prints, per label and per file, the share of windows in which the gate confirms an AIR target, so the
gate can be judged as a level-1 detector on the Muhoed recordings (UAV labels should score high, the
background labels low).  Build the tool first:

    cmake -S firmware -B build && cmake --build build --target zs_air_gate_eval
    python server/tools/eval_air_gate_wavs.py --root <dir> --tool build/zs_air_gate_eval [--csv out.csv]
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
    per_label = defaultdict(lambda: [0, 0])
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
        present = sum(int(w["present"]) for w in judged)
        per_label[label][0] += present
        per_label[label][1] += len(judged)
        share = present / len(judged) if judged else 0.0
        print(f"{label:24s} {wav.name:40s} windows {len(judged):4d} present {share:5.1%}")
        for w in wins:
            rows.append({"label": label, "file": wav.name, **w})
    print("\nper label (share of windows with AIR target confirmed):")
    for label, (p, n) in sorted(per_label.items(), key=lambda kv: -kv[1][0] / max(1, kv[1][1])):
        print(f"  {label:24s} {p / max(1, n):5.1%}  ({p}/{n})")
    if a.csv and rows:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            wr.writeheader(); wr.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())

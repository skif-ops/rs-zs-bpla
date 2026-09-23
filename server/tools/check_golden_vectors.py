#!/usr/bin/env python3
"""Compare firmware feature extractors against the server reference on golden windows.

Runs the host builds of ``zs_eval_golden`` (zs_dsp) and/or ``zs_eval_golden_mcu`` (zs_dsp_mcu) over the
PCM16LE windows of a golden set (generate_golden_vectors.py) and reports normalized errors per feature.

Acceptance (server/tools/golden/README.md): median normalized error <= 3 %, p95 <= 5 %; F0/harmonic
features are judged with absolute tolerances instead (fundamental_hz / harmonic_step_hz: 2 Hz,
harmonic_count: 1).  Normalized error = |fw - ref| / max(|ref|, 1e-3 * max|ref_j| + 1e-9).
"""
from __future__ import annotations
import argparse, csv, subprocess, sys
from pathlib import Path
import numpy as np

ABS_TOL = {"fundamental_hz": 2.0, "harmonic_step_hz": 2.0, "harmonic_count": 1.0}


def run(binary: Path, pcm: Path) -> np.ndarray:
    out = subprocess.run([str(binary), str(pcm)], capture_output=True, text=True, check=True).stdout.strip()
    return np.array([float(x) for x in out.split(",")], dtype=np.float64)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", type=Path, required=True, help="directory with vectors.csv and pcm16le/")
    ap.add_argument("--binary", action="append", required=True, help="path to zs_eval_golden or zs_eval_golden_mcu (repeatable)")
    ap.add_argument("--median", type=float, default=0.03)
    ap.add_argument("--p95", type=float, default=0.05)
    a = ap.parse_args()
    with open(a.golden / "vectors.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    names = [c for c in rows[0].keys() if c not in ("vector_id", "source", "start_s", "pcm_file")]
    ref = np.array([[float(r[n]) for n in names] for r in rows])
    scale = 1e-3 * np.max(np.abs(ref), axis=0) + 1e-9
    ok_all = True
    for b in a.binary:
        fw = np.array([run(Path(b), a.golden / "pcm16le" / r["pcm_file"]) for r in rows])
        err = np.abs(fw - ref) / np.maximum(np.abs(ref), scale)
        rel_cols = [i for i, n in enumerate(names) if n not in ABS_TOL]
        rel = err[:, rel_cols]
        med, p95, mx = float(np.median(rel)), float(np.percentile(rel, 95)), float(np.max(rel))
        ok = med <= a.median and p95 <= a.p95
        print(f"{Path(b).name}: {len(rows)} windows  normalized error median {med:.4f} p95 {p95:.4f} max {mx:.4f}  -> {'PASS' if ok else 'FAIL'}")
        worst = sorted(((float(np.percentile(err[:, i], 95)), names[i]) for i in rel_cols), reverse=True)[:5]
        print("  worst p95 per feature: " + ", ".join(f"{n} {v:.4f}" for v, n in worst))
        for n, tol in ABS_TOL.items():
            i = names.index(n)
            d = np.abs(fw[:, i] - ref[:, i])
            within = float(np.mean(d <= tol))
            print(f"  {n}: within ±{tol:g} in {within * 100:.0f} % of windows, median |Δ| {np.median(d):.3f}, max {np.max(d):.3f}")
            if within < 0.95:
                ok = False
        ok_all &= ok
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())

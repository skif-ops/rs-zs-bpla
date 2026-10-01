"""Blind zones of the station geometry (decision 5 of docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md).

Where can the stations put a point on a target, and how well?  For a target at height ``height_m`` over every cell of a
grid around the stations this answers with the rules of the bearing fusion itself (fusion/bearing_fusion.py):

* a station hears the target when its slant range is within ``range_m`` (the acoustic range of the class, e.g. the
  range at Pd >= 0.8 the acceptance tool measured) and within the fusion's MAX_RANGE_M;
* a point needs two stations whose horizontal rays cross at MIN_CROSSING_DEG or more; its error is the one the fusion
  reports (the square root of the trace of the weighted intersection's covariance, each ray weighted by its lateral
  error ``range * sigma``) and must stay within MAX_ERROR_M.

Cell codes: 0 no station hears, 1 one station only (a bearing line, no point), 2 blind geometry (two or more stations
hear, but the rays are too close to parallel or the error is too large - along the line through two stations, far out
of the array), 3 a point with the error given.
"""
from __future__ import annotations

import math

import numpy as np

from fusion.bearing_fusion import MAX_ERROR_M, MAX_RANGE_M, MIN_CROSSING_DEG

OUT, SINGLE, BLIND, OK = 0, 1, 2, 3
CODE_NAMES = {OUT: "out_of_range", SINGLE: "single_station", BLIND: "blind_geometry", OK: "position"}
MAX_CELLS = 40_000                 # one grid answer: at most 200 x 200 cells


def assess(stations: np.ndarray, points: np.ndarray, *, range_m: float, sigma_deg: float, height_m: float = 0.0
           ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """For target positions ``points`` (m x 2 east/north, or m x 3 with their own heights) and stations (k x 3 ENU):
    (code, horizontal error m (nan without a point), best crossing angle deg, number of stations hearing)."""
    st = np.asarray(stations, dtype=float).reshape(-1, 3)
    pts = np.asarray(points, dtype=float)
    pts = pts.reshape(-1, pts.shape[-1] if pts.ndim > 1 else 2)
    up = pts[:, 2] if pts.shape[1] >= 3 else np.full(len(pts), float(height_m))
    d = pts[:, None, :2] - st[None, :, :2]                                   # m x k x 2
    rho = np.hypot(d[..., 0], d[..., 1])
    slant = np.hypot(rho, up[:, None] - st[None, :, 2])
    hears = (slant <= min(float(range_m), MAX_RANGE_M)) & (rho > 1.0)
    count = hears.sum(axis=1)
    safe = np.where(rho > 1.0, rho, 1.0)
    ue, un = d[..., 0] / safe, d[..., 1] / safe                              # horizontal direction station -> target
    lateral = np.maximum(math.radians(max(float(sigma_deg), 1e-3)) * rho, 1.0)
    w = np.where(hears, 1.0 / lateral ** 2, 0.0)
    # normal of each ray (-n, e): the information matrix of the weighted intersection (bearing_fusion.intersect)
    j11 = (w * un * un).sum(axis=1)
    j22 = (w * ue * ue).sum(axis=1)
    j12 = (w * -un * ue).sum(axis=1)
    det = j11 * j22 - j12 * j12
    solvable = det > 1e-12 * np.maximum(j11 * j22, 1e-300)
    with np.errstate(divide="ignore", invalid="ignore"):
        h_err = np.where(solvable, np.sqrt(np.maximum((j11 + j22) / np.where(solvable, det, 1.0), 0.0)), np.nan)
    crossing = np.zeros(len(pts))
    k = st.shape[0]
    for a in range(k):
        for b in range(a + 1, k):
            both = hears[:, a] & hears[:, b]
            cos = np.abs(ue[:, a] * ue[:, b] + un[:, a] * un[:, b])
            ang = np.degrees(np.arccos(np.clip(cos, 0.0, 1.0)))
            crossing = np.where(both, np.maximum(crossing, ang), crossing)
    code = np.full(len(pts), OUT, dtype=np.int8)
    code[count == 1] = SINGLE
    multi = count >= 2
    good = multi & solvable & (crossing >= MIN_CROSSING_DEG) & (np.nan_to_num(h_err, nan=np.inf) <= MAX_ERROR_M)
    code[multi] = BLIND
    code[good] = OK
    h_err = np.where(good, h_err, np.nan)
    return code, h_err, crossing, count


def coverage_grid(stations: np.ndarray, *, range_m: float, sigma_deg: float, height_m: float = 0.0,
                  step_m: float | None = None, margin_m: float | None = None) -> dict:
    """The grid around the stations (ENU, k x 3): cell centres from (e0, n0) at ``step_m``, row by row from the south.
    The extent is the stations' box plus ``margin_m`` (default: the range); the step grows to keep MAX_CELLS."""
    st = np.asarray(stations, dtype=float).reshape(-1, 3)
    if len(st) == 0:
        raise ValueError("no stations")
    if not (range_m > 0 and sigma_deg > 0):
        raise ValueError("range_m and sigma_deg must be positive")
    margin = float(range_m if margin_m is None else margin_m)
    e_lo, e_hi = st[:, 0].min() - margin, st[:, 0].max() + margin
    n_lo, n_hi = st[:, 1].min() - margin, st[:, 1].max() + margin
    step = float(step_m) if step_m else max(e_hi - e_lo, n_hi - n_lo) / 150.0
    step = max(step, 1.0)
    while math.ceil((e_hi - e_lo) / step) * math.ceil((n_hi - n_lo) / step) > MAX_CELLS:
        step *= 1.25
    nx, ny = max(1, math.ceil((e_hi - e_lo) / step)), max(1, math.ceil((n_hi - n_lo) / step))
    e = e_lo + step * (np.arange(nx) + 0.5)
    n = n_lo + step * (np.arange(ny) + 0.5)
    ee, nn = np.meshgrid(e, n)                                               # row = north index
    code, h_err, _, _ = assess(st, np.column_stack([ee.ravel(), nn.ravel()]), range_m=range_m, sigma_deg=sigma_deg,
                               height_m=height_m)
    cells = len(code)
    share = {CODE_NAMES[c]: round(float((code == c).sum()) / cells, 4) for c in (OUT, SINGLE, BLIND, OK)}
    return {
        "e0": round(float(e[0]), 1), "n0": round(float(n[0]), 1), "step_m": round(step, 2), "nx": nx, "ny": ny,
        "height_m": float(height_m), "range_m": float(range_m), "sigma_deg": float(sigma_deg),
        "min_crossing_deg": MIN_CROSSING_DEG, "max_error_m": MAX_ERROR_M,
        "codes": "".join(str(int(c)) for c in code),
        "h_err_m": [None if not np.isfinite(v) else int(round(float(v))) for v in h_err],
        "share": share,
    }

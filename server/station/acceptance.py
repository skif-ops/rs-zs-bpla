"""Acceptance metrics from a trial (decision 5 of docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md).

A trial is the server's event store over the trial window plus the ground truth of what flew (``dioneya.trial/1``,
docs/ACCEPTANCE_METRICS.md): the stations under test, the passes (class and GNSS log of each target), quiet periods
and exclusions, optionally the readings of a reference sound level meter at the stations.  From them:

* Pd per class: a station-pass is an opportunity when the target came within ``max_range_m`` of the station while it
  was operating; detected when the station reported it (a detection or a bearing associated with the pass); with the
  95 % Wilson interval, by closest-approach range and by the highest elevation of the pass;
* the range of the first report of every detected station-pass and the range up to which Pd stays at ``pd_threshold``;
* classification: the class of the first and the majority of the station's detections against the truth;
* false alarms: detections associated with no pass, grouped per station into episodes (gaps under ``episode_gap_s``),
  per operating station-hour and as a share of all alarms; separately in the quiet periods;
* bearing accuracy: every bearing (and every valid detection DOA) with trusted time against the direction to the
  target at the emission time; also whether the error stays within the sigma the station reported;
* fused track points against the truth at their (emission) time;
* the received level: the reference meter's SPL, and the level of the uploaded audio at the moment of detection
  when the calibration of the station's audio chain (dBFS of a 94 dB SPL calibrator) is given.

Sound is heard late: a report at arrival time ta is compared with the target where it was at te, ta = te + range / c.
"""
from __future__ import annotations

import csv
import json
import math
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from fusion.geodesy import EnuFrame
from station import geometry_coverage as geo
from station.schemas import TargetClass

FORMAT = "dioneya.trial/1"
SOUND_SPEED_MPS = 343.0
TRUSTED_TIME = ("GNSS_TIME_TRUSTED", "HOLDOVER")
CLASS_NAMES = frozenset(c.name for c in TargetClass if c != TargetClass.UNKNOWN)


class TrialError(ValueError):
    pass


@dataclass(frozen=True)
class Criteria:
    max_range_m: float = 3000.0          # a station-pass is an opportunity when the target came this close
    assoc_range_m: float = 3000.0        # a report belongs to a pass when the target was this close at emission
    assoc_margin_s: float = 5.0          # ... or up to this long before/after the logged track (clamped to its ends)
    episode_gap_s: float = 60.0          # unassociated detections of one station closer than this are one false alarm
    pd_threshold: float = 0.8
    range_bins_m: tuple[float, ...] = (0, 250, 500, 1000, 1500, 2000, 3000)
    elevation_bins_deg: tuple[float, ...] = (0, 15, 30, 45, 60, 90)
    level_bins_db: tuple[float, ...] = (30, 40, 45, 50, 55, 60, 70, 90)
    max_time_error_us: int = 200_000     # a detection DOA counts for the bearing accuracy with this time error or less
    sample_s: float = 1.0                # step of the truth track for ranges, elevations and geometry
    sigma_deg: float | None = None       # bearing sigma for the geometry (None: the median of the trial's bearings)
    audio_cal_dbfs_at_94: float | None = None   # dBFS this tool measures for a 94 dB SPL calibrator through the chain


# ---- time and the truth ---------------------------------------------------------------------------------------------

def parse_time_us(value) -> int:
    """Microseconds since the epoch from an integer (microseconds) or an ISO 8601 string (a 'Z' or an offset)."""
    if isinstance(value, bool):
        raise TrialError(f"bad time {value!r}")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00").replace("z", "+00:00")
        try:
            t = datetime.fromisoformat(text)
        except ValueError as exc:
            raise TrialError(f"bad time {value!r}") from exc
        if t.tzinfo is None:
            raise TrialError(f"time {value!r} has no time zone (give Z or an offset)")
        return int(round(t.astimezone(timezone.utc).timestamp() * 1e6))
    raise TrialError(f"bad time {value!r}")


def _interval(obj: dict, what: str) -> tuple[int, int]:
    try:
        t0, t1 = parse_time_us(obj["since"]), parse_time_us(obj["until"])
    except KeyError as exc:
        raise TrialError(f"{what} needs since and until") from exc
    if t1 <= t0:
        raise TrialError(f"{what}: until is not after since")
    return t0, t1


@dataclass
class TruthPass:
    pass_id: str
    target_class: str
    t_us: np.ndarray                     # sorted, int64
    enu: np.ndarray                      # n x 3
    note: str = ""

    @property
    def span(self) -> tuple[int, int]:
        return int(self.t_us[0]), int(self.t_us[-1])

    def position(self, t_us: float, margin_us: float = 0.0) -> np.ndarray | None:
        """The target at time t (linear between log points); within ``margin_us`` of the ends, the nearest end."""
        t0, t1 = self.span
        if t_us < t0 - margin_us or t_us > t1 + margin_us:
            return None
        t = min(max(t_us, t0), t1)
        return np.array([np.interp(t, self.t_us, self.enu[:, k]) for k in range(3)])


@dataclass
class Trial:
    name: str
    frame: EnuFrame
    stations: dict[int, np.ndarray]                       # ENU
    station_geo: dict[int, tuple[float, float, float]]
    window: tuple[int, int]
    operating: dict[int, list[tuple[int, int]]]
    passes: list[TruthPass]
    quiet: list[tuple[int, int]] = field(default_factory=list)
    exclude: list[tuple[int, int, int | None]] = field(default_factory=list)
    levels: dict[int, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)

    def operates(self, station: int, t_us: float) -> bool:
        if not any(a <= t_us <= b for a, b in self.operating[station]):
            return False
        return not any(a <= t_us <= b and (s is None or s == station) for a, b, s in self.exclude)


def _track_rows(p: dict, base: Path) -> list[dict]:
    if "track" in p:
        rows = p["track"]
    elif "track_csv" in p:
        path = (base / p["track_csv"]).resolve()
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    else:
        raise TrialError(f"pass {p.get('pass_id')!r} has neither track nor track_csv")
    out = []
    for r in rows:
        try:
            out.append({"t": parse_time_us(int(r["time"]) if str(r["time"]).strip().lstrip("-").isdigit() else r["time"]),
                        "lat": float(r["lat"]), "lon": float(r["lon"]), "alt": float(r["alt_msl_m"])})
        except KeyError as exc:
            raise TrialError(f"pass {p.get('pass_id')!r}: track rows need time, lat, lon, alt_msl_m") from exc
    return out


def load_trial(path: str | Path, store=None) -> Trial:
    """The ground truth of a trial; stations without a position in the file take it from the event store."""
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("format") != FORMAT:
        raise TrialError(f"not a {FORMAT} file")
    window = _interval(doc.get("window") or {}, "window")
    station_geo: dict[int, tuple[float, float, float]] = {}
    operating: dict[int, list[tuple[int, int]]] = {}
    for s in doc.get("stations") or []:
        sid = int(s["station_id"])
        if "lat" in s:
            station_geo[sid] = (float(s["lat"]), float(s["lon"]), float(s.get("alt_msl_m", 0.0)))
        else:
            pos = store.station_position(sid) if store is not None else None
            if pos is None:
                raise TrialError(f"station {sid}: no position in the file and none in the store")
            station_geo[sid] = pos
        operating[sid] = [_interval(o, f"station {sid} operating") for o in s["operating"]] if s.get("operating") else [window]
    if not station_geo:
        raise TrialError("no stations")
    lat0 = float(np.mean([g[0] for g in station_geo.values()]))
    lon0 = float(np.mean([g[1] for g in station_geo.values()]))
    alt0 = float(np.mean([g[2] for g in station_geo.values()]))
    frame = EnuFrame(lat0, lon0, alt0)
    stations = {sid: np.asarray(frame.to_enu(*g), dtype=float) for sid, g in station_geo.items()}
    passes = []
    seen = set()
    for p in doc.get("passes") or []:
        pid = str(p.get("pass_id") or "")
        if not pid or pid in seen:
            raise TrialError(f"pass id {pid!r} missing or repeated")
        seen.add(pid)
        cls = str(p.get("class") or "")
        if cls not in CLASS_NAMES:
            raise TrialError(f"pass {pid}: class {cls!r} is not one of {sorted(CLASS_NAMES)}")
        rows = sorted(_track_rows(p, path.parent), key=lambda r: r["t"])
        if len(rows) < 2:
            raise TrialError(f"pass {pid}: a track needs two points or more")
        t = np.array([r["t"] for r in rows], dtype=np.int64)
        if np.any(np.diff(t) <= 0):
            raise TrialError(f"pass {pid}: repeated track times")
        enu = np.array([frame.to_enu(r["lat"], r["lon"], r["alt"]) for r in rows], dtype=float)
        passes.append(TruthPass(pid, cls, t, enu, str(p.get("note") or "")))
    quiet = [_interval(q, "quiet period") for q in doc.get("quiet") or []]
    exclude = []
    for x in doc.get("exclude") or []:
        a, b = _interval(x, "exclusion")
        exclude.append((a, b, int(x["station_id"]) if x.get("station_id") is not None else None))
    levels: dict[int, list[tuple[int, float]]] = {}
    level_rows = list(doc.get("levels") or [])
    if doc.get("levels_csv"):
        with open((path.parent / doc["levels_csv"]).resolve(), newline="", encoding="utf-8") as f:
            level_rows += list(csv.DictReader(f))
    for r in level_rows:
        sid = int(r["station_id"])
        if sid not in stations:
            raise TrialError(f"level reading for station {sid}, which is not under test")
        t = r["time"]
        levels.setdefault(sid, []).append((parse_time_us(int(t) if str(t).strip().isdigit() else t), float(r["spl_db"])))
    lv = {sid: (np.array([a for a, _ in sorted(v)], dtype=np.int64), np.array([b for _, b in sorted(v)], dtype=float))
          for sid, v in levels.items()}
    return Trial(str(doc.get("name") or path.stem), frame, stations, station_geo, window, operating, passes, quiet,
                 exclude, lv)


# ---- geometry of sound ----------------------------------------------------------------------------------------------

def emission(p: TruthPass, station: np.ndarray, ta_us: float, margin_us: float) -> tuple[float, np.ndarray] | None:
    """(te_us, target ENU) for a sound heard at the station at ta: te = ta - range(te) / c."""
    te = float(ta_us)
    x = None
    for _ in range(12):
        x = p.position(te, margin_us)
        if x is None:
            return None
        te_next = ta_us - float(np.linalg.norm(x - station)) / SOUND_SPEED_MPS * 1e6
        if abs(te_next - te) < 100.0:
            te = te_next
            break
        te = te_next
    x = p.position(te, margin_us)
    return (te, x) if x is not None else None


def direction(station: np.ndarray, target: np.ndarray) -> tuple[float, float, float, float]:
    """(azimuth deg from north, elevation deg, slant range m, horizontal range m) from station to target."""
    v = target - station
    rho = math.hypot(v[0], v[1])
    return (math.degrees(math.atan2(v[0], v[1])) % 360.0, math.degrees(math.atan2(v[2], rho)),
            float(np.linalg.norm(v)), rho)


def wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


# ---- statistics ---------------------------------------------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def _stats(values) -> dict:
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if v.size == 0:
        return {"n": 0}
    return {"n": int(v.size), "min": round(float(v.min()), 2), "p10": round(float(np.percentile(v, 10)), 2),
            "median": round(float(np.median(v)), 2), "p90": round(float(np.percentile(v, 90)), 2),
            "max": round(float(v.max()), 2), "mean": round(float(v.mean()), 2)}


def _bin_label(edges, i) -> str:
    def fmt(x):
        return f"{x:g}"
    return f"{fmt(edges[i])}-{fmt(edges[i + 1])}"


def _bin_of(edges, x) -> int | None:
    for i in range(len(edges) - 1):
        if edges[i] <= x < edges[i + 1] or (i == len(edges) - 2 and x == edges[-1]):
            return i
    return None


def _pd_table(items, key, edges) -> list[dict]:
    rows = []
    for i in range(len(edges) - 1):
        sel = [it for it in items if _bin_of(edges, key(it)) == i]
        k = sum(1 for it in sel if it["detected"])
        rows.append({"bin": _bin_label(edges, i), "opportunities": len(sel), "detected": k,
                     "pd": round(k / len(sel), 4) if sel else None, "pd_ci95": wilson(k, len(sel))})
    return rows


def _bearing_stats(rows) -> dict:
    if not rows:
        return {"n": 0}
    az = np.array([abs(r["az_err_deg"]) for r in rows])
    signed = np.array([r["az_err_deg"] for r in rows])
    el = np.array([r["el_err_deg"] for r in rows])
    within = [abs(r["az_err_deg"]) <= r["sigma_deg"] for r in rows if r["sigma_deg"]]
    return {"n": len(rows), "abs_mean_deg": round(float(az.mean()), 2), "rms_deg": round(float(np.sqrt((signed ** 2).mean())), 2),
            "median_abs_deg": round(float(np.median(az)), 2), "p90_abs_deg": round(float(np.percentile(az, 90)), 2),
            "max_abs_deg": round(float(az.max()), 2), "bias_deg": round(float(signed.mean()), 2),
            "elevation_rms_deg": round(float(np.sqrt((el ** 2).mean())), 2),
            "within_sigma": round(float(np.mean(within)), 4) if within else None}


# ---- the audio level at a detection -------------------------------------------------------------------------------

def wav_level_dbfs(path: str | Path, start_s: float | None = None, seconds: float | None = None) -> float | None:
    """RMS level of a mono 16-bit WAV (or a part of it) in dBFS, a full-scale sine being 0 dBFS; DC removed."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise TrialError(f"{path}: only 16-bit WAV is measured")
        rate, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        a = 0 if start_s is None else max(0, int(round(start_s * rate)))
        b = n if seconds is None else min(n, a + int(round(seconds * rate)))
        if b - a < rate // 10:
            return None
        w.setpos(a)
        x = np.frombuffer(w.readframes(b - a), dtype="<i2").astype(float)
    x = x.reshape(-1, ch)[:, 0]
    x -= x.mean()
    rms = float(np.sqrt(np.mean(x * x)))
    return None if rms <= 0.0 else 20.0 * math.log10(rms / 32768.0) + 3.0103


def detection_level_db(store, station: int, event_id: int, event_time_us: int, cal_dbfs_at_94: float | None
                       ) -> dict | None:
    """Level of the second of uploaded audio around the detection time: dBFS, and dB SPL with the calibration."""
    for a in store.list_audio(station, event_id):
        start, dur = a.get("start_time_us"), a.get("duration_ms")
        if start is None or not dur:
            continue
        offset_s = (event_time_us - 500_000 - int(start)) / 1e6
        if offset_s < -0.25 or offset_s + 1.0 > dur / 1000.0 + 0.25:
            continue
        path = Path(a["path"])
        if not path.is_file():                     # a store moved since: the layout under its audio root
            path = Path(store.audio_root) / str(station) / str(event_id) / f"{a['segment']}.wav"
            if not path.is_file():
                continue
        dbfs = wav_level_dbfs(path, max(offset_s, 0.0), 1.0)
        if dbfs is None:
            continue
        return {"dbfs": round(dbfs, 1), "spl_db": round(dbfs - cal_dbfs_at_94 + 94.0, 1) if cal_dbfs_at_94 is not None else None}
    return None


def _reference_level(trial: Trial, station: int, t_us: float, tolerance_us: float = 5e6) -> float | None:
    lv = trial.levels.get(station)
    if lv is None or lv[0].size == 0:
        return None
    i = int(np.argmin(np.abs(lv[0] - t_us)))
    return float(lv[1][i]) if abs(lv[0][i] - t_us) <= tolerance_us else None


# ---- the evaluation -------------------------------------------------------------------------------------------------

def _reports(store, trial: Trial, crit: Criteria) -> list[dict]:
    """Detections and bearings of the stations under test in the window, as reports at arrival time."""
    t0, t1 = trial.window
    out = []
    for sid in trial.stations:
        for d in store.station_detections(sid, t0, t1):
            doa = d.doa if d.doa.valid else None
            trusted = d.gnss.expected_time_error_us <= crit.max_time_error_us
            out.append({"kind": "detection", "station_id": sid, "t_us": d.event_time_us, "event_id": d.event_id,
                        "label": d.classification.label, "f0_hz": d.features[0] if d.features else None,
                        "az": doa.azimuth_cdeg / 100.0 if doa else None, "el": doa.elevation_cdeg / 100.0 if doa else None,
                        "sigma": doa.sigma_cdeg / 100.0 if doa else None, "time_trusted": trusted})
        for b in store.list_bearings(station_id=sid, since_us=t0, until_us=t1, limit=50000):
            out.append({"kind": "bearing", "station_id": sid, "t_us": b["time_us"], "event_id": b["track_event_id"],
                        "label": None, "az": b["azimuth_deg"], "el": b["elevation_deg"], "sigma": b["sigma_deg"],
                        "time_trusted": b["time_trust"] in TRUSTED_TIME})
    out.sort(key=lambda r: (r["t_us"], r["station_id"], r["kind"]))
    return out


def _associate(trial: Trial, report: dict, crit: Criteria) -> tuple[TruthPass, float, np.ndarray] | None:
    st = trial.stations[report["station_id"]]
    best = None
    for p in trial.passes:
        hit = emission(p, st, report["t_us"], crit.assoc_margin_s * 1e6)
        if hit is None:
            continue
        rng = float(np.linalg.norm(hit[1] - st))
        if rng <= crit.assoc_range_m and (best is None or rng < best[0]):
            best = (rng, p, hit[0], hit[1])
    return (best[1], best[2], best[3]) if best else None


def _pass_samples(trial: Trial, p: TruthPass, sid: int, crit: Criteria) -> list[dict]:
    """The truth along a pass, every sample_s of emission time, as the station hears it."""
    st = trial.stations[sid]
    t0, t1 = p.span
    out = []
    for te in np.arange(t0, t1 + 1, crit.sample_s * 1e6):
        x = p.position(float(te))
        az, el, rng, rho = direction(st, x)
        ta = float(te) + rng / SOUND_SPEED_MPS * 1e6
        if trial.operates(sid, ta):
            out.append({"te": float(te), "ta": ta, "x": x, "range": rng, "rho": rho, "el": el})
    return out


def evaluate(store, trial: Trial, crit: Criteria = Criteria()) -> dict:
    reports = _reports(store, trial, crit)
    by_pair: dict[tuple[str, int], list[dict]] = {}
    unassociated: list[dict] = []
    bearing_rows: list[dict] = []
    excluded = 0
    for r in reports:
        if not trial.operates(r["station_id"], r["t_us"]):
            excluded += 1
            continue
        hit = _associate(trial, r, crit)
        if hit is None:
            if r["kind"] == "detection":
                unassociated.append(r)
            continue
        p, te, x = hit
        az, el, rng, rho = direction(trial.stations[r["station_id"]], x)
        r = dict(r, pass_id=p.pass_id, te=te, range=rng, rho=rho, el_truth=el, az_truth=az)
        by_pair.setdefault((p.pass_id, r["station_id"]), []).append(r)
        if r["az"] is not None and r["time_trusted"]:
            bearing_rows.append({"class": p.target_class, "station_id": r["station_id"], "kind": r["kind"],
                                 "az_err_deg": wrap180(r["az"] - az), "el_err_deg": r["el"] - el, "el_truth": el,
                                 "range_m": rng, "sigma_deg": r["sigma"] or 0.0})

    sigma_geo = crit.sigma_deg or (float(np.median([b["sigma_deg"] for b in bearing_rows if b["sigma_deg"]]))
                                   if any(b["sigma_deg"] for b in bearing_rows) else 3.0)
    st_ids = sorted(trial.stations)
    st_arr = np.array([trial.stations[s] for s in st_ids])

    pairs = []
    pass_info = []
    confusion: dict[str, dict[str, int]] = {}
    for p in trial.passes:
        for sid in st_ids:
            samples = _pass_samples(trial, p, sid, crit)
            if not samples:
                continue
            cpa = min(samples, key=lambda s: s["range"])
            in_range = [s for s in samples if s["range"] <= crit.assoc_range_m]
            reps = sorted(by_pair.get((p.pass_id, sid), []), key=lambda r: r["t_us"])
            labels = [r["label"] for r in reps if r["kind"] == "detection"]
            first = reps[0] if reps else None
            majority = max(labels, key=lambda lb: (labels.count(lb), -labels.index(lb))) if labels else None
            item = {
                "pass_id": p.pass_id, "class": p.target_class, "station_id": sid,
                "opportunity": cpa["range"] <= crit.max_range_m,
                "cpa_m": round(cpa["range"], 1), "cpa_elevation_deg": round(cpa["el"], 1),
                "max_elevation_deg": round(max(s["el"] for s in in_range), 1) if in_range else None,
                "detected": bool(reps), "reports": len(reps),
                "detections": len(labels), "bearings": sum(1 for r in reps if r["kind"] == "bearing"),
                "first_report_us": first["t_us"] if first else None,
                "first_range_m": round(first["range"], 1) if first else None,
                "first_elevation_deg": round(first["el_truth"], 1) if first else None,
                "first_label": labels[0] if labels else None, "majority_label": majority,
                "elevations_heard_deg": [round(min(r["el_truth"] for r in reps), 1), round(max(r["el_truth"] for r in reps), 1)] if reps else None,
                "reference_spl_at_first_db": _reference_level(trial, sid, first["t_us"]) if first else None,
                "reference_spl_max_db": max((v for v in (_reference_level(trial, sid, s["ta"]) for s in in_range) if v is not None), default=None),
            }
            lvl = None                                  # the level of the uploaded audio of its first detection
            for r in reps:
                if r["kind"] == "detection":
                    lvl = detection_level_db(store, sid, r["event_id"], r["t_us"], crit.audio_cal_dbfs_at_94)
                    if lvl:
                        break
            item["audio_level_at_detection"] = lvl
            pairs.append(item)
            if item["opportunity"] and item["detected"]:
                key = item["first_label"] or "BEARING_ONLY"
                confusion.setdefault(p.target_class, {})
                confusion[p.target_class][key] = confusion[p.target_class].get(key, 0) + 1
        # geometry along the pass for all stations: where the target was, could the stations give it a point?
        xs = np.array([p.position(float(te)) for te in np.arange(p.span[0], p.span[1] + 1, crit.sample_s * 1e6)])
        codes, _, _, _ = geo.assess(st_arr, xs, range_m=crit.assoc_range_m, sigma_deg=sigma_geo)
        pass_info.append({"pass_id": p.pass_id, "class": p.target_class, "since_us": p.span[0], "until_us": p.span[1],
                          "geometry_share": {geo.CODE_NAMES[c]: round(float(np.mean(codes == c)), 4)
                                             for c in (geo.OUT, geo.SINGLE, geo.BLIND, geo.OK)}})

    classes = sorted({p.target_class for p in trial.passes})
    summary = {}
    for cls in classes + ["ALL"]:
        sel = [it for it in pairs if it["opportunity"] and (cls == "ALL" or it["class"] == cls)]
        det = [it for it in sel if it["detected"]]
        k, n = len(det), len(sel)
        firsts = [it for it in det if it["first_label"]]
        correct_first = sum(1 for it in firsts if it["first_label"] == it["class"])
        correct_major = sum(1 for it in firsts if it["majority_label"] == it["class"])
        # range at Pd >= threshold: the largest bin edge such that the station-passes closer than it keep Pd there
        range_at = None
        for edge in crit.range_bins_m[1:]:
            inner = [it for it in sel if it["cpa_m"] <= edge]
            if inner and sum(1 for it in inner if it["detected"]) / len(inner) >= crit.pd_threshold:
                range_at = edge
            elif inner:
                break
        bear = [b for b in bearing_rows if cls == "ALL" or b["class"] == cls]
        by_el = []
        for i in range(len(crit.elevation_bins_deg) - 1):
            rows = [b for b in bear if _bin_of(crit.elevation_bins_deg, max(b["el_truth"], 0.0)) == i]
            by_el.append({"bin": _bin_label(crit.elevation_bins_deg, i), **_bearing_stats(rows)})
        heard = [e for it in det for e in (it["elevations_heard_deg"] or [])]
        ref_first = [it["reference_spl_at_first_db"] for it in det if it["reference_spl_at_first_db"] is not None]
        audio = [it["audio_level_at_detection"] for it in det if it.get("audio_level_at_detection")]
        level_rows = [it for it in sel if it["reference_spl_max_db"] is not None]
        summary[cls] = {
            "passes": sum(1 for p in trial.passes if cls == "ALL" or p.target_class == cls),
            "opportunities": n, "detected": k, "pd": round(k / n, 4) if n else None, "pd_ci95": wilson(k, n),
            "classified": len(firsts),
            "p_correct_class_first": round(correct_first / len(firsts), 4) if firsts else None,
            "p_correct_class_majority": round(correct_major / len(firsts), 4) if firsts else None,
            "p_correct_class_ci95": wilson(correct_first, len(firsts)),
            "first_report_range_m": _stats([it["first_range_m"] for it in det]),
            "pd_by_cpa_range": _pd_table(sel, lambda it: it["cpa_m"], crit.range_bins_m),
            "range_at_pd_m": range_at, "pd_threshold": crit.pd_threshold,
            "elevation_heard_deg": [min(heard), max(heard)] if heard else None,
            "pd_by_max_elevation": _pd_table([it for it in sel if it["max_elevation_deg"] is not None],
                                             lambda it: max(it["max_elevation_deg"], 0.0), crit.elevation_bins_deg),
            "bearing_error": _bearing_stats(bear),
            "bearing_error_by_elevation": by_el,
            "reference_spl_at_first_db": _stats(ref_first),
            "pd_by_reference_spl_max": _pd_table(level_rows, lambda it: it["reference_spl_max_db"], crit.level_bins_db) if level_rows else [],
            "audio_level_at_detection_dbfs": _stats([a["dbfs"] for a in audio]),
            "audio_level_at_detection_spl_db": _stats([a["spl_db"] for a in audio if a["spl_db"] is not None]),
        }

    # false alarms: unassociated detections, per station in episodes
    def episodes(rows):
        out = []
        for sid in st_ids:
            ts = sorted(r["t_us"] for r in rows if r["station_id"] == sid)
            start = None
            last = None
            for t in ts:
                if last is None or t - last > crit.episode_gap_s * 1e6:
                    if start is not None:
                        out.append((sid, start, last))
                    start = t
                last = t
            if start is not None:
                out.append((sid, start, last))
        return out

    def station_hours(intervals=None) -> float:
        total = 0.0
        for sid in st_ids:
            for a, b in trial.operating[sid]:
                spans = [(max(a, q0), min(b, q1)) for q0, q1 in intervals] if intervals is not None else [(a, b)]
                for x0, x1 in spans:
                    if x1 <= x0:
                        continue
                    ex = sum(max(0, min(x1, e1) - max(x0, e0)) for e0, e1, s in trial.exclude if s is None or s == sid)
                    total += max(0.0, (x1 - x0 - ex) / 3.6e9)
        return total

    false_eps = episodes(unassociated)
    hours = station_hours()
    quiet_rows = [r for r in unassociated if any(a <= r["t_us"] <= b for a, b in trial.quiet)]
    quiet_eps = episodes(quiet_rows)
    quiet_hours = station_hours(trial.quiet) if trial.quiet else 0.0
    detected_pairs = sum(1 for it in pairs if it["detected"])
    by_label: dict[str, int] = {}
    for r in unassociated:
        by_label[r["label"]] = by_label.get(r["label"], 0) + 1
    false_alarms = {
        "station_hours": round(hours, 3), "episodes": len(false_eps),
        "per_station_hour": round(len(false_eps) / hours, 4) if hours > 0 else None,
        "detections": len(unassociated),
        "false_share": round(len(false_eps) / (len(false_eps) + detected_pairs), 4) if (false_eps or detected_pairs) else None,
        "by_station": {str(s): sum(1 for e in false_eps if e[0] == s) for s in st_ids},
        "by_label": dict(sorted(by_label.items())),
        "quiet": {"station_hours": round(quiet_hours, 3), "episodes": len(quiet_eps),
                  "per_station_hour": round(len(quiet_eps) / quiet_hours, 4) if quiet_hours > 0 else None},
        "list": [{"station_id": s, "since_us": a, "until_us": b} for s, a, b in false_eps],
    }

    localization = _localization(store, trial, crit)
    geometry_range = summary["ALL"]["range_at_pd_m"] or crit.assoc_range_m
    grid = geo.coverage_grid(st_arr, range_m=geometry_range, sigma_deg=sigma_geo,
                             height_m=float(np.median([np.median(p.enu[:, 2]) for p in trial.passes])) if trial.passes else 0.0)
    return {
        "format": "dioneya.acceptance/1", "trial": trial.name,
        "window": {"since_us": trial.window[0], "until_us": trial.window[1]},
        "criteria": {k: (list(v) if isinstance(v, tuple) else v) for k, v in crit.__dict__.items()},
        "stations": {str(s): {"lat": g[0], "lon": g[1], "alt_msl_m": g[2]} for s, g in sorted(trial.station_geo.items())},
        "summary": summary, "confusion": confusion, "false_alarms": false_alarms, "localization": localization,
        "geometry": {"range_m": geometry_range, "sigma_deg": round(sigma_geo, 2), "height_m": grid["height_m"],
                     "share": grid["share"], "step_m": grid["step_m"]},
        "reports_outside_operation": excluded,
        "passes": pass_info,
        "station_passes": pairs,
    }


def _localization(store, trial: Trial, crit: Criteria) -> dict:
    """Fused track points against the truth at their emission time."""
    t0, t1 = trial.window
    errs, verrs, within, false_points = [], [], [], 0
    by_class: dict[str, list[float]] = {}
    for summary in store.list_tracks(since_us=t0, until_us=t1, limit=10000):
        track = store.get_track(summary["track_id"])
        for pt in (track or {}).get("track_points") or []:
            x = np.asarray(trial.frame.to_enu(pt["lat"], pt["lon"], pt["alt_msl_m"]), dtype=float)
            best = None
            for p in trial.passes:
                tx = p.position(pt["time_us"], crit.assoc_margin_s * 1e6)
                if tx is None:
                    continue
                d = float(np.hypot(*(x[:2] - tx[:2])))
                if best is None or d < best[0]:
                    best = (d, p, tx)
            if best is None or best[0] > geo.MAX_ERROR_M:
                false_points += 1
                continue
            d, p, tx = best
            errs.append(d)
            verrs.append(abs(float(x[2] - tx[2])))
            within.append(d <= float(pt["horizontal_error_m"]))
            by_class.setdefault(p.target_class, []).append(d)
    return {"points": len(errs), "false_points": false_points, "horizontal_error_m": _stats(errs),
            "vertical_error_m": _stats(verrs), "within_reported_error": round(float(np.mean(within)), 4) if within else None,
            "by_class": {c: _stats(v) for c, v in sorted(by_class.items())}}


# ---- the report in words ------------------------------------------------------------------------------------------

def _fmt(x, unit="", digits=2):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{digits}f}{unit}"
    return f"{x}{unit}"


def _ci(ci):
    return "—" if not ci else f"{ci[0]:.2f}…{ci[1]:.2f}"


def markdown(result: dict) -> str:
    s = result["summary"]
    lines = [f"# Метрики приёмки: {result['trial']}", "",
             f"Станции: {', '.join(result['stations'])}. Критерии: возможность обнаружения — цель подходила ближе "
             f"{result['criteria']['max_range_m']:g} м к работающей станции; отметка относится к проходу, если цель была "
             f"ближе {result['criteria']['assoc_range_m']:g} м в момент излучения звука.", "",
             "## Обнаружение по классам", "",
             "| Класс | Проходов | Возможностей | Обнаружено | Pd | 95 % ДИ | Верный класс (первый) | Дальность первой отметки, медиана / макс, м | Дальность при Pd ≥ "
             f"{result['criteria']['pd_threshold']:g}, м | Угол места отметок, ° |",
             "|---|---:|---:|---:|---:|---|---:|---|---:|---|"]
    for cls, v in s.items():
        fr = v["first_report_range_m"]
        el = v["elevation_heard_deg"]
        lines.append(f"| {cls} | {v['passes']} | {v['opportunities']} | {v['detected']} | {_fmt(v['pd'])} | {_ci(v['pd_ci95'])} | "
                     f"{_fmt(v['p_correct_class_first'])} | {_fmt(fr.get('median'), digits=0)} / {_fmt(fr.get('max'), digits=0)} | "
                     f"{_fmt(v['range_at_pd_m'])} | {'—' if not el else f'{el[0]:.0f}…{el[1]:.0f}'} |")
    a = s.get("ALL", {})
    lines += ["", "## Pd по дальности наибольшего сближения (все классы)", "", "| Дальность, м | Возможностей | Обнаружено | Pd | 95 % ДИ |",
              "|---|---:|---:|---:|---|"]
    for r in a.get("pd_by_cpa_range", []):
        lines.append(f"| {r['bin']} | {r['opportunities']} | {r['detected']} | {_fmt(r['pd'])} | {_ci(r['pd_ci95'])} |")
    lines += ["", "## Pd по наибольшему углу места прохода (все классы)", "", "| Угол места, ° | Возможностей | Обнаружено | Pd |",
              "|---|---:|---:|---:|"]
    for r in a.get("pd_by_max_elevation", []):
        lines.append(f"| {r['bin']} | {r['opportunities']} | {r['detected']} | {_fmt(r['pd'])} |")
    fa = result["false_alarms"]
    lines += ["", "## Ложные тревоги", "",
              f"Станцио-часов работы: {fa['station_hours']:g}; эпизодов ложных тревог: {fa['episodes']} "
              f"({_fmt(fa['per_station_hour'], ' в час на станцию', 3)}); доля ложных среди всех тревог: {_fmt(fa['false_share'], digits=3)}. "
              f"В тихие периоды: {fa['quiet']['episodes']} за {fa['quiet']['station_hours']:g} станцио-ч.",
              f"Классы ложных обнаружений: {', '.join(f'{k} {v}' for k, v in fa['by_label'].items()) or '—'}."]
    be = a.get("bearing_error", {})
    lines += ["", "## Точность пеленга (все классы)", ""]
    if be.get("n"):
        lines.append(f"Пеленгов: {be['n']}; азимут: средняя абсолютная ошибка {be['abs_mean_deg']}°, СКО {be['rms_deg']}°, "
                     f"медиана {be['median_abs_deg']}°, 90 % — {be['p90_abs_deg']}°, смещение {be['bias_deg']}°; угол места СКО "
                     f"{be['elevation_rms_deg']}°; в пределах заявленной станцией сигмы: {_fmt(be['within_sigma'], digits=2)}.")
        lines += ["", "| Угол места цели, ° | Пеленгов | Средняя абс., ° | СКО, ° | 90 %, ° |", "|---|---:|---:|---:|---:|"]
        for r in a.get("bearing_error_by_elevation", []):
            lines.append(f"| {r['bin']} | {r['n']} | {_fmt(r.get('abs_mean_deg'))} | {_fmt(r.get('rms_deg'))} | {_fmt(r.get('p90_abs_deg'))} |")
    else:
        lines.append("Пеленгов с доверенным временем нет.")
    loc = result["localization"]
    he = loc["horizontal_error_m"]
    lines += ["", "## Точки общего трека", "",
              (f"Точек: {loc['points']} (ложных {loc['false_points']}); ошибка по горизонтали: медиана {he['median']} м, 90 % — {he['p90']} м, "
               f"макс. {he['max']} м; в пределах заявленной ошибки: {_fmt(loc['within_reported_error'], digits=2)}.")
              if loc["points"] else f"Точек нет (ложных {loc['false_points']})."]
    ref, aud = a.get("reference_spl_at_first_db", {}), a.get("audio_level_at_detection_spl_db", {})
    audf = a.get("audio_level_at_detection_dbfs", {})
    lines += ["", "## Уровень звука при обнаружении", "",
              f"По эталонному шумомеру (первая отметка): {('мин. ' + str(ref['min']) + ' дБ SPL, медиана ' + str(ref['median'])) if ref.get('n') else 'нет данных'}.",
              f"По записи станции: {('мин. ' + str(aud['min']) + ' дБ SPL, медиана ' + str(aud['median'])) if aud.get('n') else ('только дБFS: мин. ' + str(audf['min']) if audf.get('n') else 'нет записей')}."]
    g = result["geometry"]
    lines += ["", "## Геометрия расстановки", "",
              f"Для дальности {g['range_m']:g} м, сигмы пеленга {g['sigma_deg']}° и высоты цели {g['height_m']:.0f} м: доля площади "
              f"(прямоугольник станций плюс дальность) с точкой — {g['share']['position']:.2f}, слепая геометрия — "
              f"{g['share']['blind_geometry']:.2f}, одна станция — {g['share']['single_station']:.2f}, вне слышимости — "
              f"{g['share']['out_of_range']:.2f}.", ""]
    return "\n".join(lines)

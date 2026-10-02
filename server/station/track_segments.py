"""Segments of a station track: where a station's bearing stream switches from one target to another.

A station tracks whatever it hears loudest.  With two targets in the air its tracking window stays open (the level
stays CONFIRMED) while the bearing jumps from the first target to the second; the window's track event id does not
change.  Fused as one station track, such a stream would pull a fused track from one target to the other and leave
the second target without a track.  The server therefore splits every station track into segments at sustained
bearing jumps and associates segments, not whole tracks (station/track_hypotheses.py).

The split follows the bearings in time order:

- every active segment (a bearing within the last ACTIVE_S seconds) predicts the next bearing from its recent
  bearings: a robust straight line (Theil-Sen) through the last PREDICT_S seconds, at least three bearings over a
  second; otherwise their median;
- a bearing within the tolerance of a prediction (JUMP_MIN_DEG or 4 sigma, wider after a gap in the stream)
  continues the segment that predicts it best; a station alternating between two targets keeps two segments;
- a bearing outside all of them waits; NEW_SEGMENT_BEARINGS waiting bearings (within WAIT_S) that agree with each other over at least
  NEW_SEGMENT_MIN_S start a new segment at the first of them;
- waiting bearings that never form a segment (single outliers, reflections) belong to no segment and are not fused;
- a bearing the station itself gives a sigma above MAX_SIGMA_DEG (its array heard no single clear direction, e.g.
  two targets at once) takes no part: with its wide tolerance it would join any segment and tilt the prediction,
  and the fusion would give it next to no weight anyway;
- nor does a bearing the station gives a confidence below MIN_CONFIDENCE (a direction bearing of fewer than two bins
  of its own, zs_doa_sep.h; a comb bearing whose pairs barely agree): two targets of one engine note heard at once
  give such bearings between them, steady enough to form a segment whose rays cross the others' in ghost points
  (twin field, three targets of 185 Hz 100..300 m apart: 24..47 ghost points of 180 s, 0..4 without them);
- a bearing that names the fundamental of its source (bearing batch schema 2: a station hearing several targets at
  once sends one bearing per source, zs_comb_bearing.h) continues only a segment whose last named fundamental is
  within F0_STEP of it (more after a gap: Doppler moves the pitch of a pass by a few per cent a second), and waiting
  bearings form a new segment only with waiting bearings of the same fundamental.  So the bearings of two or three
  targets a station hears at the same time make two or three segments, also where their directions cross.  Bearings
  without a fundamental (schema 1) follow the direction alone, as before.

A target passing close to the station turns the bearing fast but smoothly: the straight-line prediction follows it.
The decisions depend on earlier bearings only, so segments found once stay as they are when later batches arrive.
A segment is named by the time of its first bearing (plus 1 us for each earlier segment starting at the same time:
several sources start together); the first segment of a track by 0 (FIRST_SEGMENT), so a fused track stored before
segments existed keeps its members.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

FIRST_SEGMENT = 0
PREDICT_S = 2.0                 # the prediction fits the bearings of the last 2 s of the segment (a close pass curves)
PREDICT_MAX = 5
JUMP_MIN_DEG = 12.0             # tolerance of a continuing bearing: at least 12 deg or 4 sigma
JUMP_SIGMA = 4.0
GAP_SLACK_DEG_PER_S = 3.0       # after a gap in the stream the tolerance grows by 3 deg per second beyond the first
NEW_SEGMENT_BEARINGS = 4        # waiting bearings that agree with each other start a new segment...
NEW_SEGMENT_MIN_S = 1.0         # ...when they span at least a second
AGREE_MIN_DEG = 8.0             # waiting bearings agree within 8 deg or 3 sigma of their own line
WAIT_S = 6.0                    # a bearing waits this long for others to agree with it
ACTIVE_S = 6.0                  # a segment without a bearing for 6 s takes no more (the station window: 3 s)
MAX_RATE_DEG_S = 30.0           # the prediction never turns faster (a target 100 m away at 50 m/s: 29 deg/s)
MAX_SIGMA_DEG = 10.0            # bearings less certain than this belong to no segment
MIN_CONFIDENCE = 0.2            # nor bearings the station gives so little confidence (its bins do not agree)
F0_STEP = 0.05                  # a bearing's fundamental within 5 % of the segment's last one...
F0_STEP_PER_S = 0.05            # ...plus 5 % per second of gap (Doppler of a close pass: up to ~7 %/s)


def wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


@dataclass
class Segment:
    key: int                                    # FIRST_SEGMENT or the time of the first bearing, us
    rows: list[dict] = field(default_factory=list)
    formed_us: int | None = None                # the bearing whose arrival made it a segment (None: the first one)

    @property
    def known_since_us(self) -> int:
        """Time of the bearing from which the segment exists: the bearings before it were still waiting."""
        return self.rows[0]["time_us"] if self.formed_us is None else self.formed_us

    @property
    def first_us(self) -> int:
        return self.rows[0]["time_us"]

    @property
    def last_us(self) -> int:
        return self.rows[-1]["time_us"]

    @property
    def f0_hz(self) -> float | None:
        """Median fundamental of the bearings that name one (None: none does)."""
        f0s = [r["f0_hz"] for r in self.rows if r.get("f0_hz")]
        return float(np.median(f0s)) if f0s else None

    def last_f0(self) -> tuple[float, int] | None:
        """(fundamental, time) of the last bearing that names one."""
        for r in reversed(self.rows):
            if r.get("f0_hz"):
                return r["f0_hz"], r["time_us"]
        return None


def _line(rows: list[dict]) -> tuple[float, float, float]:
    """(reference time s, azimuth at it, slope deg/s): a robust line through the bearings (Theil-Sen slope, median
    intercept), the azimuths unwrapped around their median, so one outlier does not tilt it."""
    t = np.array([r["time_us"] for r in rows], dtype=float) * 1e-6
    a = np.array([r["azimuth_deg"] for r in rows])
    ref = float(a[-1])
    a = ref + np.array([wrap(x - ref) for x in a])
    ref = float(np.median(a))
    a = ref + np.array([wrap(x - ref) for x in a])
    t0 = float(t[-1])
    slope = 0.0
    if len(rows) >= 3 and t[-1] - t[0] >= 1.0:
        i, j = np.triu_indices(len(rows), 1)
        dt = t[j] - t[i]
        ok = dt > 0.2
        if ok.any():
            slope = float(np.clip(np.median((a[j] - a[i])[ok] / dt[ok]), -MAX_RATE_DEG_S, MAX_RATE_DEG_S))
    return t0, float(np.median(a - slope * (t - t0))), slope


def _predict(history: list[dict], time_us: int) -> float:
    last = history[-1]["time_us"]
    recent = [r for r in history[-PREDICT_MAX:] if last - r["time_us"] <= PREDICT_S * 1e6]
    t0, a0, slope = _line(recent)
    return a0 + slope * (time_us * 1e-6 - t0)


def _tolerance(row: dict, gap_s: float) -> float:
    return max(JUMP_MIN_DEG, JUMP_SIGMA * row["sigma_deg"]) + GAP_SLACK_DEG_PER_S * max(0.0, gap_s - 1.0)


def _f0_close(a: float | None, b: float | None, gap_s: float) -> bool:
    if not a or not b:
        return True
    return abs(a - b) <= (F0_STEP + F0_STEP_PER_S * max(0.0, gap_s)) * min(a, b)


def _same_source(segment: Segment, row: dict) -> bool:
    last = segment.last_f0()
    if last is None or not row.get("f0_hz"):
        return True
    return _f0_close(last[0], row["f0_hz"], (row["time_us"] - last[1]) * 1e-6)


def _agree(rows: list[dict]) -> bool:
    if len(rows) < 2:
        return True
    t0, a0, slope = _line(rows)
    return all(abs(wrap(r["azimuth_deg"] - (a0 + slope * (r["time_us"] * 1e-6 - t0)))) <= max(AGREE_MIN_DEG, 3.0 * r["sigma_deg"])
               for r in rows)


def split(rows: list[dict]) -> list[Segment]:
    """The segments of one station track's bearings (any order; sorted by time here).  Up to MAX_ACTIVE segments
    run at once (a station whose bearing alternates between two targets): a bearing joins the active segment that
    predicts it best."""
    rows = sorted((r for r in rows if r["sigma_deg"] <= MAX_SIGMA_DEG and r.get("confidence", 1.0) >= MIN_CONFIDENCE),
                  key=lambda r: (r["time_us"], r.get("f0_hz") or 0.0))
    if not rows:
        return []
    segments = [Segment(FIRST_SEGMENT, [rows[0]])]
    waiting: list[dict] = []
    for row in rows[1:]:
        best = None
        for seg in segments:
            gap_s = (row["time_us"] - seg.last_us) * 1e-6
            if gap_s > ACTIVE_S or seg.last_us == row["time_us"] or not _same_source(seg, row):
                continue                                         # one bearing per segment and window
            residual = abs(wrap(row["azimuth_deg"] - _predict(seg.rows, row["time_us"])))
            if residual <= _tolerance(row, gap_s) and (best is None or residual < best[0]):
                best = (residual, seg)
        waiting = [w for w in waiting if row["time_us"] - w["time_us"] <= WAIT_S * 1e6]
        if best is not None:
            best[1].rows.append(row)
            continue
        waiting.append(row)
        # the waiting bearings of this bearing's source (all of them when the bearings name none)
        group = [w for w in waiting if _f0_close(w.get("f0_hz"), row.get("f0_hz"), (row["time_us"] - w["time_us"]) * 1e-6)
                 and (w is row or w["time_us"] != row["time_us"])]
        while not _agree(group):
            waiting.remove(group.pop(0))
        if len(group) >= NEW_SEGMENT_BEARINGS and (group[-1]["time_us"] - group[0]["time_us"]) * 1e-6 >= NEW_SEGMENT_MIN_S:
            key = group[0]["time_us"]
            while any(s.key == key for s in segments):
                key += 1                                         # several sources start at the same time
            segments.append(Segment(key, group, formed_us=row["time_us"]))
            waiting = [w for w in waiting if not any(w is g for g in group)]
    return segments


def segment_at(segments: list[Segment], time_us: int, f0_hz: float | None = None) -> Segment | None:
    """The segment holding the bearing of this time (and source, when several share the time; None: an outlier or a
    bearing still waiting)."""
    for s in segments:
        if any(r["time_us"] == time_us and (f0_hz is None or (r.get("f0_hz") or None) == f0_hz) for r in s.rows):
            return s
    return None


def by_key(segments: list[Segment], key: int) -> Segment | None:
    return next((s for s in segments if s.key == key), None)

"""Association of station tracks into fused target tracks with several hypotheses and a deferred decision (decision 2
of docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md; docs/SERVER_SAME_TYPE_TARGETS_2026-10-02.md, variant "в").

The unit of association is a segment of a station track (station/track_segments.py): the bearings one station gives
of one target.  Rays of stations hearing different targets cross in ghost points, and two targets of one type and
engine note (target_match.compatible) are told apart by geometry only.  Instead of pairing segments once and for all,
the server keeps every explanation open and decides on a moving window:

1. Steps.  The decision is taken once a second of bearing time (a step), up to the time to which at least two stations
   have sent their bearings (stations more than LAG_S behind those two do not hold the steps back).  A step uses only
   the bearings up to its time, and a segment only from the bearing that made it a segment, so the decisions do not
   depend on the order in which the stations' batches arrive.
2. Hypotheses.  Every combination of active segments (a bearing within track_segments.ACTIVE_S) of two to four
   stations that may hear one target (target_match) is a hypothesis.  Its rays are intersected on the 1 s grid of
   emission times of the last WINDOW_S seconds (fusion/bearing_fusion.py: each station's bearing at emission +
   range / c); bearings off their segment's own course (own_course) are left out.  A point counts for the hypothesis
   when the stations agree on the height (HEIGHT_AGREE_SIGMA) and, with three or more stations, when the rays meet
   (their lateral misses, in each ray's sigma, give a chi-square within CHI2_PER_DOF per degree of freedom): rays of
   three stations meet in a ghost only by chance.  The score is the number of rays the hypothesis explains, less the
   rays that disagree, less a penalty for a path no straight or gently curving flight gives (KINEMATIC_LIMIT).
3. Ambiguity of two stations.  Two stations that each hear two like targets at once always offer two explanations:
   rays 1-1 and 2-2, or 1-2 and 2-1.  The explanation a station pair cannot see (its rays almost parallel: the true one
   when the targets are far beyond the pair) gives no points, and the ghost wins by default.  A pair of segments is
   therefore taken only when no other segment of its stations, paired with the other one, is "unrefuted": rays that
   cross ahead of both stations, or are too parallel to tell.  An ambiguous pair only continues a track a well
   conditioned triple confirmed less than CONTINUE_S seconds ago.
4. Global choice.  The set of hypotheses with the largest total score in which no segment takes part twice is the
   explanation of the step.
5. Deferred decision and continuity.  A hypothesis continues the track whose current segments it shares most (one to
   one), when its new points pass the gate of that track's prediction (constant-velocity Kalman filter); otherwise it
   is dropped.  A new hypothesis becomes a track only after it has been the choice for PUBLISH_STEPS steps in a row
   (WEAK_PUBLISH_STEPS when a station gives one of its segments little confidence; such a segment takes part only
   in a well conditioned hypothesis with two other stations' sure segments, or in an unambiguous pair continuing a
   track of its segments).  Three or more stations make a new track when they are well conditioned
   (STRONG_FIXES points meeting with a horizontal error up to STRONG_ERROR_M); far away the rays of three stations meet
   by chance too, and such a hypothesis is then taken only as its pairs would be (rule 3).  The new track then shows the
   points of the last BACKFILL_S seconds; every further point is gated against the track's prediction and filtered
   (REGATE_POINTS points of the track's own segments in a row off the prediction restart the filter); rays that
   disagree (rule 2) give no point.  A point is never rewritten: a ghost a track once showed stays in its history as
   it was shown.  A track without a new point for TRACK_IDLE_S is over and frees its segments.

A point is ``ambiguous`` (dioneya.alert/1) when it comes from an ambiguous pair (rule 3): only the continuity of the
track says which crossing is the target.  Only bearings with trusted station time are fused.  The state of the
decision (the tracks' segments and filters, the hypotheses waiting) is kept in the database (``fusion_state``).
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np

from fusion.bearing_fusion import (MAX_ERROR_M, MAX_RANGE_M, MAX_SAMPLE_GAP_S, MIN_CROSSING_DEG, SPEED_OF_SOUND_MPS,
                                   StationBearings, _crossing_deg, _direction, intersect)
from fusion.geodesy import EnuFrame
from fusion.kalman import ConstantVelocityKalman3D
from station import target_match, track_segments

TRUSTED_TIME = ("GNSS_TIME_TRUSTED", "HOLDOVER")
STATE = "track_hypotheses"
C = SPEED_OF_SOUND_MPS
STEP_US = 1_000_000
WINDOW_S = 20.0                  # the evidence of a hypothesis: emission times of the last 20 s (+ range / c)
LAG_S = 5.0                      # a station this far behind the second latest one does not hold the steps back
CATCH_UP_STEPS = 120             # steps one batch may advance (a gap in the stream is jumped)
MAX_STATIONS = 4                 # hypotheses of up to four stations
MAX_UNITS_PER_STATION = 4        # the latest segments of a station taken into account
MAX_CANDIDATES = 64              # the best hypotheses competing in the global choice
MIN_FIXES = 3                    # a hypothesis needs this many points in its window
HEIGHT_AGREE_SIGMA = 3.0         # the stations agree on the height within 3 sigma...
CHI2_PER_DOF = 9.0               # ...and three or more rays meet within 3 sigma (chi-square per degree of freedom)
KINEMATIC_LIMIT = 3.0            # rms miss of a quadratic path, in the points' horizontal errors
RIVAL_MIN_S = 5.0                # a rival segment counts when it overlaps the pair this long
RIVAL_REFUTED = 0.5              # a rival pairing is refuted when its rays cross behind a station or out of range this often
PUBLISH_STEPS = 5                # a new track: the choice of five steps in a row...
WEAK_CONFIDENCE = 0.5            # ...or, when a station gives one of its segments less confidence than this (median of
WEAK_PUBLISH_STEPS = 12          # its recent bearings: its bins or comb pairs barely agree), of twelve steps
STRONG_FIXES = 5                 # ...with three or more stations, this many meeting points...
STRONG_ERROR_M = 300.0           # ...of this horizontal error (median) or better
CONTINUE_S = 20.0                # an ambiguous pair continues a track confirmed this recently
GATE_CHI2 = 13.8                 # gate of the prediction (two degrees of freedom, 99.9 %)
GATE_MIN_M = 30.0
REGATE_POINTS = 3                # three points of the track's own segments in a row off the prediction restart the filter
BACKFILL_S = 15.0                # a new track shows the points of its last 15 s (+ range / c)
RANGE_GUESS_M = 2000.0           # first range of the iteration on the sound delay
TRACK_IDLE_S = 20.0              # a track without a new point this long is over (the output API ends it a little later:
                                 # integration/alert_producer.TRACK_END_US); a later hypothesis of its segments is a new track
KALMAN_ACCEL = 6.0
Member = tuple[int, int, int]    # station_id, track event id, segment key
OWN_LINE_S = 3.0                 # a bearing off its segment's own course (robust line of the bearings 3 s around it)...
OWN_LINE_DEG = 8.0               # ...by more than 8 deg or 3 sigma is another target's: a segment that alternates


def own_course(rows: list[dict], known: dict[tuple, bool] | None = None) -> list[dict]:
    """The bearings that follow the segment's own course.  A station hearing two targets close in direction may give
    the bearings of both in one segment, alternating; the robust line through the bearings around each one follows
    the target the segment mostly hears, and the other target's bearings are left out of the rays.  ``known`` keeps
    the decisions of bearings whose surroundings are all in."""
    if len(rows) < 5:
        return rows
    times = np.array([r["time_us"] for r in rows], dtype=np.int64)
    kept = []
    final_us = times[-1] - int(OWN_LINE_S * 1e6)                # bearings around these are all in
    for i, r in enumerate(rows):
        key = (r["time_us"], r.get("f0_hz"))
        if known is not None and key in known:
            if known[key]:
                kept.append(r)
            continue
        lo = int(np.searchsorted(times, times[i] - int(OWN_LINE_S * 1e6), side="left"))
        hi = int(np.searchsorted(times, times[i] + int(OWN_LINE_S * 1e6), side="right"))
        around = rows[lo:hi]
        keep = True
        if len(around) >= 5:
            t0, a0, slope = track_segments._line(around)
            predicted = a0 + slope * (r["time_us"] * 1e-6 - t0)
            keep = abs(track_segments.wrap(r["azimuth_deg"] - predicted)) <= max(OWN_LINE_DEG, 3.0 * r["sigma_deg"])
        if keep:
            kept.append(r)
        if known is not None and r["time_us"] <= final_us:
            known[key] = keep
    return kept if len(kept) >= 2 else rows


def station_segments(store, station_id: int, track_event_id: int) -> list[track_segments.Segment]:
    """The segments of a station track's trusted-time bearings."""
    rows = [r for r in store.list_bearings(station_id=station_id, track_event_id=track_event_id, limit=50000)
            if r["time_trust"] in TRUSTED_TIME]
    return track_segments.split(rows)


@dataclass
class Unit:
    """A segment as known at a step: its bearings up to the step."""
    member: Member
    rows: list[dict]
    origin: np.ndarray
    signature: target_match.Signature
    bearings: StationBearings

    @property
    def station(self) -> int:
        return self.member[0]

    @property
    def first_s(self) -> float:
        return self.rows[0]["time_us"] * 1e-6

    @property
    def last_s(self) -> float:
        return self.rows[-1]["time_us"] * 1e-6


@dataclass
class Fix:
    xyz: np.ndarray
    rays: int
    chi2: float
    height_spread: float
    horizontal_error_m: float
    vertical_error_m: float
    crossing_deg: float

    @property
    def consistent(self) -> bool:
        return self.height_spread <= HEIGHT_AGREE_SIGMA and (self.rays < 3 or self.chi2 / (self.rays - 2) <= CHI2_PER_DOF)


@dataclass
class Hypothesis:
    units: tuple[Unit, ...]
    fixes: list[tuple[float, Fix]]
    score: float
    ambiguous: bool

    @property
    def members(self) -> tuple[Member, ...]:
        return tuple(sorted(u.member for u in self.units))

    def weak(self) -> bool:
        """A station gives one of the segments little confidence (zs_doa_sep.h, zs_comb_bearing.h): two like targets
        heard at once give such bearings, between them or alternating, and their rays meet others' in ghosts."""
        return any(_weak_unit(u) for u in self.units)

    def strong(self) -> bool:
        """Two stations, or three and more whose rays meet in enough well conditioned points."""
        if len(self.units) < 3:
            return True
        meeting = [f for _, f in self.fixes if f.consistent]
        return len(meeting) >= STRONG_FIXES and float(np.median([f.horizontal_error_m for f in meeting])) <= STRONG_ERROR_M


def _weak_unit(u: Unit) -> bool:
    return float(np.median([r.get("confidence", 1.0) for r in u.rows[-20:]])) < WEAK_CONFIDENCE


def _solve(units, t: float, now: float, heard: list | None = None):
    """The rays of the units for emission time t, iterated on the sound delay, bearings up to now: (azimuths,
    elevations, sigmas, origins, solution, ranges, spread) or a reason: None (no bearing), "narrow" (rays too parallel
    to tell), "refuted" (they cross behind a station or out of range).  ``heard`` (a list) receives the (station,
    arrival time) of every sample: the result is final once the bearings around them are in."""
    ranges = [RANGE_GUESS_M] * len(units)
    solved = None
    for k in range(5):
        az, el, sg = [], [], []
        for u, r in zip(units, ranges):
            ta = t + r / C
            if heard is not None:
                heard.append((u.station, ta))
            if ta > now:
                return None
            s = u.bearings.sample(ta)
            if s is None:
                return None
            az.append(s[0]); el.append(s[1]); sg.append(s[2])
        if _crossing_deg(az) < MIN_CROSSING_DEG:
            return "narrow"
        origins = np.array([u.origin for u in units])
        spread: list[float] = []
        solved = intersect(origins, az, el, sg, None if k == 0 else ranges, spread)
        if solved is None:
            return "narrow"
        new = [float(np.linalg.norm(solved[0][:2] - o[:2])) for o in origins]
        if max(new) > MAX_RANGE_M:
            return "refuted"
        converged = k > 0 and max(abs(a - b) for a, b in zip(new, ranges)) < 2.0
        ranges = new
        if converged:
            break
    xyz = solved[0]
    for a, o in zip(az, origins):
        if float((xyz[:2] - o[:2]) @ _direction(a)) <= 0.0:
            return "refuted"
    return az, el, sg, origins, solved, ranges, spread


def _fix(units, t: float, now: float, heard: list | None = None) -> Fix | None:
    r = _solve(units, t, now, heard)
    if r is None or isinstance(r, str):
        return None
    az, el, sg, origins, (xyz, cov, z_sigma), ranges, spread = r
    h_err = math.sqrt(max(float(np.trace(cov)), 0.0))
    if h_err > MAX_ERROR_M:
        return None
    chi2 = 0.0
    for a, s, o, rng in zip(az, sg, origins, ranges):
        d = _direction(a)
        chi2 += (float((xyz[:2] - o[:2]) @ np.array([-d[1], d[0]])) / (math.radians(s) * max(rng, 1.0))) ** 2
    return Fix(xyz, len(units), chi2, spread[0] if spread else 0.0, h_err, max(z_sigma, 10.0), _crossing_deg(az))


class HypothesisTrackFusion:
    def __init__(self, store):
        self.store = store
        self._segments_cache: dict[tuple[int, int], list[track_segments.Segment]] = {}
        self._fix_cache: dict[tuple, object] = {}
        self._signature_cache: dict[tuple, target_match.Signature] = {}
        self._course_cache: dict[Member, dict] = {}
        self._complete: dict[int, float] = {}
        self._state = store.fusion_state(STATE) or {"step": None, "frame": None, "tracks": {}, "waiting": {}}

    # ---- inputs ---------------------------------------------------------------------------------------------------
    def _segments(self, station_id: int, track_event_id: int) -> list[track_segments.Segment]:
        key = (station_id, track_event_id)
        if key not in self._segments_cache:
            self._segments_cache[key] = station_segments(self.store, station_id, track_event_id)
        return self._segments_cache[key]

    def _frame(self, position) -> EnuFrame:
        if self._state["frame"] is None:
            self._state["frame"] = list(position)
        return EnuFrame(*self._state["frame"])

    def _signature(self, member: Member, segment: track_segments.Segment, rows: list[dict]) -> target_match.Signature:
        key = (member, rows[-1]["time_us"])
        if key not in self._signature_cache:
            part = track_segments.Segment(segment.key, rows, segment.formed_us)
            self._signature_cache[key] = target_match.station_track_signature(self.store, member[0], member[1], part)
        return self._signature_cache[key]

    def _units(self, step_us: int) -> list[Unit]:
        since = step_us - int((WINDOW_S + MAX_RANGE_M / C + 2.0) * 1e6)
        by_station: dict[int, list[Unit]] = {}
        for t in self._tracks:
            if t["last_us"] < since or t["first_us"] > step_us:
                continue
            station_id, track_event_id = t["station_id"], t["track_event_id"]
            key = (station_id, track_event_id)
            if key not in self._positions:
                self._positions[key] = self.store.station_position(station_id, track_event_id)
            position = self._positions[key]
            if position is None:
                continue
            frame = self._frame(position)
            origin = np.array(frame.to_enu(*position))
            for seg in self._segments(station_id, track_event_id):
                if seg.known_since_us > step_us:
                    continue                                     # not a segment yet at this step
                rows = [r for r in seg.rows if r["time_us"] <= step_us]
                if len(rows) < 2 or rows[-1]["time_us"] < step_us - int(track_segments.ACTIVE_S * 1e6):
                    continue                                     # the station no longer hears this target
                member = (station_id, track_event_id, seg.key)
                ray_rows = own_course(rows, self._course_cache.setdefault(member, {}))
                by_station.setdefault(station_id, []).append(Unit(member, rows, origin, self._signature(member, seg, rows),
                                                                  StationBearings.from_rows(station_id, position, ray_rows)))
        units = []
        for station_units in by_station.values():
            units += sorted(station_units, key=lambda u: -u.last_s)[:MAX_UNITS_PER_STATION]
        return units

    # ---- hypotheses -----------------------------------------------------------------------------------------------
    def _cached(self, kind: str, units, t: float, now: float):
        key = (kind, tuple(u.member for u in units), t)
        if key in self._fix_cache:
            return self._fix_cache[key]
        heard: list = []
        if kind == "fix":
            value = _fix(units, t, now, heard)
        else:
            solved = _solve(units, t, now, heard)
            value = solved if solved is None or isinstance(solved, str) else "fix"
        complete = self._complete                                # each station's bearings are in up to its latest one
        if all(ta + MAX_SAMPLE_GAP_S + OWN_LINE_S <= min(now, complete.get(station, 0.0)) for station, ta in heard):
            if len(self._fix_cache) > 400_000:
                self._fix_cache.clear()
            self._fix_cache[key] = value
        return value

    def _unrefuted(self, x: Unit, y: Unit, now: float) -> bool:
        """The pairing x-y gives rays that cross ahead of both stations, or are too parallel to tell."""
        n = refuted = 0
        start = math.floor(max(x.first_s, y.first_s, now - WINDOW_S) - MAX_RANGE_M / C)
        for t in np.arange(start, now, 1.0):
            status = self._cached("status", (x, y), float(t), now)
            if status is None:
                continue
            n += 1
            refuted += status == "refuted"
        return n >= MIN_FIXES and refuted < RIVAL_REFUTED * n

    def _ambiguous(self, a: Unit, b: Unit, by_station: dict[int, list[Unit]], now: float) -> bool:
        def overlap(u: Unit, v: Unit) -> float:
            return min(u.last_s, v.last_s) - max(u.first_s, v.first_s, now - WINDOW_S)

        def rivals(x: Unit, y: Unit) -> list[Unit]:
            """Segments x's station hears at the same time as x (not one after the other: a station that went from one
            target to another hears one at a time) that y could pair with as well."""
            return [z for z in by_station[x.station] if z is not x and target_match.compatible(z.signature, y.signature)
                    and overlap(z, x) >= RIVAL_MIN_S and overlap(z, y) >= RIVAL_MIN_S]
        return any(self._unrefuted(z, b, now) for z in rivals(a, b)) or any(self._unrefuted(z, a, now) for z in rivals(b, a))

    def _continues(self, members: set[Member], confirmed: bool = True) -> bool:
        """The pair continues a track of these segments (that a well conditioned triple confirmed CONTINUE_S ago at
        most, when ``confirmed``)."""
        now = self._now
        return any(members <= {tuple(m) for m in tr["cur"]}
                   and (not confirmed or (tr["confirmed"] and now - tr["confirmed_s"] <= CONTINUE_S))
                   for tr in self._state["tracks"].values())

    def _hypotheses(self, units: list[Unit], now: float) -> list[Hypothesis]:
        by_station: dict[int, list[Unit]] = {}
        for u in units:
            by_station.setdefault(u.station, []).append(u)
        self._by_station = by_station
        stations = sorted(by_station)
        near = {(a, b) for a in stations for b in stations if a < b
                and float(np.linalg.norm(by_station[a][0].origin[:2] - by_station[b][0].origin[:2])) <= 2.0 * MAX_RANGE_M}
        crossing: set[tuple[Member, Member]] = set()           # pairs whose rays gave fixes: a larger hypothesis builds on them
        out = []
        for k in range(2, min(MAX_STATIONS, len(stations)) + 1):
            for chosen in itertools.combinations(stations, k):
                if any((a, b) not in near for a, b in itertools.combinations(chosen, 2)):
                    continue                                     # stations too far apart to hear one target
                for combo in itertools.product(*[by_station[s] for s in chosen]):
                    if any(not target_match.compatible(a.signature, b.signature) for a, b in itertools.combinations(combo, 2)):
                        continue
                    if k > 2 and any(not any((a.member, b.member) in crossing for b in combo if b is not a) for a in combo):
                        continue                                 # every ray must cross another one of the hypothesis
                    lo = max(max(u.first_s for u in combo), now - WINDOW_S) - MAX_RANGE_M / C
                    hi = min(u.last_s for u in combo)
                    if hi - lo < MIN_FIXES:
                        continue
                    fixes = []
                    for t in np.arange(math.floor(lo), hi, 1.0):
                        f = self._cached("fix", combo, float(t), now)
                        if f is not None:
                            fixes.append((float(t), f))
                    if len(fixes) < MIN_FIXES:
                        continue
                    if k == 2:
                        crossing.add((combo[0].member, combo[1].member))
                        crossing.add((combo[1].member, combo[0].member))
                    ambiguous = False
                    weak = sum(_weak_unit(u) for u in combo)
                    if weak and k - weak < 2 and not (k == 2 and self._continues({u.member for u in combo}, confirmed=False)):
                        continue                                 # a weak segment needs two other stations' sure rays...
                    if k == 2 and self._ambiguous(combo[0], combo[1], by_station, now):
                        if weak or not self._continues({u.member for u in combo}):
                            continue
                        ambiguous = True
                    good = sum(f.rays - 1 for _, f in fixes if f.consistent)
                    bad = sum(f.rays - 1 for _, f in fixes if not f.consistent)
                    score = float(good - bad)
                    times = np.array([t for t, _ in fixes])
                    xy = np.array([f.xyz[:2] for _, f in fixes])
                    error = float(np.median([f.horizontal_error_m for _, f in fixes]))
                    tt = times - times.mean()
                    design = np.vstack([np.ones_like(tt), tt, tt ** 2]).T
                    miss = xy - design @ np.linalg.lstsq(design, xy, rcond=None)[0]
                    kinematic = float(np.sqrt(np.mean(np.sum(miss ** 2, axis=1)))) / max(error, 15.0)
                    if kinematic > KINEMATIC_LIMIT:
                        score -= (kinematic - KINEMATIC_LIMIT) * len(fixes)
                    if score > 0:
                        h = Hypothesis(tuple(combo), fixes, score, ambiguous)
                        if k >= 3 and weak and not h.strong():
                            continue                             # ...that meet its ray well
                        out.append(h)
        out.sort(key=lambda h: (-h.score, h.members))
        return out[:MAX_CANDIDATES]

    @staticmethod
    def _choose(candidates: list[Hypothesis]) -> list[Hypothesis]:
        """The set of hypotheses with the largest total score, no segment twice (branch and bound)."""
        best: list = [0.0, []]
        suffix = np.cumsum([h.score for h in candidates][::-1])[::-1] if candidates else []

        def search(i: int, used: set, total: float, chosen: list) -> None:
            if total > best[0]:
                best[0], best[1] = total, list(chosen)
            if i >= len(candidates) or total + suffix[i] <= best[0]:
                return
            h = candidates[i]
            if not set(h.members) & used:
                chosen.append(h)
                search(i + 1, used | set(h.members), total + h.score, chosen)
                chosen.pop()
            search(i + 1, used, total, chosen)

        search(0, set(), 0.0, [])
        return best[1]

    # ---- tracks ---------------------------------------------------------------------------------------------------
    @staticmethod
    def _kalman(state: dict | None) -> ConstantVelocityKalman3D:
        kf = ConstantVelocityKalman3D(process_accel_sigma=KALMAN_ACCEL)
        if state:
            kf.x, kf.p, kf.t = np.array(state["x"]), np.array(state["p"]), state["t"]
        return kf

    @staticmethod
    def _gated(kf: ConstantVelocityKalman3D, t: float, fix: Fix) -> bool:
        if kf.x is None:
            return True
        f, q = kf._predict_matrices(max(t - kf.t, 0.0))
        x = f @ kf.x
        p = f @ kf.p @ f.T + q
        s = p[:2, :2] + np.eye(2) * max(fix.horizontal_error_m, GATE_MIN_M) ** 2
        r = fix.xyz[:2] - x[:2]
        return float(r @ np.linalg.solve(s, r)) <= GATE_CHI2

    def _new_track_id(self, members: tuple[Member, ...]) -> str:
        first_event, first_station, first_segment = min((t, s, g) for s, t, g in members)
        base = f"TRK-{first_event:016x}-{first_station}" + (f"-{first_segment:x}" if first_segment else "")
        track_id, n = base, 1
        while self.store.get_track(track_id) is not None or track_id in self._state["tracks"]:
            n += 1
            track_id = f"{base}-r{n}"
        return track_id

    def _system_event(self, members) -> str | None:
        """The system event the track belongs to: an AIR_ALERT of a member's detection before an AIR_WARNING, the latest."""
        found = []
        for station_id, track_event_id, _ in members:
            sid = self.store.system_event_of_detection(station_id, track_event_id)
            event = self.store.get_event(sid) if sid else None
            if event:
                found.append((event["event_type"] == "AIR_ALERT", event["created_time_us"], sid))
        return max(found)[2] if found else None

    def _point(self, kf: ConstantVelocityKalman3D, t: float, fix: Fix, units, ambiguous: bool) -> dict:
        state = kf.update(fix.xyz, t, fix.horizontal_error_m)
        frame = EnuFrame(*self._state["frame"])
        lat, lon, alt = frame.to_geodetic(*state[:3])
        vx, vy, vz = (float(v) for v in state[3:])
        speed = math.hypot(vx, vy)
        h_err = min(fix.horizontal_error_m, math.sqrt(max(float(kf.p[0, 0] + kf.p[1, 1]), 0.0)))
        return {"time_us": int(round(t * 1e6)), "lat": lat, "lon": lon, "alt_msl_m": alt,
                "horizontal_error_m": round(h_err, 1), "vertical_error_m": round(fix.vertical_error_m, 1),
                "vx_east_mps": vx, "vy_north_mps": vy, "vz_up_mps": vz, "speed_mps": speed,
                "course_deg": (math.degrees(math.atan2(vx, vy)) + 360.0) % 360.0 if speed > 0.5 else 0.0,
                "crossing_deg": round(fix.crossing_deg, 1), "stations": sorted({u.station for u in units}),
                "ambiguous": ambiguous}

    def _step(self, step_us: int, touched: dict[str, dict]) -> None:
        now = step_us * 1e-6
        self._now = now
        tracks = self._state["tracks"]
        chosen = self._choose(self._hypotheses(self._units(step_us), now))
        self.chosen = chosen                                     # the explanation of the last step (diagnostics)
        # continuity: each chosen hypothesis continues the track whose current segments it shares most (one to one)
        pairs = []
        for i, h in enumerate(chosen):
            sure = {u.member for u in h.units if not _weak_unit(u)}     # a weak segment alone carries no continuity...
            for track_id, tr in tracks.items():
                cur = {tuple(m) for m in tr["cur"]}
                shared = len(cur & sure) or (len(cur & set(h.members)) if set(h.members) <= cur else 0)  # ...unless it stays
                if shared:
                    pairs.append((shared, h.score, i, track_id))
        pairs.sort(key=lambda p: (-p[0], -p[1], p[2], p[3]))
        assigned: dict[int, str] = {}
        refused: set[int] = set()
        for shared, _, i, track_id in pairs:
            if i in assigned or track_id in assigned.values():
                continue
            tr = tracks[track_id]
            kf = self._kalman(tr["kf"])
            new = [(t, f) for t, f in chosen[i].fixes if t > tr["last_s"]][:5]
            if new and sum(not self._gated(kf, t, f) for t, f in new) > len(new) // 2:
                refused.add(i)                                   # not the motion of that track: no decision yet
                continue
            assigned[i] = track_id
        waiting = self._state["waiting"]
        seen = set()
        for i, h in enumerate(chosen):
            if i in assigned:
                track_id = assigned[i]
            elif i in refused:
                continue
            else:
                if not h.strong() and (h.weak() or any(self._ambiguous(a, b, self._by_station, now)
                                                       for a, b in itertools.combinations(h.units, 2))):
                    continue                                     # far rays meeting by chance: only as good as its pairs
                key = repr(h.members)
                waiting[key] = waiting.get(key, 0) + 1
                seen.add(key)
                if waiting[key] < (WEAK_PUBLISH_STEPS if h.weak() else PUBLISH_STEPS):
                    continue
                track_id = self._new_track_id(h.members)
                tracks[track_id] = {"cur": [], "last_s": now - BACKFILL_S - MAX_RANGE_M / C, "kf": None, "confirmed": False,
                                    "confirmed_s": now, "points": 0, "added_s": now}
            tr = tracks[track_id]
            before_cur = tr["cur"]
            tr["cur"] = [list(m) for m in h.members]
            for other_id, other in tracks.items():               # a segment is in one track at a time
                if other_id != track_id:
                    other["cur"] = [m for m in other["cur"] if tuple(m) not in set(h.members)]
            if len(h.units) >= 3 and h.strong():
                tr["confirmed"], tr["confirmed_s"] = True, now
            elif len(h.units) == 2 and not h.ambiguous:
                tr["confirmed_s"] = now
            kf = self._kalman(tr["kf"])
            same = set(h.members) == {tuple(m) for m in before_cur}
            points = []
            for t, f in h.fixes:
                if t <= tr["last_s"]:
                    continue
                tr["last_s"] = t
                if not f.consistent:
                    continue                                     # rays that disagree give no point
                if tr["points"] >= 5 and not self._gated(kf, t, f):
                    tr["rejected"] = tr.get("rejected", 0) + 1
                    if not same or tr["rejected"] < REGATE_POINTS:
                        continue                                 # another target's crossing: not this track's point
                    kf = self._kalman(None)                      # the same segments keep missing the prediction: the
                                                                 # filter, not the association, is off (a close pass)
                tr["rejected"] = 0
                points.append(self._point(kf, t, f, h.units, h.ambiguous))
                tr["points"] += 1
            if kf.x is not None:
                tr["kf"] = {"x": kf.x.tolist(), "p": kf.p.tolist(), "t": kf.t}
            self.store.set_track_members(track_id, list(h.members))
            if points:
                tr["added_s"] = now
                self.store.append_track_points(track_id, self._system_event(h.members), points)
                entry = touched.setdefault(track_id, {"track_id": track_id, "new_points": []})
                entry["new_points"] += points
                entry["last"] = points[-1]
                entry["stations"] = sorted({u.station for u in h.units})
        for key in list(waiting):
            if key not in seen:
                del waiting[key]
        for track_id in [k for k, tr in tracks.items() if now - tr.get("added_s", now) > TRACK_IDLE_S]:
            del tracks[track_id]
            self.store.set_track_members(track_id, [])          # its segments are free: lines again, or another track

    # ---- batches --------------------------------------------------------------------------------------------------
    def _horizon(self, latest: dict[int, int]) -> int | None:
        """The time up to which the stations that keep up have sent their bearings (at least two of them)."""
        if len(latest) < 2:
            return None
        second = sorted(latest.values())[-2]
        return min(t for t in latest.values() if t >= second - int(LAG_S * 1e6))

    def on_batch(self, batch) -> list[dict]:
        """A stored bearing batch: the steps it completes, and the tracks that got points (none while one station)."""
        if batch.time_trust not in TRUSTED_TIME or not batch.samples:
            return []
        self._segments_cache.pop((batch.station_id, batch.track_event_id), None)
        last_sample = max(s.time_us for s in batch.samples)
        latest = self.store.latest_bearing_times(last_sample - int(600 * 1e6))
        self._complete = {station: t * 1e-6 for station, t in latest.items()}
        horizon = self._horizon(latest)
        if horizon is None:
            return []
        end = horizon // STEP_US * STEP_US
        step = self._state["step"]
        earliest = end - (CATCH_UP_STEPS - 1) * STEP_US
        start = earliest if step is None else max(step + STEP_US, earliest)
        if start > end:
            return []
        touched: dict[str, dict] = {}
        self._signature_cache.clear()
        if len(self._course_cache) > 2000:
            self._course_cache.clear()
        self._positions = {}
        self._tracks = self.store.bearing_tracks(start - int((WINDOW_S + MAX_RANGE_M / C + 2.0) * 1e6), end)
        for step_us in range(start, end + 1, STEP_US):
            self._step(step_us, touched)
        self._state["step"] = end
        self.store.save_fusion_state(STATE, self._state)
        results = []
        for track_id, t in touched.items():
            summary = self.store.get_track(track_id)
            results.append({**t, "system_event_id": summary["system_event_id"] if summary else None,
                            "stations": summary["stations"] if summary else t["stations"],
                            "points": summary["points"] if summary else 0})
        return results

"""Association of station tracks into fused target tracks (bearing stream, ICD addendum H; decision 2 of
docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md).

A station track is the bearing stream of one tracking window of one station (station_id + the event id of its
rising edge).  With several targets in the air a station follows the loudest one and its bearing may jump to another
target inside one window, so a station track is split into segments at sustained bearing jumps
(station/track_segments.py) and the unit of association is a segment (station, track event id, segment key).
Bearings that belong to no segment (outliers) are not fused.  Detections do not carry a track identity across
stations, so association is geometric:

1. a segment already in a fused track stays there, unless the track went stale: no point for RELEASE_S seconds
   of the segment's bearings (two stations hearing different targets give ghost points only while their rays happen
   to cross).  A stale segment moves when rule 2 or 3 finds a fused track for it elsewhere; the stale track keeps
   the points it had (a ghost stays in the history as it was shown) and is recomputed from the members left;
2. otherwise it joins the fused track whose points its bearings point at: for each of its bearings the direction
   from the station to the fused point of the matching emission time (arrival minus range / speed of sound); the
   median residual must stay within 3 sigma (at least 4 degrees) and the target within range;
3. otherwise new fused tracks are formed from unassociated segments of two stations whose rays intersect with a
   usable geometry and agree on the target's height (from their elevations, within HEIGHT_AGREE_SIGMA) for at least
   MIN_FIXES seconds.  All unassociated segments of the join window compete, not only the one whose batch arrived:
   the pair with the most such points is formed first (the segment of the batch may be left for a later batch).  A
   pair of rays towards two different targets crosses in a ghost point whose heights mostly disagree.  A ghost near
   the stations forms first (the sound of a near point arrives sooner), so a pair may also take a segment from a
   two-station track when it has STEAL_MIN_POINTS points and its rays agree on the height better by
   STEAL_MARGIN_SIGMA (median); the track left behind keeps its points.

After every accepted batch the whole fused track is recomputed from all member bearings (fusion/bearing_fusion.py),
so batches of different stations may arrive in any order and a redelivered batch changes nothing; where its members
give no points any more (a member left), the points shown before stay.  A point is marked ``ambiguous`` when a station
of it hears another target of the same class and engine note at the same time: only geometry tells such targets'
crossings from ghosts.  Only bearings with trusted station time (GNSS or holdover) are fused.

Two targets at once: rays of stations hearing different targets intersect in ghost points.  Segments whose known
classes differ or whose fundamentals are further apart than the Doppler shift allows (station/target_match.py) are
therefore never paired or joined.  Two targets of the same class and engine note are told apart by geometry only:
a pair is formed only when the rays intersect for MIN_FIXES seconds, and a joining segment must point at the fused
track's points.
"""
from __future__ import annotations

import math

import numpy as np

from fusion.bearing_fusion import MAX_NEAREST_S, MAX_RANGE_M, SPEED_OF_SOUND_MPS, StationBearings, fuse
from fusion.geodesy import EnuFrame
from station import target_match, track_segments

TRUSTED_TIME = ("GNSS_TIME_TRUSTED", "HOLDOVER")
JOIN_WINDOW_US = 15_000_000     # segments this far apart in time may still belong together
MIN_FIXES = 3                    # a new fused track needs this many seconds of usable intersections
MIN_JOIN_SAMPLES = 2
MIN_JOIN_TOLERANCE_DEG = 4.0
RELEASE_S = 10.0                 # a fused track without a point for this long of a member's bearings is stale
HEIGHT_AGREE_SIGMA = 3.0         # a point counts for a pair when its rays agree on the height within 3 sigma
STEAL_MIN_POINTS = 8             # a pair may take a segment from another two-station track with this many points...
STEAL_MARGIN_SIGMA = 0.5         # ...when its rays agree on the height better by this much (median, in sigmas)
AMBIGUITY_TIME_US = 1_000_000    # a station hears another like target within 1 s of a point's arrival...
AMBIGUITY_APART_DEG = 10.0       # ...in a direction at least this far from the point's
AMBIGUITY_SLACK_US = 20_000_000  # station tracks heard this far around the points (range / c and more)

Member = tuple[int, int, int]    # station_id, track event id, segment key


def _wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def station_segments(store, station_id: int, track_event_id: int) -> list[track_segments.Segment]:
    """The segments of a station track's trusted-time bearings."""
    rows = [r for r in store.list_bearings(station_id=station_id, track_event_id=track_event_id, limit=50000)
            if r["time_trust"] in TRUSTED_TIME]
    return track_segments.split(rows)


class BearingTrackFusion:
    def __init__(self, store):
        self.store = store
        self._cache: dict[tuple[int, int], list[track_segments.Segment]] = {}
        self._created: list[str] = []

    # ---- inputs -------------------------------------------------------------------------------------------------
    def _segments(self, station_id: int, track_event_id: int) -> list[track_segments.Segment]:
        key = (station_id, track_event_id)
        if key not in self._cache:
            self._cache[key] = station_segments(self.store, station_id, track_event_id)
        return self._cache[key]

    def _segment(self, member: Member) -> track_segments.Segment | None:
        return track_segments.by_key(self._segments(member[0], member[1]), member[2])

    def _rows(self, member: Member) -> list[dict]:
        seg = self._segment(member)
        return seg.rows if seg else []

    def _station_bearings(self, members: list[Member]) -> list[StationBearings]:
        """One StationBearings per station (its segments merged), stations without a known position left out."""
        by_station: dict[int, tuple[tuple[float, float, float] | None, list[dict]]] = {}
        for member in members:
            pos, rows = by_station.get(member[0], (None, []))
            pos = pos or self.store.station_position(member[0], member[1])
            by_station[member[0]] = (pos, rows + self._rows(member))
        return [StationBearings.from_rows(s, pos, sorted(rows, key=lambda r: r["time_us"]))
                for s, (pos, rows) in sorted(by_station.items()) if pos and rows]

    # ---- association --------------------------------------------------------------------------------------------
    def _residual_deg(self, member: Member, track: dict) -> float | None:
        """Median angular residual of a segment's bearings against a fused track's points (None: not comparable)."""
        pos = self.store.station_position(member[0], member[1])
        points = track["track_points"]
        if pos is None or not points:
            return None
        frame = EnuFrame(*pos)
        times = np.array([p["time_us"] for p in points], dtype=float) * 1e-6
        enu = [frame.to_enu(p["lat"], p["lon"], p["alt_msl_m"]) for p in points]
        residuals, limits = [], []
        for row in self._rows(member):
            ta = row["time_us"] * 1e-6
            k = int(np.argmin(np.abs(times - ta)))
            for _ in range(3):                                   # emission time of the sound heard at ta
                te = ta - float(np.linalg.norm(enu[k][:2])) / SPEED_OF_SOUND_MPS
                k = int(np.argmin(np.abs(times - te)))
            if abs(times[k] - te) > 1.5 or float(np.linalg.norm(enu[k][:2])) > MAX_RANGE_M:
                continue
            predicted = math.degrees(math.atan2(enu[k][0], enu[k][1])) % 360.0
            residuals.append(abs(_wrap(row["azimuth_deg"] - predicted)))
            limits.append(max(3.0 * row["sigma_deg"], MIN_JOIN_TOLERANCE_DEG))
        if len(residuals) < MIN_JOIN_SAMPLES:
            return None
        median = float(np.median(residuals))
        return median if median <= float(np.median(limits)) else None

    def _signature(self, member: Member) -> target_match.Signature:
        return target_match.station_track_signature(self.store, member[0], member[1], self._segment(member))

    def _nearby(self, first_us: int, last_us: int) -> list[tuple[Member, track_segments.Segment, str | None]]:
        """Segments with bearings in the join window, with their fused track (or None)."""
        out = []
        for t in self.store.bearing_tracks(first_us - JOIN_WINDOW_US, last_us + JOIN_WINDOW_US):
            assigned = self.store.segment_tracks(t["station_id"], t["track_event_id"])
            for seg in self._segments(t["station_id"], t["track_event_id"]):
                if seg.last_us >= first_us - JOIN_WINDOW_US and seg.first_us <= last_us + JOIN_WINDOW_US:
                    out.append(((t["station_id"], t["track_event_id"], seg.key), seg, assigned.get(seg.key)))
        return out

    def _associate(self, member: Member, segment: track_segments.Segment, exclude: str | None = None) -> str | None:
        nearby = [n for n in self._nearby(segment.first_us, segment.last_us) if n[0] != member]
        own = self._signature(member)
        best = None
        for track_id in sorted({n[2] for n in nearby if n[2] and n[2] != exclude}):
            members = self.store.track_members(track_id)
            if any(m[0] == member[0] for m in members if self._overlaps(m, segment)):
                continue                                         # the station is in that track at the same time already
            if not target_match.compatible(own, target_match.merge([self._signature(m) for m in members])):
                continue                                         # the fused track is another target
            track = self.store.get_track(track_id)
            residual = self._residual_deg(member, track) if track else None
            if residual is not None and (best is None or residual < best[0]):
                best = (residual, track_id)
        if best is not None:
            self.store.add_track_member(best[1], *member)
            return best[1]
        candidates = [(m, track_id) for m, _, track_id in nearby if m != member]
        candidates.append((member, None))
        pair_tracks = {}                                         # two-station tracks whose segments may be taken
        for m, track_id in candidates:
            if track_id and track_id not in pair_tracks:
                members = self.store.track_members(track_id)
                pair_tracks[track_id] = self._spread(members) if len({x[0] for x in members}) == 2 else None
        candidates = [(m, t) for m, t in candidates if t is None or pair_tracks.get(t) is not None]
        signatures = {m: self._signature(m) for m, _ in candidates}
        best_pair = None
        for i, (a, ta) in enumerate(candidates):
            for b, tb in candidates[i + 1:]:
                if a[0] == b[0] or (ta and ta == tb) or not target_match.compatible(signatures[a], signatures[b]):
                    continue                                     # one station, one track already, or two targets
                points = fuse(self._station_bearings([a, b]))
                if exclude is not None and member in (a, b) and not self._covers(points, member, segment):
                    continue                                     # a move must explain the recent bearings
                agreed = sum(1 for p in points if p.height_spread <= HEIGHT_AGREE_SIGMA)
                if agreed < MIN_FIXES:
                    continue
                taken = [t for t in (ta, tb) if t]
                if taken:
                    spread = float(np.median([p.height_spread for p in points]))
                    if agreed < STEAL_MIN_POINTS or any(spread + STEAL_MARGIN_SIGMA >= pair_tracks[t] for t in taken):
                        continue                                 # not clearly better than the pair it would break
                key = (agreed, len(points))
                if best_pair is None or key > best_pair[0]:
                    best_pair = (key, [(a, ta), (b, tb)])
        if best_pair is None:
            return None
        for m, t in best_pair[1]:
            if t:                                                # taken from a ghost: that track keeps its points
                self.store.remove_track_member(t, *m)
                self._created.append(t)
        pair = [m for m, _ in best_pair[1]]
        track_id = self._new_track(pair)
        if member in pair:
            return track_id
        self._created.append(track_id)                           # another pair was the better hypothesis
        return None

    def _spread(self, members: list[Member]) -> float:
        """Median height disagreement of a track's points (in sigmas; infinite without points)."""
        points = fuse(self._station_bearings(members))
        return float(np.median([p.height_spread for p in points])) if points else math.inf

    def _new_track(self, members: list[Member]) -> str:
        # the earliest (track event_id, station) pair: event_id is unique within a station only (ICD); a later
        # segment of the same station track adds the segment's time
        first_event, first_station, first_segment = min((t, s, g) for s, t, g in members)
        base = f"TRK-{first_event:016x}-{first_station}" + (f"-{first_segment:x}" if first_segment else "")
        track_id, n = base, 1
        while self.store.get_track(track_id) is not None:       # a segment that left a track pairs anew: a new id
            n += 1
            track_id = f"{base}-r{n}"
        self.store.replace_track(track_id, members, None, [])
        return track_id

    def _stale_since(self, track_id: str, member: Member, segment: track_segments.Segment) -> bool:
        """The fused track has no point for the last RELEASE_S seconds of the segment's bearings (the sound of the last
        point reached the station range / c after it was emitted)."""
        track = self.store.get_track(track_id)
        if track is None:
            return False
        return not self._covers([p for p in track["track_points"]], member, segment)

    def _covers(self, points, member: Member, segment: track_segments.Segment) -> bool:
        """A point heard by the station within RELEASE_S of the segment's last bearing."""
        if not points:
            return False
        last = points[-1]
        d = last.as_dict() if hasattr(last, "as_dict") else last
        pos = self.store.station_position(member[0], member[1])
        if pos is None:
            return True
        frame = EnuFrame(*pos)
        heard_us = d["time_us"] + float(np.linalg.norm(frame.to_enu(d["lat"], d["lon"], d["alt_msl_m"])[:2])) / SPEED_OF_SOUND_MPS * 1e6
        return segment.last_us - heard_us <= RELEASE_S * 1e6

    def _overlaps(self, member: Member, segment: track_segments.Segment) -> bool:
        seg = self._segment(member)
        return seg is not None and seg.first_us <= segment.last_us and segment.first_us <= seg.last_us

    # ---- recomputation ------------------------------------------------------------------------------------------
    def _system_event(self, members: list[Member]) -> str | None:
        """The system event the track belongs to: an AIR_ALERT of a member's detection before an AIR_WARNING, the latest."""
        found = []
        for station_id, track_event_id, _ in members:
            sid = self.store.system_event_of_detection(station_id, track_event_id)
            event = self.store.get_event(sid) if sid else None
            if event:
                found.append((event["event_type"] == "AIR_ALERT", event["created_time_us"], sid))
        return max(found)[2] if found else None

    def _mark_ambiguous(self, members: list[Member], points: list[dict]) -> None:
        """Mark the points a ghost could explain as well (``ambiguous``): a station of the point hears, at the same
        time, another target it cannot tell from this one (a segment of another direction, its class and fundamental
        compatible with the track's: target_match).  Rays of such stations cross the other target's rays too, and only
        geometry tells which crossings are targets (same-type targets in formation: most points of a ghost and of a
        target alike).  Targets told apart by class or fundamental, and a single target, leave the points unmarked."""
        if not points:
            return
        own = set(members)
        signature = target_match.merge([self._signature(m) for m in members])
        heard: dict[int, list[tuple[int, float]]] = {}           # station -> (time, azimuth) of like targets' bearings
        for t in self.store.bearing_tracks(points[0]["time_us"] - AMBIGUITY_SLACK_US, points[-1]["time_us"] + AMBIGUITY_SLACK_US):
            for seg in self._segments(t["station_id"], t["track_event_id"]):
                member = (t["station_id"], t["track_event_id"], seg.key)
                if member not in own and target_match.compatible(signature, self._signature(member)):
                    heard.setdefault(t["station_id"], []).extend((r["time_us"], r["azimuth_deg"]) for r in seg.rows)
        lookup = {}
        for station_id, rows in heard.items():
            pos = next((self.store.station_position(m[0], m[1]) for m in members if m[0] == station_id), None)
            if pos:
                rows.sort()
                lookup[station_id] = (EnuFrame(*pos), np.array([r[0] for r in rows], dtype=np.int64), np.array([r[1] for r in rows]))
        for p in points:
            p["ambiguous"] = False
            for station_id in p["stations"]:
                if station_id not in lookup:
                    continue
                frame, times, azimuths = lookup[station_id]
                enu = frame.to_enu(p["lat"], p["lon"], p["alt_msl_m"])
                heard_us = p["time_us"] + float(np.linalg.norm(enu[:2])) / SPEED_OF_SOUND_MPS * 1e6
                lo, hi = np.searchsorted(times, [heard_us - AMBIGUITY_TIME_US, heard_us + AMBIGUITY_TIME_US])
                if hi > lo:
                    toward = math.degrees(math.atan2(enu[0], enu[1]))
                    if np.any(np.abs((azimuths[lo:hi] - toward + 180.0) % 360.0 - 180.0) > AMBIGUITY_APART_DEG):
                        p["ambiguous"] = True
                        break

    def recompute(self, track_id: str) -> dict:
        """The track's points from all its member bearings.  Where its members cannot give points any more (a member
        left the track: it heard another target, or the target went on without the track), the points shown before
        stay as they were: a member leaving never erases a track's history, a ghost's included.  Where two or more
        member stations have bearings, the fresh points are the track (so the order of the batches does not matter)."""
        members = self.store.track_members(track_id)
        stations = self._station_bearings(members)
        fresh = list({p.time_us: p.as_dict() for p in fuse(stations)}.values())    # one point per time
        self._mark_ambiguous(members, fresh)
        old = self.store.get_track(track_id)
        # the emission times a station's bearings serve: fuse() samples them at emission + range / c and takes the
        # nearest bearing up to MAX_NEAREST_S beyond the first and the last one (a target close to the station)
        spans = [(float(s.time_s[0]) - MAX_NEAREST_S - MAX_RANGE_M / SPEED_OF_SOUND_MPS, float(s.time_s[-1]) + MAX_NEAREST_S)
                 for s in stations if s.time_s.size]

        def covered(time_us: int) -> bool:                   # two member stations heard the emission time
            return sum(1 for a, b in spans if a <= time_us * 1e-6 <= b) >= 2

        renewed = {p["time_us"] for p in fresh}              # fresh points win, whatever the spans say
        kept = [p for p in (old["track_points"] if old else []) if not covered(p["time_us"]) and p["time_us"] not in renewed]
        points = sorted(kept + fresh, key=lambda p: p["time_us"])
        system_event_id = self._system_event(members)
        self.store.replace_track(track_id, members, system_event_id, points)
        return {"track_id": track_id, "system_event_id": system_event_id, "stations": sorted({m[0] for m in members}),
                "points": len(points), "last": fresh[-1] if fresh else None}

    def on_batch(self, batch) -> list[dict]:
        """A stored bearing batch: the fused tracks of the segments it fed, recomputed (none while single-station)."""
        if batch.time_trust not in TRUSTED_TIME or not batch.samples:
            return []
        self._cache = {}
        self._created = []
        times = {s.time_us for s in batch.samples}
        assigned = self.store.segment_tracks(batch.station_id, batch.track_event_id)
        touched = []
        for seg in self._segments(batch.station_id, batch.track_event_id):
            if not any(r["time_us"] in times for r in seg.rows):
                continue                                         # the batch fed other segments
            member = (batch.station_id, batch.track_event_id, seg.key)
            track_id = assigned.get(seg.key)
            if track_id and self._stale_since(track_id, member, seg):
                self.store.remove_track_member(track_id, *member)   # a segment is in one fused track at a time
                moved = self._associate(member, seg, exclude=track_id)
                if moved:
                    touched.append(track_id)                     # recomputed from the members left
                    track_id = moved
                else:
                    self.store.add_track_member(track_id, *member)
            elif not track_id:
                track_id = self._associate(member, seg)
            if track_id and track_id not in touched:
                touched.append(track_id)
        touched += [t for t in self._created if t not in touched]
        results = [self.recompute(t) for t in touched]
        self._cache = {}
        return results

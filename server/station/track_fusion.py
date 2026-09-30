"""Association of station tracks into fused target tracks (bearing stream, ICD addendum H; decision 2 of
docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md).

A station track is the bearing stream of one tracking window of one station (station_id + the event id of its
rising edge).  Detections do not carry a track identity across stations, so association is geometric:

1. a station track already in a fused track stays there (membership never moves);
2. otherwise it joins the fused track whose points its bearings point at: for each of its bearings the direction
   from the station to the fused point of the matching emission time (arrival minus range / speed of sound); the
   median residual must stay within 3 sigma (at least 4 degrees) and the target within range;
3. otherwise it forms a new fused track with an unassociated station track of another station whose rays intersect
   it with a usable geometry for at least MIN_FIXES seconds.

After every accepted batch the whole fused track is recomputed from all member bearings (fusion/bearing_fusion.py),
so batches of different stations may arrive in any order and a redelivered batch changes nothing.  Only bearings
with trusted station time (GNSS or holdover) are fused.

Two targets at once: rays of stations hearing different targets intersect in ghost points.  Station tracks whose
known classes differ or whose fundamentals are further apart than the Doppler shift allows (station/target_match.py)
are therefore never paired or joined.  Two targets of the same class and engine note can still form a ghost pair.
"""
from __future__ import annotations

import math

import numpy as np

from fusion.bearing_fusion import MAX_RANGE_M, SPEED_OF_SOUND_MPS, StationBearings, fuse
from fusion.geodesy import EnuFrame
from station import target_match

TRUSTED_TIME = ("GNSS_TIME_TRUSTED", "HOLDOVER")
JOIN_WINDOW_US = 15_000_000     # station tracks this far apart in time may still belong together
MIN_FIXES = 3                    # a new fused track needs this many seconds of usable intersections
MIN_JOIN_SAMPLES = 2
MIN_JOIN_TOLERANCE_DEG = 4.0


def _wrap(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


class BearingTrackFusion:
    def __init__(self, store):
        self.store = store

    # ---- inputs -------------------------------------------------------------------------------------------------
    def _rows(self, station_id: int, track_event_id: int) -> list[dict]:
        return [r for r in self.store.list_bearings(station_id=station_id, track_event_id=track_event_id, limit=50000)
                if r["time_trust"] in TRUSTED_TIME]

    def _station_bearings(self, members: list[tuple[int, int]]) -> list[StationBearings]:
        """One StationBearings per station (its station tracks merged), stations without a known position left out."""
        by_station: dict[int, tuple[tuple[float, float, float] | None, list[dict]]] = {}
        for station_id, track_event_id in members:
            pos, rows = by_station.get(station_id, (None, []))
            pos = pos or self.store.station_position(station_id, track_event_id)
            by_station[station_id] = (pos, rows + self._rows(station_id, track_event_id))
        return [StationBearings.from_rows(s, pos, rows) for s, (pos, rows) in sorted(by_station.items()) if pos and rows]

    # ---- association --------------------------------------------------------------------------------------------
    def _residual_deg(self, station_id: int, track_event_id: int, track: dict) -> float | None:
        """Median angular residual of a station track's bearings against a fused track's points (None: not comparable)."""
        pos = self.store.station_position(station_id, track_event_id)
        points = track["track_points"]
        if pos is None or not points:
            return None
        frame = EnuFrame(*pos)
        times = np.array([p["time_us"] for p in points], dtype=float) * 1e-6
        enu = [frame.to_enu(p["lat"], p["lon"], p["alt_msl_m"]) for p in points]
        residuals, limits = [], []
        for row in self._rows(station_id, track_event_id):
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

    def _signature(self, station_id: int, track_event_id: int) -> target_match.Signature:
        return target_match.station_track_signature(self.store, station_id, track_event_id)

    def _associate(self, station_id: int, track_event_id: int, first_us: int, last_us: int) -> str | None:
        nearby = [t for t in self.store.bearing_tracks(first_us - JOIN_WINDOW_US, last_us + JOIN_WINDOW_US)
                  if (t["station_id"], t["track_event_id"]) != (station_id, track_event_id)]
        own = self._signature(station_id, track_event_id)
        best = None
        for track_id in sorted({t["track_id"] for t in nearby if t["track_id"]}):
            members = self.store.track_members(track_id)
            if not target_match.compatible(own, target_match.merge([self._signature(s, t) for s, t in members])):
                continue                                         # the fused track is another target
            track = self.store.get_track(track_id)
            residual = self._residual_deg(station_id, track_event_id, track) if track else None
            if residual is not None and (best is None or residual < best[0]):
                best = (residual, track_id)
        if best is not None:
            self.store.add_track_member(best[1], station_id, track_event_id)
            return best[1]
        pair = None
        for other in nearby:
            if other["track_id"] or other["station_id"] == station_id:
                continue
            if not target_match.compatible(own, self._signature(other["station_id"], other["track_event_id"])):
                continue                                         # the other station hears another target
            members = [(station_id, track_event_id), (other["station_id"], other["track_event_id"])]
            points = fuse(self._station_bearings(members))
            if len(points) >= MIN_FIXES and (pair is None or len(points) > pair[0]):
                pair = (len(points), members)
        if pair is None:
            return None
        members = pair[1]
        track_id = f"TRK-{min(t for _, t in members):016x}-{min(s for s, _ in members)}"
        self.store.replace_track(track_id, members, None, [])
        return track_id

    # ---- recomputation ------------------------------------------------------------------------------------------
    def _system_event(self, members: list[tuple[int, int]]) -> str | None:
        """The system event the track belongs to: an AIR_ALERT of a member's detection before an AIR_WARNING, the latest."""
        found = []
        for station_id, track_event_id in members:
            sid = self.store.system_event_of_detection(station_id, track_event_id)
            event = self.store.get_event(sid) if sid else None
            if event:
                found.append((event["event_type"] == "AIR_ALERT", event["created_time_us"], sid))
        return max(found)[2] if found else None

    def recompute(self, track_id: str) -> dict:
        members = self.store.track_members(track_id)
        points = [p.as_dict() for p in fuse(self._station_bearings(members))]
        system_event_id = self._system_event(members)
        self.store.replace_track(track_id, members, system_event_id, points)
        return {"track_id": track_id, "system_event_id": system_event_id, "stations": sorted({s for s, _ in members}),
                "points": len(points), "last": points[-1] if points else None}

    def on_batch(self, batch) -> dict | None:
        """A stored bearing batch: the fused track it belongs to, recomputed (None when it stays single-station)."""
        if batch.time_trust not in TRUSTED_TIME or not batch.samples:
            return None
        track_id = self.store.track_of_member(batch.station_id, batch.track_event_id)
        if track_id is None:
            track_id = self._associate(batch.station_id, batch.track_event_id, batch.samples[0].time_us, batch.samples[-1].time_us)
        return self.recompute(track_id) if track_id else None

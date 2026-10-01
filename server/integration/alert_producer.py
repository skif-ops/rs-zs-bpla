"""Producer of the output API dioneya.alert/1: turns what the fusion service stores into messages of one outbox.

Runs inside the process that ingests station data (the MQTT bridge of a tenant, or the HTTP bench): every message is
appended to the ``alert_outbox`` table of the shared database with a deterministic ``msg_id`` (a repeated fact is
appended once), and the consumers (HTTP polling, WebSocket, webhook dispatcher) read the outbox by ``seq`` from any
process.

Entities:

* alert episode, per tenant: starts with the first air event, bearing or track while none is open; its level is
  ``warning`` (one station) or ``alert`` (two or more stations or a fused track); it ends ``ALERT_END_US`` after the
  last activity.  Messages ``alert.start``, ``alert.update`` (level, stations or class changed), ``alert.end``.
* fused track (station/track_fusion.py): ``track.update`` with its newest point (the fusion grid gives at most one a
  second), ``track.end`` when its fusion has not been updated for ``TRACK_END_US`` or the alert ends.
* single-station bearing: while a station track is not part of a fused track, its newest bearing at most once a second
  as ``bearing`` (a line from the station), then nothing: the track carries the target.
"""
from __future__ import annotations

import time

from integration import dioneya_alert as msg
from station import target_match, track_segments
from station.track_fusion import station_segments

TRUSTED_TIME = ("GNSS_TIME_TRUSTED", "HOLDOVER")
BEARING_PERIOD_US = 1_000_000
TRACK_END_US = 20_000_000          # longer than the join window of station tracks (15 s): an ended track does not resume
ALERT_END_US = 120_000_000
SWEEP_PERIOD_US = 1_000_000
LEVEL_RANK = {"warning": 1, "alert": 2}


class AlertProducer:
    def __init__(self, store, tenant: str = "default", clock=time.time):
        self.store = store
        self.tenant = tenant
        self.clock = clock
        self._last_bearing: dict[tuple[int, int], int] = {}
        self._last_sweep = 0

    def now_us(self) -> int:
        return int(self.clock() * 1e6)

    # ---- outbox ---------------------------------------------------------------------------------------------------
    def _emit(self, msg_type: str, msg_id: str, alert_id: str | None, time_us: int, now: int, **body) -> int | None:
        message = msg.envelope(msg_type, msg_id, self.tenant, alert_id, time_us if time_us > 0 else now, now, **body)
        return self.store.append_alert(msg_id, self.tenant, msg_type, now, message)

    def _stations(self, station_ids: list[int]) -> list[dict]:
        return [msg.station(s, self.store.station_position(s)) for s in station_ids]

    def _alert_body(self, episode: dict) -> dict:
        return msg.alert_object(episode, self._stations(episode["stations"]), self.store.alert_tracks_of(episode["alert_id"]))

    # ---- alert episode --------------------------------------------------------------------------------------------
    def _touch(self, now: int, time_us: int, *, stations: list[int], level: str, klass: dict | None,
               new_track: tuple[str, int] | None = None) -> dict:
        """The open episode of the tenant with this activity, started or updated (alert.start / alert.update).
        ``new_track`` (track id, point time) joins the episode first, so the message lists it."""
        episode = self.store.open_episode(self.tenant)
        if episode is None:
            started = time_us if time_us > 0 else now
            episode = {"alert_id": f"ALR-{self.tenant}-{started:016x}", "tenant": self.tenant, "started_us": started,
                       "last_activity_us": now, "level": level, "stations": sorted(set(stations)),
                       "class": klass or target_match.UNKNOWN.as_class(), "ended_us": None}
            self.store.save_episode(episode)
            if new_track:
                self.store.save_alert_track(new_track[0], episode["alert_id"], new_track[1])
            self._emit("alert.start", f"alert.start:{episode['alert_id']}", episode["alert_id"], started, now,
                       alert=self._alert_body(episode))
            return episode
        changed = False
        if new_track:
            self.store.save_alert_track(new_track[0], episode["alert_id"], new_track[1])
            changed = True
        merged = sorted(set(episode["stations"]) | set(stations))
        if merged != episode["stations"]:
            episode["stations"], changed = merged, True
        if LEVEL_RANK[level] > LEVEL_RANK[episode["level"]]:
            episode["level"], changed = level, True
        if klass and self._better(klass, episode["class"]):
            episode["class"], changed = klass, True
        episode["last_activity_us"] = max(episode["last_activity_us"], now)
        self.store.save_episode(episode)
        if changed:
            tracks = len(self.store.alert_tracks_of(episode["alert_id"]))
            key = f"{episode['level']}:{'-'.join(map(str, episode['stations']))}:{episode['class']['code']}:{tracks}"
            self._emit("alert.update", f"alert.update:{episode['alert_id']}:{key}", episode["alert_id"], time_us, now,
                       alert=self._alert_body(episode))
        return episode

    @staticmethod
    def _better(new: dict, old: dict) -> bool:
        """A class replaces the alert's when it is known and the old one is not, or it is the same with more confidence."""
        if new["code"] == "unknown":
            return False
        if old["code"] == "unknown":
            return True
        return new["code"] != old["code"] and new["confidence"] > old["confidence"] + 0.1

    # ---- inputs from the fusion service ---------------------------------------------------------------------------
    def on_event(self, event, detections: list) -> None:
        """A system event (station/service.py): an air event opens or feeds the alert."""
        if event.event_type not in ("AIR_WARNING", "AIR_ALERT"):
            return
        now = self.now_us()
        self.sweep(now)
        klass = target_match.from_detections(detections).as_class()
        self._touch(now, event.created_time_us, stations=list(event.source_station_ids),
                    level="alert" if event.event_type == "AIR_ALERT" else "warning", klass=klass)

    def on_bearings(self, batch) -> None:
        """A stored bearing batch: a line from the station while its track is not part of a fused track."""
        if batch.time_trust not in TRUSTED_TIME or not batch.samples:
            return
        now = self.now_us()
        self.sweep(now)
        key = (batch.station_id, batch.track_event_id)
        sample = batch.samples[-1]
        # the segment of the station track this bearing belongs to (station/track_segments.py); an outlier or a
        # bearing still waiting for its segment draws no line
        segment = track_segments.segment_at(station_segments(self.store, *key), sample.time_us)
        if segment is None or self.store.track_of_member(*key, segment.key) is not None:   # a fused track carries it
            self._touch(now, sample.time_us, stations=[batch.station_id], level="warning", klass=None)
            return
        signature = target_match.station_track_signature(self.store, *key, segment).as_class()
        episode = self._touch(now, sample.time_us, stations=[batch.station_id], level="warning", klass=signature)
        last = self._last_bearing.get(key)
        if last is not None and sample.time_us < last + BEARING_PERIOD_US:
            return
        self._last_bearing[key] = sample.time_us
        position = self.store.station_position(batch.station_id, batch.track_event_id)
        body = msg.bearing_object(msg.station(batch.station_id, position), batch.track_event_id, sample.as_dict(), signature)
        self._emit("bearing", f"bearing:{batch.station_id}:{batch.track_event_id:016x}:{sample.time_us}",
                   episode["alert_id"], sample.time_us, now, bearing=body)

    def on_track(self, track: dict) -> None:
        """A recomputed fused track (station/track_fusion.py): its newest point, once."""
        point = track.get("last")
        if not point:
            return
        now = self.now_us()
        self.sweep(now)
        track_id = track["track_id"]
        state = self.store.alert_track(track_id)
        if state is not None and (state["ended_us"] is not None or point["time_us"] <= state["last_point_us"]):
            return
        klass = self._track_class(track_id)
        if state is None:
            episode = self._touch(now, point["time_us"], stations=track["stations"], level="alert", klass=klass,
                                  new_track=(track_id, point["time_us"]))
            alert_id = episode["alert_id"]
        else:
            alert_id = state["alert_id"]
            episode = self.store.get_episode(alert_id)
            if episode and episode["ended_us"] is None:
                self._touch(now, point["time_us"], stations=track["stations"], level="alert", klass=klass)
            self.store.save_alert_track(track_id, alert_id, point["time_us"])
        summary = self.store.get_track(track_id)
        body = msg.track_object(track_id, point, first_us=summary["first_time_us"], points=summary["points"],
                                stations=sorted(set(point["stations"])), klass=klass)
        self._emit("track.update", f"track.update:{track_id}:{point['time_us']}", alert_id, point["time_us"], now, track=body)

    def _track_class(self, track_id: str) -> dict:
        members = self.store.track_members(track_id)
        signatures = []
        for station_id, track_event_id, segment_us in members:
            segment = track_segments.by_key(station_segments(self.store, station_id, track_event_id), segment_us)
            signatures.append(target_match.station_track_signature(self.store, station_id, track_event_id, segment))
        return target_match.merge(signatures).as_class()

    # ---- ends -----------------------------------------------------------------------------------------------------
    def _end_track(self, track_id: str, alert_id: str, now: int, reason: str) -> None:
        summary = self.store.get_track(track_id)
        state = self.store.alert_track(track_id)
        if summary is None or state is None or state["ended_us"] is not None:
            return
        self.store.save_alert_track(track_id, alert_id, state["last_point_us"], ended_us=now)
        points = summary["track_points"]
        if not points:
            return
        last = points[-1]
        body = msg.track_object(track_id, last, first_us=summary["first_time_us"], points=len(points),
                                stations=summary["stations"], klass=self._track_class(track_id), ended_us=now, end_reason=reason)
        self._emit("track.end", f"track.end:{track_id}", alert_id, last["time_us"], now, track=body)

    def sweep(self, now: int | None = None, *, force: bool = False) -> None:
        """End tracks whose fusion went quiet and the alert after its last activity (called by the bridge loop)."""
        now = self.now_us() if now is None else now
        if not force and now - self._last_sweep < SWEEP_PERIOD_US:
            return
        self._last_sweep = now
        episode = self.store.open_episode(self.tenant)
        if episode is None:
            return
        for t in self.store.open_alert_tracks(episode["alert_id"]):
            if t["updated_us"] < now - TRACK_END_US:
                self._end_track(t["track_id"], episode["alert_id"], now, "lost")
        if episode["last_activity_us"] < now - ALERT_END_US:
            for t in self.store.open_alert_tracks(episode["alert_id"]):
                self._end_track(t["track_id"], episode["alert_id"], now, "alert_end")
            episode["ended_us"] = now
            self.store.save_episode(episode)
            self._emit("alert.end", f"alert.end:{episode['alert_id']}", episode["alert_id"], now, now,
                       alert=self._alert_body(episode))
            self._last_bearing.clear()

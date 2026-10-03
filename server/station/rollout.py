"""Firmware rollouts: canary, waves, pause, resume, cancel, revert, and the journal (docs/SERVER_OTA_ROLLOUT_2026-10-03.md).

A rollout takes a release of the firmware repository (ICD addendum F) to a set of stations in two waves.  The canary
wave is commanded first; the main wave starts only when every canary station has confirmed the release (its
heartbeat reports the new version running and no longer on trial).  Within a wave at most ``max_in_flight`` stations
are in flight (commanded, downloading or on trial).  A failure (an ACK other than OK, or a heartbeat that reports the
release rolled back by the station's boot guard) pauses the rollout once there are ``max_failures`` of them; the
engineer resumes, cancels or reverts it.  Every step is written to the rollout's journal, next to the operator audit
log of the requests that made it: who started it, which station got the command when, every ACK, every heartbeat
that moved a station, every pause and its reason.

A station refuses a release that is not newer than the one it runs (addendum F: ``REJECTED 4``), so a rollout cannot
be undone by commanding the previous version.  ``revert`` cancels what is still pending and commands a *revert
release* instead: the earlier image signed again under a version above the one being reverted.  The journal keeps
both the stations' own rollbacks (the boot guard after three failed starts) and the operator's reverts.

The runner ticks every ``ZS_ROLLOUT_TICK_S`` (30 s) in the server process: it reads the ACKs and heartbeats the
bridges stored, moves the stations and commands the next ones.  ``ZS_ROLLOUT_TICK_S=0`` disables the periodic run
(the tests call ``tick`` themselves).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any, Mapping

from station.command_codec import ACK_RESULTS, validate_command_payload
from station.firmware_codec import UPDATE_COMMAND, ReleaseRepository
from station.store import COMMAND_TTL_US, EventStore

log = logging.getLogger(__name__)

ACTIVE_STATES = ("canary", "running")
ROLLOUT_STATES = ACTIVE_STATES + ("paused", "completed", "cancelled")
IN_FLIGHT = ("commanded", "installed", "trial")
FAILURE_STATES = ("failed", "rolled_back")
FINAL_STATES = ("confirmed", "already", "skipped", "failed", "rolled_back", "unreachable")
STATION_STATES = ("pending",) + IN_FLIGHT + FINAL_STATES
REJECTED, FAILED = 1, 2
VERSION_NOT_NEWER = 4                       # addendum F §3: REJECTED 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS rollouts(rollout_id TEXT PRIMARY KEY, created_us INTEGER NOT NULL, updated_us INTEGER NOT NULL,
  created_by TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL, max_failures INTEGER NOT NULL,
  max_in_flight INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT '', revert_version INTEGER, failures_seen INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS rollout_stations(rollout_id TEXT NOT NULL, station_id INTEGER NOT NULL, wave TEXT NOT NULL,
  state TEXT NOT NULL, from_version INTEGER NOT NULL DEFAULT 0, command_id TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  commanded_us INTEGER NOT NULL DEFAULT 0, updated_us INTEGER NOT NULL, detail TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(rollout_id, station_id));
CREATE TABLE IF NOT EXISTS rollout_journal(id INTEGER PRIMARY KEY AUTOINCREMENT, rollout_id TEXT NOT NULL,
  created_us INTEGER NOT NULL, actor TEXT NOT NULL, event TEXT NOT NULL, station_id INTEGER, detail TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS idx_rollout_journal ON rollout_journal(rollout_id, id);
"""


class RolloutError(ValueError):
    """A request the rollout rules refuse; the message says why."""


@dataclass(frozen=True)
class RolloutSettings:
    tick_s: float = 30.0                    # ZS_ROLLOUT_TICK_S: period of the runner, 0 = no periodic run
    command_attempts: int = 4               # ZS_ROLLOUT_COMMAND_ATTEMPTS: commands per station before 'unreachable'
    max_in_flight: int = 10                 # ZS_ROLLOUT_MAX_IN_FLIGHT: default of a rollout
    max_failures: int = 1                   # ZS_ROLLOUT_MAX_FAILURES: default of a rollout
    confirm_timeout_s: float = 7200.0       # ZS_ROLLOUT_CONFIRM_TIMEOUT_S: installed or on trial without a confirming heartbeat

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RolloutSettings":
        env = os.environ if env is None else env
        settings = cls()
        for name, field, lowest in (("ZS_ROLLOUT_TICK_S", "tick_s", 0), ("ZS_ROLLOUT_COMMAND_ATTEMPTS", "command_attempts", 1),
                                    ("ZS_ROLLOUT_MAX_IN_FLIGHT", "max_in_flight", 1), ("ZS_ROLLOUT_MAX_FAILURES", "max_failures", 1),
                                    ("ZS_ROLLOUT_CONFIRM_TIMEOUT_S", "confirm_timeout_s", 60)):
            text = env.get(name)
            if text is None or not text.strip():
                continue
            try:
                value = float(text) if field in ("tick_s", "confirm_timeout_s") else int(text)
            except ValueError:
                raise ValueError(f"{name} must be a number, not {text!r}") from None
            if value < lowest:
                raise ValueError(f"{name} must be at least {lowest}")
            settings = replace(settings, **{field: value})
        return settings

    def as_dict(self) -> dict[str, Any]:
        return {"tick_s": self.tick_s, "command_attempts": self.command_attempts, "max_in_flight": self.max_in_flight,
                "max_failures": self.max_failures, "confirm_timeout_s": self.confirm_timeout_s}


def ensure_schema(store: EventStore) -> None:
    if getattr(store, "_rollout_schema", False):
        return
    with store.lock, store._conn() as c:
        c.executescript(SCHEMA)
    store._rollout_schema = True


def _now_us() -> int:
    return int(time.time() * 1_000_000)


def _ids(values: Any, what: str) -> list[int]:
    if not isinstance(values, (list, tuple)):
        raise RolloutError(f"{what} must be a list of station ids")
    out: list[int] = []
    for v in values:
        if type(v) is not int or not 0 < v <= 0xFFFFFFFF:
            raise RolloutError(f"{what}: {v!r} is not a station id")
        if v not in out:
            out.append(v)
    return out


class RolloutRunner:
    """Creates, drives and reports firmware rollouts over an EventStore and a ReleaseRepository."""

    def __init__(self, settings: RolloutSettings):
        self.settings = settings
        self.last: dict[str, Any] | None = None

    # ---- requests of the operator --------------------------------------------------------------------------------
    def create(self, store: EventStore, repository: ReleaseRepository, *, version: int, stations: list[int],
               canary: list[int] | None = None, canary_count: int | None = None, max_failures: int | None = None,
               max_in_flight: int | None = None, actor: str = "", now_us: int | None = None) -> dict[str, Any]:
        """A rollout of release ``version`` to ``stations``; ``canary`` names the canary stations (or the first
        ``canary_count`` of the list, default 1).  Only one active or paused rollout may hold a station."""
        ensure_schema(store)
        if type(version) is not int or version <= 0:
            raise RolloutError("version must be a positive integer")
        try:
            release = repository.get(version)
        except ValueError as exc:
            raise RolloutError(f"release {version} is inconsistent: {exc}") from None
        if release is None:
            raise RolloutError(f"release {version} is not in the firmware repository")
        validate_command_payload(UPDATE_COMMAND, release.command_payload())
        targets = _ids(stations, "stations")
        if not targets:
            raise RolloutError("stations must name at least one station")
        if canary is not None:
            canaries = _ids(canary, "canary")
            if any(s not in targets for s in canaries):
                raise RolloutError("every canary station must be in stations")
        else:
            count = 1 if canary_count is None else canary_count
            if type(count) is not int or count < 0:
                raise RolloutError("canary_count must be a non-negative integer")
            canaries = targets[:count]
        failures = self.settings.max_failures if max_failures is None else max_failures
        in_flight = self.settings.max_in_flight if max_in_flight is None else max_in_flight
        if type(failures) is not int or failures < 1 or type(in_flight) is not int or in_flight < 1:
            raise RolloutError("max_failures and max_in_flight must be positive integers")
        when = _now_us() if now_us is None else now_us
        rollout_id = str(uuid.uuid4())
        with store.lock, store._conn() as c:
            busy = c.execute("SELECT rs.station_id, r.rollout_id FROM rollout_stations rs JOIN rollouts r USING(rollout_id) "
                             "WHERE r.state IN ('canary','running','paused') AND rs.state NOT IN ('confirmed','already','skipped','failed','rolled_back','unreachable') "
                             "AND rs.station_id IN (%s)" % ",".join("?" * len(targets)), targets).fetchall()
            if busy:
                raise RolloutError(f"station {busy[0]['station_id']} is still in rollout {busy[0]['rollout_id']}")
            state = "canary" if canaries else "running"
            c.execute("INSERT INTO rollouts(rollout_id,created_us,updated_us,created_by,version,state,max_failures,max_in_flight) VALUES(?,?,?,?,?,?,?,?)",
                      (rollout_id, when, when, actor or "", version, state, failures, in_flight))
            c.executemany("INSERT INTO rollout_stations(rollout_id,station_id,wave,state,updated_us) VALUES(?,?,?,?,?)",
                          [(rollout_id, s, "canary" if s in canaries else "main", "pending", when) for s in targets])
            self._journal(c, rollout_id, when, actor, "created",
                          detail={"version": version, "stations": targets, "canary": canaries, "max_failures": failures, "max_in_flight": in_flight})
        log.info("rollout %s of release %u to %u stations (canary %s) by %s", rollout_id, version, len(targets), canaries, actor or "-")
        return self.get(store, rollout_id)

    def pause(self, store: EventStore, rollout_id: str, *, actor: str = "", reason: str = "", now_us: int | None = None) -> dict[str, Any]:
        return self._transition(store, rollout_id, ACTIVE_STATES, "paused", "paused", actor, reason or "by the operator", now_us)

    def resume(self, store: EventStore, rollout_id: str, *, actor: str = "", now_us: int | None = None) -> dict[str, Any]:
        """Back to the wave the rollout was in.  The failures so far are taken as seen: the rollout pauses again
        after ``max_failures`` new ones."""
        ensure_schema(store)
        when = _now_us() if now_us is None else now_us
        with store.lock, store._conn() as c:
            row = c.execute("SELECT * FROM rollouts WHERE rollout_id=?", (rollout_id,)).fetchone()
            if row is None:
                raise RolloutError("rollout not found")
            if row["state"] != "paused":
                raise RolloutError(f"rollout is {row['state']}, not paused")
            canary_open = c.execute("SELECT COUNT(*) FROM rollout_stations WHERE rollout_id=? AND wave='canary' AND state NOT IN ('confirmed','already','skipped')",
                                    (rollout_id,)).fetchone()[0]
            state = "canary" if canary_open else "running"
            seen = self._failures(c, rollout_id)
            c.execute("UPDATE rollouts SET state=?, reason='', failures_seen=?, updated_us=? WHERE rollout_id=?", (state, seen, when, rollout_id))
            self._journal(c, rollout_id, when, actor, "resumed", detail={"state": state, "failures_seen": seen})
        return self.get(store, rollout_id)

    def cancel(self, store: EventStore, rollout_id: str, *, actor: str = "", reason: str = "", now_us: int | None = None) -> dict[str, Any]:
        """Nothing more is commanded; the stations in flight finish on their own and are still followed."""
        ensure_schema(store)
        when = _now_us() if now_us is None else now_us
        with store.lock, store._conn() as c:
            row = c.execute("SELECT state FROM rollouts WHERE rollout_id=?", (rollout_id,)).fetchone()
            if row is None:
                raise RolloutError("rollout not found")
            if row["state"] not in ACTIVE_STATES + ("paused",):
                raise RolloutError(f"rollout is already {row['state']}")
            c.execute("UPDATE rollout_stations SET state='skipped', detail='cancelled', updated_us=? WHERE rollout_id=? AND state='pending'", (when, rollout_id))
            c.execute("UPDATE rollouts SET state='cancelled', reason=?, updated_us=? WHERE rollout_id=?", (reason or "by the operator", when, rollout_id))
            self._journal(c, rollout_id, when, actor, "cancelled", detail={"reason": reason or "by the operator"})
        return self.get(store, rollout_id)

    def skip(self, store: EventStore, rollout_id: str, station_id: int, *, actor: str = "", reason: str = "", now_us: int | None = None) -> dict[str, Any]:
        """Takes a station out of the rollout (a pending one, or one the rollout waits for, e.g. unreachable)."""
        ensure_schema(store)
        when = _now_us() if now_us is None else now_us
        with store.lock, store._conn() as c:
            row = c.execute("SELECT state FROM rollout_stations WHERE rollout_id=? AND station_id=?", (rollout_id, station_id)).fetchone()
            if row is None:
                raise RolloutError("station is not in the rollout")
            if row["state"] in ("confirmed", "already", "skipped"):
                raise RolloutError(f"station is {row['state']}")
            c.execute("UPDATE rollout_stations SET state='skipped', detail=?, updated_us=? WHERE rollout_id=? AND station_id=?",
                      (reason or "by the operator", when, rollout_id, station_id))
            self._journal(c, rollout_id, when, actor, "skipped", station_id, {"was": row["state"], "reason": reason or "by the operator"})
        return self.get(store, rollout_id)

    def revert(self, store: EventStore, rollout_id: str, repository: ReleaseRepository, *, revert_version: int,
               actor: str = "", reason: str = "", now_us: int | None = None) -> dict[str, Any]:
        """Cancels the rollout and starts a new one that takes the *revert release* ``revert_version`` (above the
        reverted version, addendum F: a station refuses a version that is not newer) to every station the reverted
        rollout commanded; returns the new rollout.  The journal of both carries the link."""
        ensure_schema(store)
        if type(revert_version) is not int or revert_version <= 0:
            raise RolloutError("revert_version must be a positive integer")
        with store._conn() as c:
            row = c.execute("SELECT * FROM rollouts WHERE rollout_id=?", (rollout_id,)).fetchone()
            if row is None:
                raise RolloutError("rollout not found")
            touched = [r["station_id"] for r in c.execute("SELECT station_id FROM rollout_stations WHERE rollout_id=? AND state IN ('commanded','installed','trial','confirmed','rolled_back','unreachable') ORDER BY station_id", (rollout_id,))]
        if revert_version <= row["version"]:
            raise RolloutError(f"a station refuses a version that is not newer than the one it runs (addendum F, REJECTED 4): "
                               f"the revert release must be above {row['version']}, sign the earlier image again as a higher version")
        if not touched:
            raise RolloutError("no station was commanded by this rollout; cancel it instead")
        try:
            release = repository.get(revert_version)
        except ValueError as exc:
            raise RolloutError(f"release {revert_version} is inconsistent: {exc}") from None
        if release is None:
            raise RolloutError(f"release {revert_version} is not in the firmware repository")
        when = _now_us() if now_us is None else now_us
        if row["state"] in ACTIVE_STATES + ("paused",):
            self.cancel(store, rollout_id, actor=actor, reason=f"reverted to {revert_version}: {reason}" if reason else f"reverted to {revert_version}", now_us=when)
        new = self.create(store, repository, version=revert_version, stations=touched, canary_count=0, max_failures=row["max_failures"],
                          max_in_flight=row["max_in_flight"], actor=actor, now_us=when)
        with store.lock, store._conn() as c:
            c.execute("UPDATE rollouts SET revert_version=?, updated_us=? WHERE rollout_id=?", (revert_version, when, rollout_id))
            self._journal(c, rollout_id, when, actor, "reverted", detail={"revert_version": revert_version, "revert_rollout_id": new["rollout_id"], "stations": touched, "reason": reason})
            self._journal(c, new["rollout_id"], when, actor, "reverts", detail={"rollout_id": rollout_id, "version": row["version"]})
        return self.get(store, new["rollout_id"])

    # ---- the runner -------------------------------------------------------------------------------------------------
    def tick(self, store: EventStore, repository: ReleaseRepository, now_us: int | None = None) -> dict[str, Any]:
        """One pass over the active rollouts: evidence first (ACKs, expired commands, heartbeats), then the pauses,
        then the commands of the next stations; returns what moved."""
        ensure_schema(store)
        when = _now_us() if now_us is None else now_us
        moved: dict[str, Any] = {"rollouts": 0, "commanded": 0, "moved": 0, "paused": 0, "completed": 0}
        with store._conn() as c:
            active = [dict(r) for r in c.execute("SELECT * FROM rollouts WHERE state IN ('canary','running','cancelled') ORDER BY created_us")]
        for rollout in active:
            with store.lock, store._conn() as c:
                stations = [dict(r) for r in c.execute("SELECT * FROM rollout_stations WHERE rollout_id=? ORDER BY (wave='canary') DESC, station_id", (rollout["rollout_id"],))]
                if rollout["state"] == "cancelled" and not any(s["state"] in IN_FLIGHT for s in stations):
                    continue
                moved["rollouts"] += 1
                moved["moved"] += self._evidence(store, c, rollout, stations, when)
                if rollout["state"] == "cancelled":
                    continue
                failures = self._failures(c, rollout["rollout_id"])          # events, so a skipped failure stays counted
                if failures - rollout["failures_seen"] >= rollout["max_failures"]:
                    reason = f"{failures} failure(s): " + ", ".join(f"{s['station_id']} {s['state']}" for s in stations if s["state"] in FAILURE_STATES)
                    c.execute("UPDATE rollouts SET state='paused', reason=?, updated_us=? WHERE rollout_id=?", (reason, when, rollout["rollout_id"]))
                    self._journal(c, rollout["rollout_id"], when, "runner", "paused", detail={"reason": reason, "auto": True})
                    moved["paused"] += 1
                    continue
                if rollout["state"] == "canary":
                    canary = [s for s in stations if s["wave"] == "canary"]
                    if all(s["state"] in ("confirmed", "already", "skipped") for s in canary):
                        rollout["state"] = "running"
                        c.execute("UPDATE rollouts SET state='running', updated_us=? WHERE rollout_id=?", (when, rollout["rollout_id"]))
                        self._journal(c, rollout["rollout_id"], when, "runner", "canary_passed",
                                      detail={"stations": [s["station_id"] for s in canary]})
                wave = "canary" if rollout["state"] == "canary" else None
                in_flight = sum(s["state"] in IN_FLIGHT for s in stations)
                for s in stations:
                    if s["state"] != "pending" or (wave and s["wave"] != wave) or in_flight >= rollout["max_in_flight"]:
                        continue
                    if self._command(store, c, repository, rollout, s, when, "runner"):
                        in_flight += 1
                        moved["commanded"] += 1
                if not any(s["state"] in ("pending",) + IN_FLIGHT for s in stations):
                    counts = {k: sum(s["state"] == k for s in stations) for k in STATION_STATES if any(s["state"] == k for s in stations)}
                    c.execute("UPDATE rollouts SET state='completed', updated_us=? WHERE rollout_id=?", (when, rollout["rollout_id"]))
                    self._journal(c, rollout["rollout_id"], when, "runner", "completed", detail=counts)
                    moved["completed"] += 1
        self.last = {"at": when / 1e6, **moved}
        return moved

    def _evidence(self, store: EventStore, c, rollout: dict, stations: list[dict], when: int) -> int:
        """ACKs, expired commands and heartbeats move the stations in flight (and the pending ones that already run
        the release); returns how many moved."""
        moved = 0
        version = rollout["version"]
        for s in stations:
            if s["state"] not in ("pending",) + IN_FLIGHT:
                continue
            hb = store.get_station_heartbeat(s["station_id"])
            det = hb.detector if hb is not None else None
            if s["state"] == "pending":
                if det is not None and det.fw_version >= version and det.fw_state != "TRIAL":
                    self._set(c, rollout, s, "already", when, {"fw_version": det.fw_version}, "heartbeat")
                    moved += 1
                continue
            cmd = c.execute("SELECT acked, ack_result, ack_detail, expires_us, completed_us FROM commands WHERE command_id=?", (s["command_id"],)).fetchone()
            if s["state"] == "commanded" and cmd is not None:
                if cmd["acked"]:
                    result = ACK_RESULTS.get(cmd["ack_result"], str(cmd["ack_result"]))
                    detail = {"ack": result, "detail": cmd["ack_detail"]}
                    moved += 1
                    if cmd["ack_result"] == 0:
                        self._set(c, rollout, s, "installed", when, detail, "ack")      # the heartbeats below may go on
                    elif cmd["ack_result"] == REJECTED and cmd["ack_detail"] == VERSION_NOT_NEWER and det is not None and det.fw_version >= version:
                        self._set(c, rollout, s, "already", when, {**detail, "fw_version": det.fw_version}, "ack")
                        continue
                    else:
                        self._set(c, rollout, s, "failed", when, detail, "ack")
                        continue
                elif cmd["expires_us"] <= when:
                    if s["attempts"] < self.settings.command_attempts:
                        self._command(store, c, None, rollout, s, when, "runner", again=True)
                    else:
                        self._set(c, rollout, s, "unreachable", when, {"attempts": s["attempts"]}, "expired")
                    moved += 1
                    continue
            if s["state"] in ("installed", "trial") and when - s["updated_us"] > self.settings.confirm_timeout_s * 1e6:
                self._set(c, rollout, s, "unreachable", when, {"timeout_s": self.settings.confirm_timeout_s, "last": s["state"]}, "timeout")
                moved += 1
                continue
            if det is None:
                continue
            if det.fw_state == "ROLLED_BACK" and det.fw_other_version == version:
                self._set(c, rollout, s, "rolled_back", when, {"fw_version": det.fw_version, "fw_other_version": det.fw_other_version}, "heartbeat")
                moved += 1
            elif det.fw_version == version and det.fw_state == "TRIAL" and s["state"] != "trial":
                self._set(c, rollout, s, "trial", when, {"fw_version": det.fw_version}, "heartbeat")
                moved += 1
            elif det.fw_version == version and det.fw_state == "IDLE":
                self._set(c, rollout, s, "confirmed", when, {"fw_version": det.fw_version}, "heartbeat")
                moved += 1
        return moved

    def _command(self, store: EventStore, c, repository: ReleaseRepository | None, rollout: dict, s: dict, when: int, actor: str,
                 again: bool = False) -> bool:
        """Queues CMD_UPDATE_FIRMWARE for the station in the caller's transaction."""
        payload = None
        if again:
            row = c.execute("SELECT payload FROM commands WHERE command_id=?", (s["command_id"],)).fetchone()
            payload = json.loads(row["payload"]) if row else None
        if payload is None:
            try:
                release = repository.get(rollout["version"]) if repository is not None else None
            except ValueError:
                release = None
            if release is None:
                self._set(c, rollout, s, "failed", when, {"error": f"release {rollout['version']} missing from the repository"}, "runner")
                return False
            payload = release.command_payload()
        hb = store.get_station_heartbeat(s["station_id"])
        from_version = hb.detector.fw_version if hb is not None and hb.detector is not None else s["from_version"]
        # the command row as EventStore.create_command writes it, in this transaction (the bridge publishes it)
        command_id = str(uuid.uuid4())
        c.execute("INSERT INTO commands(command_id,station_id,created_us,expires_us,command,payload) VALUES(?,?,?,?,?,?)",
                  (command_id, s["station_id"], when, when + COMMAND_TTL_US, UPDATE_COMMAND, json.dumps(payload, ensure_ascii=False)))
        c.execute("UPDATE rollout_stations SET state='commanded', command_id=?, attempts=attempts+1, commanded_us=?, from_version=?, updated_us=?, detail='' "
                  "WHERE rollout_id=? AND station_id=?", (command_id, when, from_version, when, rollout["rollout_id"], s["station_id"]))
        s.update(state="commanded", command_id=command_id, attempts=s["attempts"] + 1, commanded_us=when, from_version=from_version)
        self._journal(c, rollout["rollout_id"], when, actor, "commanded", s["station_id"],
                      {"command_id": command_id, "attempt": s["attempts"], "from_version": from_version, "wave": s["wave"]})
        return True

    def _set(self, c, rollout: dict, s: dict, state: str, when: int, detail: dict, source: str) -> None:
        c.execute("UPDATE rollout_stations SET state=?, detail=?, updated_us=? WHERE rollout_id=? AND station_id=?",
                  (state, json.dumps(detail, ensure_ascii=False), when, rollout["rollout_id"], s["station_id"]))
        self._journal(c, rollout["rollout_id"], when, source, state, s["station_id"], {"was": s["state"], **detail})
        s["state"] = state
        s["updated_us"] = when

    @staticmethod
    def _failures(c, rollout_id: str) -> int:
        return c.execute("SELECT COUNT(*) FROM rollout_journal WHERE rollout_id=? AND event IN ('failed','rolled_back')", (rollout_id,)).fetchone()[0]

    @staticmethod
    def _journal(c, rollout_id: str, when: int, actor: str, event: str, station_id: int | None = None, detail: dict | None = None) -> None:
        c.execute("INSERT INTO rollout_journal(rollout_id,created_us,actor,event,station_id,detail) VALUES(?,?,?,?,?,?)",
                  (rollout_id, when, actor or "", event, station_id, json.dumps(detail or {}, ensure_ascii=False)))

    def _transition(self, store, rollout_id, from_states, to_state, event, actor, reason, now_us):
        ensure_schema(store)
        when = _now_us() if now_us is None else now_us
        with store.lock, store._conn() as c:
            row = c.execute("SELECT state FROM rollouts WHERE rollout_id=?", (rollout_id,)).fetchone()
            if row is None:
                raise RolloutError("rollout not found")
            if row["state"] not in from_states:
                raise RolloutError(f"rollout is {row['state']}")
            c.execute("UPDATE rollouts SET state=?, reason=?, updated_us=? WHERE rollout_id=?", (to_state, reason, when, rollout_id))
            self._journal(c, rollout_id, when, actor, event, detail={"reason": reason})
        return self.get(store, rollout_id)

    # ---- reading ------------------------------------------------------------------------------------------------------
    def list(self, store: EventStore, station_ids: list[int] | None = None) -> list[dict[str, Any]]:
        """The rollouts, newest first, with their station counts; ``station_ids`` limits them to the ones that touch a
        visible station (a limited operator account)."""
        ensure_schema(store)
        with store._conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM rollouts ORDER BY created_us DESC")]
            out = []
            for r in rows:
                stations = [dict(s) for s in c.execute("SELECT station_id, state FROM rollout_stations WHERE rollout_id=?", (r["rollout_id"],))]
                if station_ids is not None and not any(s["station_id"] in station_ids for s in stations):
                    continue
                r["counts"] = {k: sum(s["state"] == k for s in stations) for k in STATION_STATES if any(s["state"] == k for s in stations)}
                r["stations_total"] = len(stations)
                out.append(r)
        return out

    def get(self, store: EventStore, rollout_id: str) -> dict[str, Any]:
        ensure_schema(store)
        with store._conn() as c:
            row = c.execute("SELECT * FROM rollouts WHERE rollout_id=?", (rollout_id,)).fetchone()
            if row is None:
                raise RolloutError("rollout not found")
            out = dict(row)
            out["stations"] = [dict(s) for s in c.execute("SELECT * FROM rollout_stations WHERE rollout_id=? ORDER BY (wave='canary') DESC, station_id", (rollout_id,))]
            out["journal"] = [dict(j) for j in c.execute("SELECT * FROM rollout_journal WHERE rollout_id=? ORDER BY id", (rollout_id,))]
        for s in out["stations"]:
            s["detail"] = _loads(s["detail"])
        for j in out["journal"]:
            j["detail"] = _loads(j["detail"])
        out["counts"] = {k: sum(s["state"] == k for s in out["stations"]) for k in STATION_STATES if any(s["state"] == k for s in out["stations"])}
        return out

    def status(self) -> dict[str, Any]:
        return {"settings": self.settings.as_dict(), "last_tick": self.last}

    async def run_forever(self, store_of, repository_of, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        while not stop.is_set():
            try:
                await asyncio.to_thread(self.tick, store_of(), repository_of())
            except Exception:  # noqa: BLE001 - the periodic run must survive and report
                log.exception("rollout tick failed")
            if self.settings.tick_s <= 0:
                return
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.settings.tick_s)


def _loads(text: str) -> Any:
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {"text": text}


RUNNER: RolloutRunner | None = None         # the server's runner, used by the routes and /api/v1/health


def lifespan(runner: RolloutRunner, store_of, repository_of):
    """FastAPI lifespan that ticks the rollouts while the application is up (``tick_s`` > 0)."""
    global RUNNER
    RUNNER = runner

    @contextlib.asynccontextmanager
    async def _lifespan(app):
        task = stop = None
        if runner.settings.tick_s > 0:
            stop = asyncio.Event()
            task = asyncio.create_task(runner.run_forever(store_of, repository_of, stop))
        try:
            yield
        finally:
            if task is not None:
                stop.set()
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    return _lifespan


def combine(*lifespans):
    """One FastAPI lifespan out of several (retention, rollouts): all entered on startup, left in reverse."""
    @contextlib.asynccontextmanager
    async def _lifespan(app):
        async with contextlib.AsyncExitStack() as stack:
            for item in lifespans:
                await stack.enter_async_context(item(app))
            yield

    return _lifespan

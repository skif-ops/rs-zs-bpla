"""What an operator account sees: its tenants (участки) and stations (docs/SERVER_ACCESS_CONTROL_2026-10-02.md, §6).

An account limited with ``python -m station.operator_auth set-scope`` (or ``PUT /api/v1/access/accounts/{name}/scope``)
sees only the stations it is given and only stations of its tenants; both limits hold together, an empty one does not
limit.  A station's tenant is the tenant of the MQTT bridge (or of the HTTP bench) its messages came through
(``EventStore.note_station_tenant``); a station whose tenant is unknown is not visible to a tenant-limited account.

What a limited account gets:

* stations, bearings, event audio, commands: only its stations (anything else answers 404, as if it did not exist);
* system events, fused tracks, replay: those its stations took part in (a target heard by one of its stations is its
  target), with the lists of stations cut to its own (the other stations' ids and positions are not shown; the fused
  position of the target is);
* the output API ``dioneya.alert/1`` (``/alerts``, ``/alerts/stream``): messages of its tenants that one of its stations
  took part in, ``alert.stations`` cut to its own (``track.stations`` keeps its ids: the schema needs two);
* the live stream ``/stream`` the same way; an open stream re-checks the account every few seconds, so a logout, a
  password change, a disabled account or a changed scope reaches it without a reconnect.

An account without limits (and the isolated bench, where no operator is checked) sees everything as before.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable

LIVE_RECHECK_S = 5.0


class Scope:
    """The stations (``allowed``: a set, or None for all) and tenants (empty: all) one request may see."""

    def __init__(self, tenants: Iterable[str] = (), allowed: Iterable[int] | None = None):
        self.tenants = frozenset(tenants)
        self.allowed = None if allowed is None else frozenset(int(s) for s in allowed)

    @property
    def unrestricted(self) -> bool:
        return self.allowed is None and not self.tenants

    @property
    def station_list(self) -> list[int] | None:
        """For the store's SQL filters: the visible stations, or None for all."""
        return None if self.allowed is None else sorted(self.allowed)

    def station(self, station_id: Any) -> bool:
        if self.allowed is None:
            return True
        try:
            return int(station_id) in self.allowed
        except (TypeError, ValueError):
            return False

    def any_station(self, station_ids: Iterable[Any]) -> bool:
        return self.allowed is None or any(self.station(s) for s in station_ids)

    def tenant(self, tenant: Any) -> bool:
        return not self.tenants or tenant in self.tenants

    # ---- cutting what a limited account must not see ----------------------------------------------------------------
    def event(self, e: dict[str, Any]) -> dict[str, Any] | None:
        """A system event (also a security event) its stations took part in, with the other stations cut out."""
        if self.allowed is None:
            return e
        stations = list(e.get("source_station_ids") or [])
        if not self.any_station(stations):
            return None
        events = list(e.get("source_event_ids") or [])
        keep = [i for i, s in enumerate(stations) if self.station(s)]
        out = dict(e, source_station_ids=[stations[i] for i in keep])
        if len(events) == len(stations):
            out["source_event_ids"] = [events[i] for i in keep]
        out["route_summary"] = [r for r in e.get("route_summary") or [] if self.station(str(r).split(":", 1)[0])]
        return out

    def point(self, p: dict[str, Any] | None) -> dict[str, Any] | None:
        if p is None or self.allowed is None or "stations" not in p:
            return p
        return dict(p, stations=[s for s in p["stations"] if self.station(s)])

    def track(self, t: dict[str, Any] | None) -> dict[str, Any] | None:
        """A fused track (summary, full track or live update) its stations took part in, the other stations cut out."""
        if t is None or self.allowed is None:
            return t
        if not self.any_station(t.get("stations") or []):
            return None
        out = dict(t, stations=[s for s in t.get("stations") or [] if self.station(s)])
        if "members" in t:
            out["members"] = [m for m in t["members"] if self.station(m.get("station_id"))]
        if "track_points" in t:
            out["track_points"] = [self.point(p) for p in t["track_points"]]
        if isinstance(t.get("last"), dict):
            out["last"] = self.point(t["last"])
        if "new_points" in t:
            out["new_points"] = [self.point(p) for p in t["new_points"]]
        return out

    def alert(self, m: dict[str, Any]) -> dict[str, Any] | None:
        """A dioneya.alert/1 message, or None when this account does not get it."""
        if self.unrestricted:
            return m
        if m.get("type") == "heartbeat":
            return m
        if not self.tenant(m.get("tenant")):
            return None
        if self.allowed is None:
            return m
        if "alert" in m:
            stations = [s for s in m["alert"].get("stations") or [] if self.station(s.get("station_id"))]
            return dict(m, alert=dict(m["alert"], stations=stations)) if stations else None
        if "track" in m:
            return m if self.any_station(m["track"].get("stations") or []) else None
        if "bearing" in m:
            return m if self.station((m["bearing"].get("station") or {}).get("station_id")) else None
        return None

    def live(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """An item of the live /stream bus, or None when this account does not get it."""
        if self.allowed is None:
            return item
        kind = item.get("type")
        if kind in ("station", "type_update"):
            return item if self.station((item.get("data") or {}).get("station_id")) else None
        if kind == "bearings":
            return item if self.station(item.get("station_id")) else None
        if kind == "track":
            return self.track(item)
        if "system_event_id" in item:
            return self.event(item)
        return None                                  # an item nobody declared: not to a limited account


UNRESTRICTED = Scope()


def _operator(conn) -> dict[str, Any] | None:
    return (conn.scope.get("state") or {}).get("operator")


def scope_for(operator: dict[str, Any] | None, store) -> Scope:
    """The scope of an operator (the ``request.state.operator`` of operator_auth); none (the bench): everything."""
    if not operator:
        return UNRESTRICTED
    tenants = [t for t in operator.get("tenants") or [] if t]
    stations = [int(s) for s in operator.get("stations") or []]
    if not tenants and not stations:
        return UNRESTRICTED
    if tenants:
        known = store.station_tenants()
        candidates = stations or list(known)
        allowed = [s for s in candidates if known.get(s) in tenants]
    else:
        allowed = stations
    return Scope(tenants, allowed)


def scope_of(conn, store) -> Scope:
    """The scope of an HTTP request or WebSocket."""
    return scope_for(_operator(conn), store)


class LiveScope:
    """The scope of an open WebSocket, re-checked every few seconds: the account may log out, lose its password,
    be disabled or get another scope while the stream runs.  ``current()`` answers None when the stream must close."""

    def __init__(self, ws, store, clock=time.monotonic):
        self.ws, self.store, self.clock = ws, store, clock
        self.operator = _operator(ws)
        self.scope = scope_for(self.operator, store)
        self.checked = clock()

    def current(self) -> Scope | None:
        if self.operator is None or self.clock() - self.checked < LIVE_RECHECK_S:
            return self.scope
        from station import operator_auth

        self.checked = self.clock()
        if operator_auth.auth_disabled():
            return self.scope
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in self.ws.scope.get("headers", [])}
        user, _ = operator_auth.authenticate(headers)
        if user is None or user["name"] != self.operator["name"] or operator_auth.READ not in user["permissions"]:
            return None
        self.operator = {"name": user["name"], "tenants": list(user.get("tenants") or []),
                         "stations": list(user.get("stations") or [])}
        self.scope = scope_for(self.operator, self.store)
        return self.scope


async def close_revoked(ws) -> None:
    try:
        await ws.close(code=4401)
    except (RuntimeError, asyncio.CancelledError):
        pass

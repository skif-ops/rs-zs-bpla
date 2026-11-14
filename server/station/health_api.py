"""``GET /api/v1/stations/health``: the monitoring page's data (station/health.py) for the account that asks, cut to the
stations it may see (station/access_scope.py).  Read-only: the ``read`` permission, like the other station data."""
from __future__ import annotations

from fastapi import APIRouter, Request

from station import health, pki_registry
from station.access_scope import Scope, scope_of

router = APIRouter(prefix="/api/v1/stations", tags=["ZS-BPLA stations"])


def _station_store():
    from station.router import store

    return store


def _health_scope(request: Request, store, registry_rows: list[dict]) -> Scope:
    """Include registered stations before their first heartbeat.

    The generic tenant scope is derived from ``station_tenants`` because most
    APIs only expose stations that have sent data.  The monitoring page also
    has to show registered units as ``never``.  Build its station set from the
    event store and the public PKI registry, while preserving an explicit
    per-station restriction from the operator account.
    """
    scope = scope_of(request, store)
    operator = (request.scope.get("state") or {}).get("operator") or {}
    tenants = {str(t) for t in operator.get("tenants") or [] if t}
    explicit = {int(s) for s in operator.get("stations") or []}
    if not tenants:
        return scope
    tenant_by_station = {int(r["station_id"]): str(r.get("tenant") or "") for r in registry_rows}
    # A received message is the runtime authority for the station's tenant;
    # the registry fills only stations that have never reported.
    tenant_by_station.update({int(s): str(t) for s, t in store.station_tenants().items()})
    candidates = explicit or set(tenant_by_station)
    allowed = {sid for sid in candidates if tenant_by_station.get(sid) in tenants}
    return Scope(tenants, allowed)


@router.get("/health")
async def stations_health(request: Request):
    store = _station_store()
    registry_rows, _ = pki_registry.registry_rows()
    return health.report(store, _health_scope(request, store, registry_rows), registry_rows)

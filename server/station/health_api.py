"""``GET /api/v1/stations/health``: the monitoring page's data (station/health.py) for the account that asks, cut to the
stations it may see (station/access_scope.py).  Read-only: the ``read`` permission, like the other station data."""
from __future__ import annotations

from fastapi import APIRouter, Request

from station import health, pki_registry
from station.access_scope import scope_of

router = APIRouter(prefix="/api/v1/stations", tags=["ZS-BPLA stations"])


def _station_store():
    from station.router import store

    return store


@router.get("/health")
async def stations_health(request: Request):
    store = _station_store()
    registry_rows, _ = pki_registry.registry_rows()
    return health.report(store, scope_of(request, store), registry_rows)

"""Who sees which stations, set by the security admin and engineers (docs/SERVER_ACCESS_CONTROL_2026-10-02.md, §6).

Both need the ``scopes.manage`` permission (operator_auth.ROLE_PERMISSIONS).  An engineer sets the scope of viewers,
operators and service accounts only; the admin (``users.manage``) of any account but the superuser skif_root, which
sees everything.  Nobody sets their own scope, and a manager limited to stations or tenants gives only what it sees
itself (never "all").  Every change goes to the audit log with what was set.  The CLI (``python -m
station.operator_auth set-scope``) stays for the server's shell.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from station import operator_auth
from station.access_scope import scope_for

ENGINEER_MANAGES = {"viewer", "operator", "service"}
BASE = Path(__file__).resolve().parents[1]
PKI_DIR_ENV = "ZS_PKI_DIR"          # the PKI directory of python -m pki.cli (default data/pki): its registry feeds the catalog

router = APIRouter(prefix="/api/v1/access", tags=["access"])


class ScopeRequest(BaseModel):
    tenants: list[str] = Field(default_factory=list, max_length=64)
    stations: list[int] = Field(default_factory=list, max_length=4096)


def _manager(request: Request) -> dict:
    operator = (request.scope.get("state") or {}).get("operator")
    if not operator or operator_auth.SCOPES_MANAGE not in operator.get("permissions", []):
        raise HTTPException(403, "managing scopes needs an operator account with scopes.manage")
    return operator


def _manages(manager: dict, roles: list[str]) -> bool:
    if operator_auth.SUPERUSER_ROLE in roles:      # the superuser sees everything: nobody limits it
        return False
    return operator_auth.USERS_MANAGE in manager["permissions"] or set(roles) <= ENGINEER_MANAGES


def _station_store():
    from station.router import store

    return store


def _entry(name: str, entry: dict) -> dict:
    return {"name": name, "roles": entry["roles"], "disabled": entry["disabled"], "tenants": entry["tenants"],
            "stations": entry["stations"]}


@router.get("/accounts")
async def accounts(request: Request):
    """The accounts this manager may give a scope to, with their scopes (empty: all)."""
    manager = _manager(request)
    users = operator_auth.current_store().listing()["users"]
    return [_entry(name, e) for name, e in sorted(users.items()) if name != manager["name"] and _manages(manager, e["roles"])]


def _registry() -> tuple[list[dict], set[str]]:
    """The stations of the PKI registry (server/pki, ``registry.sqlite3`` in the PKI directory) and the tenants of its
    lots, when the server keeps the registry: every unit of the pilot with its serial, lot and tenant, before it ever
    connects.  Without a registry the catalog has only the stations that reported."""
    path = Path(os.environ.get(PKI_DIR_ENV) or BASE / "data" / "pki") / "registry.sqlite3"
    if not path.exists():
        return [], set()
    try:
        from pki.registry import Registry

        registry = Registry(path)
        rows = [{"station_id": r.station_id, "serial": r.serial, "tenant": r.tenant, "lot": r.lot, "status": r.status}
                for r in registry.list()]
        return rows, set(registry.tenant_by_lot.values())
    except Exception:          # noqa: BLE001 - a registry this server cannot read: the catalog still lists what reported
        return [], set()


@router.get("/catalog")
async def catalog(request: Request):
    """What a manager may choose from: the tenants and stations it sees itself (everything for an unlimited one), from
    the PKI registry (serial, lot, tenant, status) and the stations that reported (``seen``, with the tenant of the
    bridge they came through)."""
    manager = _manager(request)
    store = _station_store()
    own = scope_for(manager, store)
    seen_tenants = store.station_tenants()
    seen = {int(s["station_id"]) for s in store.list_stations() if s.get("station_id") is not None} | set(seen_tenants)
    registry_rows, registry_tenants = _registry()
    rows = {r["station_id"]: dict(r, seen=r["station_id"] in seen) for r in registry_rows}
    for sid in sorted(seen):
        if sid not in rows:
            rows[sid] = {"station_id": sid, "serial": None, "tenant": None, "lot": None, "status": "seen", "seen": True}
        if seen_tenants.get(sid):                     # the bridge a station really came through wins over its lot
            rows[sid]["tenant"] = seen_tenants[sid]
    stations = [rows[sid] for sid in sorted(rows) if own.station(sid)]
    tenants = {r["tenant"] for r in rows.values() if r["tenant"]} | registry_tenants
    if own.tenants:
        tenants = {t for t in tenants if t in own.tenants}
    return {"tenants": sorted(tenants), "stations": stations}


@router.put("/accounts/{name}/scope")
async def set_scope(request: Request, name: str, body: ScopeRequest):
    manager = _manager(request)
    store = operator_auth.current_store()
    target = store.user(name)
    if target is None or name == manager["name"] or not _manages(manager, target["roles"]):
        raise HTTPException(404, "no such account to manage")
    tenants = sorted({t.strip() for t in body.tenants if t.strip()})
    stations = sorted(set(body.stations))
    own = scope_for(manager, _station_store())
    if not own.unrestricted:                    # a limited manager gives only what it sees itself
        if not stations or not set(stations) <= set(own.station_list or []):
            raise HTTPException(403, "give only stations this account sees itself")
        if own.tenants and (not tenants or not set(tenants) <= own.tenants):
            raise HTTPException(403, "give only tenants this account sees itself")
    try:
        store.set_scope(name, tenants, stations)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    operator_auth.current_state().audit(manager["name"], manager.get("via", "?"), operator_auth._client_address(request.scope, {
        k.lower(): v for k, v in request.headers.items()}), "set-scope", name, detail={"tenants": tenants, "stations": stations})
    return _entry(name, store.listing()["users"][name])

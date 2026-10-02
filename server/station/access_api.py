"""Who sees which stations, set by the security admin and engineers (docs/SERVER_ACCESS_CONTROL_2026-10-02.md, §6).

Both need the ``scopes.manage`` permission (operator_auth.ROLE_PERMISSIONS).  An engineer sets the scope of viewers,
operators and service accounts only; the admin (``users.manage``) of any account but the superuser skif_root, which
sees everything.  Nobody sets their own scope, and a manager limited to stations or tenants gives only what it sees
itself (never "all").  Every change goes to the audit log with what was set.  The CLI (``python -m
station.operator_auth set-scope``) stays for the server's shell.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from station import operator_auth
from station.access_scope import scope_for

ENGINEER_MANAGES = {"viewer", "operator", "service"}

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

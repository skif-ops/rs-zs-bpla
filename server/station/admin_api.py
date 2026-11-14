"""Administration API behind the /admin page (docs/SERVER_ACCESS_CONTROL_2026-10-02.md, §8 and §9).

* Accounts (``users.manage``: the security admin and the superuser): list with sessions and tokens, create with a
  temporary password, change roles, disable and enable, reset the password (a temporary one again) or the second
  factor (enrolled anew at the next login), end the sessions, issue and revoke API tokens, remove.  A new or reset
  account changes its password at its next login, and an engineer or admin enrols its second factor there.  Nobody
  manages their own account here, and nobody but the superuser itself touches skif_root.  A token issued here goes to
  the issuer, so it never carries a permission the issuer does not have (an admin cannot mint a station command token).
* The audit log (``audit.read``): the latest records and whether the hash chain is intact.
* The switch of the audit log of actions: reading needs ``audit.read``, switching ``audit.control`` (the superuser
  only, never through an API token); the switching itself is always recorded.

Every change here is made from a browser session (never an API token) and repeats the code of the second factor
(header ``X-Second-Factor``) when the account has one; operator_auth.PERMISSION_RULES binds the permissions, and the
middleware records each change in the audit log.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from station import operator_auth

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AuditLoggingRequest(BaseModel):
    enabled: bool


class NewAccount(BaseModel):
    name: str = Field(max_length=32)
    roles: list[str] = Field(min_length=1, max_length=8)
    password: str = Field(max_length=256)


class AccountChange(BaseModel):
    roles: list[str] | None = Field(default=None, max_length=8)
    disabled: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(max_length=256)


class TokenRequest(BaseModel):
    label: str = Field(default="", max_length=64)
    scopes: list[str] = Field(default_factory=lambda: [operator_auth.READ], max_length=16)
    expires_days: int | None = Field(default=None, ge=1, le=3650)


def _operator(request: Request, permission: str) -> dict:
    operator = (request.scope.get("state") or {}).get("operator")
    if not operator or permission not in operator.get("permissions", []):
        raise HTTPException(403, f"needs an operator account with {permission}")
    return operator


def _address(request: Request) -> str:
    return operator_auth._client_address(request.scope, {k.lower(): v for k, v in request.headers.items()})


def _changing(request: Request, permission: str) -> dict:
    """A change: a browser session of an account with the permission, confirmed by the second factor's code."""
    operator = _operator(request, permission)
    if operator.get("via") != "cookie":
        raise HTTPException(403, "administration changes are made from a browser session, not with an API token")
    user = operator_auth.current_store().user(operator["name"])
    if user is None or not operator_auth.confirm_second_factor(user, request.headers.get("x-second-factor")):
        raise HTTPException(403, "confirm with the current code of your second factor")
    return operator


def _target(operator: dict, name: str) -> dict:
    """An account this operator may manage: not its own, not the superuser's."""
    if name == operator["name"]:
        raise HTTPException(403, "your own account is not managed here")
    if name == operator_auth.SUPERUSER_NAME:
        raise HTTPException(403, f"{operator_auth.SUPERUSER_NAME} is managed only by itself")
    user = operator_auth.current_store().user(name)
    if user is None:
        raise HTTPException(404, "no such account")
    return user


def _value_error(exc: ValueError) -> HTTPException:
    return HTTPException(422, str(exc))


def _account(name: str, entry: dict, tokens: dict, sessions: dict, raw: dict) -> dict:
    return {"name": name, "roles": entry["roles"], "disabled": entry["disabled"], "tenants": entry["tenants"],
            "stations": entry["stations"], "second_factor": entry["second_factor"], "must_change": entry["must_change"],
            "totp_at_login": bool(raw.get("totp_at_login")), "superuser": entry["superuser"], "created": entry["created"],
            "sessions": sessions.get(name, 0),
            "tokens": [dict(t, id=tid) for tid, t in sorted(tokens.items()) if t["user"] == name]}


# ---- the audit log -----------------------------------------------------------------------------------------------
@router.get("/audit-logging")
async def audit_logging(request: Request):
    _operator(request, operator_auth.AUDIT_READ)
    return operator_auth.current_state().audit_logging()


@router.put("/audit-logging")
async def set_audit_logging(request: Request, body: AuditLoggingRequest):
    operator = _changing(request, operator_auth.AUDIT_CONTROL)
    state = operator_auth.current_state()
    if state.audit_logging()["enabled"] != body.enabled:
        state.set_audit_logging(body.enabled, operator["name"], operator.get("via", "?"), _address(request))
    return state.audit_logging()


@router.get("/audit")
async def audit(request: Request, limit: int = Query(200, ge=1, le=5000), actor: str | None = Query(None, max_length=64)):
    _operator(request, operator_auth.AUDIT_READ)
    state = operator_auth.current_state()
    intact, checked = state.audit_verify()
    return {"records": state.audit_records(limit, actor or None), "intact": intact, "checked": checked}


# ---- accounts ----------------------------------------------------------------------------------------------------
@router.get("/accounts")
async def accounts(request: Request):
    _operator(request, operator_auth.USERS_MANAGE)
    store = operator_auth.current_store()
    listing = store.listing()
    sessions: dict[str, int] = {}
    for s in operator_auth.current_state().sessions():
        sessions[s["user"]] = sessions.get(s["user"], 0) + 1
    raw = {name: store.user(name) or {} for name in listing["users"]}
    return [_account(name, e, listing["tokens"], sessions, raw[name]) for name, e in sorted(listing["users"].items())]


@router.post("/accounts")
async def create_account(request: Request, body: NewAccount):
    _changing(request, operator_auth.USERS_MANAGE)
    store = operator_auth.current_store()
    try:
        store.add_user(body.name, body.roles, body.password)
    except ValueError as exc:
        raise _value_error(exc) from None
    store.require_first_login(body.name)
    return {"name": body.name, "roles": store.user(body.name)["roles"]}


@router.put("/accounts/{name}")
async def change_account(request: Request, name: str, body: AccountChange):
    operator = _changing(request, operator_auth.USERS_MANAGE)
    _target(operator, name)
    store = operator_auth.current_store()
    try:
        if body.roles is not None:
            store.set_roles(name, body.roles)
            user = store.user(name)
            if operator_auth.needs_second_factor(user) and not user.get("totp"):
                store.set_totp(name, None, enrol_at_login=True)     # a new engineer or admin enrols at the next login
        if body.disabled is not None:
            store.set_disabled(name, body.disabled)
            if body.disabled:
                operator_auth.current_state().close_sessions(name)
    except ValueError as exc:
        raise _value_error(exc) from None
    user = store.user(name)
    return {"name": name, "roles": user["roles"], "disabled": bool(user.get("disabled"))}


@router.post("/accounts/{name}/password")
async def reset_password(request: Request, name: str, body: PasswordReset):
    operator = _changing(request, operator_auth.USERS_MANAGE)
    _target(operator, name)
    store = operator_auth.current_store()
    try:
        store.set_password(name, body.password)
    except ValueError as exc:
        raise _value_error(exc) from None
    store.require_first_login(name)
    operator_auth.current_state().close_sessions(name)
    return {"name": name, "must_change": True}


@router.post("/accounts/{name}/totp-reset")
async def reset_second_factor(request: Request, name: str):
    operator = _changing(request, operator_auth.USERS_MANAGE)
    _target(operator, name)
    operator_auth.current_store().set_totp(name, None, enrol_at_login=True)
    operator_auth.current_state().close_sessions(name)
    return {"name": name, "second_factor": False, "totp_at_login": True}


@router.post("/accounts/{name}/logout")
async def logout_account(request: Request, name: str):
    operator = _changing(request, operator_auth.USERS_MANAGE)
    _target(operator, name)
    return {"name": name, "sessions_closed": operator_auth.current_state().close_sessions(name)}


@router.post("/accounts/{name}/tokens")
async def issue_token(request: Request, name: str, body: TokenRequest):
    operator = _changing(request, operator_auth.USERS_MANAGE)
    _target(operator, name)
    beyond = set(body.scopes) - set(operator["permissions"])
    if beyond:                                  # the token goes to whoever issues it: never more than they may do
        raise HTTPException(403, f"a token may not carry what you may not do yourself: {', '.join(sorted(beyond))}")
    try:
        token_id, token = operator_auth.current_store().issue_token(name, body.label, body.scopes, body.expires_days)
    except ValueError as exc:
        raise _value_error(exc) from None
    return {"id": token_id, "token": token}


@router.delete("/tokens/{token_id}")
async def revoke_token(request: Request, token_id: str):
    operator = _changing(request, operator_auth.USERS_MANAGE)
    store = operator_auth.current_store()
    owner = store.listing()["tokens"].get(token_id, {}).get("user")
    if owner is None:
        raise HTTPException(404, "no such token")
    _target(operator, owner)
    store.revoke_token(token_id)
    return {"id": token_id, "revoked": True}


@router.delete("/accounts/{name}")
async def remove_account(request: Request, name: str):
    operator = _changing(request, operator_auth.USERS_MANAGE)
    _target(operator, name)
    try:
        operator_auth.current_store().remove_user(name)
    except ValueError as exc:
        raise _value_error(exc) from None
    operator_auth.current_state().close_sessions(name)
    return {"name": name, "removed": True}

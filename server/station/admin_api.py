"""Administration API (docs/SERVER_ACCESS_CONTROL_2026-10-02.md, §8): the switch of the audit log of actions.

Reading the switch needs ``audit.read`` (the security admin and the superuser); switching it needs ``audit.control``,
which only the superuser skif_root has and never through an API token (operator_auth.PERMISSION_RULES).  The switching
itself is always recorded, so the log shows when and by whom the actions were not recorded.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from station import operator_auth

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class AuditLoggingRequest(BaseModel):
    enabled: bool


def _operator(request: Request, permission: str) -> dict:
    operator = (request.scope.get("state") or {}).get("operator")
    if not operator or permission not in operator.get("permissions", []):
        raise HTTPException(403, f"needs an operator account with {permission}")
    return operator


@router.get("/audit-logging")
async def audit_logging(request: Request):
    _operator(request, operator_auth.AUDIT_READ)
    return operator_auth.current_state().audit_logging()


@router.put("/audit-logging")
async def set_audit_logging(request: Request, body: AuditLoggingRequest):
    operator = _operator(request, operator_auth.AUDIT_CONTROL)
    state = operator_auth.current_state()
    address = operator_auth._client_address(request.scope, {k.lower(): v for k, v in request.headers.items()})
    if state.audit_logging()["enabled"] != body.enabled:
        state.set_audit_logging(body.enabled, operator["name"], operator.get("via", "?"), address)
    return state.audit_logging()

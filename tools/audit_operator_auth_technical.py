#!/usr/bin/env python3
"""QG-2 independent runtime audit of operator authentication: every route the application registers (today's and
any added later) is closed without an operator, except the explicit public set and the station bench ingress."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
PUBLIC = {("GET", "/login"), ("POST", "/login"), ("POST", "/logout"), ("GET", "/api/v1/health")}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def effective_routes(routes, prefix: str = ""):
    """(kind, methods, path) of every route, descending into included routers (FastAPI keeps them as nodes)."""
    from starlette.routing import Mount, WebSocketRoute

    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from effective_routes(inner.routes, prefix + route.include_context.prefix)
        elif isinstance(route, Mount):
            yield "mount", set(), prefix + route.path
        elif isinstance(route, WebSocketRoute) or type(route).__name__ == "APIWebSocketRoute":
            yield "websocket", set(), prefix + route.path
        else:
            yield "http", set(getattr(route, "methods", None) or ()) - {"HEAD"}, prefix + route.path


def main() -> int:
    sys.path.insert(0, str(SERVER))
    tmp = Path(tempfile.mkdtemp(prefix="zs_auth_audit_"))
    for name in ("ZS_OPERATOR_AUTH_INSECURE_BENCH", "ZS_STATION_HTTP_INSECURE_BENCH", "ZS_OPERATOR_COOKIE_SECURE"):
        os.environ.pop(name, None)
    os.environ["ZS_OPERATOR_ACCOUNTS"] = str(tmp / "operators.json")
    os.environ["ZS_OPERATOR_SESSION_KEY_FILE"] = str(tmp / "session.key")

    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from app import app
    from station import operator_auth
    from station.router import router, station_http_router

    station = {(m, router.prefix + r.path) for r in station_http_router.routes if isinstance(r, APIRoute) for m in r.methods}
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)

    routes = list(effective_routes(app.routes))
    require([path for kind, _, path in routes if kind == "mount"] == ["/static"], "unexpected mounted application")
    require(any(kind == "websocket" for kind, _, _ in routes), "event stream not found: route walk is broken")
    require(any(path.startswith("/api/v1/") for _, _, path in routes), "API routes not found: route walk is broken")

    def sweep(expected: int) -> int:
        checked = 0
        for kind, methods, path in routes:
            if kind == "websocket":
                try:
                    with client.websocket_connect(concrete(path)):
                        raise AssertionError(f"websocket {path} accepted without an operator")
                except WebSocketDisconnect as exc:
                    require(exc.code == 4000 + expected, f"websocket {path} closed with {exc.code}")
                checked += 1
                continue
            for method in sorted(methods):
                if (method, path) in PUBLIC or (method, path) in station:
                    continue
                status = client.request(method, concrete(path)).status_code
                require(status == expected, f"{method} {path} answered {status} without an operator")
                checked += 1
        return checked

    closed = sweep(503)                                         # no accounts: fail-closed
    store = operator_auth.current_store()
    store.add_user("audit", "viewer", "audit password 1")
    require(sweep(401) == closed, "route set changed between sweeps")   # accounts exist, no login: 401 everywhere
    require(client.get("/api/v1/health").status_code == 200, "health probe is not public")
    require(client.post("/api/v1/stations/1/heartbeat", json={}).status_code == 403, "station bench guard bypassed")

    ok = client.post("/login", data={"username": "audit", "password": "audit password 1"}, headers={"origin": "https://testserver"})
    require(ok.status_code == 303 and "samesite=strict" in ok.headers["set-cookie"].lower(), "login failed or weak cookie")
    require(client.get("/api/v1/events").status_code == 200, "viewer cannot read")
    require(client.get("/api/v1/stations/1/events/1/audio").status_code == 403, "viewer can fetch event audio")
    require(client.post("/api/v1/stations/1/audio-request", json={"event_id": 1},
                        headers={"origin": "https://testserver"}).status_code == 403, "viewer can change things")

    os.environ["ZS_OPERATOR_AUTH_INSECURE_BENCH"] = "yes"
    require(TestClient(app).get("/api/v1/events").status_code == 401, "ambiguous bench opt-out accepted")
    os.environ.pop("ZS_OPERATOR_AUTH_INSECURE_BENCH")

    print("Operator authentication QG-2 independent runtime audit: PASS")
    print(f"{closed} route/method pairs closed without an operator (503 without accounts, 401 without login); "
          "viewer read-only, event audio operator-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

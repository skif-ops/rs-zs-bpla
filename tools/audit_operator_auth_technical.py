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
PUBLIC = {("GET", "/login"), ("POST", "/login"), ("POST", "/logout"), ("POST", "/login/password"), ("POST", "/login/totp"),
          ("GET", "/api/v1/health")}


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
    os.environ["ZS_OPERATOR_STATE"] = str(tmp / "state.sqlite3")
    os.environ.pop("ZS_OPERATOR_TOTP", None)

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

    closed = sweep(401)                                         # no accounts but the superuser the server made: closed
    store = operator_auth.current_store()
    root = store.user(operator_auth.SUPERUSER_NAME)
    require(root is not None and root["roles"] == [operator_auth.SUPERUSER_ROLE] and root["must_change"],
            "the superuser is missing or its default password is not to be changed")
    first = client.post("/login", data={"username": operator_auth.SUPERUSER_NAME, "password": operator_auth.SUPERUSER_DEFAULT_PASSWORD},
                        headers={"origin": "https://testserver"})
    require(first.status_code == 200 and operator_auth.COOKIE_NAME not in first.cookies and "/login/password" in first.text,
            "the default superuser password opened a session")
    store.add_user("audit", "viewer", "audit password 1")
    require(sweep(401) == closed, "route set changed between sweeps")   # accounts exist, no login: 401 everywhere
    require(client.get("/api/v1/health").status_code == 200, "health probe is not public")
    for kind, methods, path in routes:                          # every changing route names its permission
        for method in methods - operator_auth.SAFE_METHODS:
            if kind == "http" and (method, path) not in PUBLIC and (method, path) not in station:
                require(operator_auth.required_permission(method, concrete(path)) not in (None, operator_auth.UNMAPPED),
                        f"{method} {path} has no permission rule")
    require(client.post("/api/v1/stations/1/heartbeat", json={}).status_code == 403, "station bench guard bypassed")

    ok = client.post("/login", data={"username": "audit", "password": "audit password 1"}, headers={"origin": "https://testserver"})
    require(ok.status_code == 303 and "samesite=strict" in ok.headers["set-cookie"].lower(), "login failed or weak cookie")
    require(client.get("/api/v1/events").status_code == 200, "viewer cannot read")
    require(client.get("/api/v1/stations/1/events/1/audio").status_code == 403, "viewer can fetch event audio")
    require(client.post("/api/v1/stations/1/audio-request", json={"event_id": 1},
                        headers={"origin": "https://testserver"}).status_code == 403, "viewer can change things")

    changing = [(m, p) for kind, ms, p in routes if kind == "http" for m in ms - operator_auth.SAFE_METHODS
                if (m, p) not in PUBLIC and (m, p) not in station]
    for method, path in changing:                               # a viewer changes nothing
        status = client.request(method, concrete(path), headers={"origin": "https://testserver"}).status_code
        require(status == 403, f"viewer {method} {path} answered {status}")
    store.add_user("auditop", "operator", "audit password 1")
    op = TestClient(app, base_url="https://testserver", follow_redirects=False)
    require(op.post("/login", data={"username": "auditop", "password": "audit password 1"},
                    headers={"origin": "https://testserver"}).status_code == 303, "operator login failed")
    for method, path in changing:                               # an operator neither edits the dataset nor commands stations
        need = operator_auth.required_permission(method, concrete(path))
        if need not in operator_auth.ROLE_PERMISSIONS["operator"]:
            status = op.request(method, concrete(path), headers={"origin": "https://testserver"}).status_code
            require(status == 403, f"operator {method} {path} answered {status}")
    store.add_user("auditeng", "engineer", "audit password 1")
    eng = TestClient(app, base_url="https://testserver", follow_redirects=False)
    require(eng.post("/login", data={"username": "auditeng", "password": "audit password 1"},
                     headers={"origin": "https://testserver"}).status_code == 403, "engineer logged in without a second factor")
    ok_chain, records = operator_auth.current_state().audit_verify()
    require(ok_chain and records >= len(changing), "audit log incomplete or broken")

    os.environ["ZS_OPERATOR_AUTH_INSECURE_BENCH"] = "yes"
    require(TestClient(app).get("/api/v1/events").status_code == 401, "ambiguous bench opt-out accepted")
    os.environ.pop("ZS_OPERATOR_AUTH_INSECURE_BENCH")

    print("Operator authentication QG-2 independent runtime audit: PASS")
    print(f"{closed} route/method pairs closed without an operator (401; only the superuser exists at first and its default "
          "password opens no session until changed); "
          "viewer read-only, event audio operator-only, every changing route declared, operators do not command stations, "
          "engineers need the second factor, audit chain intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

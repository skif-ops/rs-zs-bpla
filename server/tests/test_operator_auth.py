"""Operator authentication (release audit item 1): fail-closed without accounts, login sessions kept on the server,
roles and permissions, the second factor of engineers and admins, API tokens with scopes, same-origin checks, login
throttling, the audit log, the event stream, and the station bench routes left to their own guard."""
import io
import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from station import operator_auth as oa

PASSWORD = "correct horse battery"
ORIGIN = {"origin": "https://testserver"}
AUDIO_REQUEST = "/api/v1/stations/17/audio-request"


@pytest.fixture
def auth(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(oa.INSECURE_BENCH_ENV, raising=False)
    monkeypatch.delenv(oa.TOTP_ENV, raising=False)
    monkeypatch.setenv(oa.ACCOUNTS_ENV, str(tmp_path / "operators.json"))
    monkeypatch.setenv(oa.SESSION_KEY_ENV, str(tmp_path / "session.key"))
    monkeypatch.setenv(oa.STATE_ENV, str(tmp_path / "state.sqlite3"))
    monkeypatch.setattr(oa, "throttle", oa.LoginThrottle())
    from app import app

    return oa.current_store(), app


def client(app) -> TestClient:
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def login(c: TestClient, name: str, password: str = PASSWORD, next_url: str = "/", code: str = ""):
    return c.post("/login", data={"username": name, "password": password, "next": next_url, "code": code}, headers=ORIGIN)


def code_now(secret: str, step: int = 0) -> str:
    return oa.totp_code(secret, int(time.time() // oa.TOTP_STEP_S) + step)


def enrolled(store, name: str, roles: str) -> str:
    store.add_user(name, roles, PASSWORD)
    secret = oa.new_totp_secret()
    store.set_totp(name, secret)
    return secret


def test_fail_closed_without_accounts(auth):
    store, app = auth
    c = client(app)
    r = c.get("/api/v1/events")
    assert r.status_code == 401                                          # only the superuser exists: a login is needed
    assert store.listing()["users"].keys() == {oa.SUPERUSER_NAME} and store.user(oa.SUPERUSER_NAME)["must_change"]
    page = c.get("/", headers={"accept": "text/html"})
    assert page.status_code == 303 and page.headers["location"] == "/login?next=/"
    assert c.get("/api/v1/health").status_code == 200                    # public probe
    assert c.get("/static/js/app.js").status_code == 200


def test_login_session_roles_and_logout(auth):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    store.add_user("vic", "viewer", PASSWORD)
    c = client(app)
    assert c.get("/api/v1/events").status_code == 401
    assert login(c, "anna", "wrong password!").status_code == 401
    r = login(c, "anna", next_url="/dataset")
    assert r.status_code == 303 and r.headers["location"] == "/dataset"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "secure" in cookie
    assert c.get("/api/v1/events").status_code == 200
    assert "anna (operator)" in c.get("/single").text                    # nav shows who is logged in
    assert c.post(AUDIO_REQUEST, json={"event_id": 5}, headers=ORIGIN).status_code == 200
    replay = c.cookies[oa.COOKIE_NAME]
    assert c.post("/logout", headers=ORIGIN).status_code == 303
    assert c.get("/api/v1/events").status_code == 401
    # logout ends the session on the server: the old cookie, replayed, is refused
    assert c.get("/api/v1/events", headers={"cookie": f"{oa.COOKIE_NAME}={replay}"}).status_code == 401

    v = client(app)
    login(v, "vic")
    assert v.get("/api/v1/events").status_code == 200                   # viewers read
    assert v.post(AUDIO_REQUEST, json={"event_id": 5}, headers=ORIGIN).status_code == 403
    assert v.get("/api/v1/stations/17/events/5/audio").status_code == 403   # event audio: operators only


def test_cookie_requests_that_change_things_must_be_same_origin(auth):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    c = client(app)
    login(c, "anna")
    body = {"event_id": 5}
    assert c.post(AUDIO_REQUEST, json=body).status_code == 403                 # no Origin/Referer
    assert c.post(AUDIO_REQUEST, json=body, headers={"origin": "https://evil.example"}).status_code == 403
    assert c.post(AUDIO_REQUEST, json=body, headers={"referer": "https://testserver/dataset"}).status_code == 200
    assert c.post("/login", data={"username": "anna", "password": PASSWORD}, headers={"origin": "https://evil.example"}).status_code == 403


def test_bearer_tokens_for_scripts(auth):
    store, app = auth
    store.add_user("bot", "operator", PASSWORD)
    store.add_user("vic", "viewer", PASSWORD)
    read_id, read_token = store.issue_token("bot", "dashboard")                 # default scope: read
    token_id, token = store.issue_token("bot", "ci", scopes="read,audio.request")
    _, viewer_token = store.issue_token("vic", "x", scopes="read,audio.request")
    c = client(app)
    h = {"authorization": f"Bearer {token}"}
    assert c.get("/api/v1/stations", headers=h).status_code == 200
    assert c.post(AUDIO_REQUEST, json={"event_id": 5}, headers=h).status_code == 200   # no origin check
    r = {"authorization": f"Bearer {read_token}"}
    assert c.get("/api/v1/stations", headers=r).status_code == 200
    assert c.post(AUDIO_REQUEST, json={"event_id": 5}, headers=r).status_code == 403   # outside the token's scopes
    assert c.get("/api/v1/stations/17/events/5/audio", headers=h).status_code == 403   # audio.listen not granted
    # a token never has more than its account
    assert c.post(AUDIO_REQUEST, json={"event_id": 5}, headers={"authorization": f"Bearer {viewer_token}"}).status_code == 403
    assert c.get("/api/v1/stations", headers={"authorization": "Bearer zso_forged"}).status_code == 401
    assert token not in Path(store.path).read_text()                   # only its hash is stored
    store.revoke_token(token_id)
    assert c.get("/api/v1/stations", headers=h).status_code == 401
    with pytest.raises(ValueError):
        store.issue_token("bot", scopes="read,everything")
    _, short = store.issue_token("bot", scopes="read", expires_days=1)
    data = json.loads(Path(store.path).read_text())
    for entry in data["tokens"].values():
        entry["expires"] = int(time.time()) - 1
    Path(store.path).write_text(json.dumps(data))
    assert c.get("/api/v1/stations", headers={"authorization": f"Bearer {short}"}).status_code == 401


def test_password_change_and_removal_end_sessions_at_once(auth):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    c = client(app)
    login(c, "anna")
    assert c.get("/api/v1/events").status_code == 200
    store.set_password("anna", PASSWORD + " new")
    assert c.get("/api/v1/events").status_code == 401
    login(c, "anna", PASSWORD + " new")
    store.set_roles("anna", "viewer")                                   # the roles come from the file, not the cookie
    assert c.post(AUDIO_REQUEST, json={"event_id": 5}, headers=ORIGIN).status_code == 403
    store.set_disabled("anna", True)                                    # a disabled account: no request, no login
    assert c.get("/api/v1/events").status_code == 401
    assert login(c, "anna", PASSWORD + " new").status_code == 401
    store.set_disabled("anna", False)
    login(c, "anna", PASSWORD + " new")
    store.add_user("boris", "operator", PASSWORD)
    store.remove_user("anna")
    assert c.get("/api/v1/events").status_code == 401


def test_forged_and_expired_cookies(auth):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    signer = oa.current_signer()
    user = store.user("anna")
    c = client(app)

    def with_cookie(value):
        return c.get("/api/v1/events", headers={"cookie": f"{oa.COOKIE_NAME}={value}"}).status_code

    assert with_cookie(oa.open_session(user, now=time.time() - oa.SESSION_TTL_S - 1)) == 401   # expired
    good = oa.open_session(user)
    version, body, mac = good.split(".")
    claims = json.loads(oa._unb64(body)); claims["u"] = "admin"
    assert with_cookie(f"{version}.{oa._b64(json.dumps(claims).encode())}.{mac}") == 401        # altered claims
    assert with_cookie(good[:-2] + "AA") == 401                                                  # altered MAC
    assert with_cookie("garbage") == 401
    assert with_cookie(signer.issue(user, "made-up session id")) == 401                          # signed, but no session
    assert with_cookie(good) == 200


def test_sessions_end_when_idle_and_on_demand(auth):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    c = client(app)
    login(c, "anna")
    assert c.get("/api/v1/events").status_code == 200
    with sqlite3.connect(oa.state_path()) as db:                       # 31 minutes without a request
        db.execute("UPDATE sessions SET last_seen = last_seen - ?", (oa.SESSION_IDLE_S + 60,))
    assert c.get("/api/v1/events").status_code == 401
    login(c, "anna")
    other = client(app)
    login(other, "anna")
    assert [s["user"] for s in oa.current_state().sessions("anna")] == ["anna", "anna"]
    assert oa.current_state().close_sessions("anna") == 2                # CLI logout-all
    assert c.get("/api/v1/events").status_code == 401 and other.get("/api/v1/events").status_code == 401


def test_login_is_throttled(auth, monkeypatch):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    store.add_user("boris", "operator", PASSWORD)
    c = client(app)
    for _ in range(oa.LOGIN_FAILURE_LIMIT):
        assert login(c, "anna", "not the password").status_code == 401
    assert login(c, "anna").status_code == 429                          # even the right password waits
    assert login(c, "boris").status_code == 303                         # a colleague behind the same address is not locked out
    for i in range(oa.LOGIN_ADDRESS_LIMIT):
        login(c, f"guess{i}", "not the password")
    assert login(c, "boris").status_code == 429                         # a guessing address is locked for everyone
    # behind the HTTPS proxy: the client address comes from X-Forwarded-For only when the proxy is declared trusted
    monkeypatch.setattr(oa, "throttle", oa.LoginThrottle())
    monkeypatch.setenv(oa.TRUSTED_PROXY_ENV, "1")
    for _ in range(oa.LOGIN_FAILURE_LIMIT):
        c.post("/login", data={"username": "anna", "password": "nope nope nope"}, headers={**ORIGIN, "x-forwarded-for": "198.51.100.7"})
    assert c.post("/login", data={"username": "anna", "password": PASSWORD}, headers={**ORIGIN, "x-forwarded-for": "198.51.100.7"}).status_code == 429
    assert c.post("/login", data={"username": "anna", "password": PASSWORD}, headers={**ORIGIN, "x-forwarded-for": "203.0.113.9"}).status_code == 303


def test_second_factor_for_engineers_and_admins(auth, monkeypatch):
    store, app = auth
    store.add_user("eve", "engineer", PASSWORD)
    c = client(app)
    r = login(c, "eve")
    assert r.status_code == 403 and "totp-enroll" in r.text             # no second factor enrolled: no login
    secret = oa.new_totp_secret()
    store.set_totp("eve", secret)
    assert login(c, "eve").status_code == 401                           # the code is missing
    step = int(time.time() // oa.TOTP_STEP_S)                           # one step for the whole test: no flake at a step edge
    near = {oa.totp_code(secret, step + d) for d in (-1, 0, 1, 2)}
    assert login(c, "eve", code=next(f"{n:06d}" for n in range(10) if f"{n:06d}" not in near)).status_code == 401
    assert login(c, "eve", code=oa.totp_code(secret, step)).status_code == 303
    assert c.get("/api/v1/events").status_code == 200
    assert login(client(app), "eve", code=oa.totp_code(secret, step)).status_code == 401   # a seen code does not log in twice
    assert login(client(app), "eve", code=oa.totp_code(secret, step + 1)).status_code == 303   # the next step (clock drift) does
    store.add_user("ops", "operator", PASSWORD)                          # operators and viewers: password only
    assert login(client(app), "ops").status_code == 303
    store.add_user("ada", "admin", PASSWORD)
    assert login(client(app), "ada").status_code == 403
    monkeypatch.setenv(oa.TOTP_ENV, "0")                                # an isolated bench may switch it off
    assert login(client(app), "ada").status_code == 303


def test_totp_matches_rfc_6238():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"                         # "12345678901234567890", RFC 6238 appendix B
    for t, code in ((59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")):
        assert oa.totp_code(secret, t // 30) == code
        assert oa.totp_counter(code, secret, t) == t // 30
    assert oa.totp_counter("287082", secret, 59 + 90) is None             # three steps later
    assert oa.totp_counter("28708", secret, 59) is None
    assert oa.totp_uri("eve", secret).startswith("otpauth://totp/Muhoed:eve?secret=" + secret)


def test_roles_and_permissions(auth):
    store, app = auth
    store.add_user("vic", "viewer", PASSWORD)
    store.add_user("ops", "operator", PASSWORD)
    store.add_user("svc", "service", PASSWORD)
    eng = enrolled(store, "eng", "engineer")
    adm = enrolled(store, "adm", "admin")
    both = enrolled(store, "duo", "operator,admin")
    sessions = {}
    for name, secret in (("vic", None), ("ops", None), ("svc", None), ("eng", eng), ("adm", adm), ("duo", both)):
        sessions[name] = client(app)
        assert login(sessions[name], name, code=code_now(secret) if secret else "").status_code == 303
    key = {"public_key": "00" * 32}
    net = {"server_host": "example.org"}
    checks = [                                                  # (method, path, body, who may)
        ("GET", "/api/v1/events", None, {"vic", "ops", "svc", "eng", "adm", "duo"}),
        ("GET", "/api/v1/stations/17/events/5/audio", None, {"ops", "eng", "duo"}),
        ("POST", AUDIO_REQUEST, {"event_id": 5}, {"ops", "eng", "duo"}),
        ("POST", "/dataset/delete", None, {"eng"}),
        ("POST", "/api/v1/stations/17/network-config", net, {"eng"}),
        ("POST", "/api/v1/stations/17/firmware-update", {"version": "9.9.9"}, {"eng"}),
        ("POST", "/api/v1/stations/17/command-key-rotation", key, {"adm", "duo"}),
        ("POST", "/single/analyze", None, {"ops", "eng", "duo"}),
    ]
    for method, path, body, allowed in checks:
        for name, c in sessions.items():
            status = c.request(method, path, json=body, headers=ORIGIN).status_code
            assert (status != 403) == (name in allowed), (method, path, name, status)
    assert store.user("duo")["roles"] == ["operator", "admin"] and store.user("duo")["role"] == "operator, admin"
    with pytest.raises(ValueError):
        store.add_user("bad", "operator,root", PASSWORD)


def test_every_changing_route_is_declared(auth):
    _, app = auth
    seen = 0
    for route in app.routes:
        inner = getattr(route, "original_router", None)
        for r in (inner.routes if inner is not None else [route]):
            if not isinstance(r, APIRoute):
                continue
            path = (route.include_context.prefix if inner is not None else "") + r.path
            concrete = path.replace("{station_id}", "1").replace("{event_id}", "1")
            for method in set(r.methods) - oa.SAFE_METHODS:
                need = oa.required_permission(method, concrete)
                assert need != oa.UNMAPPED, f"{method} {path} has no permission rule"
                seen += 1
    assert seen >= 10
    assert oa.required_permission("POST", "/api/v1/stations/1/something-new") == oa.UNMAPPED
    assert all(oa.UNMAPPED not in perms for perms in oa.ROLE_PERMISSIONS.values())


def test_legacy_account_file_keeps_working(auth):
    store, app = auth
    token = oa.TOKEN_PREFIX + "legacy-token-legacy-token-legacy-token-xx"
    Path(store.path).write_text(json.dumps({
        "users": {"anna": {"role": "operator", "password": oa.hash_password(PASSWORD), "created": 1},
                  "vic": {"role": "viewer", "password": oa.hash_password(PASSWORD), "created": 1}},
        "tokens": {"ab12cd34": {"user": "anna", "sha256": oa.hashlib.sha256(token.encode()).hexdigest(), "label": "ci", "created": 1}}}))
    c = client(app)
    assert login(c, "anna").status_code == 303                          # no second factor needed: nobody is locked out
    assert c.post(AUDIO_REQUEST, json={"event_id": 5}, headers=ORIGIN).status_code == 200
    assert c.post("/dataset/delete", headers=ORIGIN).status_code == 403 # engineer rights are given on purpose
    h = {"authorization": f"Bearer {token}"}                             # a token without scopes: its account's rights
    assert c.post(AUDIO_REQUEST, json={"event_id": 5}, headers=h).status_code == 200
    v = client(app)
    login(v, "vic")
    assert v.post(AUDIO_REQUEST, json={"event_id": 5}, headers=ORIGIN).status_code == 403
    store.set_roles("anna", "operator,engineer")                         # the first change writes the new form
    entry = json.loads(Path(store.path).read_text())["users"]["anna"]
    assert entry["roles"] == ["operator", "engineer"] and "role" not in entry


def test_scope_reaches_the_request(auth):
    store, _ = auth
    store.add_user("anna", "operator", PASSWORD)
    store.set_scope("anna", ["north"], [17, 18])
    seen = {}

    async def app(scope, receive, send):
        seen.update(scope["state"]["operator"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    c = TestClient(oa.OperatorAuthMiddleware(app), base_url="https://testserver")
    c.get("/api/v1/events", headers={"cookie": f"{oa.COOKIE_NAME}={oa.open_session(store.user('anna'))}"})
    assert seen["tenants"] == ["north"] and seen["stations"] == [17, 18] and seen["roles"] == ["operator"]
    assert "audio.listen" in seen["permissions"] and "dataset.edit" not in seen["permissions"]
    with pytest.raises(ValueError):
        store.set_scope("anna", ["North Side"], [])
    with pytest.raises(ValueError):
        store.set_scope("anna", [], [0])


def test_audit_log_is_chained(auth):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    store.add_user("vic", "viewer", PASSWORD)
    c = client(app)
    login(c, "anna", "wrong password!")
    login(c, "anna")
    c.post(AUDIO_REQUEST, json={"event_id": 5}, headers=ORIGIN)
    c.get("/api/v1/events")                                              # reads are not recorded
    v = client(app)
    login(v, "vic")
    v.post(AUDIO_REQUEST, json={"event_id": 5}, headers=ORIGIN)          # a refused change is
    c.post("/logout", headers=ORIGIN)
    state = oa.current_state()
    rows = [(r["actor"], r["action"], r["result"]) for r in state.audit_records()]
    assert rows == [("system", "superuser-created", "ok"),
                    ("anna", "login", "failed"), ("anna", "login", "ok"), ("anna", f"POST {AUDIO_REQUEST}", "200"),
                    ("vic", "login", "ok"), ("vic", f"POST {AUDIO_REQUEST}", "403"), ("anna", "logout", "ok")]
    assert state.audit_verify() == (True, 7)
    with sqlite3.connect(oa.state_path()) as db:                         # a record changed afterwards shows
        db.execute("UPDATE audit SET result='200' WHERE actor='vic' AND result='403'")
    assert state.audit_verify() == (False, 5)


def test_event_stream_needs_a_viewer(auth):
    store, app = auth
    store.add_user("vic", "viewer", PASSWORD)
    c = client(app)
    with pytest.raises(WebSocketDisconnect) as refused:
        with c.websocket_connect("/api/v1/stream"):
            pass
    assert refused.value.code == 4401
    session = login(c, "vic").cookies[oa.COOKIE_NAME]
    cookie = {"cookie": f"{oa.COOKIE_NAME}={session}"}                  # TestClient speaks ws://, a browser sends it on wss://
    with c.websocket_connect("/api/v1/stream", headers={**cookie, **ORIGIN}):
        pass
    with pytest.raises(WebSocketDisconnect) as foreign:
        with c.websocket_connect("/api/v1/stream", headers={**cookie, "origin": "https://evil.example"}):
            pass
    assert foreign.value.code == 4403


def test_station_bench_routes_keep_their_own_guard(auth, monkeypatch):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    c = client(app)
    hb = {"station_id": 17, "time_us": 1, "station": {"lat_e7": 0, "lon_e7": 0, "alt_dm": 0}}
    denied = c.post("/api/v1/stations/17/heartbeat", json=hb)
    assert denied.status_code == 403 and "mutual-TLS MQTT" in denied.json()["detail"]   # the station guard, not a login
    monkeypatch.setenv("ZS_STATION_HTTP_INSECURE_BENCH", "1")
    assert c.post("/api/v1/stations/17/heartbeat", json=hb).status_code == 200          # bench stations need no operator


@pytest.mark.parametrize("value", ["true", "yes", "on", "0", ""])
def test_bench_switch_is_exact(auth, monkeypatch, value):
    _, app = auth
    monkeypatch.setenv(oa.INSECURE_BENCH_ENV, value)
    assert client(app).get("/api/v1/events").status_code == 401


def test_policy_and_redirect_targets():
    assert oa.required_permission("GET", "/api/v1/health") is None
    assert oa.required_permission("POST", "/api/v1/stations/5/heartbeat") is None
    assert oa.required_permission("POST", "/api/v1/stations/5/events/9/audio") is None    # bench upload
    assert oa.required_permission("GET", "/api/v1/stations/5/events/9/audio") == oa.AUDIO_LISTEN
    assert oa.required_permission("GET", "/api/v1/stations/5/events/9/audio/pre.wav") == oa.AUDIO_LISTEN
    assert oa.required_permission("GET", "/dataset") == oa.READ
    assert oa.required_permission("POST", "/dataset/delete") == oa.DATASET_EDIT
    assert oa.required_permission("POST", "/api/v1/stations/5/model-update") == oa.STATION_FIRMWARE
    assert oa.required_permission("WEBSOCKET", "/api/v1/stream") == oa.READ
    assert oa.required_role("POST", "/dataset/delete") == "engineer"
    assert oa.required_role("GET", "/api/v1/stations/5/events/9/audio") == "operator"
    assert oa.required_role("POST", "/api/v1/stations/5/command-key-rotation") == "admin"
    for bad in ("//evil.example", "https://evil.example", "\\\\evil", "", None):
        assert oa.safe_next(bad) == "/"
    assert oa.safe_next("/dataset?x=1") == "/dataset?x=1"


def test_passwords_and_cli(tmp_path: Path, monkeypatch, capsys):
    stored = oa.hash_password(PASSWORD)
    assert stored.startswith("scrypt$") and PASSWORD not in stored
    assert oa.verify_password(PASSWORD, stored) and not oa.verify_password(PASSWORD + "x", stored)
    path = tmp_path / "ops.json"
    cli = ["--accounts", str(path)]
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    assert oa.main([*cli, "add-user", "anna", "--role", "operator", "--password-stdin"]) == 2
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert oa.main([*cli, "add-user", "anna", "--role", "operator", "--password-stdin"]) == 0
    assert oa.main([*cli, "issue-token", "anna", "--label", "ci", "--scopes", "read,audio.request"]) == 0
    assert oa.main([*cli, "set-roles", "anna", "--roles", "operator,engineer"]) == 0
    assert oa.main([*cli, "set-scope", "anna", "--tenants", "north", "--stations", "17,18"]) == 0
    assert oa.main([*cli, "set-scope", "anna", "--stations", "x"]) == 2
    assert oa.main([*cli, "totp-enroll", "anna"]) == 0
    capsys.readouterr()
    assert oa.main([*cli, "list"]) == 0
    listing = json.loads(capsys.readouterr().out)
    anna = listing["users"]["anna"]
    assert anna["roles"] == ["operator", "engineer"] and anna["role"] == "operator, engineer"
    assert anna["tenants"] == ["north"] and anna["stations"] == [17, 18] and anna["second_factor"]
    assert list(listing["tokens"].values())[0]["scopes"] == ["read", "audio.request"]
    assert "password" not in json.dumps(listing) and "totp\"" not in json.dumps(listing)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    state = path.with_name("operator_state.sqlite3")
    assert oct(state.stat().st_mode & 0o777) == "0o600"
    assert oa.main([*cli, "audit-verify"]) == 0
    capsys.readouterr()
    assert oa.main([*cli, "audit"]) == 0
    actions = [line.split()[5] for line in capsys.readouterr().out.splitlines()]   # date time actor (via, address) action
    assert actions == ["superuser-created", "add-user", "issue-token", "set-roles", "set-scope", "totp-enroll"]

"""Operator authentication (release audit item 1): fail-closed without accounts, login sessions, roles, API tokens,
same-origin checks, login throttling, the event stream, and the station bench routes left to their own guard."""
import io
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from station import operator_auth as oa

PASSWORD = "correct horse battery"
ORIGIN = {"origin": "https://testserver"}


@pytest.fixture
def auth(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(oa.INSECURE_BENCH_ENV, raising=False)
    monkeypatch.setenv(oa.ACCOUNTS_ENV, str(tmp_path / "operators.json"))
    monkeypatch.setenv(oa.SESSION_KEY_ENV, str(tmp_path / "session.key"))
    monkeypatch.setattr(oa, "throttle", oa.LoginThrottle())
    from app import app

    return oa.current_store(), app


def client(app) -> TestClient:
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def login(c: TestClient, name: str, password: str = PASSWORD, next_url: str = "/"):
    return c.post("/login", data={"username": name, "password": password, "next": next_url}, headers=ORIGIN)


def test_fail_closed_without_accounts(auth):
    _, app = auth
    c = client(app)
    r = c.get("/api/v1/events")
    assert r.status_code == 503 and "add-user" in r.json()["detail"]
    page = c.get("/", headers={"accept": "text/html"})
    assert page.status_code == 303 and page.headers["location"] == "/login?next=/"
    assert "add-user" in c.get("/login").text                            # the login page says how to create one
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
    assert c.post("/api/v1/stations/17/audio-request", json={"event_id": 5}, headers=ORIGIN).status_code == 200
    assert c.post("/logout", headers=ORIGIN).status_code == 303
    assert c.get("/api/v1/events").status_code == 401

    v = client(app)
    login(v, "vic")
    assert v.get("/api/v1/events").status_code == 200                   # viewers read
    assert v.post("/api/v1/stations/17/audio-request", json={"event_id": 5}, headers=ORIGIN).status_code == 403
    assert v.get("/api/v1/stations/17/events/5/audio").status_code == 403   # event audio: operators only


def test_cookie_requests_that_change_things_must_be_same_origin(auth):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    c = client(app)
    login(c, "anna")
    body = {"event_id": 5}
    assert c.post("/api/v1/stations/17/audio-request", json=body).status_code == 403                 # no Origin/Referer
    assert c.post("/api/v1/stations/17/audio-request", json=body, headers={"origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/v1/stations/17/audio-request", json=body, headers={"referer": "https://testserver/dataset"}).status_code == 200
    assert c.post("/login", data={"username": "anna", "password": PASSWORD}, headers={"origin": "https://evil.example"}).status_code == 403


def test_bearer_tokens_for_scripts(auth):
    store, app = auth
    store.add_user("bot", "operator", PASSWORD)
    token_id, token = store.issue_token("bot", "ci")
    c = client(app)
    h = {"authorization": f"Bearer {token}"}
    assert c.get("/api/v1/stations", headers=h).status_code == 200
    assert c.post("/api/v1/stations/17/audio-request", json={"event_id": 5}, headers=h).status_code == 200   # no origin check
    assert c.get("/api/v1/stations", headers={"authorization": "Bearer zso_forged"}).status_code == 401
    assert token not in Path(store.path).read_text()                   # only its hash is stored
    store.revoke_token(token_id)
    assert c.get("/api/v1/stations", headers=h).status_code == 401


def test_password_change_and_removal_end_sessions_at_once(auth):
    store, app = auth
    store.add_user("anna", "operator", PASSWORD)
    c = client(app)
    login(c, "anna")
    assert c.get("/api/v1/events").status_code == 200
    store.set_password("anna", PASSWORD + " new")
    assert c.get("/api/v1/events").status_code == 401
    login(c, "anna", PASSWORD + " new")
    store.set_role("anna", "viewer")                                    # the role comes from the file, not the cookie
    assert c.post("/api/v1/stations/17/audio-request", json={"event_id": 5}, headers=ORIGIN).status_code == 403
    store.add_user("boris", "operator", PASSWORD)                        # (without any account the server answers 503)
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

    assert with_cookie(signer.issue(user, now=time.time() - oa.SESSION_TTL_S - 1)) == 401      # expired
    good = signer.issue(user)
    version, body, mac = good.split(".")
    claims = json.loads(oa._unb64(body)); claims["u"] = "admin"
    assert with_cookie(f"{version}.{oa._b64(json.dumps(claims).encode())}.{mac}") == 401        # altered claims
    assert with_cookie(good[:-2] + "AA") == 401                                                  # altered MAC
    assert with_cookie("garbage") == 401
    assert with_cookie(good) == 200


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
    assert client(app).get("/api/v1/events").status_code == 503


def test_policy_and_redirect_targets():
    assert oa.required_role("GET", "/api/v1/health") is None
    assert oa.required_role("POST", "/api/v1/stations/5/heartbeat") is None
    assert oa.required_role("POST", "/api/v1/stations/5/events/9/audio") is None          # bench upload
    assert oa.required_role("GET", "/api/v1/stations/5/events/9/audio") == "operator"
    assert oa.required_role("GET", "/api/v1/stations/5/events/9/audio/pre.wav") == "operator"
    assert oa.required_role("GET", "/dataset") == "viewer"
    assert oa.required_role("POST", "/dataset/delete") == "operator"
    assert oa.required_role("WEBSOCKET", "/api/v1/stream") == "viewer"
    for bad in ("//evil.example", "https://evil.example", "\\\\evil", "", None):
        assert oa.safe_next(bad) == "/"
    assert oa.safe_next("/dataset?x=1") == "/dataset?x=1"


def test_passwords_and_cli(tmp_path: Path, monkeypatch, capsys):
    stored = oa.hash_password(PASSWORD)
    assert stored.startswith("scrypt$") and PASSWORD not in stored
    assert oa.verify_password(PASSWORD, stored) and not oa.verify_password(PASSWORD + "x", stored)
    path = tmp_path / "ops.json"
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    assert oa.main(["--accounts", str(path), "add-user", "anna", "--role", "operator", "--password-stdin"]) == 2
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert oa.main(["--accounts", str(path), "add-user", "anna", "--role", "operator", "--password-stdin"]) == 0
    assert oa.main(["--accounts", str(path), "issue-token", "anna", "--label", "ci"]) == 0
    capsys.readouterr()
    assert oa.main(["--accounts", str(path), "list"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["users"]["anna"]["role"] == "operator" and "password" not in json.dumps(listing)
    assert oct(path.stat().st_mode & 0o777) == "0o600"

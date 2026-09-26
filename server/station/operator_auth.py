"""Operator authentication and authorisation for the Muhoed web UI and REST/WebSocket API (release audit item 1).

Everything the application serves needs an operator, except the static assets, the login/logout pages, the health
probe and the station bench routes (``station_http_router``: they are machine ingress with their own fail-closed
guard, ``ZS_STATION_HTTP_INSECURE_BENCH``).

* Accounts live in a JSON file (``ZS_OPERATOR_ACCOUNTS``, default ``data/operators.json``, mode 0600): passwords as
  scrypt hashes, API tokens as SHA-256 of the token.  ``python -m station.operator_auth`` manages them.
* Roles: ``viewer`` reads (GET/HEAD, the event stream); ``operator`` also changes things (POST: audio requests,
  dataset, analysis) and is the only role that may fetch event audio, which can contain speech.
* Browsers log in and get a session cookie: HMAC-signed, HttpOnly, SameSite=Strict, Secure (``ZS_OPERATOR_COOKIE_SECURE=0``
  only for a plain-HTTP bench), 12 h.  The role is read from the account file on every request, so removing a user
  or changing a password takes effect at once (the cookie carries a password version).  Changing requests made with
  the cookie must come from the same origin (Origin, else Referer, equal to Host).
* Scripts use ``Authorization: Bearer zso_...`` tokens (no cookie, no origin check).
* Five failed logins for one name from one address, or twenty from one address, lock that login for 15 minutes
  (never a name on its own: anyone could lock an operator out).  Behind the HTTPS proxy the client address comes
  from ``X-Forwarded-For`` only with ``ZS_OPERATOR_TRUSTED_PROXY=1``; otherwise every login shares the proxy address.
* Fail-closed: without accounts every protected route is refused.  ``ZS_OPERATOR_AUTH_INSECURE_BENCH=1`` (exactly)
  switches the check off for an isolated bench, like the station HTTP bench switch.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

BASE = Path(__file__).resolve().parents[1]
INSECURE_BENCH_ENV = "ZS_OPERATOR_AUTH_INSECURE_BENCH"
ACCOUNTS_ENV = "ZS_OPERATOR_ACCOUNTS"
SESSION_KEY_ENV = "ZS_OPERATOR_SESSION_KEY_FILE"
COOKIE_SECURE_ENV = "ZS_OPERATOR_COOKIE_SECURE"
TRUSTED_PROXY_ENV = "ZS_OPERATOR_TRUSTED_PROXY"
COOKIE_NAME = "zs_operator"
SESSION_TTL_S = 12 * 3600
ROLE_RANK = {"viewer": 1, "operator": 2}
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2 ** 14, 8, 1, 32
MIN_PASSWORD_LEN = 12
USERNAME_RE = re.compile(r"[a-z][a-z0-9._-]{1,31}")
TOKEN_PREFIX = "zso_"
LOGIN_FAILURE_LIMIT = 5          # one name from one address
LOGIN_ADDRESS_LIMIT = 20         # any names from one address
LOGIN_LOCK_S = 15 * 60
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# operator-only reads: event audio (addendum B) may contain speech
OPERATOR_READ_RE = re.compile(r"^/api/v1/stations/\d+/events/\d+/audio(?:/|$)")
PUBLIC_ROUTES = {("GET", "/login"), ("HEAD", "/login"), ("POST", "/login"), ("POST", "/logout"),
                 ("GET", "/api/v1/health"), ("HEAD", "/api/v1/health")}


def auth_disabled() -> bool:
    return os.getenv(INSECURE_BENCH_ENV) == "1"


def accounts_path() -> Path:
    return Path(os.getenv(ACCOUNTS_ENV) or BASE / "data" / "operators.json")


def session_key_path() -> Path:
    return Path(os.getenv(SESSION_KEY_ENV) or BASE / "data" / "operator_session.key")


def cookie_secure() -> bool:
    return os.getenv(COOKIE_SECURE_ENV, "1") != "0"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ---- passwords -------------------------------------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        expected = _unb64(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))   # equal work for unknown users


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ---- accounts --------------------------------------------------------------------------------------------------------
class AccountStore:
    """The account file, re-read when it changes on disk (the CLI edits it while the server runs)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._stamp: tuple[int, int] | None = None
        self._data: dict[str, Any] = {"users": {}, "tokens": {}}

    def _load(self) -> dict[str, Any]:
        with self._lock:
            try:
                st = self.path.stat()
            except FileNotFoundError:
                self._stamp, self._data = None, {"users": {}, "tokens": {}}
                return self._data
            stamp = (st.st_mtime_ns, st.st_size)
            if stamp != self._stamp:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = {"users": dict(data.get("users", {})), "tokens": dict(data.get("tokens", {}))}
                self._stamp = stamp
            return self._data

    def _save(self, data: dict[str, Any]) -> None:
        with self._lock:
            _atomic_write(self.path, json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))
            self._stamp = None

    def _copy(self) -> dict[str, Any]:
        data = self._load()
        return {"users": {k: dict(v) for k, v in data["users"].items()}, "tokens": {k: dict(v) for k, v in data["tokens"].items()}}

    def has_users(self) -> bool:
        return bool(self._load()["users"])

    def user(self, name: str) -> dict[str, Any] | None:
        entry = self._load()["users"].get(name)
        return dict(entry, name=name) if entry else None

    def add_user(self, name: str, role: str, password: str) -> None:
        if not USERNAME_RE.fullmatch(name):
            raise ValueError("username: 2..32 of a-z 0-9 . _ -, starting with a letter")
        if role not in ROLE_RANK:
            raise ValueError(f"role must be one of {sorted(ROLE_RANK)}")
        _check_password(password)
        data = self._copy()
        if name in data["users"]:
            raise ValueError(f"user {name} exists")
        data["users"][name] = {"role": role, "password": hash_password(password), "created": int(time.time())}
        self._save(data)

    def set_password(self, name: str, password: str) -> None:
        _check_password(password)
        data = self._copy()
        if name not in data["users"]:
            raise ValueError(f"no user {name}")
        data["users"][name]["password"] = hash_password(password)
        self._save(data)

    def set_role(self, name: str, role: str) -> None:
        if role not in ROLE_RANK:
            raise ValueError(f"role must be one of {sorted(ROLE_RANK)}")
        data = self._copy()
        if name not in data["users"]:
            raise ValueError(f"no user {name}")
        data["users"][name]["role"] = role
        self._save(data)

    def remove_user(self, name: str) -> None:
        data = self._copy()
        if data["users"].pop(name, None) is None:
            raise ValueError(f"no user {name}")
        data["tokens"] = {k: v for k, v in data["tokens"].items() if v.get("user") != name}
        self._save(data)

    def issue_token(self, name: str, label: str = "") -> tuple[str, str]:
        data = self._copy()
        if name not in data["users"]:
            raise ValueError(f"no user {name}")
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token_id = secrets.token_hex(4)
        data["tokens"][token_id] = {"user": name, "sha256": hashlib.sha256(token.encode()).hexdigest(),
                                    "label": label, "created": int(time.time())}
        self._save(data)
        return token_id, token

    def revoke_token(self, token_id: str) -> None:
        data = self._copy()
        if data["tokens"].pop(token_id, None) is None:
            raise ValueError(f"no token {token_id}")
        self._save(data)

    def authenticate_password(self, name: str, password: str) -> dict[str, Any] | None:
        entry = self.user(name) if USERNAME_RE.fullmatch(name or "") else None
        ok = verify_password(password, entry["password"] if entry else _DUMMY_HASH)
        return entry if ok and entry else None

    def authenticate_token(self, token: str) -> dict[str, Any] | None:
        if not token.startswith(TOKEN_PREFIX):
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        for entry in self._load()["tokens"].values():
            if hmac.compare_digest(entry.get("sha256", ""), digest):
                return self.user(entry.get("user", ""))
        return None

    def listing(self) -> dict[str, Any]:
        data = self._load()
        return {"users": {k: {"role": v["role"], "created": v.get("created")} for k, v in data["users"].items()},
                "tokens": {k: {"user": v["user"], "label": v.get("label", ""), "created": v.get("created")}
                           for k, v in data["tokens"].items()}}


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must have at least {MIN_PASSWORD_LEN} characters")


def password_version(user: dict[str, Any]) -> str:
    return hashlib.sha256(user["password"].encode()).hexdigest()[:16]


# ---- sessions --------------------------------------------------------------------------------------------------------
def load_session_key(path: Path) -> bytes:
    try:
        key = path.read_bytes()
        if len(key) >= 32:
            return key
    except FileNotFoundError:
        pass
    key = secrets.token_bytes(32)
    _atomic_write(path, key)
    return key


class SessionSigner:
    def __init__(self, key: bytes):
        self.key = key

    def _mac(self, body: str) -> str:
        return _b64(hmac.new(self.key, body.encode("ascii"), hashlib.sha256).digest())

    def issue(self, user: dict[str, Any], now: float | None = None) -> str:
        t = int(time.time() if now is None else now)
        body = _b64(json.dumps({"u": user["name"], "pv": password_version(user), "iat": t, "exp": t + SESSION_TTL_S},
                               separators=(",", ":")).encode())
        return f"v1.{body}.{self._mac(body)}"

    def verify(self, value: str, now: float | None = None) -> dict[str, Any] | None:
        try:
            version, body, mac = value.split(".")
            if version != "v1" or not hmac.compare_digest(mac, self._mac(body)):
                return None
            claims = json.loads(_unb64(body))
        except (ValueError, TypeError):
            return None
        return claims if int(claims.get("exp", 0)) > (time.time() if now is None else now) else None


class LoginThrottle:
    def __init__(self):
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    @staticmethod
    def keys(address: str, name: str) -> list[tuple[str, int]]:
        return [(f"pair:{address}:{name}", LOGIN_FAILURE_LIMIT), (f"addr:{address}", LOGIN_ADDRESS_LIMIT)]

    def locked(self, keys: list[tuple[str, int]], now: float) -> bool:
        with self._lock:
            return any(len([t for t in self._failures.get(k, []) if now - t < LOGIN_LOCK_S]) >= limit for k, limit in keys)

    def fail(self, keys: list[tuple[str, int]], now: float) -> None:
        with self._lock:
            for k, _ in keys:
                self._failures[k] = [t for t in self._failures.get(k, []) if now - t < LOGIN_LOCK_S] + [now]

    def reset(self, keys: list[tuple[str, int]]) -> None:
        with self._lock:
            self._failures.pop(keys[0][0], None)          # a success clears its own pair, not the address count


_stores: dict[Path, AccountStore] = {}
_signers: dict[Path, SessionSigner] = {}
throttle = LoginThrottle()


def current_store() -> AccountStore:
    path = accounts_path()
    if path not in _stores:
        _stores[path] = AccountStore(path)
    return _stores[path]


def current_signer() -> SessionSigner:
    path = session_key_path()
    if path not in _signers:
        _signers[path] = SessionSigner(load_session_key(path))
    return _signers[path]


# ---- policy ----------------------------------------------------------------------------------------------------------
_station_routes: list[tuple[re.Pattern, set[str]]] | None = None


def _station_bench_routes() -> list[tuple[re.Pattern, set[str]]]:
    """The station bench ingress routes (their own guard applies): taken from the router, not re-listed here."""
    global _station_routes
    if _station_routes is None:
        from fastapi.routing import APIRoute
        from starlette.routing import compile_path

        from station.router import router, station_http_router

        _station_routes = []
        for route in station_http_router.routes:
            if isinstance(route, APIRoute):
                regex, _, _ = compile_path(router.prefix + route.path)
                _station_routes.append((regex, set(route.methods)))
    return _station_routes


def required_role(method: str, path: str) -> str | None:
    """None: public (or guarded elsewhere); otherwise the least role that may make the request."""
    if path.startswith("/static/") or (method, path) in PUBLIC_ROUTES:
        return None
    for regex, methods in _station_bench_routes():
        if method in methods and regex.match(path):
            return None
    if OPERATOR_READ_RE.match(path):
        return "operator"
    return "viewer" if method in SAFE_METHODS or method == "WEBSOCKET" else "operator"


def _headers(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


def _same_origin(headers: dict[str, str]) -> bool:
    host = headers.get("host", "")
    source = headers.get("origin") or headers.get("referer")
    if not source or not host:
        return False
    return urlsplit(source).netloc == host


def authenticate(headers: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
    store = current_store()
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return store.authenticate_token(auth[7:].strip()), "token"
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("cookie", ""))
    except Exception:  # noqa: BLE001 - a malformed cookie header is simply no session
        return None, "cookie"
    morsel = cookie.get(COOKIE_NAME)
    if morsel is None:
        return None, "cookie"
    claims = current_signer().verify(morsel.value)
    if claims is None:
        return None, "cookie"
    user = store.user(str(claims.get("u", "")))
    if user is None or claims.get("pv") != password_version(user):
        return None, "cookie"
    return user, "cookie"


class OperatorAuthMiddleware:
    """Pure ASGI (it must see WebSocket handshakes too)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        websocket = scope["type"] == "websocket"
        method = "WEBSOCKET" if websocket else scope["method"].upper()
        need = required_role(method, scope["path"])
        if need is None or auth_disabled():
            return await self.app(scope, receive, send)
        headers = _headers(scope)
        if not current_store().has_users():
            return await self._deny(scope, send, headers, 503, "operator accounts are not configured: "
                                    "python -m station.operator_auth add-user <name> --role operator")
        user, via = authenticate(headers)
        if user is None:
            return await self._deny(scope, send, headers, 401, "operator login required")
        if ROLE_RANK.get(user["role"], 0) < ROLE_RANK[need]:
            return await self._deny(scope, send, headers, 403, f"role {user['role']} may not do this")
        if via == "cookie" and not websocket and method not in SAFE_METHODS and not _same_origin(headers):
            return await self._deny(scope, send, headers, 403, "cross-site request refused")
        if websocket and via == "cookie" and headers.get("origin") and not _same_origin(headers):
            return await self._deny(scope, send, headers, 403, "cross-site request refused")
        scope.setdefault("state", {})["operator"] = {"name": user["name"], "role": user["role"], "via": via}
        return await self.app(scope, receive, send)

    async def _deny(self, scope, send, headers, status: int, detail: str):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4000 + status})
            return
        wants_html = scope["method"].upper() in ("GET", "HEAD") and "text/html" in headers.get("accept", "")
        if wants_html and status in (401, 503):
            target = scope["path"] + ("?" + scope["query_string"].decode("latin-1") if scope.get("query_string") else "")
            await send({"type": "http.response.start", "status": 303,
                        "headers": [(b"location", f"/login?next={quote(target)}".encode("latin-1")), (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": b""})
            return
        body = json.dumps({"detail": detail}).encode()
        out = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
        if status == 401:
            out.append((b"www-authenticate", b'Bearer realm="muhoed"'))
        await send({"type": "http.response.start", "status": status, "headers": out})
        await send({"type": "http.response.body", "body": body})


# ---- login / logout --------------------------------------------------------------------------------------------------
def client_address(request: Request) -> str:
    if os.getenv(TRUSTED_PROXY_ENV) == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()          # the hop our proxy added
    return request.client.host if request.client else "?"


def safe_next(target: str | None) -> str:
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


def build_router(templates) -> APIRouter:
    auth_router = APIRouter()

    def page(request: Request, status: int = 200, error: str | None = None, next_url: str = "/"):
        return templates.TemplateResponse(request, "login.html", {"error": error, "next_url": next_url,
                                                                  "configured": current_store().has_users()},
                                          status_code=status, headers={"cache-control": "no-store"})

    @auth_router.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, next: str = "/"):
        return page(request, next_url=safe_next(next))

    @auth_router.post("/login", response_class=HTMLResponse)
    async def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/")):
        headers = {k.lower(): v for k, v in request.headers.items()}
        if headers.get("origin") and not _same_origin(headers):
            return page(request, 403, "Запрос с чужого сайта отклонён.")
        now = time.time()
        keys = LoginThrottle.keys(client_address(request), username.lower())
        if throttle.locked(keys, now):
            return page(request, 429, "Слишком много неудачных попыток. Повторите через 15 минут.", safe_next(next))
        user = current_store().authenticate_password(username.lower(), password)
        if user is None:
            throttle.fail(keys, now)
            return page(request, 401, "Неверное имя или пароль.", safe_next(next))
        throttle.reset(keys)
        response = RedirectResponse(safe_next(next), status_code=303)
        response.set_cookie(COOKIE_NAME, current_signer().issue(user, now), max_age=SESSION_TTL_S, httponly=True,
                            secure=cookie_secure(), samesite="strict", path="/")
        return response

    @auth_router.post("/logout")
    async def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE_NAME, path="/", secure=cookie_secure(), httponly=True, samesite="strict")
        return response

    return auth_router


# ---- CLI -------------------------------------------------------------------------------------------------------------
def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("password: ")
    if first != getpass.getpass("repeat: "):
        raise ValueError("passwords differ")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m station.operator_auth", description="Muhoed operator accounts")
    parser.add_argument("--accounts", help=f"account file (default ${ACCOUNTS_ENV} or data/operators.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add-user"); p.add_argument("name"); p.add_argument("--role", choices=sorted(ROLE_RANK), required=True)
    p.add_argument("--password-stdin", action="store_true")
    p = sub.add_parser("passwd"); p.add_argument("name"); p.add_argument("--password-stdin", action="store_true")
    p = sub.add_parser("set-role"); p.add_argument("name"); p.add_argument("--role", choices=sorted(ROLE_RANK), required=True)
    p = sub.add_parser("remove-user"); p.add_argument("name")
    p = sub.add_parser("issue-token"); p.add_argument("name"); p.add_argument("--label", default="")
    p = sub.add_parser("revoke-token"); p.add_argument("token_id")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    store = AccountStore(Path(args.accounts) if args.accounts else accounts_path())
    try:
        if args.cmd == "add-user":
            store.add_user(args.name, args.role, _read_password(args.password_stdin))
            print(f"user {args.name} ({args.role}) added")
        elif args.cmd == "passwd":
            store.set_password(args.name, _read_password(args.password_stdin))
            print(f"password of {args.name} changed; its sessions are closed")
        elif args.cmd == "set-role":
            store.set_role(args.name, args.role)
            print(f"{args.name} is now {args.role}")
        elif args.cmd == "remove-user":
            store.remove_user(args.name)
            print(f"user {args.name} and its tokens removed")
        elif args.cmd == "issue-token":
            token_id, token = store.issue_token(args.name, args.label)
            print(f"token {token_id} for {args.name} (shown once, store it as a secret):\n{token}")
        elif args.cmd == "revoke-token":
            store.revoke_token(args.token_id)
            print(f"token {args.token_id} revoked")
        else:
            print(json.dumps(store.listing(), indent=2, ensure_ascii=False))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

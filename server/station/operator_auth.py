"""Operator authentication and authorisation for the Muhoed web UI and REST/WebSocket API (release audit item 1).

Everything the application serves needs an operator, except the static assets, the login/logout pages, the health
probe and the station bench routes (``station_http_router``: they are machine ingress with their own fail-closed
guard, ``ZS_STATION_HTTP_INSECURE_BENCH``).

* Accounts live in a JSON file (``ZS_OPERATOR_ACCOUNTS``, default ``data/operators.json``, mode 0600): passwords as
  scrypt hashes, API tokens as SHA-256 of the token, TOTP secrets of the second factor.  ``python -m
  station.operator_auth`` manages them.  Sessions and the audit log live next to it in an SQLite file
  (``ZS_OPERATOR_STATE``, default ``data/operator_state.sqlite3``).
* Roles (an account may have several; docs/SERVER_ACCESS_CONTROL_2026-10-02.md): ``viewer`` reads (maps, tracks,
  alerts, stations, the event stream); ``operator`` also listens to event audio (it can contain speech), requests
  audio and runs analyses; ``engineer`` also edits the dataset and commands stations (network configuration, firmware
  and model updates); ``admin`` manages accounts, rotates the command signing key and reads the audit log, but does not
  command stations; ``service`` is for integrations (read only).  A role is a set of permissions (ROLE_PERMISSIONS);
  every request needs one permission (required_permission), and a route nobody declared is refused.  Accounts of the
  file before roles keep their name: ``"role": "operator"`` becomes the operator role (it still logs in without a
  second factor; editing the dataset and commanding stations now need the engineer role, given with ``set-roles``).
* Browsers log in and get a session cookie: random, HMAC-signed, HttpOnly, SameSite=Strict, Secure
  (``ZS_OPERATOR_COOKIE_SECURE=0`` only for a plain-HTTP bench).  The session is kept on the server: logout ends it,
  30 minutes without a request end it, and so do 12 hours; a password change, a removed or disabled account end all of
  the account's sessions at once (the cookie carries a password version).  Roles are read from the account file on
  every request.  Changing requests made with the cookie must come from the same origin (Origin, else Referer, equal
  to Host).
* Engineers and admins log in with a second factor: a TOTP code (RFC 6238, 30 s, 6 digits, an authenticator app,
  no network needed).  ``totp-enroll`` gives the secret; without it such an account cannot log in
  (``ZS_OPERATOR_TOTP=0`` switches the requirement off for a bench).
* Scripts use ``Authorization: Bearer zso_...`` tokens (no cookie, no origin check).  A token has scopes: the
  permissions it may use (default ``read``), never more than its account's.
* Five failed logins for one name from one address, or twenty from one address, lock that login for 15 minutes
  (never a name on its own: anyone could lock an operator out).  Behind the HTTPS proxy the client address comes
  from ``X-Forwarded-For`` only with ``ZS_OPERATOR_TRUSTED_PROXY=1``; otherwise every login shares the proxy address.
* The audit log records logins, failed logins, logouts, every changing request (who, from where, what, the answer)
  and every account change of the CLI; each record carries the hash of the one before, so a changed or removed record
  shows (``audit-verify``).
* An account may be limited to tenants and stations (``set-scope``, or ``/api/v1/access`` by the admin and engineers);
  every request carries them (``request.state.operator``) and the data APIs show it only those
  (station/access_scope.py).
* One superuser, ``skif_root`` (role ``superuser``, which no other account may have): every permission, every station
  and tenant, and ``audit.control``, the switch of the audit log of actions.  The server creates it when it is missing,
  with the default password ``12345678`` that must be changed at the first login; the same login then enrols its
  second factor (the secret is shown once and confirmed with a code).  It cannot be removed, disabled, limited or
  given other roles, and its API tokens never carry ``audit.control``.  With the audit log of actions switched off,
  logins, logouts and changing requests are not recorded; the switching itself, failed and locked logins and refused
  requests always are, so the log shows when and by whom it was off.
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
import sqlite3
import struct
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
STATE_ENV = "ZS_OPERATOR_STATE"
COOKIE_SECURE_ENV = "ZS_OPERATOR_COOKIE_SECURE"
TRUSTED_PROXY_ENV = "ZS_OPERATOR_TRUSTED_PROXY"
TOTP_ENV = "ZS_OPERATOR_TOTP"
COOKIE_NAME = "zs_operator"
SESSION_TTL_S = 12 * 3600
SESSION_IDLE_S = 30 * 60
SESSION_TOUCH_S = 60             # last activity is written at most once a minute
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LEN = 2 ** 14, 8, 1, 32
MIN_PASSWORD_LEN = 12
USERNAME_RE = re.compile(r"[a-z][a-z0-9._-]{1,31}")
TENANT_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
TOKEN_PREFIX = "zso_"
LOGIN_FAILURE_LIMIT = 5          # one name from one address
LOGIN_ADDRESS_LIMIT = 20         # any names from one address
LOGIN_LOCK_S = 15 * 60
TOTP_STEP_S, TOTP_DIGITS = 30, 6
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SUPERUSER_NAME = "skif_root"
SUPERUSER_ROLE = "superuser"
SUPERUSER_DEFAULT_PASSWORD = "12345678"   # only until the first login, which must change it
PENDING_TTL_S = 10 * 60                   # a login waiting for a new password or a second-factor enrolment

# ---- roles and permissions -------------------------------------------------------------------------------------------
READ = "read"                         # pages, data APIs, the event stream
AUDIO_LISTEN = "audio.listen"         # event audio: may contain speech
AUDIO_REQUEST = "audio.request"
ANALYSIS_RUN = "analysis.run"         # one-file analysis, localization
DATASET_EDIT = "dataset.edit"         # add, train, delete
STATION_COMMAND = "station.command"   # network configuration (and later reboot, parameters)
STATION_FIRMWARE = "station.firmware" # firmware and model updates
KEYS_ROTATE = "keys.rotate"           # command signing key rotation
USERS_MANAGE = "users.manage"
SCOPES_MANAGE = "scopes.manage"       # which tenants and stations an operator or viewer sees
AUDIT_READ = "audit.read"
AUDIT_CONTROL = "audit.control"       # switch the audit log of actions off and on: the superuser only, never a token
PERMISSIONS = (READ, AUDIO_LISTEN, AUDIO_REQUEST, ANALYSIS_RUN, DATASET_EDIT, STATION_COMMAND, STATION_FIRMWARE,
               KEYS_ROTATE, USERS_MANAGE, SCOPES_MANAGE, AUDIT_READ)   # the scopes a token may have
ROLE_PERMISSIONS = {
    "viewer": {READ},
    "operator": {READ, AUDIO_LISTEN, AUDIO_REQUEST, ANALYSIS_RUN},
    "engineer": {READ, AUDIO_LISTEN, AUDIO_REQUEST, ANALYSIS_RUN, DATASET_EDIT, STATION_COMMAND, STATION_FIRMWARE,
                 SCOPES_MANAGE},
    "admin": {READ, USERS_MANAGE, SCOPES_MANAGE, KEYS_ROTATE, AUDIT_READ},
    "service": {READ},
    SUPERUSER_ROLE: set(PERMISSIONS) | {AUDIT_CONTROL},
}
ROLES = tuple(ROLE_PERMISSIONS)
GRANTABLE_ROLES = tuple(r for r in ROLES if r != SUPERUSER_ROLE)
SECOND_FACTOR_ROLES = {"engineer", "admin", SUPERUSER_ROLE}
LEGACY_ROLES = {"viewer": ["viewer"], "operator": ["operator"]}   # the file before roles: nobody is locked out, and
# engineer rights (dataset, station commands) are given on purpose, with the second factor
UNMAPPED = "unmapped"                 # a changing route nobody declared: refused to everyone

# operator-only reads: event audio (addendum B) may contain speech
OPERATOR_READ_RE = re.compile(r"^/api/v1/stations/\d+/events/\d+/audio(?:/|$)")
# (methods, path, permission): the first match decides; a safe method not listed needs READ
PERMISSION_RULES: list[tuple[set[str], re.Pattern, str]] = [
    ({"GET", "HEAD"}, OPERATOR_READ_RE, AUDIO_LISTEN),
    ({"POST"}, re.compile(r"^/api/v1/stations/\d+/audio-request$"), AUDIO_REQUEST),
    ({"POST"}, re.compile(r"^/api/v1/stations/\d+/command-key-rotation$"), KEYS_ROTATE),
    ({"POST"}, re.compile(r"^/api/v1/stations/\d+/network-config$"), STATION_COMMAND),
    ({"POST"}, re.compile(r"^/api/v1/stations/\d+/(?:firmware|model)-update$"), STATION_FIRMWARE),
    ({"POST"}, re.compile(r"^/api/v1/firmware/rollouts(?:/[^/]+(?:/(?:pause|resume|cancel|revert)|/stations/\d+/skip))?$"), STATION_FIRMWARE),
    ({"POST"}, re.compile(r"^/(?:dataset/(?:add|train|delete)|api/dataset/train)$"), DATASET_EDIT),
    ({"POST"}, re.compile(r"^/(?:single/analyze|api/analyze-single|localization/analyze|api/localize)$"), ANALYSIS_RUN),
    ({"GET", "HEAD", "PUT"}, re.compile(r"^/api/v1/access/(?:accounts(?:/[^/]+/scope)?|catalog)$"), SCOPES_MANAGE),
    ({"GET", "HEAD"}, re.compile(r"^/api/v1/admin/audit-logging$"), AUDIT_READ),
    ({"PUT"}, re.compile(r"^/api/v1/admin/audit-logging$"), AUDIT_CONTROL),
    ({"GET", "HEAD"}, re.compile(r"^/api/v1/admin/audit$"), AUDIT_READ),
    ({"GET", "HEAD", "POST"}, re.compile(r"^/api/v1/admin/accounts$"), USERS_MANAGE),
    ({"PUT", "DELETE"}, re.compile(r"^/api/v1/admin/accounts/[^/]+$"), USERS_MANAGE),
    ({"POST"}, re.compile(r"^/api/v1/admin/accounts/[^/]+/(?:password|totp-reset|logout|tokens)$"), USERS_MANAGE),
    ({"DELETE"}, re.compile(r"^/api/v1/admin/tokens/[^/]+$"), USERS_MANAGE),
]
# the login steps before a session exists: a new password, the second-factor enrolment (each needs the signed step
# token the password step gave)
PUBLIC_ROUTES = {("GET", "/login"), ("HEAD", "/login"), ("POST", "/login"), ("POST", "/logout"),
                 ("POST", "/login/password"), ("POST", "/login/totp"),
                 ("GET", "/api/v1/health"), ("HEAD", "/api/v1/health")}


def auth_disabled() -> bool:
    return os.getenv(INSECURE_BENCH_ENV) == "1"


def accounts_path() -> Path:
    return Path(os.getenv(ACCOUNTS_ENV) or BASE / "data" / "operators.json")


def session_key_path() -> Path:
    return Path(os.getenv(SESSION_KEY_ENV) or BASE / "data" / "operator_session.key")


def state_path() -> Path:
    return Path(os.getenv(STATE_ENV) or accounts_path().with_name("operator_state.sqlite3"))


def cookie_secure() -> bool:
    return os.getenv(COOKIE_SECURE_ENV, "1") != "0"


def second_factor_required() -> bool:
    return os.getenv(TOTP_ENV, "1") != "0"


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


# ---- second factor (RFC 6238) ----------------------------------------------------------------------------------------
def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** TOTP_DIGITS).zfill(TOTP_DIGITS)


def totp_counter(code: str, secret: str, now: float) -> int | None:
    """The time step the code belongs to (the current one, or one step either side: clock drift), else None."""
    code = (code or "").strip().replace(" ", "")
    if not re.fullmatch(r"\d{%d}" % TOTP_DIGITS, code):
        return None
    step = int(now // TOTP_STEP_S)
    for counter in (step, step - 1, step + 1):
        if hmac.compare_digest(totp_code(secret, counter), code):
            return counter
    return None


def totp_uri(name: str, secret: str) -> str:
    return f"otpauth://totp/Muhoed:{quote(name)}?secret={secret}&issuer=Muhoed&digits={TOTP_DIGITS}&period={TOTP_STEP_S}"


# ---- accounts --------------------------------------------------------------------------------------------------------
def roles_of(entry: dict[str, Any]) -> list[str]:
    """The roles of an account (an entry of the file before roles has one ``role``)."""
    roles = entry.get("roles")
    if roles is None:
        roles = LEGACY_ROLES.get(entry.get("role", ""), [])
    return [r for r in ROLES if r in roles]


def permissions_of(roles: list[str]) -> set[str]:
    out: set[str] = set()
    for role in roles:
        out |= ROLE_PERMISSIONS.get(role, set())
    return out


def _parse_roles(roles: str | list[str]) -> list[str]:
    names = [r.strip() for r in (roles.split(",") if isinstance(roles, str) else roles) if r.strip()]
    bad = [r for r in names if r not in ROLE_PERMISSIONS]
    if not names or bad:
        raise ValueError(f"roles must be some of {list(ROLES)}")
    return [r for r in ROLES if r in names]


def _parse_scopes(scopes: str | list[str]) -> list[str]:
    names = [s.strip() for s in (scopes.split(",") if isinstance(scopes, str) else scopes) if s.strip()]
    bad = [s for s in names if s not in PERMISSIONS]
    if not names or bad:
        raise ValueError(f"token scopes must be some of {list(PERMISSIONS)}")
    return [s for s in PERMISSIONS if s in names]


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

    def _entry(self, data: dict[str, Any], name: str) -> dict[str, Any]:
        if name not in data["users"]:
            raise ValueError(f"no user {name}")
        entry = data["users"][name]
        if "roles" not in entry:                      # first change of an account of the file before roles
            entry["roles"] = roles_of(entry)
            entry.pop("role", None)
        return entry

    def has_users(self) -> bool:
        return bool(self._load()["users"])

    def user(self, name: str) -> dict[str, Any] | None:
        entry = self._load()["users"].get(name)
        if not entry:
            return None
        roles = roles_of(entry)
        return dict(entry, name=name, roles=roles, role=", ".join(roles), permissions=permissions_of(roles))

    # the superuser: one account, created by the server, never another role, never removed, disabled or limited
    def ensure_superuser(self) -> str | None:
        """Create skif_root when it is missing (default password, to be changed at the first login, which also enrols
        its second factor), and keep the superuser role on it alone.  "created" or "repaired" when the file changed."""
        data = self._copy()
        changed = None
        for name, entry in data["users"].items():
            if name != SUPERUSER_NAME and SUPERUSER_ROLE in (entry.get("roles") or []):
                entry["roles"] = [r for r in entry["roles"] if r != SUPERUSER_ROLE]
                changed = "repaired"
        entry = data["users"].get(SUPERUSER_NAME)
        if entry is None:
            data["users"][SUPERUSER_NAME] = {"roles": [SUPERUSER_ROLE], "password": hash_password(SUPERUSER_DEFAULT_PASSWORD),
                                             "created": int(time.time()), "tenants": [], "stations": [],
                                             "must_change": True, "totp_at_login": True}
            changed = "created"
        else:
            fixed = {"roles": [SUPERUSER_ROLE], "tenants": [], "stations": []}
            if any(entry.get(k) != v for k, v in fixed.items()) or entry.get("disabled") or "role" in entry:
                entry.update(fixed)
                entry.pop("disabled", None)
                entry.pop("role", None)
                changed = "repaired"
        if changed:
            self._save(data)
        return changed

    @staticmethod
    def _not_superuser(name: str, what: str) -> None:
        if name == SUPERUSER_NAME:
            raise ValueError(f"{SUPERUSER_NAME} is the superuser: it cannot be {what}")

    def add_user(self, name: str, roles: str | list[str], password: str) -> None:
        if not USERNAME_RE.fullmatch(name):
            raise ValueError("username: 2..32 of a-z 0-9 . _ -, starting with a letter")
        roles = _parse_roles(roles)
        if name == SUPERUSER_NAME or SUPERUSER_ROLE in roles:
            raise ValueError(f"the superuser is {SUPERUSER_NAME} alone, created by the server")
        _check_password(password)
        data = self._copy()
        if name in data["users"]:
            raise ValueError(f"user {name} exists")
        data["users"][name] = {"roles": roles, "password": hash_password(password), "created": int(time.time()),
                               "tenants": [], "stations": []}
        self._save(data)

    def set_password(self, name: str, password: str) -> None:
        """A new password (at least MIN_PASSWORD_LEN characters); a required change is then done."""
        _check_password(password)
        data = self._copy()
        entry = self._entry(data, name)
        entry["password"] = hash_password(password)
        entry.pop("must_change", None)
        self._save(data)

    def set_roles(self, name: str, roles: str | list[str]) -> None:
        roles = _parse_roles(roles)
        self._not_superuser(name, "given other roles")
        if SUPERUSER_ROLE in roles:
            raise ValueError(f"the superuser is {SUPERUSER_NAME} alone")
        data = self._copy()
        self._entry(data, name)["roles"] = roles
        self._save(data)

    set_role = set_roles

    def set_disabled(self, name: str, disabled: bool) -> None:
        self._not_superuser(name, "disabled")
        data = self._copy()
        entry = self._entry(data, name)
        if disabled:
            entry["disabled"] = True
        else:
            entry.pop("disabled", None)
        self._save(data)

    def set_scope(self, name: str, tenants: list[str], stations: list[int]) -> None:
        """The tenants and stations the account sees (empty: all)."""
        for t in tenants:
            if not TENANT_RE.fullmatch(t):
                raise ValueError(f"bad tenant {t!r}")
        if any(type(s) is not int or not 0 < s < 1 << 32 for s in stations):
            raise ValueError("stations are positive 32-bit ids")
        self._not_superuser(name, "limited to tenants or stations")
        data = self._copy()
        entry = self._entry(data, name)
        entry["tenants"] = sorted(set(tenants))
        entry["stations"] = sorted(set(stations))
        self._save(data)

    def set_totp(self, name: str, secret: str | None, enrol_at_login: bool = False) -> None:
        """The second-factor secret (None: removed; the superuser, or with ``enrol_at_login`` any account, then enrols a
        new one at its next login)."""
        data = self._copy()
        entry = self._entry(data, name)
        if secret:
            entry["totp"] = secret
            entry.pop("totp_at_login", None)
        else:
            entry.pop("totp", None)
            if name == SUPERUSER_NAME or enrol_at_login:
                entry["totp_at_login"] = True
        self._save(data)

    def require_first_login(self, name: str) -> None:
        """The next login changes the (temporary) password; an account that needs the second factor and has none enrols
        it there too (accounts made or reset by an administrator)."""
        data = self._copy()
        entry = self._entry(data, name)
        entry["must_change"] = True
        if SECOND_FACTOR_ROLES & set(roles_of(entry)) and not entry.get("totp"):
            entry["totp_at_login"] = True
        self._save(data)

    def remove_user(self, name: str) -> None:
        self._not_superuser(name, "removed")
        data = self._copy()
        if data["users"].pop(name, None) is None:
            raise ValueError(f"no user {name}")
        data["tokens"] = {k: v for k, v in data["tokens"].items() if v.get("user") != name}
        self._save(data)

    def issue_token(self, name: str, label: str = "", scopes: str | list[str] = READ,
                    expires_days: int | None = None) -> tuple[str, str]:
        scopes = _parse_scopes(scopes)
        data = self._copy()
        self._entry(data, name)
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token_id = secrets.token_hex(4)
        data["tokens"][token_id] = {"user": name, "sha256": hashlib.sha256(token.encode()).hexdigest(),
                                    "label": label, "created": int(time.time()), "scopes": scopes}
        if expires_days:
            data["tokens"][token_id]["expires"] = int(time.time()) + int(expires_days) * 86400
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
        return entry if ok and entry and not entry.get("disabled") else None

    def authenticate_token(self, token: str) -> dict[str, Any] | None:
        """The token's account with only the permissions of the token's scopes (a token of the file before scopes:
        all of its account's)."""
        if not token.startswith(TOKEN_PREFIX):
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        for token_id, entry in self._load()["tokens"].items():
            if hmac.compare_digest(entry.get("sha256", ""), digest):
                if entry.get("expires") and entry["expires"] < time.time():
                    return None
                user = self.user(entry.get("user", ""))
                if user is None or user.get("disabled"):
                    return None
                if "scopes" in entry:
                    user["permissions"] = user["permissions"] & set(entry["scopes"])
                user["permissions"] = user["permissions"] - {AUDIT_CONTROL}   # the audit switch: interactive only
                user["token_id"] = token_id
                return user
        return None

    def listing(self) -> dict[str, Any]:
        data = self._load()
        return {"users": {k: {"roles": roles_of(v), "role": ", ".join(roles_of(v)), "created": v.get("created"),
                              "disabled": bool(v.get("disabled")), "tenants": v.get("tenants", []), "stations": v.get("stations", []),
                              "second_factor": bool(v.get("totp")), "must_change": bool(v.get("must_change")),
                              "superuser": k == SUPERUSER_NAME} for k, v in data["users"].items()},
                "tokens": {k: {"user": v["user"], "label": v.get("label", ""), "created": v.get("created"),
                               "scopes": v.get("scopes"), "expires": v.get("expires")} for k, v in data["tokens"].items()}}


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must have at least {MIN_PASSWORD_LEN} characters")


def password_version(user: dict[str, Any]) -> str:
    return hashlib.sha256(user["password"].encode()).hexdigest()[:16]


# ---- server state: sessions, used TOTP steps, audit log --------------------------------------------------------------
class StateStore:
    """Sessions (so logout and the idle timeout end them on the server), the last TOTP step of each account (a code
    works once) and the audit log, in one SQLite file next to the accounts."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(sid TEXT PRIMARY KEY, user TEXT NOT NULL, pv TEXT NOT NULL,
                    created REAL NOT NULL, last_seen REAL NOT NULL, address TEXT NOT NULL, agent TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user);
                CREATE TABLE IF NOT EXISTS totp_used(user TEXT PRIMARY KEY, counter INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, actor TEXT NOT NULL,
                    via TEXT NOT NULL, address TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL,
                    result TEXT NOT NULL, detail TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pending_totp(user TEXT PRIMARY KEY, secret TEXT NOT NULL, created REAL NOT NULL);
            """)
        if new:
            os.chmod(self.path, 0o600)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    # sessions
    def open_session(self, user: dict[str, Any], address: str, agent: str, now: float) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM sessions WHERE created < ? OR last_seen < ?", (now - SESSION_TTL_S, now - SESSION_IDLE_S))
            c.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", (hashlib.sha256(sid.encode()).hexdigest(), user["name"],
                      password_version(user), now, now, address[:64], agent[:200]))
        return sid

    def session(self, sid: str, now: float) -> sqlite3.Row | None:
        key = hashlib.sha256(sid.encode()).hexdigest()
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM sessions WHERE sid=?", (key,)).fetchone()
            if row is None:
                return None
            if now - row["created"] > SESSION_TTL_S or now - row["last_seen"] > SESSION_IDLE_S:
                c.execute("DELETE FROM sessions WHERE sid=?", (key,))
                return None
            if now - row["last_seen"] > SESSION_TOUCH_S:
                c.execute("UPDATE sessions SET last_seen=? WHERE sid=?", (now, key))
            return row

    def close_session(self, sid: str) -> str | None:
        key = hashlib.sha256(sid.encode()).hexdigest()
        with self._lock, self._conn() as c:
            row = c.execute("SELECT user FROM sessions WHERE sid=?", (key,)).fetchone()
            c.execute("DELETE FROM sessions WHERE sid=?", (key,))
        return row["user"] if row else None

    def close_sessions(self, user: str) -> int:
        with self._lock, self._conn() as c:
            return c.execute("DELETE FROM sessions WHERE user=?", (user,)).rowcount

    def sessions(self, user: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT user, created, last_seen, address, agent FROM sessions" + (" WHERE user=?" if user else "")
                             + " ORDER BY created", (user,) if user else ()).fetchall()
        return [dict(r) for r in rows]

    # second factor
    def use_totp_step(self, user: str, counter: int) -> bool:
        """False when the code's step (or a later one) was used already: a seen code does not log in twice."""
        with self._lock, self._conn() as c:
            row = c.execute("SELECT counter FROM totp_used WHERE user=?", (user,)).fetchone()
            if row is not None and counter <= row["counter"]:
                return False
            c.execute("INSERT OR REPLACE INTO totp_used VALUES(?,?)", (user, counter))
            return True

    def put_pending_totp(self, user: str, secret: str, now: float) -> None:
        """The secret shown to an account enrolling its second factor at login, until a code confirms it."""
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO pending_totp VALUES(?,?,?)", (user, secret, now))

    def pending_totp(self, user: str, now: float) -> str | None:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT secret, created FROM pending_totp WHERE user=?", (user,)).fetchone()
        return row["secret"] if row and now - row["created"] <= PENDING_TTL_S else None

    def drop_pending_totp(self, user: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM pending_totp WHERE user=?", (user,))

    # the switch of the audit log of actions (the superuser's audit.control)
    def audit_logging(self) -> dict[str, Any]:
        with self._lock, self._conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key='audit_logging'").fetchone()
        state = json.loads(row["value"]) if row else {}
        return {"enabled": state.get("enabled", True), "changed_at": state.get("at"), "changed_by": state.get("by")}

    def set_audit_logging(self, enabled: bool, actor: str, via: str, address: str, now: float | None = None) -> None:
        """Switch the audit log of actions; the switching itself is always recorded."""
        at = time.time() if now is None else now
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO settings VALUES('audit_logging', ?)",
                      (json.dumps({"enabled": bool(enabled), "at": round(at, 3), "by": actor}),))
        self.audit(actor, via, address, "audit-logging", "on" if enabled else "off", force=True, now=at)

    # audit
    def audit(self, actor: str, via: str, address: str, action: str, target: str = "", result: str = "ok",
              detail: dict[str, Any] | None = None, now: float | None = None, force: bool = False) -> None:
        """One record of the chained audit log.  With the log of actions switched off only ``force`` records are
        written: the switching, failed and locked logins, refused requests, the superuser's creation."""
        if not force and not self.audit_logging()["enabled"]:
            return
        at = time.time() if now is None else now
        body = json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)
        with self._lock, self._conn() as c:
            last = c.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
            prev = last["hash"] if last else ""
            record = [round(at, 6), actor, via, address[:64], action, target, result, body, prev]
            digest = hashlib.sha256(json.dumps(record, ensure_ascii=False).encode()).hexdigest()
            c.execute("INSERT INTO audit(at,actor,via,address,action,target,result,detail,prev,hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (*record, digest))

    def audit_records(self, limit: int = 100, actor: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM audit" + (" WHERE actor=?" if actor else "") + " ORDER BY id DESC LIMIT ?",
                             ((actor, limit) if actor else (limit,))).fetchall()
        return [dict(r) for r in reversed(rows)]

    def audit_verify(self) -> tuple[bool, int]:
        """(intact, records): every record's hash over its fields and the hash of the one before."""
        prev = ""
        n = 0
        with self._lock, self._conn() as c:
            for r in c.execute("SELECT * FROM audit ORDER BY id"):
                record = [r["at"], r["actor"], r["via"], r["address"], r["action"], r["target"], r["result"], r["detail"], r["prev"]]
                if r["prev"] != prev or hashlib.sha256(json.dumps(record, ensure_ascii=False).encode()).hexdigest() != r["hash"]:
                    return False, n
                prev = r["hash"]
                n += 1
        return True, n


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
    """The cookie: the session id and the account's password version, signed (a forged or altered cookie is refused
    before the session table is asked)."""

    def __init__(self, key: bytes):
        self.key = key

    def _mac(self, body: str) -> str:
        return _b64(hmac.new(self.key, body.encode("ascii"), hashlib.sha256).digest())

    def issue(self, user: dict[str, Any], sid: str, now: float | None = None) -> str:
        t = int(time.time() if now is None else now)
        body = _b64(json.dumps({"u": user["name"], "s": sid, "pv": password_version(user), "iat": t, "exp": t + SESSION_TTL_S},
                               separators=(",", ":")).encode())
        return f"v2.{body}.{self._mac(body)}"

    def verify(self, value: str, now: float | None = None) -> dict[str, Any] | None:
        try:
            version, body, mac = value.split(".")
            if version != "v2" or not hmac.compare_digest(mac, self._mac(body)):
                return None
            claims = json.loads(_unb64(body))
        except (ValueError, TypeError):
            return None
        return claims if int(claims.get("exp", 0)) > (time.time() if now is None else now) else None

    def issue_step(self, user: dict[str, Any], step: str, now: float | None = None) -> str:
        """A login step that follows a correct password (``password``: set a new one, ``totp``: enrol the second
        factor), bound to the account's password version and valid for PENDING_TTL_S; it opens no session."""
        t = int(time.time() if now is None else now)
        body = _b64(json.dumps({"u": user["name"], "st": step, "pv": password_version(user), "exp": t + PENDING_TTL_S},
                               separators=(",", ":")).encode())
        return f"s1.{body}.{self._mac('step.' + body)}"

    def verify_step(self, value: str, step: str, now: float | None = None) -> dict[str, Any] | None:
        """The claims (account ``u``, password version ``pv``) of a valid token of this step; the caller checks that
        the password has not changed since."""
        try:
            version, body, mac = (value or "").split(".")
            if version != "s1" or not hmac.compare_digest(mac, self._mac("step." + body)):
                return None
            claims = json.loads(_unb64(body))
        except (ValueError, TypeError):
            return None
        if claims.get("st") != step or int(claims.get("exp", 0)) <= (time.time() if now is None else now):
            return None
        return claims if isinstance(claims.get("u"), str) else None


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
_states: dict[Path, StateStore] = {}
throttle = LoginThrottle()


def current_store() -> AccountStore:
    """The account file of the server; with the check on, skif_root is created here when it is missing."""
    path = accounts_path()
    if path not in _stores:
        _stores[path] = AccountStore(path)
    store = _stores[path]
    if not auth_disabled():
        changed = store.ensure_superuser()
        if changed:
            current_state().audit("system", "server", "local", f"superuser-{changed}", SUPERUSER_NAME, force=True)
    return store


def current_signer() -> SessionSigner:
    path = session_key_path()
    if path not in _signers:
        _signers[path] = SessionSigner(load_session_key(path))
    return _signers[path]


def current_state() -> StateStore:
    path = state_path()
    if path not in _states:
        _states[path] = StateStore(path)
    return _states[path]


def open_session(user: dict[str, Any], address: str = "?", agent: str = "", now: float | None = None) -> str:
    """A new session of the account: the cookie value."""
    t = time.time() if now is None else now
    return current_signer().issue(user, current_state().open_session(user, address, agent, t), t)


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


def required_permission(method: str, path: str) -> str | None:
    """None: public (or guarded elsewhere); otherwise the permission the request needs (UNMAPPED: a changing route no
    rule names, refused to everyone until it is declared)."""
    if path.startswith("/static/") or (method, path) in PUBLIC_ROUTES:
        return None
    for regex, methods in _station_bench_routes():
        if method in methods and regex.match(path):
            return None
    for methods, regex, permission in PERMISSION_RULES:
        if method in methods and regex.match(path):
            return permission
    return READ if method in SAFE_METHODS or method == "WEBSOCKET" else UNMAPPED


def required_role(method: str, path: str) -> str | None:
    """The least of the basic roles that may make the request (None: public); kept for tools that ask by role."""
    need = required_permission(method, path)
    if need is None:
        return None
    return next((role for role in ("viewer", "operator", "engineer", "admin") if need in ROLE_PERMISSIONS[role]), UNMAPPED)


def _headers(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


def _same_origin(headers: dict[str, str]) -> bool:
    host = headers.get("host", "")
    source = headers.get("origin") or headers.get("referer")
    if not source or not host:
        return False
    return urlsplit(source).netloc == host


def _session_cookie(headers: dict[str, str]) -> str | None:
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("cookie", ""))
    except Exception:  # noqa: BLE001 - a malformed cookie header is simply no session
        return None
    morsel = cookie.get(COOKIE_NAME)
    return morsel.value if morsel is not None else None


def authenticate(headers: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
    store = current_store()
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return store.authenticate_token(auth[7:].strip()), "token"
    value = _session_cookie(headers)
    if value is None:
        return None, "cookie"
    claims = current_signer().verify(value)
    if claims is None:
        return None, "cookie"
    session = current_state().session(str(claims.get("s", "")), time.time())
    if session is None or session["user"] != claims.get("u"):
        return None, "cookie"
    user = store.user(str(claims.get("u", "")))
    if user is None or user.get("disabled") or claims.get("pv") != password_version(user) or session["pv"] != claims.get("pv"):
        return None, "cookie"
    return user, "cookie"


def _client_address(scope, headers: dict[str, str]) -> str:
    if os.getenv(TRUSTED_PROXY_ENV) == "1" and headers.get("x-forwarded-for"):
        return headers["x-forwarded-for"].split(",")[-1].strip()
    client = scope.get("client")
    return client[0] if client else "?"


class OperatorAuthMiddleware:
    """Pure ASGI (it must see WebSocket handshakes too)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        websocket = scope["type"] == "websocket"
        method = "WEBSOCKET" if websocket else scope["method"].upper()
        need = required_permission(method, scope["path"])
        if need is None or auth_disabled():
            return await self.app(scope, receive, send)
        headers = _headers(scope)
        if not current_store().has_users():
            return await self._deny(scope, send, headers, 503, "operator accounts are not configured: "
                                    "python -m station.operator_auth add-user <name> --role operator")
        user, via = authenticate(headers)
        if user is None:
            return await self._deny(scope, send, headers, 401, "operator login required")
        if need not in user["permissions"]:
            if method not in SAFE_METHODS and method != "WEBSOCKET":
                current_state().audit(user["name"], via, _client_address(scope, headers), f"{method} {scope['path']}",
                                      result="403", detail={"needs": need}, force=True)
            return await self._deny(scope, send, headers, 403, f"{user['name']} ({user['role']}) may not do this: needs {need}")
        if via == "cookie" and not websocket and method not in SAFE_METHODS and not _same_origin(headers):
            return await self._deny(scope, send, headers, 403, "cross-site request refused")
        if websocket and via == "cookie" and headers.get("origin") and not _same_origin(headers):
            return await self._deny(scope, send, headers, 403, "cross-site request refused")
        scope.setdefault("state", {})["operator"] = {
            "name": user["name"], "role": user["role"], "roles": user["roles"], "permissions": sorted(user["permissions"]),
            "tenants": list(user.get("tenants") or []), "stations": list(user.get("stations") or []), "via": via}
        if method in SAFE_METHODS or websocket:
            return await self.app(scope, receive, send)
        status = {"code": 500}

        async def recording_send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, recording_send)
        finally:                                            # every changing request: who, from where, what, the answer
            current_state().audit(user["name"], via, _client_address(scope, headers), f"{method} {scope['path']}",
                                  result=str(status["code"]),
                                  detail={"token": user["token_id"]} if user.get("token_id") else None)

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


def needs_second_factor(user: dict[str, Any]) -> bool:
    return second_factor_required() and bool(SECOND_FACTOR_ROLES & set(user["roles"]))


def confirm_second_factor(user: dict[str, Any], code: str | None, now: float | None = None) -> bool:
    """A dangerous action of a session repeats the code of its account's second factor (the current 30-s step or a
    neighbour; not consumed, so several actions in one step need one code).  True without a second factor to ask."""
    if not needs_second_factor(user):
        return True
    secret = user.get("totp")
    return bool(secret) and totp_counter(code or "", secret, time.time() if now is None else now) is not None


def build_router(templates) -> APIRouter:
    auth_router = APIRouter()

    def page(request: Request, status: int = 200, error: str | None = None, next_url: str = "/", **step):
        context = {"error": error, "next_url": next_url, "configured": current_store().has_users(), "mode": "login",
                   "min_password": MIN_PASSWORD_LEN, **step}
        return templates.TemplateResponse(request, "login.html", context, status_code=status,
                                          headers={"cache-control": "no-store"})

    def finish(user: dict[str, Any], address: str, headers: dict[str, str], next_url: str, now: float):
        """The session of a login all of whose steps are done."""
        current_state().audit(user["name"], "login", address, "login")
        response = RedirectResponse(safe_next(next_url), status_code=303)
        response.set_cookie(COOKIE_NAME, open_session(user, address, headers.get("user-agent", ""), now), max_age=SESSION_TTL_S,
                            httponly=True, secure=cookie_secure(), samesite="strict", path="/")
        return response

    def enrol(request: Request, user: dict[str, Any], address: str, next_url: str, now: float):
        """The second-factor enrolment step: a new secret, shown once, confirmed by a code at /login/totp."""
        secret = new_totp_secret()
        current_state().put_pending_totp(user["name"], secret, now)
        return page(request, 200, None, next_url, mode="totp", step=current_signer().issue_step(user, "totp", now),
                    name=user["name"], secret=" ".join(secret[i:i + 4] for i in range(0, len(secret), 4)),
                    uri=totp_uri(user["name"], secret))

    def after_password(request: Request, user: dict[str, Any], address: str, headers: dict[str, str], next_url: str,
                       now: float, code: str | None):
        """What follows a correct password: a required change, a second-factor enrolment, the code, or the session."""
        state = current_state()
        if user.get("must_change"):
            state.audit(user["name"], "login", address, "login", result="password change required")
            return page(request, 200, None, next_url, mode="password", step=current_signer().issue_step(user, "password", now),
                        name=user["name"])
        if needs_second_factor(user):
            if not user.get("totp"):
                if user.get("totp_at_login"):
                    return enrol(request, user, address, next_url, now)
                state.audit(user["name"], "login", address, "login", result="no second factor", force=True)
                return page(request, 403, "Для роли инженера и администратора нужен второй фактор. Выдать секрет: "
                                          f"python -m station.operator_auth totp-enroll {user['name']}", next_url)
            if code is not None:
                counter = totp_counter(code, user["totp"], now)
                if counter is None or not state.use_totp_step(user["name"], counter):
                    throttle.fail(LoginThrottle.keys(address, user["name"]), now)
                    state.audit(user["name"], "login", address, "login", result="bad code", force=True)
                    return page(request, 401, "Неверный или уже использованный код второго фактора.", next_url)
            else:                                       # a new password set: log in with it and the code
                return page(request, 200, "Пароль изменён. Войдите с новым паролем и кодом второго фактора.", next_url)
        throttle.reset(LoginThrottle.keys(address, user["name"]))
        return finish(user, address, headers, next_url, now)

    def step_user(request: Request, step_token: str, step: str, now: float) -> dict[str, Any] | None:
        """The account of a valid step token whose password has not changed since."""
        claims = current_signer().verify_step(step_token, step, now)
        user = current_store().user(claims["u"]) if claims else None
        if user is None or user.get("disabled") or claims.get("pv") != password_version(user):
            return None
        return user

    def foreign(request: Request) -> bool:
        headers = {k.lower(): v for k, v in request.headers.items()}
        return bool(headers.get("origin")) and not _same_origin(headers)

    @auth_router.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, next: str = "/"):
        return page(request, next_url=safe_next(next))

    @auth_router.post("/login", response_class=HTMLResponse)
    async def login(request: Request, username: str = Form(""), password: str = Form(""), code: str = Form(""),
                    next: str = Form("/")):
        headers = {k.lower(): v for k, v in request.headers.items()}
        if foreign(request):
            return page(request, 403, "Запрос с чужого сайта отклонён.")
        now = time.time()
        address = client_address(request)
        name = username.lower()
        keys = LoginThrottle.keys(address, name)
        state = current_state()
        if throttle.locked(keys, now):
            state.audit(name or "?", "login", address, "login", result="locked", force=True)
            return page(request, 429, "Слишком много неудачных попыток. Повторите через 15 минут.", safe_next(next))
        user = current_store().authenticate_password(name, password)
        if user is None:
            throttle.fail(keys, now)
            state.audit(name or "?", "login", address, "login", result="failed", force=True)
            return page(request, 401, "Неверное имя или пароль.", safe_next(next))
        return after_password(request, user, address, headers, safe_next(next), now, code)

    @auth_router.post("/login/password", response_class=HTMLResponse)
    async def login_password(request: Request, step: str = Form(""), new_password: str = Form(""), repeat: str = Form(""),
                             next: str = Form("/")):
        """The required change of the password (the superuser's default one): the step the password gave."""
        headers = {k.lower(): v for k, v in request.headers.items()}
        if foreign(request):
            return page(request, 403, "Запрос с чужого сайта отклонён.")
        now = time.time()
        address = client_address(request)
        user = step_user(request, step, "password", now)
        if user is None or not user.get("must_change"):
            return page(request, 401, "Шаг входа устарел. Войдите заново.", safe_next(next))
        again = {"mode": "password", "step": step, "name": user["name"]}
        if new_password != repeat:
            return page(request, 400, "Пароли не совпадают.", safe_next(next), **again)
        if len(new_password) < MIN_PASSWORD_LEN:
            return page(request, 400, f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов.", safe_next(next), **again)
        if verify_password(new_password, user["password"]) or new_password == SUPERUSER_DEFAULT_PASSWORD:
            return page(request, 400, "Новый пароль должен отличаться от прежнего.", safe_next(next), **again)
        current_store().set_password(user["name"], new_password)
        current_state().close_sessions(user["name"])
        current_state().audit(user["name"], "login", address, "passwd", user["name"], detail={"required": True})
        user = current_store().user(user["name"])
        return after_password(request, user, address, headers, safe_next(next), now, None)

    @auth_router.post("/login/totp", response_class=HTMLResponse)
    async def login_totp(request: Request, step: str = Form(""), code: str = Form(""), next: str = Form("/")):
        """The second-factor enrolment at login: the code of the secret shown confirms it and opens the session."""
        headers = {k.lower(): v for k, v in request.headers.items()}
        if foreign(request):
            return page(request, 403, "Запрос с чужого сайта отклонён.")
        now = time.time()
        address = client_address(request)
        user = step_user(request, step, "totp", now)
        state = current_state()
        secret = state.pending_totp(user["name"], now) if user else None
        if user is None or secret is None or user.get("totp") or not user.get("totp_at_login"):
            return page(request, 401, "Шаг входа устарел. Войдите заново.", safe_next(next))
        keys = LoginThrottle.keys(address, user["name"])
        if throttle.locked(keys, now):
            state.audit(user["name"], "login", address, "totp-enroll", result="locked", force=True)
            return page(request, 429, "Слишком много неудачных попыток. Повторите через 15 минут.", safe_next(next))
        counter = totp_counter(code, secret, now)
        if counter is None or not state.use_totp_step(user["name"], counter):
            throttle.fail(keys, now)
            state.audit(user["name"], "login", address, "totp-enroll", result="bad code", force=True)
            return page(request, 401, "Код не подошёл. Проверьте время на телефоне и введите новый код.", safe_next(next),
                        mode="totp", step=step, name=user["name"],
                        secret=" ".join(secret[i:i + 4] for i in range(0, len(secret), 4)), uri=totp_uri(user["name"], secret))
        current_store().set_totp(user["name"], secret)
        state.drop_pending_totp(user["name"])
        state.audit(user["name"], "login", address, "totp-enroll", user["name"])
        throttle.reset(keys)
        return finish(current_store().user(user["name"]), address, headers, safe_next(next), now)

    @auth_router.post("/logout")
    async def logout(request: Request):
        value = _session_cookie({k.lower(): v for k, v in request.headers.items()})
        claims = current_signer().verify(value) if value else None
        if claims:
            user = current_state().close_session(str(claims.get("s", "")))
            if user:
                current_state().audit(user, "cookie", client_address(request), "logout")
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


def _ints(text: str) -> list[int]:
    try:
        return [int(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise ValueError("stations: comma-separated ids") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m station.operator_auth", description="Muhoed operator accounts")
    parser.add_argument("--accounts", help=f"account file (default ${ACCOUNTS_ENV} or data/operators.json)")
    parser.add_argument("--state", help=f"sessions and audit log (default ${STATE_ENV} or operator_state.sqlite3 next to the accounts)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    roles_help = "comma-separated: " + ",".join(GRANTABLE_ROLES)
    p = sub.add_parser("add-user"); p.add_argument("name"); p.add_argument("--role", "--roles", dest="roles", required=True, help=roles_help)
    p.add_argument("--password-stdin", action="store_true")
    p = sub.add_parser("passwd"); p.add_argument("name"); p.add_argument("--password-stdin", action="store_true")
    p = sub.add_parser("set-role", aliases=["set-roles"]); p.add_argument("name")
    p.add_argument("--role", "--roles", dest="roles", required=True, help=roles_help)
    p = sub.add_parser("set-scope", help="tenants and stations the account sees (empty: all)"); p.add_argument("name")
    p.add_argument("--tenants", default=""); p.add_argument("--stations", default="")
    p = sub.add_parser("disable"); p.add_argument("name")
    p = sub.add_parser("enable"); p.add_argument("name")
    p = sub.add_parser("remove-user"); p.add_argument("name")
    p = sub.add_parser("totp-enroll", help="a new second-factor secret (shown once)"); p.add_argument("name")
    p = sub.add_parser("totp-reset"); p.add_argument("name")
    p = sub.add_parser("issue-token"); p.add_argument("name"); p.add_argument("--label", default="")
    p.add_argument("--scopes", default=READ, help="comma-separated: " + ",".join(PERMISSIONS))
    p.add_argument("--expires-days", type=int)
    p = sub.add_parser("revoke-token"); p.add_argument("token_id")
    p = sub.add_parser("sessions"); p.add_argument("name", nargs="?")
    p = sub.add_parser("logout-all", help="end every session of the account"); p.add_argument("name")
    p = sub.add_parser("audit"); p.add_argument("--limit", type=int, default=50); p.add_argument("--actor")
    sub.add_parser("audit-verify")
    p = sub.add_parser("audit-logging", help="the audit log of actions: show, or switch on or off (always recorded)")
    p.add_argument("switch", nargs="?", choices=["on", "off"])
    sub.add_parser("list")
    args = parser.parse_args(argv)
    accounts = Path(args.accounts) if args.accounts else accounts_path()
    store = AccountStore(accounts)
    state = StateStore(Path(args.state) if args.state else Path(os.getenv(STATE_ENV) or accounts.with_name("operator_state.sqlite3")))
    actor = f"cli:{getpass.getuser()}"
    created = store.ensure_superuser()                 # the CLI sees the same accounts as the server
    if created:
        state.audit("system", "cli", "local", f"superuser-{created}", SUPERUSER_NAME, force=True)

    def done(action: str, target: str, detail: dict[str, Any] | None = None) -> None:
        state.audit(actor, "cli", "local", action, target, detail=detail)

    try:
        if args.cmd == "add-user":
            store.add_user(args.name, args.roles, _read_password(args.password_stdin))
            done("add-user", args.name, {"roles": store.user(args.name)["roles"]})
            print(f"user {args.name} ({store.user(args.name)['role']}) added")
        elif args.cmd == "passwd":
            store.set_password(args.name, _read_password(args.password_stdin))
            state.close_sessions(args.name)
            done("passwd", args.name)
            print(f"password of {args.name} changed; its sessions are closed")
        elif args.cmd in ("set-role", "set-roles"):
            store.set_roles(args.name, args.roles)
            done("set-roles", args.name, {"roles": store.user(args.name)["roles"]})
            print(f"{args.name} is now {store.user(args.name)['role']}")
        elif args.cmd == "set-scope":
            tenants = [t.strip() for t in args.tenants.split(",") if t.strip()]
            store.set_scope(args.name, tenants, _ints(args.stations))
            done("set-scope", args.name, {"tenants": tenants, "stations": _ints(args.stations)})
            print(f"{args.name} sees tenants {tenants or 'all'}, stations {_ints(args.stations) or 'all'}")
        elif args.cmd in ("disable", "enable"):
            store.set_disabled(args.name, args.cmd == "disable")
            if args.cmd == "disable":
                state.close_sessions(args.name)
            done(args.cmd, args.name)
            print(f"{args.name} {args.cmd}d")
        elif args.cmd == "remove-user":
            store.remove_user(args.name)
            state.close_sessions(args.name)
            done("remove-user", args.name)
            print(f"user {args.name} and its tokens removed")
        elif args.cmd == "totp-enroll":
            secret = new_totp_secret()
            store.set_totp(args.name, secret)
            done("totp-enroll", args.name)
            print(f"second factor of {args.name} (shown once; add it to an authenticator app):\n{secret}\n{totp_uri(args.name, secret)}")
        elif args.cmd == "totp-reset":
            store.set_totp(args.name, None)
            state.close_sessions(args.name)
            done("totp-reset", args.name)
            print(f"second factor of {args.name} removed; " + ("it enrols a new one at its next login" if args.name == SUPERUSER_NAME
                                                               else "enrol a new one before the next login"))
        elif args.cmd == "issue-token":
            token_id, token = store.issue_token(args.name, args.label, args.scopes, args.expires_days)
            done("issue-token", args.name, {"token": token_id, "scopes": _parse_scopes(args.scopes)})
            print(f"token {token_id} for {args.name} (shown once, store it as a secret):\n{token}")
        elif args.cmd == "revoke-token":
            store.revoke_token(args.token_id)
            done("revoke-token", args.token_id)
            print(f"token {args.token_id} revoked")
        elif args.cmd == "sessions":
            print(json.dumps(state.sessions(args.name), indent=2, ensure_ascii=False))
        elif args.cmd == "logout-all":
            n = state.close_sessions(args.name)
            done("logout-all", args.name, {"sessions": n})
            print(f"{n} session(s) of {args.name} closed")
        elif args.cmd == "audit":
            for r in state.audit_records(args.limit, args.actor):
                when = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r["at"]))
                print(f"{when}Z {r['actor']} ({r['via']}, {r['address']}) {r['action']} {r['target']} -> {r['result']} {r['detail']}")
        elif args.cmd == "audit-logging":
            if args.switch:
                state.set_audit_logging(args.switch == "on", actor, "cli", "local")
            print(json.dumps(state.audit_logging(), ensure_ascii=False))
        elif args.cmd == "audit-verify":
            ok, n = state.audit_verify()
            print(f"audit log {'intact' if ok else 'CHANGED'}: {n} record(s) checked")
            return 0 if ok else 1
        else:
            print(json.dumps(store.listing(), indent=2, ensure_ascii=False))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""QG-1 completeness and traceability for operator authentication of the Muhoed UI/API (release audit item 1)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = "ZS_OPERATOR_AUTH_INSECURE_BENCH"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    module = read("server/station/operator_auth.py")
    app = read("server/app.py")
    tests = read("server/tests/test_operator_auth.py")
    conftest = read("server/tests/conftest.py")
    gitignore = read(".gitignore")
    readme = read("server/deploy/README.md")
    audit = read("server/EVT_PRE_20_RELEASE_AUDIT.md")
    gates = read("server/tests/test_operator_auth_gates.py")
    prod = {name: read(f"server/deploy/{name}") for name in ("compose.ubuntu.yml", "compose.windows.tls.yml")}
    bench = {name: read(f"server/deploy/{name}") for name in ("docker-compose.dev.yml", "compose.windows.yml")}

    for token in (
        f'INSECURE_BENCH_ENV = "{ENV}"',
        'os.getenv(INSECURE_BENCH_ENV) == "1"',
        "hashlib.scrypt(",
        "hmac.compare_digest",
        'samesite="strict"',
        "httponly=True",
        "secure=cookie_secure()",
        "password_version(user)",
        "station_http_router.routes",
        "OPERATOR_READ_RE",
        "LOGIN_FAILURE_LIMIT = 5",
        "_same_origin(headers)",
        '"websocket.close"',
        "has_users()",
        "0o600",
    ):
        require(token in module, f"operator auth contract missing: {token}")
    require("TOKEN_PREFIX + secrets.token_urlsafe(32)" in module and "hashlib.sha256(token.encode())" in module,
            "API tokens are not random or not stored as hashes")
    require("app.add_middleware(OperatorAuthMiddleware)" in app and "build_auth_router(templates)" in app,
            "operator auth is not mounted on the application")

    for name, text in prod.items():
        require(ENV not in text and "ZS_OPERATOR_COOKIE_SECURE" not in text,
                f"production compose {name} weakens operator auth")
    for name, text in bench.items():
        require(f'{ENV}: "1"' in text, f"bench compose {name} does not opt out explicitly")
    for entry in ("server/data/operators.json", "server/data/operator_session.key", "server/data/audio/"):
        require(entry in gitignore, f"secret or recording not excluded from Git: {entry}")

    for token in (
        "test_fail_closed_without_accounts",
        "test_login_session_roles_and_logout",
        "test_cookie_requests_that_change_things_must_be_same_origin",
        "test_bearer_tokens_for_scripts",
        "test_password_change_and_removal_end_sessions_at_once",
        "test_forged_and_expired_cookies",
        "test_login_is_throttled",
        "test_event_stream_needs_a_viewer",
        "test_station_bench_routes_keep_their_own_guard",
        "test_bench_switch_is_exact",
    ):
        require(token in tests, f"operator auth QG-2 case missing: {token}")
    require(ENV in conftest, "API tests do not opt out explicitly")
    require("python -m station.operator_auth add-user" in readme and f"Never set `{ENV}`" in readme,
            "deployment guide does not cover operator accounts")
    require("proxy_set_header Host" in readme, "reverse proxy Host requirement undocumented")
    require("Пункт 1 остаётся открытым до\ndeployment-проверок" in audit and "station/operator_auth.py" in audit,
            "release audit does not state the operator auth scope")
    # bound to CI through the server job's `pytest tests` (a dedicated ci.yml step may be added as well)
    require("validate_operator_auth.py" in gates and "audit_operator_auth_technical.py" in gates,
            "operator auth QG-1/QG-2 are not bound to CI")

    print("Operator authentication QG-1 completeness/traceability: PASS")
    print("fail-closed login/roles/tokens mounted on the whole app; bench opt-out explicit; deployment checks remain open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

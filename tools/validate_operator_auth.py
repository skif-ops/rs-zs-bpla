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
        # roles and permissions, server-side sessions, second factor, audit chain (2026-10-02)
        "ROLE_PERMISSIONS = {",
        "def required_permission(",
        "UNMAPPED",
        'SECOND_FACTOR_ROLES = {"engineer", "admin"}',
        "SESSION_IDLE_S = 30 * 60",
        "close_sessions(",
        "use_totp_step(",
        "hashlib.sha1",
        "def audit_verify(",
        'user["permissions"] & set(entry["scopes"])',
    ):
        require(token in module, f"operator auth contract missing: {token}")
    require('"viewer": {READ}' in module and '"service": {READ}' in module, "viewer or service role may change things")
    require("STATION_COMMAND" not in module.split('"admin": {', 1)[1].split("}", 1)[0],
            "the security admin must not command stations")
    require("TOKEN_PREFIX + secrets.token_urlsafe(32)" in module and "hashlib.sha256(token.encode())" in module,
            "API tokens are not random or not stored as hashes")
    require("app.add_middleware(OperatorAuthMiddleware)" in app and "build_auth_router(templates)" in app,
            "operator auth is not mounted on the application")

    for name, text in prod.items():
        require(ENV not in text and "ZS_OPERATOR_COOKIE_SECURE" not in text and "ZS_OPERATOR_TOTP" not in text,
                f"production compose {name} weakens operator auth")
    for name, text in bench.items():
        require(f'{ENV}: "1"' in text, f"bench compose {name} does not opt out explicitly")
    for entry in ("server/data/operators.json", "server/data/operator_session.key", "server/data/audio/", "server/data/*.sqlite3"):
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
        "test_sessions_end_when_idle_and_on_demand",
        "test_second_factor_for_engineers_and_admins",
        "test_totp_matches_rfc_6238",
        "test_roles_and_permissions",
        "test_every_changing_route_is_declared",
        "test_legacy_account_file_keeps_working",
        "test_audit_log_is_chained",
    ):
        require(token in tests, f"operator auth QG-2 case missing: {token}")
    scope_module = read("server/station/access_scope.py")
    scope_tests = read("server/tests/test_access_scope.py")
    router = read("server/station/router.py")
    for token in ("def scope_for(", "class LiveScope", "return None                                  # an item nobody declared"):
        require(token in scope_module, f"station visibility contract missing: {token}")
    require(router.count("scope_of(request,store)") >= 10 and "LiveScope(ws,store)" in router,
            "data APIs do not apply the account's stations and tenants")
    for token in (
        "test_stations_follow_tenants_and_stations",
        "test_events_tracks_and_bearings_are_cut_to_the_account",
        "test_replay_and_coverage_show_only_own_stations",
        "test_audio_and_commands_of_other_stations_do_not_exist",
        "test_output_api_follows_the_account",
        "test_live_stream_follows_scope_and_logout",
        "test_admin_and_engineers_set_who_sees_what",
    ):
        require(token in scope_tests, f"station visibility case missing: {token}")
    require(ENV in conftest, "API tests do not opt out explicitly")
    require("totp-enroll" in readme and "audit-verify" in readme, "deployment guide does not cover the second factor and the audit log")
    require("python -m station.operator_auth add-user" in readme and f"Never set `{ENV}`" in readme,
            "deployment guide does not cover operator accounts")
    require("proxy_set_header Host" in readme, "reverse proxy Host requirement undocumented")
    require("Пункт 1 остаётся открытым до\ndeployment-проверок" in audit and "station/operator_auth.py" in audit,
            "release audit does not state the operator auth scope")
    # bound to CI through the server job's `pytest tests` (a dedicated ci.yml step may be added as well)
    require("validate_operator_auth.py" in gates and "audit_operator_auth_technical.py" in gates,
            "operator auth QG-1/QG-2 are not bound to CI")

    print("Operator authentication QG-1 completeness/traceability: PASS")
    print("fail-closed login/roles/permissions/second factor/tokens/audit mounted on the whole app; bench opt-out explicit; "
          "deployment checks remain open")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

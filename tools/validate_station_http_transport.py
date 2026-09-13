#!/usr/bin/env python3
"""QG-1 completeness and traceability for fail-closed station HTTP traffic."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV = "ZS_STATION_HTTP_INSECURE_BENCH"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    policy = read("server/station/http_transport.py")
    router = read("server/station/router.py")
    tests = read("server/tests/test_station_api.py")
    dev_compose = read("server/deploy/docker-compose.dev.yml")
    windows_bench = read("server/deploy/compose.windows.yml")
    ubuntu_prod = read("server/deploy/compose.ubuntu.yml")
    windows_prod = read("server/deploy/compose.windows.tls.yml")
    deployment = read("server/deploy/README.md")
    audit = read("server/EVT_PRE_20_RELEASE_AUDIT.md")
    ci = read(".github/workflows/ci.yml")

    require(f'INSECURE_BENCH_ENV = "{ENV}"' in policy, "bench opt-in name drift")
    require('os.getenv(INSECURE_BENCH_ENV) == "1"' in policy,
            "station HTTP opt-in is not exact and fail-closed")
    require("status.HTTP_403_FORBIDDEN" in policy and "use mutual-TLS MQTT in production" in policy,
            "default rejection or production route guidance missing")
    require("station_http_router=APIRouter(dependencies=[Depends(require_insecure_station_http_bench)])" in router,
            "guarded station HTTP router missing")

    guarded_decorators = {
        "@station_http_router.post('/stations/{station_id}/heartbeat')",
        "@station_http_router.post('/stations/{station_id}/detection')",
        "@station_http_router.post('/stations/{station_id}/detection.cbor')",
        "@station_http_router.post('/stations/{station_id}/events/{event_id}/features')",
        "@station_http_router.post('/stations/{station_id}/security')",
        "@station_http_router.get('/stations/{station_id}/commands/poll')",
        "@station_http_router.post('/stations/{station_id}/commands/{command_id}/ack')",
        "@station_http_router.post('/stations/{station_id}/events/{event_id}/audio')",
    }
    actual_guarded_decorators = {
        line.strip() for line in router.splitlines()
        if line.strip().startswith("@station_http_router.")
    }
    require(actual_guarded_decorators == guarded_decorators,
            f"guarded station route set drift: {actual_guarded_decorators ^ guarded_decorators}")
    unguarded_station_decorators = {
        line.strip() for line in router.splitlines()
        if "/stations/{station_id}/" in line and line.strip().startswith("@router.")
    }
    require(
        unguarded_station_decorators == {
            "@router.post('/stations/{station_id}/audio-request')",
        },
        f"station transport route bypasses guarded router: {unguarded_station_decorators}",
    )

    require("router.include_router(station_http_router)" in router,
            "guarded station router is not mounted")
    require("test_station_http_ingress_is_disabled_by_default" in tests,
            "default-deny regression test missing")
    require("test_station_http_ingress_rejects_ambiguous_opt_in" in tests,
            "exact opt-in regression test missing")
    require("test_http_heartbeat_rejects_full_cellular_identity" in tests,
            "HTTP protected-identity rejection regressed")

    require(f'{ENV}: "1"' in dev_compose and f'{ENV}: "1"' in windows_bench,
            "bench compose does not opt in explicitly")
    require("--insecure-bench" in windows_bench,
            "Windows plaintext MQTT bridge is not explicitly bench-only")
    require(ENV not in ubuntu_prod and ENV not in windows_prod,
            "production compose enables insecure station HTTP")
    require("isolated-bench configurations" in deployment and
            "must not be used for production" in deployment,
            "bench deployment warning missing")
    require("Пункт 1 остаётся открытым" in audit,
            "release audit overclaims operator API authorization")
    require("audit_station_http_transport_technical.py" in ci and
            "validate_station_http_transport.py" in ci,
            "station HTTP QG-1/QG-2 are not bound to CI")

    print("Station HTTP transport QG-1 completeness/traceability: PASS")
    print("production default deny and isolated-bench opt-in are documented and CI-bound")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Test isolation for station persistence.

The production store is intentionally persistent, but API regression tests must
not depend on a SQLite database left by a previous pytest run.
"""
from pathlib import Path

import pytest

BASE=Path(__file__).resolve().parents[1]
for suffix in ('','-wal','-shm'):
    p=BASE/'data'/f'zs_bpla.sqlite3{suffix}'
    try: p.unlink()
    except FileNotFoundError: pass


@pytest.fixture(scope="session", autouse=True)
def isolate_station_store_after_collection():
    """Clear rows after test modules import the application-level store."""

    try:
        from station.router import service, store, type_service
    except ModuleNotFoundError:
        # PKI-only environments (e.g. the Windows executable build) install
        # requirements-pki.txt only; no station API tests are collected there.
        yield
        return

    with store.lock, store._conn() as connection:
        for table in ("audio", "commands", "security_events", "system_events", "detections", "stations"):
            connection.execute(f"DELETE FROM {table}")
    service.track_filters.clear()
    service.track_frames.clear()
    type_service.sessions.clear()
    yield


@pytest.fixture
def insecure_station_http_bench(monkeypatch):
    """Enable the legacy station HTTP transport for an isolated test only."""

    monkeypatch.setenv("ZS_STATION_HTTP_INSECURE_BENCH", "1")


@pytest.fixture(autouse=True)
def operator_auth_bench(monkeypatch):
    """Most API tests exercise routes, not operator login: switch the operator check off for them (the exact bench
    opt-in).  test_operator_auth.py removes it and runs with real accounts."""

    monkeypatch.setenv("ZS_OPERATOR_AUTH_INSECURE_BENCH", "1")

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

    from station.router import service, store, type_service

    with store.lock, store._conn() as connection:
        for table in ("audio", "commands", "security_events", "system_events", "detections", "stations"):
            connection.execute(f"DELETE FROM {table}")
    service.track_filters.clear()
    service.track_frames.clear()
    type_service.sessions.clear()
    yield

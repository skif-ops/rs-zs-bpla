"""Alert journal: one episode, scoped read access and append-only operator decisions."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

import station.router as station_router
from station.store import DAY_US, EventStore


def episode(alert_id: str, tenant: str, started_us: int, stations: list[int], *, ended: bool = True) -> dict:
    return {"alert_id": alert_id, "tenant": tenant, "started_us": started_us,
            "last_activity_us": started_us + 30_000_000, "level": "alert" if len(stations) > 1 else "warning",
            "stations": stations, "class": {"code": "uav_piston", "label": "PISTON_UAV", "confidence": .82,
                                                   "type": None, "f0_hz": 91.0},
            "ended_us": started_us + 120_000_000 if ended else None}


def test_store_keeps_decision_revisions_and_filters(tmp_path):
    store = EventStore(tmp_path / "journal.sqlite3")
    store.save_episode(episode("ALR-north-1", "north", 100, [17, 18]))
    store.save_episode(episode("ALR-south-2", "south", 200, [19]))
    store.save_alert_track("TRK-1", "ALR-north-1", 150)

    first = store.save_alert_decision("ALR-north-1", "ops", "confirmed_target", "Визуально подтверждено", now_us=300)
    second = store.save_alert_decision("ALR-north-1", "ops2", "false_alarm", "Птицы", now_us=400)
    assert first["decision_id"] < second["decision_id"]
    row = store.get_alert_journal("ALR-north-1")
    assert row["tracks"] == ["TRK-1"]
    assert row["decision"]["disposition"] == "false_alarm"
    assert [d["disposition"] for d in row["decisions"]] == ["false_alarm", "confirmed_target"]
    assert [e["alert_id"] for e in store.list_alert_episodes(stations=[17])] == ["ALR-north-1"]
    assert [e["alert_id"] for e in store.list_alert_episodes(tenants=["south"], disposition="pending")] == ["ALR-south-2"]
    assert store.save_alert_decision("missing", "ops", "confirmed_target") is None


def test_journal_api_and_comment_rule(tmp_path, monkeypatch):
    store = EventStore(tmp_path / "journal.sqlite3")
    store.save_episode(episode("ALR-bench-1", "bench", 1_000_000, [9001, 9002]))
    monkeypatch.setattr(station_router, "store", store)
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/journal", "headers": [],
                       "query_string": b"", "state": {}})
    listing = asyncio.run(station_router.alert_journal(request, 200, None, None, None, None))
    assert listing["entries"][0]["alert_id"] == "ALR-bench-1" and listing["entries"][0]["decision"] is None
    with pytest.raises(HTTPException) as bad:
        asyncio.run(station_router.decide_alert(request, "ALR-bench-1",
                    station_router.AlertDecisionRequest(disposition="false_alarm", comment="")))
    assert bad.value.status_code == 422
    saved = asyncio.run(station_router.decide_alert(request, "ALR-bench-1",
                        station_router.AlertDecisionRequest(disposition="confirmed_target", comment="Цель наблюдалась")))
    assert saved["decision"]["actor"] == "bench"
    detail = asyncio.run(station_router.alert_journal_entry(request, "ALR-bench-1"))
    assert detail["decision"]["comment"] == "Цель наблюдалась" and len(detail["decisions"]) == 1
    token_request = Request({"type": "http", "method": "POST", "path": "/api/v1/journal/ALR-bench-1/decision",
                             "headers": [], "query_string": b"", "state": {"operator": {"name": "ops", "via": "token"}}})
    with pytest.raises(HTTPException) as token_denied:
        asyncio.run(station_router.decide_alert(token_request, "ALR-bench-1",
                    station_router.AlertDecisionRequest(disposition="confirmed_target", comment="")))
    assert token_denied.value.status_code == 403


def test_journal_pagination_does_not_skip_equal_timestamps(tmp_path):
    store = EventStore(tmp_path / "journal.sqlite3")
    for alert_id in ("ALR-C", "ALR-B", "ALR-A"):
        store.save_episode(episode(alert_id, "bench", 100, [9001]))
    first = store.list_alert_episodes(2)
    assert [row["alert_id"] for row in first] == ["ALR-C", "ALR-B"]
    second = store.list_alert_episodes(2, before_us=first[-1]["started_us"], before_id=first[-1]["alert_id"])
    assert [row["alert_id"] for row in second] == ["ALR-A"]


def test_journal_page_renders():
    from app import app
    with TestClient(app) as client:
        page = client.get("/journal")
    assert page.status_code == 200 and "Журнал тревог" in page.text and "/static/js/journal.js" in page.text


def test_decision_is_removed_with_expired_episode(tmp_path):
    store = EventStore(tmp_path / "journal.sqlite3")
    now = 100 * DAY_US
    store.save_episode(episode("ALR-old", "bench", DAY_US, [1]))
    store.save_alert_decision("ALR-old", "ops", "technical_event", "Проверка стенда", now_us=DAY_US + 1)
    removed = store.cleanup(90, now_us=now)
    assert removed["alert_episodes"] == 1 and removed["alert_decisions"] == 1
    assert store.get_alert_journal("ALR-old") is None

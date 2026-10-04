"""Who sees which stations (station/access_scope.py, station/access_api.py): an operator account limited to tenants or
stations gets only their stations, bearings, audio and commands, the events, tracks, replay and alerts they took part in
(with the other stations cut out), and a live stream that follows the account."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import station.router as station_router
from station import access_scope, operator_auth as oa
from station.command_codec import CommandAck, encode_command_ack
from station.mqtt_bridge import process_message
from station.schemas import HeartbeatMessage
from station.store import EventStore

PASSWORD = "correct horse battery"
ORIGIN = {"origin": "https://testserver"}
T0 = 1_900_000_000_000_000


def point(t_us, stations):
    return {"time_us": t_us, "lat": 55.01, "lon": 37.01, "alt_msl_m": 300.0, "horizontal_error_m": 30.0,
            "vertical_error_m": 40.0, "vx_east_mps": 10.0, "vy_north_mps": 0.0, "vz_up_mps": 0.0, "speed_mps": 10.0,
            "course_deg": 90.0, "crossing_deg": 60.0, "stations": stations}


def event(sid, stations, t_us):
    return {"system_event_id": sid, "event_type": "AIR_ALERT", "created_time_us": t_us,
            "source_event_ids": [s * 1000 + 1 for s in stations], "source_station_ids": stations,
            "classification_label": "FP-1", "confidence": 0.9, "stations_used": len(stations), "target": {},
            "route_summary": [f"{s}:MQTT:0" for s in stations], "status": "active"}


@pytest.fixture
def field(tmp_path: Path, monkeypatch):
    """Stations 17, 18 (tenant north) and 19 (south), their events, tracks, bearings and alert messages."""
    monkeypatch.delenv(oa.INSECURE_BENCH_ENV, raising=False)
    monkeypatch.delenv(oa.TOTP_ENV, raising=False)
    monkeypatch.setenv(oa.ACCOUNTS_ENV, str(tmp_path / "operators.json"))
    monkeypatch.setenv(oa.SESSION_KEY_ENV, str(tmp_path / "session.key"))
    monkeypatch.setenv(oa.STATE_ENV, str(tmp_path / "state.sqlite3"))
    monkeypatch.setattr(oa, "throttle", oa.LoginThrottle())
    store = EventStore(tmp_path / "zs.sqlite3")
    monkeypatch.setattr(station_router, "store", store)
    for sid, tenant, lon in ((17, "north", 37.00), (18, "north", 37.02), (19, "south", 37.04)):
        store.note_station_tenant(sid, tenant)
        store.upsert_station(HeartbeatMessage.model_validate(
            {"station_id": sid, "time_us": T0, "station": {"lat_e7": 550000000, "lon_e7": int(lon * 1e7), "alt_dm": 1500}}))
    with store._conn() as c:
        for e in (event("E-17-19", [17, 19], T0 + 1), event("E-19", [19], T0 + 2), event("E-18", [18], T0 + 3)):
            c.execute("INSERT INTO system_events VALUES(?,?,?,?)", (e["system_event_id"], e["created_time_us"], e["event_type"], json.dumps(e)))
        rows = [(s, s * 1000 + 1, T0 + k * 1_000_000, 9000, 500, 200, 0.8, 4, "GNSS_TIME_TRUSTED", T0, 0)
                for s in (17, 18, 19) for k in range(3)]
        c.executemany("INSERT INTO bearings VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
    store.replace_track("TRK-17-19", [(17, 17001, 0), (19, 19001, 0)], "E-17-19",
                        [point(T0, [17, 19]), point(T0 + 1_000_000, [19])])
    store.replace_track("TRK-18-19", [(18, 18001, 0), (19, 19001, 1)], None, [point(T0 + 2_000_000, [18, 19])])
    stations = {s: {"station_id": s, "lat": 55.0, "lon": 37.0, "alt_msl_m": 150.0} for s in (17, 18, 19)}
    messages = [("north", "alert.start", {"alert": {"level": "alert", "stations": [stations[17], stations[18]]}}),
                ("south", "alert.start", {"alert": {"level": "alert", "stations": [stations[19]]}}),
                ("north", "track.update", {"track": {"track_id": "TRK-18-19", "stations": [18, 19]}}),
                ("north", "bearing", {"bearing": {"station": stations[18]}}),
                ("north", "bearing", {"bearing": {"station": stations[17]}})]
    for i, (tenant, kind, body) in enumerate(messages):
        store.append_alert(f"m{i}", tenant, kind, T0 + i, {"schema": "dioneya.alert/1", "msg_id": f"m{i}", "type": kind,
                                                         "tenant": tenant, **body})
    from app import app

    return oa.current_store(), store, app


def client(app) -> TestClient:
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def logged_in(app, name, code=""):
    c = client(app)
    r = c.post("/login", data={"username": name, "password": PASSWORD, "code": code}, headers=ORIGIN)
    assert r.status_code == 303, r.text
    return c


def code_now(secret):
    return oa.totp_code(secret, int(time.time() // oa.TOTP_STEP_S))


def ids(rows, key="station_id"):
    return sorted(r[key] for r in rows)


def test_stations_follow_tenants_and_stations(field):
    accounts, store, app = field
    for name, tenants, stations in (("all", [], []), ("north", ["north"], []), ("only17", [], [17]),
                                    ("north1819", ["north"], [18, 19])):
        accounts.add_user(name, "viewer", PASSWORD)
        accounts.set_scope(name, tenants, stations)
    seen = {name: ids(logged_in(app, name).get("/api/v1/stations").json())
            for name in ("all", "north", "only17", "north1819")}
    assert seen == {"all": [17, 18, 19], "north": [17, 18], "only17": [17], "north1819": [18]}
    store.upsert_station(HeartbeatMessage.model_validate(              # a station whose tenant nobody reported
        {"station_id": 20, "time_us": T0, "station": {"lat_e7": 550000000, "lon_e7": 370000000, "alt_dm": 1500}}))
    assert ids(logged_in(app, "north").get("/api/v1/stations").json()) == [17, 18]
    assert ids(logged_in(app, "all").get("/api/v1/stations").json()) == [17, 18, 19, 20]


def test_events_tracks_and_bearings_are_cut_to_the_account(field):
    accounts, store, app = field
    accounts.add_user("vic", "viewer", PASSWORD)
    accounts.set_scope("vic", [], [17])
    c = logged_in(app, "vic")
    events = c.get("/api/v1/events").json()
    assert [e["system_event_id"] for e in events] == ["E-17-19"]                 # the target its station heard
    assert events[0]["source_station_ids"] == [17] and events[0]["source_event_ids"] == [17001]
    assert events[0]["route_summary"] == ["17:MQTT:0"]
    assert c.get("/api/v1/events/E-19").status_code == 404 and c.get("/api/v1/events/E-18/tracks").status_code == 404
    assert c.get("/api/v1/events/E-17-19").json()["source_station_ids"] == [17]
    assert ids(c.get("/api/v1/bearings").json()) == [17, 17, 17]
    assert c.get("/api/v1/bearings", params={"station_id": 19}).json() == []
    tracks = c.get("/api/v1/tracks").json()
    assert [t["track_id"] for t in tracks] == ["TRK-17-19"] and tracks[0]["stations"] == [17]
    full = c.get("/api/v1/tracks/TRK-17-19").json()
    assert [m["station_id"] for m in full["members"]] == [17]
    assert [p["stations"] for p in full["track_points"]] == [[17], []]        # the fused positions stay, 19 is cut
    assert c.get("/api/v1/tracks/TRK-18-19").status_code == 404
    accounts.add_user("all", "viewer", PASSWORD)
    everyone = logged_in(app, "all")
    assert len(everyone.get("/api/v1/events").json()) == 3 and len(everyone.get("/api/v1/tracks").json()) == 2
    assert everyone.get("/api/v1/events/E-17-19").json()["source_station_ids"] == [17, 19]


def test_replay_and_coverage_show_only_own_stations(field):
    accounts, store, app = field
    accounts.add_user("vic", "viewer", PASSWORD)
    accounts.set_scope("vic", ["north"], [])
    c = logged_in(app, "vic")
    replay = c.get("/api/v1/replay", params={"since_us": T0 - 1, "until_us": T0 + 5_000_000}).json()
    assert ids(replay["stations"]) == [17, 18]
    assert sorted({b["station_id"] for b in replay["bearings"]}) == [17, 18]
    assert sorted(t["track_id"] for t in replay["tracks"]) == ["TRK-17-19", "TRK-18-19"]
    assert all(set(p["stations"]) <= {17, 18} for t in replay["tracks"] for p in t["points"])
    assert c.get("/api/v1/replay", params={"system_event_id": "E-19"}).status_code == 404
    one = c.get("/api/v1/replay", params={"since_us": T0 - 1, "until_us": T0 + 5_000_000,
                                           "station_ids": "17"}).json()
    assert ids(one["stations"]) == [17]
    assert {b["station_id"] for b in one["bearings"]} == {17}
    assert all(set(p["stations"]) <= {17} for t in one["tracks"] for p in t["points"])
    assert c.get("/api/v1/replay", params={"since_us": T0 - 1, "until_us": T0 + 5_000_000,
                                            "station_ids": "17,19"}).status_code == 404
    assert c.get("/api/v1/replay", params={"since_us": T0 - 1, "until_us": T0 + 5_000_000,
                                            "station_ids": "bogus"}).status_code == 422
    sources = c.get("/api/v1/replay/sources").json()
    assert sorted(e["system_event_id"] for e in sources["events"]) == ["E-17-19", "E-18"]
    assert all(set(e["stations"]) <= {17, 18} for e in sources["events"])
    assert c.get("/api/v1/geometry/coverage", params={"station_ids": "17,18", "range_m": 3000}).status_code == 200
    hidden = c.get("/api/v1/geometry/coverage", params={"station_ids": "17,19", "range_m": 3000})
    assert hidden.status_code == 404 and "19" in hidden.json()["detail"]


def test_audio_and_commands_of_other_stations_do_not_exist(field):
    accounts, store, app = field
    accounts.add_user("ops", "operator", PASSWORD)
    accounts.set_scope("ops", [], [17])
    c = logged_in(app, "ops")
    assert c.post("/api/v1/stations/17/audio-request", json={"event_id": 17001}, headers=ORIGIN).status_code == 200
    assert c.post("/api/v1/stations/19/audio-request", json={"event_id": 19001}, headers=ORIGIN).status_code == 404
    assert c.get("/api/v1/stations/19/events/19001/audio").status_code == 404
    assert c.get("/api/v1/stations/19/events/19001/audio/pre.wav").status_code == 404
    assert c.get("/api/v1/stations/17/events/17001/audio").json() == []
    accounts.add_user("eng", "engineer", PASSWORD)
    secret = oa.new_totp_secret()
    accounts.set_totp("eng", secret)
    accounts.set_scope("eng", [], [17])
    e = logged_in(app, "eng", code_now(secret))                          # a limited engineer commands only its stations
    assert e.post("/api/v1/stations/19/network-config", json={"server_host": "example.org"}, headers=ORIGIN).status_code == 404
    assert e.post("/api/v1/stations/19/firmware-update", json={"version": 5}, headers=ORIGIN).status_code == 404


def test_output_api_follows_the_account(field):
    accounts, store, app = field
    accounts.add_user("svc", "service", PASSWORD)
    accounts.set_scope("svc", ["north"], [17])
    c = logged_in(app, "svc")
    assert c.get("/api/v1/alerts/head").json() == {"seq": store.last_alert_seq()}
    page = c.get("/api/v1/alerts").json()
    assert [m["msg_id"] for m in page["messages"]] == ["m0", "m4"]          # north, with station 17
    assert page["messages"][0]["alert"]["stations"] == [{"station_id": 17, "lat": 55.0, "lon": 37.0, "alt_msl_m": 150.0}]
    assert page["next_after_seq"] == 5
    first = c.get("/api/v1/alerts", params={"limit": 1}).json()             # the page is filled past what it drops
    assert [m["msg_id"] for m in first["messages"]] == ["m0"] and first["next_after_seq"] == 1
    rest = c.get("/api/v1/alerts", params={"after_seq": 1, "limit": 1}).json()
    assert [m["msg_id"] for m in rest["messages"]] == ["m4"] and rest["next_after_seq"] == 5
    assert c.get("/api/v1/alerts", params={"tenant": "south"}).status_code == 403
    cookie = {"cookie": f"{oa.COOKIE_NAME}={c.cookies[oa.COOKIE_NAME]}", **ORIGIN}
    with pytest.raises(WebSocketDisconnect) as foreign:
        with c.websocket_connect("/api/v1/alerts/stream?tenant=south", headers=cookie):
            pass
    assert foreign.value.code == 4403
    with c.websocket_connect("/api/v1/alerts/stream?after_seq=0", headers=cookie) as ws:
        assert [ws.receive_json()["msg_id"], ws.receive_json()["msg_id"]] == ["m0", "m4"]
    accounts.add_user("all", "service", PASSWORD)
    everything = logged_in(app, "all").get("/api/v1/alerts").json()["messages"]
    assert len(everything) == 5 and len(everything[0]["alert"]["stations"]) == 2


def test_scope_cuts_messages_as_documented():
    scope = access_scope.Scope(["north"], [17])
    assert scope.alert({"type": "heartbeat", "tenant": None}) is not None
    assert scope.alert({"type": "alert.end", "tenant": "south", "alert": {"stations": [{"station_id": 17}]}}) is None
    assert scope.alert({"type": "mystery", "tenant": "north"}) is None
    assert scope.live({"type": "station", "data": {"station_id": 17}}) is not None
    assert scope.live({"type": "type_update", "data": {"station_id": 19}}) is None
    assert scope.live({"type": "bearings", "station_id": 19}) is None
    cut = scope.live({"type": "track", "stations": [17, 19], "last": point(T0, [17, 19])})
    assert cut["stations"] == [17] and cut["last"]["stations"] == [17]
    assert scope.live({"type": "track", "stations": [18, 19], "last": None}) is None
    assert scope.live({"system_event_id": "SECURITY-1-19", "source_station_ids": [19]}) is None
    assert scope.live({"type": "something new"}) is None                     # undeclared: not to a limited account
    assert access_scope.UNRESTRICTED.live({"type": "something new"}) == {"type": "something new"}


def test_live_stream_follows_scope_and_logout(field, monkeypatch):
    accounts, store, app = field
    monkeypatch.setattr(access_scope, "LIVE_RECHECK_S", 0.05)
    monkeypatch.setattr(station_router, "LIVE_RECHECK_S", 0.05)
    monkeypatch.setenv("ZS_STATION_HTTP_INSECURE_BENCH", "1")
    accounts.add_user("vic", "viewer", PASSWORD)
    accounts.set_scope("vic", [], [17])
    c = logged_in(app, "vic")
    cookie = {"cookie": f"{oa.COOKIE_NAME}={c.cookies[oa.COOKIE_NAME]}", **ORIGIN}
    beat = {"time_us": T0, "station": {"lat_e7": 550000000, "lon_e7": 370000000, "alt_dm": 1500}}
    with c.websocket_connect("/api/v1/stream", headers=cookie) as ws:
        assert c.post("/api/v1/stations/19/heartbeat", json={"station_id": 19, **beat}).status_code == 200
        assert c.post("/api/v1/stations/17/heartbeat", json={"station_id": 17, **beat}).status_code == 200
        assert ws.receive_json()["data"]["station_id"] == 17               # 19 never reaches this account
        accounts.set_disabled("vic", True)                                   # the open stream closes by itself
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(100):
                ws.receive_json()
        assert closed.value.code == 4401


def test_admin_and_engineers_set_who_sees_what(field):
    accounts, store, app = field
    accounts.add_user("vic", "viewer", PASSWORD)
    accounts.add_user("ops", "operator", PASSWORD)
    secrets = {}
    for name, roles in (("eng", "engineer"), ("eng2", "engineer"), ("sec", "admin")):
        accounts.add_user(name, roles, PASSWORD)
        secrets[name] = oa.new_totp_secret()
        accounts.set_totp(name, secrets[name])
    eng = logged_in(app, "eng", code_now(secrets["eng"]))
    assert [a["name"] for a in eng.get("/api/v1/access/accounts").json()] == ["ops", "vic"]   # not admins, engineers, itself
    r = eng.put("/api/v1/access/accounts/vic/scope", json={"tenants": ["north"], "stations": [17]}, headers=ORIGIN)
    assert r.status_code == 200 and r.json()["stations"] == [17] and r.json()["tenants"] == ["north"]
    assert accounts.user("vic")["stations"] == [17]
    assert ids(logged_in(app, "vic").get("/api/v1/stations").json()) == [17]
    assert eng.put("/api/v1/access/accounts/eng2/scope", json={"stations": [17]}, headers=ORIGIN).status_code == 404
    assert eng.put("/api/v1/access/accounts/eng/scope", json={"stations": []}, headers=ORIGIN).status_code == 404
    assert eng.put("/api/v1/access/accounts/vic/scope", json={"tenants": ["North Side"]}, headers=ORIGIN).status_code == 422
    sec = logged_in(app, "sec", code_now(secrets["sec"]))
    assert "eng2" in [a["name"] for a in sec.get("/api/v1/access/accounts").json()]
    assert sec.put("/api/v1/access/accounts/eng2/scope", json={"stations": [17, 18]}, headers=ORIGIN).status_code == 200
    eng2 = logged_in(app, "eng2", oa.totp_code(secrets["eng2"], int(time.time() // oa.TOTP_STEP_S)))
    # a limited engineer gives only what it sees itself, never "all"
    assert eng2.put("/api/v1/access/accounts/ops/scope", json={"stations": [18]}, headers=ORIGIN).status_code == 200
    assert eng2.put("/api/v1/access/accounts/ops/scope", json={"stations": [19]}, headers=ORIGIN).status_code == 403
    assert eng2.put("/api/v1/access/accounts/ops/scope", json={"stations": []}, headers=ORIGIN).status_code == 403
    vic = logged_in(app, "vic")
    assert vic.get("/api/v1/access/accounts").status_code == 403
    assert vic.put("/api/v1/access/accounts/ops/scope", json={"stations": []}, headers=ORIGIN).status_code == 403
    actions = [(r["actor"], r["action"], r["target"]) for r in oa.current_state().audit_records() if r["action"] == "set-scope"]
    assert actions == [("eng", "set-scope", "vic"), ("sec", "set-scope", "eng2"), ("eng2", "set-scope", "ops")]
    assert oa.current_state().audit_verify()[0]


def test_catalog_offers_what_the_manager_sees(field, tmp_path, monkeypatch):
    """The drop-downs of the admin page: every unit of the PKI registry (serial, lot, tenant) plus the stations that
    reported, the tenant of the bridge a station came through winning over its lot; a limited manager gets only what
    it sees itself; nobody without scopes.manage gets the catalog."""
    from pki.registry import Registry
    from station import access_api

    accounts, store, app = field
    monkeypatch.setenv(access_api.PKI_DIR_ENV, str(tmp_path / "pki"))
    registry = Registry(tmp_path / "pki" / "registry.sqlite3")
    registry.add("DIO-EVT-017")                    # reported through the north bridge: north, not its lot's pilot1
    registry.add("DIO-EVT-021")                    # registered, never reported
    accounts.add_user("vic", "viewer", PASSWORD)
    secrets = {}
    for name, roles in (("eng", "engineer"), ("sec", "admin")):
        accounts.add_user(name, roles, PASSWORD)
        secrets[name] = oa.new_totp_secret()
        accounts.set_totp(name, secrets[name])
    eng = logged_in(app, "eng", code_now(secrets["eng"]))
    catalog = eng.get("/api/v1/access/catalog").json()
    assert catalog["tenants"] == ["bench", "north", "pilot1", "pilot2", "south"]
    by_id = {s["station_id"]: s for s in catalog["stations"]}
    assert sorted(by_id) == [17, 18, 19, 21]
    assert by_id[17] == {"station_id": 17, "serial": "DIO-EVT-017", "tenant": "north", "lot": "EVT-LOT-1", "status": "created", "seen": True}
    assert by_id[21] == {"station_id": 21, "serial": "DIO-EVT-021", "tenant": "pilot2", "lot": "EVT-LOT-2", "status": "created", "seen": False}
    assert by_id[19] == {"station_id": 19, "serial": None, "tenant": "south", "lot": None, "status": "seen", "seen": True}
    accounts.set_scope("sec", ["north"], [])      # a manager limited to a tenant chooses only inside it
    sec = logged_in(app, "sec", code_now(secrets["sec"]))
    limited = sec.get("/api/v1/access/catalog").json()
    assert limited["tenants"] == ["north"] and ids(limited["stations"]) == [17, 18]
    assert logged_in(app, "vic").get("/api/v1/access/catalog").status_code == 403
    monkeypatch.setenv(access_api.PKI_DIR_ENV, str(tmp_path / "nowhere"))   # no registry: only what reported
    assert ids(eng.get("/api/v1/access/catalog").json()["stations"]) == [17, 18, 19]


def test_bridge_records_the_tenant_of_a_station(tmp_path: Path):
    store = EventStore(tmp_path / "zs.sqlite3")
    command = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 17001})
    payload = encode_command_ack(CommandAck(17, command.command_id, 0, 1))
    assert process_message("zs/v1/pilot/17/ack", payload, "pilot", True, event_store=store) == "acked"
    assert store.station_tenants() == {17: "pilot"}
    store.note_station_tenant(17, "west")                                    # a station moved to another bridge
    assert store.station_tenants() == {17: "west"}

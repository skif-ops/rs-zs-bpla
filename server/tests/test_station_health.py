"""The stations page (station/health.py, station/health_api.py): a station's state from its silence, what its last
heartbeat says needs attention, the registry's units that never reported, the summary, and the page's data cut to
what the account sees."""
import time
from pathlib import Path

import pytest

from station import health
from station.schemas import HeartbeatMessage
from station.store import EventStore
from tests.test_access_scope import PASSWORD, field, ids, logged_in  # noqa: F401

T = health.Thresholds()
NOW = 1_900_000_000_000_000


def hb(**extra):
    base = {"station_id": 17, "time_us": NOW, "station": {"lat_e7": 550000000, "lon_e7": 370000000, "alt_dm": 1500},
            "power": {"battery_pct": 80, "battery_mv": 4000, "solar_mv": 5000, "temperature_c10": 200},
            "gnss": {"fix_type": 3, "satellites": 9, "hdop_x100": 100, "pps_ok": True, "time_trust": "GNSS_TIME_TRUSTED",
                     "position_trust": "CONFIGURED_OK"},
            "route": {"transport": "LTE", "rssi_dbm": -90, "snr_db10": 80}, "firmware_ver": "1.2.0", "model_ver": "m3",
            "detector": {"uptime_s": 3600, "reset_cause": "POWER", "fw_version": 7, "fw_state": "IDLE", "net_state": "STABLE"}}
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return HeartbeatMessage.model_validate(base).model_dump()


def codes(problems):
    return [p["code"] for p in problems]


def test_thresholds_come_from_the_environment_with_sane_fallbacks():
    assert health.Thresholds.from_env({}) == health.Thresholds(7 * 3600, 13 * 3600, 20)
    t = health.Thresholds.from_env({health.LATE_ENV: "3600", health.LOST_ENV: "7200", health.BATTERY_LOW_ENV: "30"})
    assert (t.late_s, t.lost_s, t.battery_low_pct) == (3600, 7200, 30)
    t = health.Thresholds.from_env({health.LATE_ENV: "abc", health.LOST_ENV: "10", health.BATTERY_LOW_ENV: "150"})
    assert t == health.Thresholds()                                      # nonsense: the defaults
    t = health.Thresholds.from_env({health.LATE_ENV: "36000", health.LOST_ENV: "3600"})
    assert t.lost_s == t.late_s == 36000                                 # lost never comes before late


def test_silence_decides_the_state_and_a_clean_heartbeat_raises_nothing():
    assert health.assess(hb(), NOW - 6 * 3600 * 10**6, NOW, T)["state"] == "online"
    assert health.assess(hb(), NOW - 8 * 3600 * 10**6, NOW, T)["state"] == "late"
    assert health.assess(hb(), NOW - 14 * 3600 * 10**6, NOW, T)["state"] == "lost"
    assert health.assess(None, None, NOW, T) == {"state": "never", "level": "ok", "silence_s": None, "problems": []}
    clean = health.assess(hb(), NOW - 60 * 10**6, NOW, T)
    assert clean["level"] == "ok" and clean["problems"] == [] and clean["silence_s"] == 60.0
    assert health.assess(hb(), NOW - 8 * 3600 * 10**6, NOW, T)["level"] == "warn"
    assert health.assess(hb(), NOW - 14 * 3600 * 10**6, NOW, T)["level"] == "alarm"


def test_problems_of_the_last_heartbeat_with_their_levels():
    found = health.problems(hb(power={"battery_pct": 15}), T)
    assert codes(found) == ["battery_low"] and found[0]["level"] == "warn" and "15 %" in found[0]["text"]
    assert health.problems(hb(power={"battery_pct": 9}), T)[0]["level"] == "alarm"
    assert codes(health.problems(hb(power={"temperature_c10": 650}), T)) == ["temperature"]
    assert codes(health.problems(hb(self_test_ok=False, fault_flags=["mic2"]), T)) == ["self_test", "fault:mic2"]
    found = health.problems(hb(detector={"selftest_failed_tests": 1 << 4 | 1 << 7}), T)
    assert codes(found) == ["selftest_failed"] and "захват микрофонов" in found[0]["text"] and "GNSS PPS" in found[0]["text"]
    assert codes(health.problems(hb(gnss={"jam": True, "spoof": True}), T)) == ["gnss_spoof", "gnss_jam"]
    assert codes(health.problems(hb(gnss={"position_trust": "CONFIGURED_SUSPECT"}), T)) == ["position_suspect"]
    assert codes(health.problems(hb(gnss={"position_warn": True, "position_delta_m": 12}), T)) == ["position_warn"]
    assert codes(health.problems(hb(gnss={"time_trust": "UNSYNCED"}), T)) == ["time_unsynced"]
    assert codes(health.problems(hb(gnss={"time_trust": "GNSS_TIME_SUSPECT"}), T)) == ["time_suspect"]
    # a station waking from the duty cycle: holdover and no fix yet are information, not alarms
    found = health.problems(hb(gnss={"fix_type": 0, "time_trust": "HOLDOVER"}), T)
    assert codes(found) == ["time_holdover", "gnss_no_fix"] and {p["level"] for p in found} == {"info"}
    assert codes(health.problems(hb(detector={"reset_cause": "IWDG", "watchdog_missed_tasks": 2}), T)) == ["watchdog_reset", "watchdog_missed"]
    found = health.problems(hb(detector={"outbox_pending": 3}), T)
    assert codes(found) == ["outbox"] and found[0]["level"] == "info"
    assert health.problems(hb(detector={"outbox_pending": 12}), T)[0]["level"] == "warn"
    assert codes(health.problems(hb(detector={"fw_state": "ROLLED_BACK"}), T)) == ["fw_rolled_back"]
    assert health.problems(hb(detector={"fw_state": "TRIAL"}), T)[0] == {"code": "fw_update", "level": "info", "text": "обновление прошивки: TRIAL"}
    assert codes(health.problems(hb(detector={"net_state": "ROLLED_BACK"}), T)) == ["net_rolled_back"]
    assert health.problems(hb(detector={"net_state": "ACCEPTED"}), T)[0]["level"] == "info"
    # worst first, and the row's level follows the worst problem
    found = health.problems(hb(power={"battery_pct": 15}, detector={"fw_state": "TRIAL"}, self_test_ok=False), T)
    assert [p["level"] for p in found] == ["alarm", "warn", "info"]
    assert health.assess(hb(self_test_ok=False), NOW - 60 * 10**6, NOW, T)["level"] == "alarm"


def test_row_and_summary():
    r = health.row(17, hb(), NOW - 120 * 10**6, NOW, {"serial": "DIO-EVT-017", "lot": "EVT-LOT-1", "status": "created",
                                                     "tenant": "pilot1"}, "north", NOW, T)
    assert (r["station_id"], r["serial"], r["lot"], r["tenant"], r["state"], r["silence_s"]) == (17, "DIO-EVT-017", "EVT-LOT-1", "north", "online", 120.0)
    assert r["power"] == {"battery_pct": 80, "battery_mv": 4000, "solar_mv": 5000, "temperature_c": 20.0,
                          "battery_current_ma": None, "battery_power_mw": None}
    assert r["gnss"]["hdop"] == 1.0 and r["route"]["snr_db"] == 8.0 and r["position"]["lat"] == 55.0
    assert r["versions"]["fw_version"] == 7 and r["detector"]["uptime_s"] == 3600 and r["cellular"] is None
    assert r["heartbeat"]["station_id"] == 17
    never = health.row(21, None, None, None, {"serial": "DIO-EVT-021", "lot": "EVT-LOT-2", "status": "created", "tenant": "pilot2"}, None, NOW, T)
    assert (never["state"], never["tenant"], never["heartbeat"], never["position"], never["power"]["battery_pct"]) == ("never", "pilot2", None, None, None)
    rows = [r, never, health.row(18, hb(power={"battery_pct": 10}, gnss={"jam": True}), NOW - 8 * 3600 * 10**6, NOW, None, "north", NOW, T),
            health.row(19, hb(detector={"fw_state": "TRIAL"}), NOW - 14 * 3600 * 10**6, NOW, None, "south", NOW, T)]
    assert health.summary(rows) == {"total": 4, "online": 1, "late": 1, "lost": 1, "never": 1, "alarm": 2, "warn": 0,
                                    "battery_low": 1, "gnss": 1, "updating": 1}


def test_received_time_is_the_server_clock_and_old_rows_fall_back(tmp_path: Path):
    store = EventStore(tmp_path / "zs.sqlite3")
    before = int(time.time() * 1e6)
    store.upsert_station(HeartbeatMessage.model_validate(hb(time_us=NOW)))      # the station's clock is far away
    rows = store.station_health_rows()
    assert len(rows) == 1 and rows[0]["updated_us"] == NOW and before <= rows[0]["received_us"] <= int(time.time() * 1e6)
    with store._conn() as c:
        c.execute("UPDATE stations SET received_us=0")                          # a row from before the column
    assert store.station_health_rows()[0]["received_us"] == NOW
    assert "imsi" not in str(store.station_health_rows()[0]["heartbeat"].get("cellular"))


def test_the_page_data_follows_the_account(field, tmp_path, monkeypatch):
    from pki.registry import Registry
    from station import pki_registry

    accounts, store, app = field
    monkeypatch.setenv(pki_registry.PKI_DIR_ENV, str(tmp_path / "pki"))
    registry = Registry(tmp_path / "pki" / "registry.sqlite3")
    registry.add("DIO-EVT-017")
    registry.add("DIO-EVT-021")                                               # registered, never reported
    for name, tenants in (("all", []), ("north", ["north"])):
        accounts.add_user(name, "viewer", PASSWORD)
        accounts.set_scope(name, tenants, [])
    data = logged_in(app, "all").get("/api/v1/stations/health").json()
    assert set(data) == {"now_us", "thresholds", "summary", "stations"} and data["thresholds"]["late_s"] == 7 * 3600
    by_id = {s["station_id"]: s for s in data["stations"]}
    assert sorted(by_id) == [17, 18, 19, 21]
    assert by_id[17]["serial"] == "DIO-EVT-017" and by_id[17]["tenant"] == "north" and by_id[17]["state"] == "online"
    assert by_id[21]["state"] == "never" and by_id[21]["tenant"] == "pilot2" and by_id[21]["heartbeat"] is None
    assert data["summary"]["total"] == 4 and data["summary"]["never"] == 1 and data["summary"]["online"] == 3
    limited = logged_in(app, "north").get("/api/v1/stations/health").json()
    assert ids(limited["stations"]) == [17, 18] and limited["summary"]["total"] == 2
    page = logged_in(app, "north").get("/stations")
    assert page.status_code == 200 and 'id="st-table"' in page.text and "/static/js/stations.js" in page.text
    assert 'href="/stations"' in page.text and 'aria-current="page"' in page.text   # the menu marks the open page

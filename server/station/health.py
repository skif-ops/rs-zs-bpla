"""The state of every station for the monitoring page (``/stations``) and ``GET /api/v1/stations/health``.

A station reports a heartbeat every ``heartbeat_period_s`` (6 h in the duty cycle, ICD addendum D; every 60 s while a
session is open after an event), so its silence is measured against that period: ``online`` within ``ZS_STATION_LATE_S``
(7 h: one period plus an hour of margin), ``late`` until ``ZS_STATION_LOST_S`` (13 h: two periods), ``lost`` after.  A
unit of the PKI registry that never reported is ``never``.  Silence is measured by the server time the heartbeat
arrived (the station's own clock may be in holdover).

The last heartbeat is read for what needs attention: battery below ``ZS_STATION_BATTERY_LOW_PCT`` (20), a failed
self-test, fault flags, GNSS jamming or spoofing, a suspect position or time, a watchdog reset, undelivered messages,
a rolled-back firmware or network configuration, a temperature outside the hardware range.  Each is a problem with a
level: ``alarm`` (the station needs a visit or a decision), ``warn`` (watch it), ``info`` (an update in progress, a
GNSS that has no fix at the moment of the heartbeat, time in holdover, a few undelivered messages: normal for a
station that wakes from the duty cycle).  The row's level is the worst of its silence and its problems, so the page
sorts by it.  The customer's priority is few false alarms: weak signal, dropped detector windows and a missing PPS
are shown as values, not raised.
"""
from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

LATE_ENV = "ZS_STATION_LATE_S"
LOST_ENV = "ZS_STATION_LOST_S"
BATTERY_LOW_ENV = "ZS_STATION_BATTERY_LOW_PCT"
DEFAULT_LATE_S = 7 * 3600
DEFAULT_LOST_S = 13 * 3600
DEFAULT_BATTERY_LOW_PCT = 20
TEMPERATURE_MIN_C, TEMPERATURE_MAX_C = -30.0, 60.0      # EVT hardware operating range
STATES = ("online", "late", "lost", "never")
LEVELS = ("ok", "info", "warn", "alarm")                   # worst last
STATE_LEVEL = {"online": "ok", "late": "warn", "lost": "alarm", "never": "ok"}
SELFTEST_NAMES = {1: "питание (INA226)", 4: "захват микрофонов", 5: "выравнивание микрофонов", 7: "GNSS PPS",
                  12: "часы RTC (LSE)"}                     # firmware zs_selftest_id_t; others are shown by number


@dataclass(frozen=True)
class Thresholds:
    late_s: int = DEFAULT_LATE_S
    lost_s: int = DEFAULT_LOST_S
    battery_low_pct: int = DEFAULT_BATTERY_LOW_PCT

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Thresholds":
        env = os.environ if env is None else env

        def read(name: str, default: int, low: int, high: int) -> int:
            try:
                value = int(env.get(name, ""))
            except (TypeError, ValueError):
                return default
            return value if low <= value <= high else default

        late = read(LATE_ENV, DEFAULT_LATE_S, 60, 30 * 86400)
        lost = read(LOST_ENV, DEFAULT_LOST_S, 60, 60 * 86400)
        return cls(late, max(lost, late), read(BATTERY_LOW_ENV, DEFAULT_BATTERY_LOW_PCT, 0, 100))

    def as_dict(self) -> dict[str, int]:
        return {"late_s": self.late_s, "lost_s": self.lost_s, "battery_low_pct": self.battery_low_pct}


def silence_state(silence_s: float, t: Thresholds) -> str:
    if silence_s < t.late_s:
        return "online"
    return "late" if silence_s < t.lost_s else "lost"


def _problem(code: str, level: str, text: str) -> dict[str, str]:
    return {"code": code, "level": level, "text": text}


def problems(hb: Mapping[str, Any], t: Thresholds) -> list[dict[str, str]]:
    """What the last heartbeat says needs attention, worst first."""
    out: list[dict[str, str]] = []
    power = hb.get("power") or {}
    gnss = hb.get("gnss") or {}
    detector = hb.get("detector") or {}
    pct = power.get("battery_pct")
    if isinstance(pct, int) and pct < t.battery_low_pct:
        out.append(_problem("battery_low", "alarm" if pct < t.battery_low_pct / 2 else "warn", f"заряд батареи {pct} %"))
    temperature = power.get("temperature_c10")
    if isinstance(temperature, int) and not TEMPERATURE_MIN_C <= temperature / 10 <= TEMPERATURE_MAX_C:
        out.append(_problem("temperature", "warn", f"температура {temperature / 10:.0f} °C"))
    if hb.get("self_test_ok") is False:
        out.append(_problem("self_test", "alarm", "самотест не пройден"))
    for flag in hb.get("fault_flags") or []:
        out.append(_problem(f"fault:{flag}", "alarm", f"неисправность: {flag}"))
    failed = detector.get("selftest_failed_tests") or 0
    if isinstance(failed, int) and failed:
        names = [SELFTEST_NAMES.get(i, f"№{i}") for i in range(16) if failed >> i & 1]
        out.append(_problem("selftest_failed", "alarm", "не пройдены самотесты: " + ", ".join(names)))
    if gnss.get("spoof"):
        out.append(_problem("gnss_spoof", "alarm", "GNSS: подмена сигнала"))
    if gnss.get("jam"):
        out.append(_problem("gnss_jam", "alarm", "GNSS: помеха"))
    if gnss.get("position_suspect") or gnss.get("position_trust") in ("CONFIGURED_SUSPECT", "REVALIDATION_REQUIRED"):
        out.append(_problem("position_suspect", "alarm", "положение станции сомнительно"))
    elif gnss.get("position_warn") or gnss.get("position_trust") == "CONFIGURED_WARN":
        out.append(_problem("position_warn", "warn", f"положение ушло на {gnss.get('position_delta_m', 0)} м"))
    time_trust = gnss.get("time_trust")
    if gnss.get("time_suspect") or time_trust == "GNSS_TIME_SUSPECT":
        out.append(_problem("time_suspect", "alarm", "время станции сомнительно"))
    elif time_trust == "UNSYNCED":
        out.append(_problem("time_unsynced", "alarm", "время станции не синхронизировано"))
    elif gnss.get("time_holdover") or time_trust == "HOLDOVER":
        out.append(_problem("time_holdover", "info", "время в режиме удержания (GNSS выключен или без фиксации)"))
    if gnss.get("fix_type", 1) == 0 and hb.get("gnss") is not None:
        out.append(_problem("gnss_no_fix", "info", "нет фиксации GNSS на момент heartbeat"))
    if detector.get("reset_cause") in ("IWDG", "WWDG"):
        out.append(_problem("watchdog_reset", "warn", "последняя перезагрузка по watchdog"))
    missed = detector.get("watchdog_missed_tasks") or 0
    if isinstance(missed, int) and missed > 0:
        out.append(_problem("watchdog_missed", "warn", f"watchdog: пропущено задач {missed}"))
    pending = detector.get("outbox_pending") or 0
    if isinstance(pending, int) and pending > 0:
        out.append(_problem("outbox", "warn" if pending >= 10 else "info", f"не доставлено сообщений: {pending}"))
    fw_state = detector.get("fw_state")
    if fw_state == "ROLLED_BACK":
        out.append(_problem("fw_rolled_back", "alarm", "прошивка откатилась на прежнюю"))
    elif fw_state in ("DOWNLOADING", "INSTALL_PENDING", "TRIAL"):
        out.append(_problem("fw_update", "info", f"обновление прошивки: {fw_state}"))
    net_state = detector.get("net_state")
    if net_state == "ROLLED_BACK":
        out.append(_problem("net_rolled_back", "alarm", "сетевая настройка откатилась"))
    elif net_state in ("ACCEPTED", "TRIAL"):
        out.append(_problem("net_trial", "info", f"сетевая настройка на проверке: {net_state}"))
    out.sort(key=lambda p: -LEVELS.index(p["level"]))
    return out


def worst(levels: list[str]) -> str:
    return max(levels, key=LEVELS.index) if levels else "ok"


def assess(hb: Mapping[str, Any] | None, received_us: int | None, now_us: int, t: Thresholds) -> dict[str, Any]:
    """``state``, ``level``, ``silence_s`` and ``problems`` of one station."""
    if hb is None or not received_us:
        return {"state": "never", "level": "ok", "silence_s": None, "problems": []}
    silence_s = max(0.0, (now_us - received_us) / 1e6)
    state = silence_state(silence_s, t)
    found = problems(hb, t)
    return {"state": state, "level": worst([STATE_LEVEL[state]] + [p["level"] for p in found]),
            "silence_s": round(silence_s, 1), "problems": found}


def _opt(value: Any, scale: float | None = None) -> Any:
    if value is None or scale is None:
        return value
    return round(value / scale, 2)


def row(station_id: int, hb: Mapping[str, Any] | None, received_us: int | None, updated_us: int | None,
        registry: Mapping[str, Any] | None, tenant: str | None, now_us: int, t: Thresholds) -> dict[str, Any]:
    """One station of the page: identity, state and the readings of the last heartbeat (None where unknown)."""
    out: dict[str, Any] = {"station_id": station_id, "serial": (registry or {}).get("serial"),
                           "lot": (registry or {}).get("lot"), "registry_status": (registry or {}).get("status"),
                           "tenant": tenant or (registry or {}).get("tenant"), "received_us": received_us,
                           "time_us": updated_us, **assess(hb, received_us, now_us, t)}
    hb = hb or {}
    power, gnss, route, cellular, detector, station = (hb.get(k) or {} for k in ("power", "gnss", "route", "cellular",
                                                                                   "detector", "station"))
    out["power"] = {"battery_pct": power.get("battery_pct"), "battery_mv": power.get("battery_mv"),
                    "solar_mv": power.get("solar_mv"), "temperature_c": _opt(power.get("temperature_c10"), 10),
                    "battery_current_ma": power.get("battery_current_ma"), "battery_power_mw": power.get("battery_power_mw")}
    out["gnss"] = {"fix_type": gnss.get("fix_type"), "satellites": gnss.get("satellites"),
                   "hdop": _opt(gnss.get("hdop_x100"), 100), "pps_ok": gnss.get("pps_ok"),
                   "time_trust": gnss.get("time_trust"), "position_trust": gnss.get("position_trust"),
                   "jam": gnss.get("jam"), "spoof": gnss.get("spoof")}
    out["route"] = {"transport": route.get("transport"), "rssi_dbm": route.get("rssi_dbm"),
                    "snr_db": _opt(route.get("snr_db10"), 10), "hop_count": route.get("hop_count")}
    out["cellular"] = {"registered_operator": cellular.get("registered_operator"), "apn": cellular.get("apn"),
                       "access_technology": cellular.get("access_technology"),
                       "imsi_redacted": cellular.get("imsi_redacted"), "iccid_redacted": cellular.get("iccid_redacted")} if cellular else None
    out["versions"] = {"firmware_ver": hb.get("firmware_ver"), "model_ver": hb.get("model_ver"),
                       "hardware_rev": hb.get("hardware_rev"), "fw_version": detector.get("fw_version"),
                       "fw_state": detector.get("fw_state"), "fw_other_version": detector.get("fw_other_version"),
                       "params_version": detector.get("params_version"),
                       "net_config_version": detector.get("net_config_version"), "net_state": detector.get("net_state"),
                       "net_failed_version": detector.get("net_failed_version"),
                       "command_key_id": detector.get("command_key_id")}
    out["detector"] = {"uptime_s": detector.get("uptime_s"), "boot_id": detector.get("boot_id"),
                       "reset_cause": detector.get("reset_cause"), "watchdog_missed_tasks": detector.get("watchdog_missed_tasks"),
                       "selftest_failed_tests": detector.get("selftest_failed_tests"), "outbox_pending": detector.get("outbox_pending"),
                       "windows": detector.get("windows"), "windows_dropped": detector.get("windows_dropped"),
                       "events_emitted": detector.get("events_emitted"), "events_refused": detector.get("events_refused"),
                       "presence_level": detector.get("presence_level"), "window_max_ms": detector.get("window_max_ms")}
    out["position"] = {"lat": _opt(station.get("lat_e7"), 1e7), "lon": _opt(station.get("lon_e7"), 1e7),
                       "alt_m": _opt(station.get("alt_dm"), 10), "accuracy_m": station.get("pos_accuracy_m"),
                       "source": station.get("position_source"), "altitude_source": station.get("altitude_source")} if station else None
    out["self_test_ok"] = hb.get("self_test_ok")
    out["fault_flags"] = list(hb.get("fault_flags") or [])
    out["heartbeat"] = dict(hb) if hb else None
    return out


def summary(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    """The counters of the page's header: stations by state and by what needs attention."""
    out = {"total": len(rows), **{s: 0 for s in STATES}, "alarm": 0, "warn": 0, "battery_low": 0, "gnss": 0, "updating": 0}
    for r in rows:
        out[r["state"]] += 1
        if r["level"] == "alarm":
            out["alarm"] += 1
        elif r["level"] == "warn":
            out["warn"] += 1
        codes = {p["code"] for p in r["problems"]}
        out["battery_low"] += "battery_low" in codes
        out["gnss"] += any(c.startswith(("gnss_", "position_", "time_")) for c in codes)
        out["updating"] += any(c in ("fw_update", "net_trial") for c in codes)
    return out


def report(store, scope, registry_rows: list[Mapping[str, Any]], now_us: int | None = None,
           t: Thresholds | None = None) -> dict[str, Any]:
    """The page's data for one account: its stations (reported, or registered and never seen), the summary, the
    thresholds and the server time the states were judged at."""
    t = t or Thresholds.from_env()
    now_us = int(time.time() * 1e6) if now_us is None else now_us
    tenants = store.station_tenants()
    registry = {int(r["station_id"]): r for r in registry_rows}
    seen = {int(r["station_id"]): r for r in store.station_health_rows()}
    rows = []
    for sid in sorted(set(seen) | set(registry)):
        if not scope.station(sid):
            continue
        hb = seen.get(sid)
        rows.append(row(sid, hb["heartbeat"] if hb else None, hb["received_us"] if hb else None,
                        hb["updated_us"] if hb else None, registry.get(sid), tenants.get(sid), now_us, t))
    return {"now_us": now_us, "thresholds": t.as_dict(), "summary": summary(rows), "stations": rows}

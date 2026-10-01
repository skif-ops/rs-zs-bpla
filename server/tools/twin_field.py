#!/usr/bin/env python3
"""Field of station twins: several stations hear one target, Muhoed fuses them (the real server path).

Every station is its own zs_station_twin process (the portable station firmware on the host) in field mode: the same
target flies a straight line over all of them, each hears it with the sound delay and level of its own range, finds
its position by its GNSS receiver (or its installation record) and publishes over its own server-twin link.  The
publishes of all stations are then fed, in wall-time order, through the bridge path of the server
(station.mqtt_bridge.process_message -> EventStore + StationFusionService): detections, bearing batches, heartbeats,
fused tracks, alerts.  The truth of the run (dioneya.trial/1) goes through the acceptance metrics
(station/acceptance.py), so the run ends with the same report as a field trial.

    python tools/twin_field.py --out /tmp/field \\
        --station 17:0,0 --station 18:1200,0 --station 19:600,1000:installed \\
        --target=-2500,2200,200,45,-10,0 --seconds 180

The output directory holds zs_bpla.sqlite3 (copy it to server/data/ to open the run on the «Сопровождение» page), trial.json,
report.json / report.md and the twin logs.  The field origin is 55 N 37 E, 150 m MSL (firmware/twin/station_twin.c);
coordinates are metres east, north and up of it.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_ROOT.parent
sys.path.insert(0, str(SERVER_ROOT))

TWIN = Path(os.environ.get("ZS_STATION_TWIN", REPO_ROOT / "firmware" / "build" / "zs_station_twin"))
SERVER_CMD = f"{sys.executable} -m twin.twin_server"
LAT0, LON0, ALT0 = 55.0, 37.0, 150.0                  # field origin, as FIELD_LAT0/LON0/ALT0 of the twin
M_PER_DEG = 111320.0
WALL0_US = 1_800_000_000_000_000                     # the twins' wall clock at scene time 0
TENANT = "pilot1"


@dataclass(frozen=True)
class FieldStation:
    station_id: int
    enu: tuple[float, float, float]
    installed: bool = False


def parse_station(text: str) -> FieldStation:
    """ID:E,N[,U][:installed]"""
    parts = text.split(":")
    if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != "installed"):
        raise argparse.ArgumentTypeError("station: ID:E,N[,U][:installed]")
    xyz = [float(v) for v in parts[1].split(",")]
    if len(xyz) not in (2, 3):
        raise argparse.ArgumentTypeError("station position: E,N[,U] in metres")
    return FieldStation(int(parts[0]), (xyz[0], xyz[1], xyz[2] if len(xyz) == 3 else 0.0), len(parts) == 3)


def geodetic(e: float, n: float, u: float) -> tuple[float, float, float]:
    return LAT0 + n / M_PER_DEG, LON0 + e / (M_PER_DEG * math.cos(math.radians(LAT0))), ALT0 + u


def as_targets(target) -> list[tuple[float, ...]]:
    """One target (x0,y0,z0,vx,vy,vz[,f0]) or a list of them (up to three fly at once)."""
    return [tuple(target)] if target and not isinstance(target[0], (tuple, list)) else [tuple(t) for t in target]


def target_at(target: tuple[float, ...], t: float) -> tuple[float, float, float]:
    return tuple(target[k] + target[3 + k] * t for k in range(3))


def run_twins(stations: list[FieldStation], target: tuple[float, ...], seconds: int, out: Path, *, seed: int = 1,
              sound: str | None = None, extra: list[str] | None = None) -> dict[int, str]:
    """All stations at once, each with its own server twin on the pipe; returns the twin logs."""
    procs = {}
    for st in stations:
        args = [str(TWIN), "--seconds", str(seconds), "--seed", str(seed + st.station_id), "--station-id", str(st.station_id),
                "--pos", ",".join(f"{v:g}" for v in st.enu),
                *[a for t in as_targets(target) for a in ("--world", ",".join(f"{v:g}" for v in t))],
                "--log-uplink", str(out / f"uplink_{st.station_id}.log"), "--server", SERVER_CMD, *(extra or [])]
        if st.installed:
            args.append("--installed")
        if sound:
            args += ["--world-sound", sound]
        log = open(out / f"twin_{st.station_id}.log", "w")
        procs[st.station_id] = (subprocess.Popen(args, cwd=SERVER_ROOT, stdout=log, stderr=subprocess.STDOUT, text=True), log)
    logs = {}
    for sid, (proc, log) in procs.items():
        code = proc.wait(timeout=3600)
        log.close()
        logs[sid] = (out / f"twin_{sid}.log").read_text()
        if code != 0:
            raise SystemExit(f"twin of station {sid} exited with {code}:\n{logs[sid][-3000:]}")
    return logs


def ingest(stations: list[FieldStation], out: Path) -> tuple[object, collections.Counter]:
    """Every publish of every station, in wall-time order, through the bridge into a fresh database."""
    from station.mqtt_bridge import process_message
    from station.service import StationFusionService
    from station.store import EventStore

    db = out / "zs_bpla.sqlite3"
    for f in out.glob("zs_bpla.sqlite3*"):
        f.unlink()
    store = EventStore(db)
    service = StationFusionService(store)
    rows = []
    for st in stations:
        for line in (out / f"uplink_{st.station_id}.log").read_text().splitlines():
            t, topic, payload = line.split()
            rows.append((int(t), st.station_id, topic, bytes.fromhex(payload)))
    rows.sort(key=lambda r: (r[0], r[1]))
    results = collections.Counter()
    for _, _, topic, payload in rows:
        results[(topic.rsplit("/", 1)[1], process_message(topic, payload, TENANT, True, event_store=store, fusion_service=service))] += 1
    return store, results


def write_trial(stations: list[FieldStation], target: tuple[float, ...], seconds: int, target_class: str, out: Path,
                with_positions: bool = False) -> Path:
    """The truth: the target every second, the stations (positions only on request: the database has them).  The
    track starts a minute before scene time 0: the sound heard at the start left the target up to ~15 s earlier."""
    targets = as_targets(target)
    passes = []
    for i, tg in enumerate(targets, 1):
        track = []
        for t in range(-60, seconds + 1):
            lat, lon, alt = geodetic(*target_at(tg, t))
            track.append({"time": WALL0_US + t * 1_000_000, "lat": lat, "lon": lon, "alt_msl_m": alt})
        passes.append({"pass_id": f"P{i}", "class": target_class, "track": track})
    st_rows = []
    for st in stations:
        row = {"station_id": st.station_id}
        if with_positions:
            row["lat"], row["lon"], row["alt_msl_m"] = geodetic(*st.enu)
        st_rows.append(row)
    if len(targets) == 1:
        name = f"Поле двойников: {len(stations)} станции, цель {math.hypot(*targets[0][3:6]):.0f} м/с на {targets[0][2]:.0f} м"
    else:
        name = f"Поле двойников: {len(stations)} станции, {len(targets)} цели одновременно"
    doc = {"format": "dioneya.trial/1", "name": name,
           "window": {"since": WALL0_US, "until": WALL0_US + (seconds + 20) * 1_000_000},
           "stations": st_rows, "passes": passes}
    path = out / "trial.json"
    path.write_text(json.dumps(doc, ensure_ascii=False))
    return path


def report(store, trial_path: Path, out: Path, *, max_range_m: float, assoc_range_m: float) -> dict:
    from station.acceptance import Criteria, evaluate, load_trial, markdown

    trial = load_trial(trial_path, store)
    result = evaluate(store, trial, Criteria(max_range_m=max_range_m, assoc_range_m=assoc_range_m))
    (out / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    (out / "report.md").write_text(markdown(result))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--station", type=parse_station, action="append", required=True, help="ID:E,N[,U][:installed]")
    ap.add_argument("--target", required=True, action="append",
                    help="x0,y0,z0,vx,vy,vz[,f0]: metres and m/s in the field frame at scene time 0, the synthetic source's "
                         "fundamental in Hz (default 185); repeat for up to three targets at once")
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--class", dest="target_class", default="ELECTRIC_UAV",
                    help="the truth class of the sound (the synthetic source is an electric multirotor)")
    ap.add_argument("--sound", help="WAV recording of the target (PCM16) instead of the synthetic source")
    ap.add_argument("--max-range", type=float, default=5000.0)
    ap.add_argument("--assoc-range", type=float, default=6000.0)
    args = ap.parse_args(argv)
    target = [tuple(float(v) for v in t.split(",")) for t in args.target]
    if len(target) > 3 or any(len(t) not in (6, 7) for t in target):
        ap.error("--target needs six numbers (seven with f0), at most three targets")
    if not TWIN.exists():
        ap.error(f"{TWIN} not built (cmake --build firmware/build --target zs_station_twin, or set ZS_STATION_TWIN)")
    args.out.mkdir(parents=True, exist_ok=True)
    run_twins(args.station, target, args.seconds, args.out, seed=args.seed, sound=args.sound)
    store, results = ingest(args.station, args.out)
    result = report(store, write_trial(args.station, target, args.seconds, args.target_class, args.out), args.out,
                    max_range_m=args.max_range, assoc_range_m=args.assoc_range)
    print("bridge:", dict(results))
    for t in store.list_tracks():
        print(f"track {t['track_id']}: stations {t['stations']}, {t['points']} points")
    print((args.out / "report.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

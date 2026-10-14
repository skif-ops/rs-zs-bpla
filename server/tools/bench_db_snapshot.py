#!/usr/bin/env python3
"""Print a read-only JSON snapshot of Muhoed event counts and virtual station IDs."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

INTERESTING = (
    "stations",
    "detections",
    "bearings",
    "fused_tracks",
    "track_points",
    "system_events",
    "alert_episodes",
    "mqtt_detection_ingress",
    "security_events",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    uri = f"file:{args.db.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts = {}
    bench_counts = {}
    virtual_by_station = {}
    for table in INTERESTING:
        if table not in tables:
            continue
        counts[table] = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if "station_id" in columns:
            bench_counts[table] = connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE station_id BETWEEN 9001 AND 9040'
            ).fetchone()[0]
            virtual_by_station[table] = [
                {"station_id": row[0], "count": row[1]}
                for row in connection.execute(
                    f'SELECT station_id, COUNT(*) FROM "{table}" '
                    'WHERE station_id BETWEEN 9001 AND 9040 GROUP BY station_id ORDER BY station_id'
                )
            ]
    station_ids = []
    if "stations" in tables:
        columns = {row[1] for row in connection.execute('PRAGMA table_info("stations")')}
        if "station_id" in columns:
            station_ids = [row[0] for row in connection.execute(
                'SELECT station_id FROM "stations" WHERE station_id BETWEEN 9001 AND 9040 ORDER BY station_id'
            )]
    recent_tracks = []
    if "fused_tracks" in tables:
        for row in connection.execute(
            "SELECT * FROM fused_tracks ORDER BY first_time_us DESC LIMIT 20"
        ):
            item = dict(row)
            item["stations"] = json.loads(item["stations"])
            recent_tracks.append(item)
    episodes = []
    if "alert_episodes" in tables:
        for row in connection.execute(
            "SELECT * FROM alert_episodes ORDER BY started_us DESC LIMIT 10"
        ):
            item = dict(row)
            item["stations"] = json.loads(item["stations"])
            item["class"] = json.loads(item["class"])
            episodes.append(item)
    recent_alerts = []
    if "alert_outbox" in tables:
        for row in connection.execute(
            "SELECT seq, message FROM alert_outbox ORDER BY seq DESC LIMIT 20"
        ):
            recent_alerts.append({"seq": row["seq"], **json.loads(row["message"])})
    print(json.dumps({
        "database": str(args.db),
        "counts": counts,
        "virtual_station_counts": bench_counts,
        "virtual_by_station": virtual_by_station,
        "virtual_station_ids": station_ids,
        "recent_tracks": recent_tracks,
        "alert_episodes": episodes,
        "recent_alerts": recent_alerts,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

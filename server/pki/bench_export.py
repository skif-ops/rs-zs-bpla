"""Export only bench station metadata to the isolated monitoring server.

The live PKI registry contains pilot pairing and engineer secrets. Never mount or
copy that database into bench-data. This export includes only public certificate
metadata for bench stations, and can be refreshed before restarting bench_server.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from .registry import Registry


COLUMNS = ("serial", "station_id", "lot", "tenant", "status", "cert_serial_number",
           "cert_fingerprint_sha256", "cert_not_after", "created_at", "provisioned_at",
           "commissioned_at", "revoked_at", "revoke_reason", "note")


def export(source: Path, target: Path) -> int:
    source, target = source.resolve(), target.resolve()
    if source == target or source.parent == target.parent:
        raise ValueError("bench registry must have a separate directory")
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".new")
    if temporary.exists():
        raise FileExistsError(temporary)
    try:
        Registry(temporary)
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as live, sqlite3.connect(temporary) as bench:
            rows = live.execute("SELECT " + ",".join(COLUMNS) + " FROM stations WHERE tenant='bench'").fetchall()
            bench.executemany("INSERT INTO stations (" + ",".join(COLUMNS) + ") VALUES (" +
                              ",".join("?" for _ in COLUMNS) + ")", rows)
        os.replace(temporary, target)
        return len(rows)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(f"Exported {export(args.source, args.out)} bench stations to {args.out}")


if __name__ == "__main__":
    main()

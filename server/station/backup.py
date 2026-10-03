"""Consistent backup of the server data (docs/SERVER_RETENTION_2026-10-03.md).

``python -m station.backup --out /app/output/backups/backup_<stamp>.tar.gz`` (deploy/scripts/backup_*.sh|ps1 run it
inside the server container) archives ``data`` and ``output`` of the server directory the way a restore wants them:
every SQLite database is copied with the SQLite backup API first, so the archive holds a transactionally consistent
snapshot even while the server and the bridges write; the live files and their ``-wal``/``-shm`` companions are left
out.  Everything else (the audio files, operators.json, the PKI material under data/pki) is archived as it is.
A ``.zip`` destination gives a zip archive, anything else a gzip-compressed tar.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

ARCHIVED = ("data", "output")
DATABASE_SUFFIXES = (".sqlite3", ".sqlite3-wal", ".sqlite3-shm")


def snapshot_databases(data: Path, out: Path) -> list[Path]:
    """Copies every ``*.sqlite3`` under ``data`` (any depth) into ``out`` at the same relative path with the SQLite
    online backup API; returns the relative paths copied."""
    copied = []
    for src in sorted(p for p in data.rglob("*.sqlite3") if p.is_file()):
        rel = src.relative_to(data)
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()
        source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
        target = sqlite3.connect(dst)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        copied.append(rel)
    return copied


def members(server_dir: Path, snapshot: Path) -> list[tuple[Path, str]]:
    """(file on disk, name in the archive): data and output without the live databases, the snapshot copies in
    their place."""
    out = []
    for top in ARCHIVED:
        root = server_dir / top
        if not root.is_dir():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if path.name.endswith(DATABASE_SUFFIXES):
                continue
            out.append((path, path.relative_to(server_dir).as_posix()))
    for path in sorted(p for p in snapshot.rglob("*.sqlite3") if p.is_file()):
        out.append((path, (Path("data") / path.relative_to(snapshot)).as_posix()))
    return out


def write_archive(server_dir: Path, archive: Path) -> list[str]:
    """Writes the archive and returns the names it holds."""
    server_dir = Path(server_dir)
    archive = Path(archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="muhoed-backup-") as tmp:
        snapshot = Path(tmp)
        if (server_dir / "data").is_dir():
            snapshot_databases(server_dir / "data", snapshot)
        listed = members(server_dir, snapshot)
        partial = archive.with_name(archive.name + ".part")
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for path, name in listed:
                    z.write(path, name)
        else:
            with tarfile.open(partial, "w:gz") as t:
                for path, name in listed:
                    t.add(path, arcname=name, recursive=False)
        os.replace(partial, archive)
    return [name for _, name in listed]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m station.backup", description="consistent backup of the server data and output")
    parser.add_argument("--server-dir", default=str(Path(__file__).resolve().parents[1]), help="directory with data/ and output/ (default: the server)")
    parser.add_argument("--out", help="archive to write (.zip or .tar.gz); default output/backups/backup_<UTC stamp>.tar.gz")
    args = parser.parse_args(argv)
    server_dir = Path(args.server_dir)
    archive = Path(args.out) if args.out else server_dir / "output" / "backups" / f"backup_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.tar.gz"
    names = write_archive(server_dir, archive)
    databases = [n for n in names if n.endswith(".sqlite3")]
    print(f"backup saved: {archive} ({len(names)} files, {archive.stat().st_size / 1e6:.1f} MB; databases: {', '.join(databases) or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

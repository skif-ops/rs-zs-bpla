"""Consistent backup of the server data (docs/SERVER_RETENTION_2026-10-03.md).

``python -m station.backup --out /app/output/backups/backup_<stamp>.tar.gz`` (deploy/scripts/backup_*.sh|ps1 run it
inside the server container) archives ``data`` and ``output`` of the server directory the way a restore wants them:
every SQLite database is copied with the SQLite backup API first, so the archive holds a transactionally consistent
snapshot even while the server and the bridges write; the live files and their ``-wal``/``-shm`` companions are left
out.  Everything else (the audio files, operators.json, the PKI material under data/pki) is archived as it is,
except earlier archives in ``output/backups`` (an archive of archives would grow with every run; that directory is
where the deployment scripts have the container write, as it is on the mounted volume; the web routes never serve
it).  Without ``--out`` the archive goes to ``backups/`` beside ``data`` and ``output``, outside both.
A ``.zip`` destination gives a zip archive, anything else a gzip-compressed tar.

``python -m station.backup --restore <archive>`` (deploy/scripts/restore_*.sh|ps1 stop the services and run it
inside the server image) puts such an archive back: it refuses while the server or a bridge holds the database open,
refuses an archive with a path outside data/ and output/, without the event database or with a database that fails
``PRAGMA integrity_check``, first archives what it replaces into ``output/backups/before_restore_<stamp>.tar.gz``,
then replaces the contents of ``data`` and ``output`` (``output/backups`` stays) and sets mode 0600 on the operator
account files.  The contents are replaced, not the directories: in the container they are mount points.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import stat
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

ARCHIVED = ("data", "output")
SKIPPED = (Path("output") / "backups",)                  # earlier archives (relative to the server directory)
DATABASE_SUFFIXES = (".sqlite3", ".sqlite3-wal", ".sqlite3-shm")
EVENT_DATABASE = "data/zs_bpla.sqlite3"                  # an archive without it is not a server backup
PRIVATE_FILES = ("operators.json", "operator_session.key", "operator_state.sqlite3")   # mode 0600 after a restore


def stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.gmtime())


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
    """(file on disk, name in the archive): data and output without the live databases (the snapshot copies in
    their place) and without earlier archives."""
    out = []
    skipped = tuple(server_dir / s for s in SKIPPED)
    for top in ARCHIVED:
        root = server_dir / top
        if not root.is_dir():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if path.name.endswith(DATABASE_SUFFIXES) or any(s == path or s in path.parents for s in skipped):
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


# ---- restore -----------------------------------------------------------------------------------------------------
class RestoreError(Exception):
    """The archive or the server state does not allow a restore; nothing was changed."""


def check_archive(archive: Path) -> list[str]:
    """The file names of a restorable archive: regular files under data/ or output/ only (no absolute paths, no
    ``..``, no links), the event database among them."""
    archive = Path(archive)
    if not archive.is_file():
        raise RestoreError(f"archive not found: {archive}")
    try:
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as z:
                entries = [(i.filename, False) for i in z.infolist() if not i.is_dir()]
        else:
            with tarfile.open(archive) as t:
                entries = [(m.name, not m.isfile()) for m in t.getmembers() if not m.isdir()]
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise RestoreError(f"not a readable archive: {archive} ({exc})") from exc
    names = []
    for name, special in entries:
        parts = name.split("/")
        inside = len(parts) >= 2 and parts[0] in ARCHIVED and all(p not in ("", ".", "..") for p in parts) and "\\" not in name
        if special or not inside:
            raise RestoreError(f"archive member outside data/ and output/ or not a regular file: {name}")
        names.append(name)
    if EVENT_DATABASE not in names:
        raise RestoreError(f"archive holds no {EVENT_DATABASE}: not a server backup")
    return names


def _extract(archive: Path, into: Path) -> None:
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if not info.is_dir():
                    z.extract(info, into)
    else:
        with tarfile.open(archive) as t:
            members = [m for m in t.getmembers() if m.isfile()]
            try:
                t.extractall(into, members=members, filter="data")
            except TypeError:                                   # Python before the filter argument
                t.extractall(into, members=members)


def check_databases(root: Path) -> list[str]:
    """``PRAGMA integrity_check`` of every database under ``root``; the event database must hold its tables."""
    checked = []
    for db in sorted(p for p in root.rglob("*.sqlite3") if p.is_file()):
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            result = c.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RestoreError(f"{db.relative_to(root).as_posix()} fails integrity_check: {result}")
            if db.relative_to(root).as_posix() == EVENT_DATABASE:
                tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                missing = {"stations", "detections", "system_events"} - tables
                if missing:
                    raise RestoreError(f"{EVENT_DATABASE} lacks the tables {sorted(missing)}")
        except sqlite3.DatabaseError as exc:
            raise RestoreError(f"{db.relative_to(root).as_posix()} is not a database: {exc}") from exc
        finally:
            c.close()
        checked.append(db.relative_to(root).as_posix())
    return checked


def assert_not_in_use(db: Path) -> None:
    """Refuses while another process holds the database open (the server, a bridge): an exclusive lock is tried."""
    if not db.exists():
        return
    try:
        c = sqlite3.connect(db, timeout=1)
        try:
            c.execute("PRAGMA locking_mode=EXCLUSIVE")
            c.execute("BEGIN EXCLUSIVE")
            c.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            c.execute("COMMIT")
        finally:
            c.close()
    except sqlite3.OperationalError as exc:
        raise RestoreError(f"{db} is in use ({exc}): stop the server and the bridges first") from exc


def _replace_contents(target: Path, source: Path, keep: tuple[str, ...] = ()) -> None:
    """Replaces what is inside ``target`` (a directory that may be a mount point) with what is inside ``source``."""
    target.mkdir(parents=True, exist_ok=True)
    for entry in list(target.iterdir()):
        if entry.name in keep:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    if source.is_dir():
        for entry in list(source.iterdir()):
            if entry.name in keep:
                continue
            shutil.move(str(entry), str(target / entry.name))


def restore(server_dir: Path, archive: Path, *, force: bool = False) -> dict:
    """Puts ``archive`` back into ``server_dir`` (see the module docstring); returns what was done."""
    server_dir = Path(server_dir)
    archive = Path(archive)
    names = check_archive(archive)
    if not force:
        for db in sorted(p for p in (server_dir / "data").rglob("*.sqlite3") if p.is_file()) if (server_dir / "data").is_dir() else []:
            assert_not_in_use(db)
    when = stamp()
    staging = server_dir / f".restore_{when}.part"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        _extract(archive, staging)
        databases = check_databases(staging)
        before = server_dir / "output" / "backups" / f"before_restore_{when}.tar.gz"
        kept = write_archive(server_dir, before) if (server_dir / "data").is_dir() or (server_dir / "output").is_dir() else []
        _replace_contents(server_dir / "data", staging / "data")
        _replace_contents(server_dir / "output", staging / "output", keep=("backups",))
        for name in PRIVATE_FILES:
            path = server_dir / "data" / name
            if path.exists():
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {"archive": str(archive), "files": len(names), "databases": databases, "before": str(before) if kept else None,
            "before_files": len(kept)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m station.backup", description="consistent backup of the server data and output, and its restore")
    parser.add_argument("--server-dir", default=str(Path(__file__).resolve().parents[1]), help="directory with data/ and output/ (default: the server)")
    parser.add_argument("--out", help="archive to write (.zip or .tar.gz); default backups/backup_<UTC stamp>.tar.gz beside data and output")
    parser.add_argument("--restore", metavar="ARCHIVE", help="put this archive back instead of writing one (the server and the bridges must be stopped)")
    parser.add_argument("--force", action="store_true", help="restore even when a database seems to be in use")
    args = parser.parse_args(argv)
    server_dir = Path(args.server_dir)
    if args.restore:
        try:
            done = restore(server_dir, Path(args.restore), force=args.force)
        except RestoreError as exc:
            print(f"restore refused: {exc}", file=sys.stderr)
            return 2
        line = f"restored {done['archive']} into {server_dir}: {done['files']} files, databases checked: {', '.join(done['databases'])}"
        if done["before"]:
            line += f"; the replaced state is in {done['before']} ({done['before_files']} files)"
        print(line)
        return 0
    archive = Path(args.out) if args.out else server_dir / "backups" / f"backup_{stamp()}.tar.gz"
    names = write_archive(server_dir, archive)
    databases = [n for n in names if n.endswith(".sqlite3")]
    print(f"backup saved: {archive} ({len(names)} files, {archive.stat().st_size / 1e6:.1f} MB; databases: {', '.join(databases) or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

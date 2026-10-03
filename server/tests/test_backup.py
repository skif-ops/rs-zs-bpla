"""station/backup.py: the archive holds consistent copies of the databases taken while they are written, the audio
and the other files as they are, and no live database files; tar.gz and zip; the command line."""
import gc
import sqlite3
import tarfile
import zipfile
from pathlib import Path

import pytest

from station import backup
from station.store import EventStore


def make_server(root: Path) -> EventStore:
    store = EventStore(root / "data" / "zs_bpla.sqlite3")
    with store._conn() as c:
        c.executemany("INSERT INTO alert_outbox(msg_id,tenant,type,created_us,message) VALUES(?,?,?,?,?)",
                      [(f"m{i}", "pilot1", "bearing", i, "{}") for i in range(50)])
    (root / "data" / "pki").mkdir()
    reg = sqlite3.connect(root / "data" / "pki" / "registry.sqlite3")
    reg.execute("CREATE TABLE stations(serial TEXT)"); reg.execute("INSERT INTO stations VALUES('DIO-EVT-001')"); reg.commit(); reg.close()
    (root / "data" / "audio" / "1" / "7").mkdir(parents=True)
    (root / "data" / "audio" / "1" / "7" / "pre.wav").write_bytes(b"RIFF" + bytes(100))
    (root / "data" / "operators.json").write_text("{}")
    (root / "output").mkdir()
    (root / "output" / "report.txt").write_text("x")
    return store


def test_tar_archive_holds_consistent_databases_and_no_live_files(tmp_path):
    store = make_server(tmp_path)
    writer = sqlite3.connect(store.path, timeout=5)                     # a bridge in the middle of a transaction
    writer.execute("BEGIN")
    writer.execute("INSERT INTO alert_outbox(msg_id,tenant,type,created_us,message) VALUES('uncommitted','p','bearing',99,'{}')")
    assert (store.path.with_name("zs_bpla.sqlite3-wal")).exists()       # WAL mode: the live copy is not the whole truth
    names = backup.write_archive(tmp_path, tmp_path / "b.tar.gz")
    writer.rollback(); writer.close()
    assert "data/zs_bpla.sqlite3" in names and "data/pki/registry.sqlite3" in names
    assert "data/audio/1/7/pre.wav" in names and "data/operators.json" in names and "output/report.txt" in names
    assert not any(n.endswith(("-wal", "-shm")) for n in names)
    with tarfile.open(tmp_path / "b.tar.gz") as t:
        t.extractall(tmp_path / "restore", filter="data")
    restored = sqlite3.connect(tmp_path / "restore" / "data" / "zs_bpla.sqlite3")
    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert restored.execute("SELECT COUNT(*) FROM alert_outbox").fetchone()[0] == 50     # committed rows, not the open transaction
    assert sqlite3.connect(tmp_path / "restore" / "data" / "pki" / "registry.sqlite3").execute("SELECT serial FROM stations").fetchone()[0] == "DIO-EVT-001"
    assert (tmp_path / "restore" / "data" / "audio" / "1" / "7" / "pre.wav").read_bytes() == b"RIFF" + bytes(100)
    assert not (tmp_path / "b.tar.gz.part").exists()


def test_zip_archive_and_command_line(tmp_path, capsys):
    make_server(tmp_path)
    assert backup.main(["--server-dir", str(tmp_path), "--out", str(tmp_path / "out" / "b.zip")]) == 0
    assert "databases: data/pki/registry.sqlite3, data/zs_bpla.sqlite3" in capsys.readouterr().out
    with zipfile.ZipFile(tmp_path / "out" / "b.zip") as z:
        names = z.namelist()
        assert "data/zs_bpla.sqlite3" in names and "output/report.txt" in names and not any(n.endswith("-wal") for n in names)
        z.extract("data/zs_bpla.sqlite3", tmp_path / "restore")
    assert sqlite3.connect(tmp_path / "restore" / "data" / "zs_bpla.sqlite3").execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # the default destination: backups/backup_<stamp>.tar.gz beside data and output, outside both
    assert backup.main(["--server-dir", str(tmp_path)]) == 0
    (default,) = list((tmp_path / "backups").glob("backup_*.tar.gz"))
    with tarfile.open(default) as t:
        assert "data/zs_bpla.sqlite3" in t.getnames()


def test_earlier_archives_in_output_backups_are_not_archived_again(tmp_path):
    make_server(tmp_path)
    inside = tmp_path / "output" / "backups" / "backup_20261003_110000.tar.gz"      # where the deployment scripts write
    assert backup.main(["--server-dir", str(tmp_path), "--out", str(inside)]) == 0
    names = backup.write_archive(tmp_path, tmp_path / "second.tar.gz")
    assert "output/report.txt" in names and not any(n.startswith("output/backups/") for n in names)


def rows(db: Path) -> int:
    c = sqlite3.connect(db)
    try:
        return c.execute("SELECT COUNT(*) FROM alert_outbox").fetchone()[0]
    finally:
        c.close()


def test_restore_puts_the_archive_back_and_keeps_what_it_replaced(tmp_path, capsys):
    store = make_server(tmp_path)
    archive = tmp_path / "keep" / "b.zip"                     # zip: the file modes are not in it
    assert backup.main(["--server-dir", str(tmp_path), "--out", str(archive)]) == 0
    with store._conn() as c:                                   # life goes on after the backup
        c.execute("INSERT INTO alert_outbox(msg_id,tenant,type,created_us,message) VALUES('later','p','bearing',99,'{}')")
    c.close()
    (tmp_path / "output" / "stray.txt").write_text("after the backup")
    (tmp_path / "output" / "backups").mkdir()
    (tmp_path / "output" / "backups" / "older.tar.gz").write_bytes(b"an earlier archive")
    (tmp_path / "data" / "operators.json").chmod(0o644)
    del store
    gc.collect()                                               # the store's connections: the server is "stopped"
    assert rows(tmp_path / "data" / "zs_bpla.sqlite3") == 51
    assert backup.main(["--server-dir", str(tmp_path), "--restore", str(archive)]) == 0
    out = capsys.readouterr().out
    assert "restored" in out and "data/zs_bpla.sqlite3" in out and "before_restore_" in out
    assert rows(tmp_path / "data" / "zs_bpla.sqlite3") == 50                       # the archived state
    assert not (tmp_path / "data" / "zs_bpla.sqlite3-wal").exists()
    assert (tmp_path / "data" / "audio" / "1" / "7" / "pre.wav").read_bytes() == b"RIFF" + bytes(100)
    assert (tmp_path / "output" / "report.txt").read_text() == "x" and not (tmp_path / "output" / "stray.txt").exists()
    assert (tmp_path / "output" / "backups" / "older.tar.gz").exists()           # output/backups is kept
    assert (tmp_path / "data" / "operators.json").stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".restore_*"))
    (before,) = list((tmp_path / "output" / "backups").glob("before_restore_*.tar.gz"))
    with tarfile.open(before) as t:                             # what was replaced is still there, consistent
        names = t.getnames()
        assert "output/stray.txt" in names and "data/zs_bpla.sqlite3" in names and not any("backups/" in n for n in names)
        t.extractall(tmp_path / "undo", filter="data")
    assert rows(tmp_path / "undo" / "data" / "zs_bpla.sqlite3") == 51


def test_restore_refuses_bad_archives_and_a_database_in_use(tmp_path, capsys):
    import zipfile as zf

    store = make_server(tmp_path)
    good = tmp_path / "good.tar.gz"
    backup.write_archive(tmp_path, good)
    gc.collect()                                               # the store's connections: the server is "stopped"
    mark = tmp_path / "data" / "marker"
    mark.write_text("untouched")

    escaping = tmp_path / "escape.zip"
    with zf.ZipFile(escaping, "w") as z:
        z.writestr("data/zs_bpla.sqlite3", b"x")
        z.writestr("../evil.txt", b"x")
    with pytest.raises(backup.RestoreError, match="outside data/ and output/"):
        backup.restore(tmp_path, escaping)

    no_db = tmp_path / "nodb.zip"
    with zf.ZipFile(no_db, "w") as z:
        z.writestr("output/report.txt", b"x")
    with pytest.raises(backup.RestoreError, match="not a server backup"):
        backup.restore(tmp_path, no_db)

    corrupt = tmp_path / "corrupt.zip"
    with zf.ZipFile(corrupt, "w") as z:
        z.writestr("data/zs_bpla.sqlite3", b"SQLite format 3\x00" + bytes(2000))
    with pytest.raises(backup.RestoreError, match="not a database|integrity"):
        backup.restore(tmp_path, corrupt)

    stripped = tmp_path / "stripped.zip"                        # a real database, but not the server's
    foreign = tmp_path / "foreign.sqlite3"
    other = sqlite3.connect(foreign)
    other.execute("CREATE TABLE t(x)")
    other.commit()
    other.close()
    with zf.ZipFile(stripped, "w") as z:
        z.write(foreign, "data/zs_bpla.sqlite3")
    with pytest.raises(backup.RestoreError, match="lacks the tables"):
        backup.restore(tmp_path, stripped)

    holder = sqlite3.connect(store.path)                        # the server still has the database open
    holder.execute("SELECT COUNT(*) FROM stations").fetchone()
    with pytest.raises(backup.RestoreError, match="in use"):
        backup.restore(tmp_path, good)
    assert backup.main(["--server-dir", str(tmp_path), "--restore", str(good)]) == 2
    assert "restore refused" in capsys.readouterr().err
    holder.close()
    assert mark.read_text() == "untouched" and not list((tmp_path / "output").glob("backups/*"))
    assert backup.restore(tmp_path, good)["databases"] == ["data/pki/registry.sqlite3", "data/zs_bpla.sqlite3"]
    assert not mark.exists()

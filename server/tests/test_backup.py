"""station/backup.py: the archive holds consistent copies of the databases taken while they are written, the audio
and the other files as they are, and no live database files; tar.gz and zip; the command line."""
import sqlite3
import tarfile
import zipfile
from pathlib import Path

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
    # the default destination: output/backups/backup_<stamp>.tar.gz under the server directory
    assert backup.main(["--server-dir", str(tmp_path)]) == 0
    (default,) = list((tmp_path / "output" / "backups").glob("backup_*.tar.gz"))
    with tarfile.open(default) as t:
        assert "data/zs_bpla.sqlite3" in t.getnames()

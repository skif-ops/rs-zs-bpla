"""Only virtual/bench metadata reaches the separate monitoring process."""
from pathlib import Path
import sqlite3

from pki.bench_export import export
from pki.registry import Registry


def test_export_does_not_copy_pilot_records_or_secrets(tmp_path: Path):
    source = tmp_path / "live" / "registry.sqlite3"
    target = tmp_path / "bench" / "registry.sqlite3"
    reg = Registry(source)
    reg.add("DIO-EVT-001")
    reg.add("DIO-EVT-B01")
    reg.add("DIO-TWIN-001")
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE stations SET pairing_secret='pilot-secret' WHERE serial='DIO-EVT-001'")
        connection.execute("UPDATE stations SET engineer_key='bench-secret' WHERE serial='DIO-TWIN-001'")
    assert export(source, target) == 2
    exported = Registry(target)
    assert [r.station_id for r in exported.list()] == [901, 9001]
    assert all(r.pairing_secret is None and r.engineer_key is None for r in exported.list())
    assert b"pilot-secret" not in target.read_bytes() and b"bench-secret" not in target.read_bytes()

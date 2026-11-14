from pathlib import Path

from pki.registry import Registry
from tools.prepare_bench_pki import prepare


def test_prepared_bench_has_only_isolated_twins(tmp_path: Path):
    out = tmp_path / "fresh"
    prepare(out)
    registry = Registry(out / "deploy/server/data/pki/registry.sqlite3")
    rows = registry.list()
    assert [row.station_id for row in rows] == list(range(9001, 9041))
    assert {row.tenant for row in rows} == {"bench"}
    assert {row.status for row in rows} == {"provisioned"}
    acl = (out / "deploy/config/station_acl.conf").read_text()
    assert "zs/v1/bench/9001/status" in acl
    assert "zs/v1/bench/9040/status" in acl
    assert "pilot1" not in acl and "pilot2" not in acl
    assert (out / "offline-root/root.key.pem").is_file()
    assert not (out / "deploy/offline-root").exists()

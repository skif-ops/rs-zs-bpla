"""The network sender can only use distinct bench identities."""
from pathlib import Path
import sys

import pytest

from pki import ca as pki

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import bench_mqtt_twins  # noqa: E402


def test_plan_requires_per_station_certificate_and_exact_cn(tmp_path: Path):
    issuing = pki.create_root(b"test-root-passphrase")
    # A certificate with any other CN must never be usable as a virtual station.
    station_dir = tmp_path / "DIO-TWIN-001"
    station_dir.mkdir()
    # The root is deliberately not used to sign: malformed certificate bytes fail closed.
    (station_dir / "DIO-TWIN-001.crt.pem").write_bytes(issuing.cert_pem)
    (station_dir / "DIO-TWIN-001.key.pem").write_bytes(b"key")
    with pytest.raises(ValueError, match="CN does not match"):
        bench_mqtt_twins.identities(3, tmp_path)
    with pytest.raises(ValueError, match="3, 20 or 40"):
        bench_mqtt_twins.identities(4, tmp_path)
